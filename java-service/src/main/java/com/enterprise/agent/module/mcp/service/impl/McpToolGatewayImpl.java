package com.enterprise.agent.module.mcp.service.impl;

import cn.hutool.core.util.StrUtil;
import cn.hutool.json.JSONObject;
import cn.hutool.json.JSONUtil;
import com.enterprise.agent.common.exception.BusinessException;
import com.enterprise.agent.common.response.ResultCode;
import com.enterprise.agent.config.EnterpriseProperties;
import com.enterprise.agent.module.mcp.dto.McpAnalysisRequest;
import com.enterprise.agent.module.mcp.dto.McpAnalysisResult;
import com.enterprise.agent.module.mcp.service.McpCircuitBreaker;
import com.enterprise.agent.module.mcp.service.McpToolGateway;
import io.modelcontextprotocol.client.McpSyncClient;
import io.modelcontextprotocol.spec.McpSchema;
import jakarta.annotation.PreDestroy;
import lombok.extern.slf4j.Slf4j;
import org.springframework.beans.factory.ObjectProvider;
import org.springframework.core.ParameterizedTypeReference;
import org.springframework.http.MediaType;
import org.springframework.http.codec.ServerSentEvent;
import org.springframework.stereotype.Service;
import org.springframework.web.reactive.function.BodyInserters;
import org.springframework.web.reactive.function.client.WebClient;
import reactor.core.publisher.Flux;
import reactor.core.publisher.Sinks;

import java.time.Duration;
import java.util.ArrayList;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;
import java.util.concurrent.ConcurrentHashMap;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.TimeUnit;
import java.util.concurrent.atomic.AtomicBoolean;

/**
 * MCP 工具调用网关实现（眼前一亮增强版）。
 * <p><b>双通道架构</b>：
 * <ol>
 *   <li><b>控制面（标准 MCP）</b>：{@link McpSyncClient} 调用 {@code enterprise_analysis} 同步工具 +
 *       listTools 工具发现。严格遵循 Spring AI 官方 MCP 协议，禁止用 HTTP 替代。</li>
 *   <li><b>数据面（HTTP SSE）</b>：Spring AI 1.0.0 GA McpSyncClient 未暴露流式工具订阅 API，
 *       因此"打字机 + 多阶段进度事件"流式走 Python 内部接口
 *       {@code POST /internal/analysis/stream}（X-Internal-Key 鉴权），
 *       返回标准 text/event-stream。</li>
 * </ol>
 *
 * @author enterprise-agent
 */
@Slf4j
@Service
public class McpToolGatewayImpl implements McpToolGateway {

    private final EnterpriseProperties properties;
    private final ObjectProvider<List<McpSyncClient>> mcpSyncClients;
    private final McpCircuitBreaker circuitBreaker;
    private final WebClient pythonWebClient;

    /** 流式调用累积的最终结果（key = userId|sessionId）。 */
    private final Map<String, McpAnalysisResult> streamResults = new ConcurrentHashMap<>();

    /** Java 17 兼容：平台线程池（不使用 Java 21 虚拟线程）。 */
    private final ExecutorService streamExecutor;

    public McpToolGatewayImpl(EnterpriseProperties properties,
                              ObjectProvider<List<McpSyncClient>> mcpSyncClients,
                              McpCircuitBreaker circuitBreaker,
                              WebClient.Builder webClientBuilder) {
        this.properties = properties;
        this.mcpSyncClients = mcpSyncClients;
        this.circuitBreaker = circuitBreaker;
        long timeout = properties.getInternal() == null ? 30000L
                : Math.max(5000L, properties.getInternal().getHttpTimeoutMs());
        String baseUrl = properties.getMcp().getPythonBaseUrl();
        this.pythonWebClient = webClientBuilder
                .clone()
                .baseUrl(baseUrl)
                .codecs(configurer -> configurer.defaultCodecs().maxInMemorySize(8 * 1024 * 1024))
                .build();
        // Java 17 友好：有界弹性线程池（IO 密集型）
        this.streamExecutor = Executors.newFixedThreadPool(
                Math.max(8, Runtime.getRuntime().availableProcessors() * 4),
                r -> {
                    Thread t = new Thread(r, "mcp-stream-worker");
                    t.setDaemon(true);
                    return t;
                }
        );
        // 初始化时只用于日志提示 baseUrl，避免未使用变量检查
        log.info("McpToolGateway 初始化：pythonBaseUrl={} httpTimeoutMs={}", baseUrl, timeout);
    }

    @PreDestroy
    void shutdown() {
        streamExecutor.shutdown();
        try {
            if (!streamExecutor.awaitTermination(3, TimeUnit.SECONDS)) {
                streamExecutor.shutdownNow();
            }
        } catch (InterruptedException e) {
            Thread.currentThread().interrupt();
            streamExecutor.shutdownNow();
        }
    }

    @Override
    public McpAnalysisResult analyze(McpAnalysisRequest request) {
        if (!circuitBreaker.allowRequest()) {
            log.error("MCP 熔断打开，直接降级 question={}", request.getQuestion());
            throw new BusinessException(ResultCode.MCP_UNAVAILABLE);
        }

        String toolName = properties.getMcp().getToolName();
        int maxRetry = properties.getMcp().getMaxRetry();
        long interval = properties.getMcp().getRetryIntervalMs();

        Map<String, Object> args = buildArgs(request);
        Exception lastEx = null;

        for (int attempt = 0; attempt <= maxRetry; attempt++) {
            long start = System.currentTimeMillis();
            try {
                McpSyncClient client = pickClient();
                log.info("MCP 调用开始 tool={} attempt={} question={}", toolName, attempt, request.getQuestion());

                McpSchema.CallToolResult toolResult = client.callTool(
                        new McpSchema.CallToolRequest(toolName, args));

                long cost = System.currentTimeMillis() - start;
                if (Boolean.TRUE.equals(toolResult.isError())) {
                    throw new BusinessException(ResultCode.MCP_CALL_FAILED,
                            "Python Agent 返回错误：" + extractText(toolResult));
                }
                McpAnalysisResult result = parseResult(toolResult);
                log.info("MCP 调用成功 tool={} cost={}ms confidence={} retry={}",
                        toolName, cost, result.getConfidenceScore(), result.getRetryCount());
                circuitBreaker.onSuccess();
                return result;
            } catch (Exception e) {
                lastEx = e;
                long cost = System.currentTimeMillis() - start;
                log.warn("MCP 调用失败 tool={} attempt={} cost={}ms err={}",
                        toolName, attempt, cost, e.getMessage());
                circuitBreaker.onFailure();
                if (attempt < maxRetry) {
                    sleep(interval);
                }
            }
        }

        if (lastEx instanceof BusinessException be) {
            throw be;
        }
        throw new BusinessException(ResultCode.MCP_CALL_FAILED,
                "MCP 调用重试耗尽：" + (lastEx == null ? "unknown" : lastEx.getMessage()));
    }

    @Override
    public Flux<String> analyzeStream(McpAnalysisRequest request) {
        if (!circuitBreaker.allowRequest()) {
            return Flux.just("event: error\ndata: MCP_UNAVAILABLE\n\n");
        }
        String key = requestKey(request);
        String internalKey = properties.getInternal() == null ? "internal-secret-key-2026"
                : properties.getInternal().getApiKey();
        long timeoutMs = properties.getInternal() == null ? 120_000L
                : Math.max(30_000L, properties.getInternal().getHttpTimeoutMs() * 4L);
        Sinks.Many<String> sink = Sinks.many().unicast().onBackpressureBuffer();
        AtomicBoolean finished = new AtomicBoolean(false);

        StringBuilder reportAccumulator = new StringBuilder();
        java.util.concurrent.atomic.AtomicReference<String> finalJson = new java.util.concurrent.atomic.AtomicReference<>();

        // 组装请求体：与 /internal/analysis/stream 字段（camelCase）一致
        Map<String, Object> body = new LinkedHashMap<>();
        body.put("question", request.getQuestion());
        body.put("userId", request.getUserId());
        body.put("deptId", request.getDeptId());
        body.put("deptIds", request.getDeptIds());
        body.put("sessionId", request.getSessionId());
        body.put("callbackBaseUrl", request.getCallbackBaseUrl());
        body.put("internalApiKey", request.getInternalApiKey());
        body.put("maxRetry", properties.getMcp().getMaxRetry());

        pythonWebClient.post()
                .uri("/internal/analysis/stream")
                .header("X-Internal-Key", internalKey)
                .contentType(MediaType.APPLICATION_JSON)
                .accept(MediaType.TEXT_EVENT_STREAM)
                .body(BodyInserters.fromValue(body))
                .retrieve()
                // 响应 Content-Type=text/event-stream，Spring 自动启用 SSE reader，
                // 直接取解析好的 ServerSentEvent.event()/data()，重组原始帧格式
                // （若用 bodyToFlux(String.class)，SSE reader 会剥离 event:/data: 前缀，
                //  导致 SseAccumulator 收不到 "event:"/"data:" 标识，hasFrame 永远 false → 120s 超时）
                .bodyToFlux(new ParameterizedTypeReference<ServerSentEvent<String>>() {})
                .map(sse -> {
                    String ev = (sse.event() == null || sse.event().isBlank()) ? "report" : sse.event();
                    String data = sse.data() == null ? "" : sse.data();
                    return "event: " + ev + "\ndata: " + data + "\n\n";
                })
                .timeout(Duration.ofMillis(timeoutMs))
                .doOnNext(frame -> {
                    sink.tryEmitNext(frame);
                    String extracted = extractLastReport(frame);
                    if (extracted != null) {
                        reportAccumulator.append(extracted);
                    }
                    if (frame.startsWith("event: done")) {
                        String fjson = extractFinalJson(frame);
                        if (StrUtil.isNotBlank(fjson)) {
                            finalJson.set(fjson);
                        }
                    }
                })
                .doOnError(err -> {
                    if (finished.compareAndSet(false, true)) {
                        log.warn("流式 MCP(SSE) 异常: {}", err.getMessage());
                        sink.tryEmitNext("event: error\ndata: " + err.getMessage() + "\n\n");
                        sink.tryEmitComplete();
                    }
                })
                .doOnComplete(() -> {
                    if (finished.compareAndSet(false, true)) {
                        McpAnalysisResult result = buildFinalResult(finalJson.get(), reportAccumulator);
                        streamResults.put(key, result);
                        sink.tryEmitComplete();
                    }
                })
                // 订阅在专用线程池上，避免阻塞 Netty 线程
                .subscribeOn(reactor.core.scheduler.Schedulers.fromExecutorService(streamExecutor))
                .subscribe();

        return sink.asFlux();
    }

    @Override
    public McpAnalysisResult lastStreamResult(McpAnalysisRequest request) {
        McpAnalysisResult r = streamResults.remove(requestKey(request));
        return r == null ? emptyResult() : r;
    }

    @Override
    public List<String> discoveredTools() {
        List<String> names = new ArrayList<>();
        List<McpSyncClient> clients = mcpSyncClients.getIfAvailable();
        if (clients == null) {
            return names;
        }
        for (McpSyncClient client : clients) {
            McpSchema.ListToolsResult tools = client.listTools();
            tools.tools().forEach(t -> names.add(t.name()));
        }
        return names;
    }

    // ================= 私有辅助 =================

    private Map<String, Object> buildArgs(McpAnalysisRequest request) {
        Map<String, Object> args = new LinkedHashMap<>();
        args.put("question", request.getQuestion());
        args.put("user_id", request.getUserId());
        args.put("dept_id", request.getDeptId());
        args.put("dept_ids", request.getDeptIds());
        args.put("session_id", request.getSessionId());
        args.put("callback_base_url", request.getCallbackBaseUrl());
        args.put("internal_api_key", request.getInternalApiKey());
        return args;
    }

    private McpSyncClient pickClient() {
        List<McpSyncClient> clients = mcpSyncClients.getIfAvailable();
        if (clients == null || clients.isEmpty()) {
            throw new BusinessException(ResultCode.MCP_UNAVAILABLE, "未发现可用的 MCP 客户端连接");
        }
        return clients.get(0);
    }

    private String extractText(McpSchema.CallToolResult toolResult) {
        if (toolResult.content() == null || toolResult.content().isEmpty()) {
            return "";
        }
        StringBuilder sb = new StringBuilder();
        for (McpSchema.Content content : toolResult.content()) {
            if (content instanceof McpSchema.TextContent textContent) {
                sb.append(textContent.text());
            }
        }
        return sb.toString();
    }

    private McpAnalysisResult parseResult(McpSchema.CallToolResult toolResult) {
        String text = extractText(toolResult);
        if (text.isBlank()) {
            throw new BusinessException(ResultCode.MCP_CALL_FAILED, "MCP 返回内容为空");
        }
        try {
            JSONObject json = JSONUtil.parseObj(text);
            return JSONUtil.toBean(json, McpAnalysisResult.class);
        } catch (Exception e) {
            log.error("解析 MCP 返回失败 raw={}", text, e);
            throw new BusinessException(ResultCode.MCP_CALL_FAILED, "MCP 返回格式非法");
        }
    }

    private McpAnalysisResult buildFinalResult(String finalJsonStr, StringBuilder reportBuf) {
        try {
            if (StrUtil.isNotBlank(finalJsonStr)) {
                return JSONUtil.toBean(JSONUtil.parseObj(finalJsonStr), McpAnalysisResult.class);
            }
        } catch (Exception e) {
            log.warn("解析流式 finalJson 失败，降级空结果: {}", e.getMessage());
        }
        McpAnalysisResult result = new McpAnalysisResult();
        result.setSuccess(true);
        result.setReport(reportBuf == null ? "" : reportBuf.toString());
        result.setConfidenceScore(60);
        result.setDataSources(new ArrayList<>());
        result.setRiskTags(new ArrayList<>());
        return result;
    }

    private static String extractLastReport(String frame) {
        if (!frame.startsWith("event: report")) {
            return null;
        }
        int idx = frame.indexOf("\ndata: ");
        if (idx == -1) return null;
        int end = frame.indexOf("\n\n", idx);
        if (end == -1) end = frame.length();
        String seg = frame.substring(idx + 7, end).trim();
        if (seg.isEmpty()) return null;
        try {
            // server.py 对 report 事件做了 JSON.stringify 包裹，尝试去掉外层引号
            if (seg.startsWith("\"") && seg.endsWith("\"")) {
                return JSONUtil.toBean(seg, String.class);
            }
        } catch (Exception ignore) {
            // 原样返回
        }
        return seg;
    }

    private static String extractFinalJson(String frame) {
        int idx = frame.indexOf("\ndata: ");
        if (idx == -1) return null;
        int end = frame.indexOf("\n\n", idx);
        if (end == -1) end = frame.length();
        String seg = frame.substring(idx + 7, end).trim();
        if (seg.isEmpty()) return null;
        try {
            JSONObject obj = JSONUtil.parseObj(seg);
            Object fj = obj.get("finalJson");
            if (fj == null) return null;
            if (fj instanceof String s) return s;
            return JSONUtil.toJsonStr(fj);
        } catch (Exception e) {
            log.debug("解析 done 的 finalJson 失败 seg={}", seg);
            return null;
        }
    }

    private static McpAnalysisResult emptyResult() {
        McpAnalysisResult r = new McpAnalysisResult();
        r.setSuccess(false);
        r.setErrorCode("NO_STREAM_RESULT");
        r.setErrorMessage("流式未返回聚合结果");
        r.setReport("");
        r.setConfidenceScore(0);
        r.setRiskTags(new ArrayList<>());
        r.setDataSources(new ArrayList<>());
        r.setRetryCount(0);
        r.setTokenCost(0);
        r.setCacheHit(false);
        return r;
    }

    private static String requestKey(McpAnalysisRequest req) {
        return (req.getUserId() == null ? "0" : req.getUserId()) + "|"
                + StrUtil.blankToDefault(req.getSessionId(), "sess");
    }

    private void sleep(long ms) {
        try {
            Thread.sleep(ms);
        } catch (InterruptedException e) {
            Thread.currentThread().interrupt();
        }
    }

    /**
     * SSE 帧累加器：WebClient bodyToFlux(String) 会按缓冲区拆行，
     * 这里把相邻 "event:x / data:y / (空行)" 拼回一完整帧再向下游发。
     */
    private static final class SseAccumulator {
        private final StringBuilder buf = new StringBuilder();
        private String readyFrame = null;

        SseAccumulator accept(String chunk) {
            if (chunk == null) return this;
            buf.append(chunk);
            int sep;
            // 连续抽取所有已完成帧（最后一次作为 readyFrame 发出）
            while ((sep = buf.indexOf("\n\n")) != -1) {
                String frame = buf.substring(0, sep + 2);
                buf.delete(0, sep + 2);
                // 保证一定是一个可推送的 SSE 格式（包含 event/data）
                if (frame.contains("event:") || frame.contains("data:")) {
                    // 归一：缺失 "event:" 前缀时补默认 report 事件
                    if (!frame.startsWith("event:")) {
                        int di = frame.indexOf("data:");
                        if (di == 0) {
                            frame = "event: report\n" + frame;
                        }
                    }
                    readyFrame = frame;
                }
            }
            return this;
        }

        boolean hasFrame() {
            return readyFrame != null;
        }

        String drainFrame() {
            String f = readyFrame;
            readyFrame = null;
            return f;
        }
    }
}
