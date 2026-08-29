package com.enterprise.agent.module.analysis.service.impl;

import cn.hutool.core.util.IdUtil;
import cn.hutool.core.util.StrUtil;
import cn.hutool.json.JSONUtil;
import com.baomidou.mybatisplus.core.conditions.query.LambdaQueryWrapper;
import com.baomidou.mybatisplus.extension.plugins.pagination.Page;
import com.enterprise.agent.common.exception.BusinessException;
import com.enterprise.agent.common.response.ResultCode;
import com.enterprise.agent.config.EnterpriseProperties;
import com.enterprise.agent.entity.BizQaHistory;
import com.enterprise.agent.mapper.BizQaHistoryMapper;
import com.enterprise.agent.module.analysis.dto.AnalysisAskRequest;
import com.enterprise.agent.module.analysis.dto.AnalysisResponse;
import com.enterprise.agent.module.analysis.service.AnalysisService;
import com.enterprise.agent.module.mcp.dto.McpAnalysisRequest;
import com.enterprise.agent.module.mcp.dto.McpAnalysisResult;
import com.enterprise.agent.module.mcp.service.McpToolGateway;
import com.enterprise.agent.module.memory.MemoryManager;
import com.enterprise.agent.module.memory.SemanticMemoryClient;
import com.enterprise.agent.security.LoginUser;
import com.enterprise.agent.security.SecurityUtil;
import jakarta.annotation.PreDestroy;
import lombok.RequiredArgsConstructor;
import lombok.extern.slf4j.Slf4j;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.stereotype.Service;
import reactor.core.publisher.Flux;
import reactor.core.publisher.Sinks;

import java.util.ArrayList;
import java.util.Collections;
import java.util.List;
import java.util.Map;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.TimeUnit;
import java.util.stream.Collectors;

/**
 * 业务分析服务实现，编排完整业务链路：
 * <ol>
 *   <li>先查「语义记忆」向量库命中（P2 增强：近似语义复用）</li>
 *   <li>语义未命中再查 MD5 指纹精确长期记忆缓存</li>
 *   <li>未命中 → 封装参数经 MCP 网关调用 Python Agent 集群</li>
 *   <li>置信度校验（低于阈值提示）</li>
 *   <li>问答记录入库 + 写入「指纹 + 语义双通道」长期记忆 + 会话历史追加</li>
 *   <li>组装标准化响应返回前端</li>
 * </ol>
 *
 * @author enterprise-agent
 */
@Slf4j
@Service
@RequiredArgsConstructor
public class AnalysisServiceImpl implements AnalysisService {

    private final McpToolGateway mcpToolGateway;
    private final MemoryManager memoryManager;
    private final SemanticMemoryClient semanticMemoryClient;
    private final BizQaHistoryMapper qaHistoryMapper;
    private final EnterpriseProperties properties;

    /** 置信度合格阈值。 */
    private static final int CONFIDENCE_THRESHOLD = 60;

    /** Java 17 兼容：平台线程池（替代 Java 21 虚拟线程 API）。 */
    private final ExecutorService streamWorker = Executors.newFixedThreadPool(
            Math.max(8, Runtime.getRuntime().availableProcessors() * 2),
            r -> {
                Thread t = new Thread(r, "analysis-stream-worker");
                t.setDaemon(true);
                return t;
            }
    );

    @Value("${enterprise.internal.api-key:internal-secret-key-2026}")
    private String internalApiKey;

    /** Java 内部回调基础地址，供 Python 子 Agent 反向拉取文档/数据。 */
    @Value("${enterprise.internal.callback-base-url:http://localhost:8080}")
    private String callbackBaseUrl;

    @Override
    public AnalysisResponse ask(AnalysisAskRequest request) {
        long start = System.currentTimeMillis();
        LoginUser user = SecurityUtil.currentUser();
        String sessionId = StrUtil.blankToDefault(request.getSessionId(), IdUtil.fastSimpleUUID());

        // 1. 语义记忆命中（P2 新增：向量近似复用，提升命中率）
        Map<String, Object> semanticHit = semanticMemoryClient.hitSemantic(user.getUserId(), request.getQuestion());
        if (semanticHit != null) {
            log.info("分析命中语义记忆缓存 userId={} question={}", user.getUserId(), request.getQuestion());
            McpAnalysisResult cachedResult = JSONUtil.toBean(JSONUtil.toJsonStr(semanticHit), McpAnalysisResult.class);
            AnalysisResponse resp = buildResponse(cachedResult, request.getQuestion(), sessionId, true);
            long cost = System.currentTimeMillis() - start;
            resp.setCostMs(cost);
            resp.setQaId(persist(user, sessionId, request.getQuestion(), cachedResult, cost, true));
            return resp;
        }

        // 2. 命中 MD5 精确长期记忆缓存则直接复用
        Object cached = memoryManager.hitLongTermCache(user.getUserId(), request.getQuestion());
        if (cached != null) {
            log.info("分析命中精确长期记忆缓存 userId={} question={}", user.getUserId(), request.getQuestion());
            McpAnalysisResult cachedResult = JSONUtil.toBean(JSONUtil.toJsonStr(cached), McpAnalysisResult.class);
            AnalysisResponse resp = buildResponse(cachedResult, request.getQuestion(), sessionId, true);
            long cost = System.currentTimeMillis() - start;
            resp.setCostMs(cost);
            resp.setQaId(persist(user, sessionId, request.getQuestion(), cachedResult, cost, true));
            return resp;
        }

        // 3. 封装 MCP 请求参数
        McpAnalysisRequest mcpRequest = buildMcpRequest(request, user, sessionId);

        // 4. 调用 Python Agent 集群
        McpAnalysisResult result = mcpToolGateway.analyze(mcpRequest);
        if (!result.isSuccess()) {
            throw new BusinessException(ResultCode.MCP_CALL_FAILED,
                    StrUtil.blankToDefault(result.getErrorMessage(), "AI 分析失败"));
        }

        long cost = System.currentTimeMillis() - start;

        // 5. 持久化 + 记忆写入（双通道）
        Long qaId = persist(user, sessionId, request.getQuestion(), result, cost, false);

        // 置信度达标才写入长期记忆缓存（避免缓存低质量结果）
        if (result.getConfidenceScore() != null && result.getConfidenceScore() >= CONFIDENCE_THRESHOLD) {
            memoryManager.saveLongTermQa(user.getUserId(), request.getQuestion(), result);
            // P2 增强：同时异步写入 Chroma 语义向量库，供后续"语义近似"复用
            semanticMemoryClient.indexSemantic(user.getUserId(), request.getQuestion(), result,
                    result.getConfidenceScore());
        } else {
            log.warn("分析置信度不足未写入缓存 score={} threshold={}",
                    result.getConfidenceScore(), CONFIDENCE_THRESHOLD);
        }
        // 会话历史追加，支撑多轮连续提问复用
        memoryManager.appendSessionHistory(user.getUserId(), sessionId,
                StrUtil.format("Q:{} | score:{}", request.getQuestion(), result.getConfidenceScore()));

        AnalysisResponse resp = buildResponse(result, request.getQuestion(), sessionId, false);
        resp.setQaId(qaId);
        resp.setCostMs(cost);
        return resp;
    }

    @Override
    public Flux<String> askStream(AnalysisAskRequest request) {
        LoginUser user = SecurityUtil.currentUser();
        String sessionId = StrUtil.blankToDefault(request.getSessionId(), IdUtil.fastSimpleUUID());

        // 1) 优先语义/精确命中，直接发送两个事件秒级返回
        Map<String, Object> semanticHit = semanticMemoryClient.hitSemantic(user.getUserId(), request.getQuestion());
        Object exactHit = semanticHit == null
                ? memoryManager.hitLongTermCache(user.getUserId(), request.getQuestion())
                : null;
        if (semanticHit != null || exactHit != null) {
            Map<String, Object> raw = semanticHit != null ? semanticHit
                    : JSONUtil.parseObj(JSONUtil.toJsonStr(exactHit));
            McpAnalysisResult cachedResult = JSONUtil.toBean(JSONUtil.toJsonStr(raw), McpAnalysisResult.class);
            AnalysisResponse resp = buildResponse(cachedResult, request.getQuestion(), sessionId, true);
            long qaId = persist(user, sessionId, request.getQuestion(), cachedResult, 0, true);
            resp.setQaId(qaId);
            String cacheEvent = "event: cacheHit\ndata: " + JSONUtil.toJsonStr(resp) + "\n\n";
            String doneEvent = "event: done\ndata: CACHE_HIT\n\n";
            return Flux.just(cacheEvent, doneEvent);
        }

        // 2) 真实分析：异步调用 McpToolGateway.stream() 推 SSE 事件
        Sinks.Many<String> sink = Sinks.many().multicast().onBackpressureBuffer(512);
        McpAnalysisRequest mcpRequest = buildMcpRequest(request, user, sessionId);
        streamWorker.submit(() -> {
            long start = System.currentTimeMillis();
            try {
                sink.tryEmitNext("event: planning\ndata: 正在分析需求并拆解子任务\n\n");
                Flux<String> inner = mcpToolGateway.analyzeStream(mcpRequest);
                inner.doOnNext(sink::tryEmitNext)
                        .doOnComplete(() -> {
                            // 流式结束后需要补一次 MCP 全量结果用于落库（stream 结束时 gateway 会累积最终 JSON）
                            McpAnalysisResult result = mcpToolGateway.lastStreamResult(mcpRequest);
                            long cost = System.currentTimeMillis() - start;
                            Long qaId = persist(user, sessionId, request.getQuestion(), result, cost, false);
                            if (result.getConfidenceScore() != null
                                    && result.getConfidenceScore() >= CONFIDENCE_THRESHOLD) {
                                memoryManager.saveLongTermQa(user.getUserId(), request.getQuestion(), result);
                                semanticMemoryClient.indexSemantic(user.getUserId(), request.getQuestion(), result,
                                        result.getConfidenceScore());
                            }
                            sink.tryEmitNext("event: done\ndata: {\"qaId\":" + qaId + ",\"costMs\":" + cost + "}\n\n");
                            sink.tryEmitComplete();
                        })
                        .doOnError(e -> {
                            sink.tryEmitNext("event: error\ndata: " + e.getMessage() + "\n\n");
                            sink.tryEmitComplete();
                        })
                        .subscribe();
            } catch (Exception e) {
                sink.tryEmitNext("event: error\ndata: " + e.getMessage() + "\n\n");
                sink.tryEmitComplete();
            }
        });
        return sink.asFlux();
    }

    @PreDestroy
    void shutdown() {
        streamWorker.shutdown();
        try {
            if (!streamWorker.awaitTermination(3, TimeUnit.SECONDS)) {
                streamWorker.shutdownNow();
            }
        } catch (InterruptedException e) {
            Thread.currentThread().interrupt();
            streamWorker.shutdownNow();
        }
    }

    @Override
    public Page<BizQaHistory> history(long pageNo, long pageSize) {
        LoginUser user = SecurityUtil.currentUser();
        LambdaQueryWrapper<BizQaHistory> wrapper = new LambdaQueryWrapper<BizQaHistory>()
                .eq(BizQaHistory::getUserId, user.getUserId())
                .orderByDesc(BizQaHistory::getCreateTime);
        return qaHistoryMapper.selectPage(new Page<>(pageNo, pageSize), wrapper);
    }

    @Override
    public List<BizQaHistory> listForExport(List<Long> qaIds) {
        LoginUser user = SecurityUtil.currentUser();
        LambdaQueryWrapper<BizQaHistory> wrapper = new LambdaQueryWrapper<BizQaHistory>()
                .eq(BizQaHistory::getUserId, user.getUserId());
        if (qaIds != null && !qaIds.isEmpty()) {
            wrapper.in(BizQaHistory::getId, qaIds);
        }
        wrapper.orderByDesc(BizQaHistory::getCreateTime);
        return qaHistoryMapper.selectList(wrapper);
    }

    // ================= 私有辅助 =================

    private McpAnalysisRequest buildMcpRequest(AnalysisAskRequest request, LoginUser user, String sessionId) {
        McpAnalysisRequest mcpRequest = new McpAnalysisRequest();
        mcpRequest.setQuestion(request.getQuestion());
        mcpRequest.setUserId(user.getUserId());
        mcpRequest.setDeptId(user.getDeptId());
        mcpRequest.setDeptIds(SecurityUtil.dataScopeDeptIds());
        mcpRequest.setSessionId(sessionId);
        mcpRequest.setCallbackBaseUrl(callbackBaseUrl);
        mcpRequest.setInternalApiKey(internalApiKey);
        return mcpRequest;
    }

    /** 持久化问答记录，返回记录ID。 */
    private Long persist(LoginUser user, String sessionId, String question,
                         McpAnalysisResult result, long cost, boolean cacheHit) {
        BizQaHistory record = new BizQaHistory();
        record.setUserId(user.getUserId());
        record.setDeptId(user.getDeptId());
        record.setSessionId(sessionId);
        record.setQuestion(question);
        record.setAnswerReport(result.getReport());
        record.setConfidenceScore(result.getConfidenceScore() == null ? 0 : result.getConfidenceScore());
        record.setDataSource(result.getDataSources() == null ? null : JSONUtil.toJsonStr(result.getDataSources()));
        record.setRiskTags(result.getRiskTags() == null ? null : String.join(",", result.getRiskTags()));
        record.setRetryCount(result.getRetryCount() == null ? 0 : result.getRetryCount());
        record.setTokenCost(result.getTokenCost() == null ? 0 : result.getTokenCost());
        record.setCacheHit(cacheHit ? 1 : 0);
        record.setCostMs(cost);
        record.setStatus("SUCCESS");
        qaHistoryMapper.insert(record);
        return record.getId();
    }

    /** 组装标准化响应。 */
    private AnalysisResponse buildResponse(McpAnalysisResult result, String question,
                                           String sessionId, boolean cacheHit) {
        AnalysisResponse resp = new AnalysisResponse();
        resp.setSessionId(sessionId);
        resp.setQuestion(question);
        resp.setReport(result.getReport());
        resp.setConfidenceScore(result.getConfidenceScore());
        resp.setRiskTags(result.getRiskTags() == null ? Collections.emptyList() : result.getRiskTags());
        resp.setCacheHit(cacheHit);
        resp.setRetryCount(result.getRetryCount());
        resp.setTokenCost(result.getTokenCost());

        List<AnalysisResponse.SourceItem> sources = new ArrayList<>();
        if (result.getDataSources() != null) {
            sources = result.getDataSources().stream().map(ds -> {
                AnalysisResponse.SourceItem item = new AnalysisResponse.SourceItem();
                item.setType(ds.getType());
                item.setReference(ds.getReference());
                item.setEvidence(ds.getEvidence());
                return item;
            }).collect(Collectors.toList());
        }
        resp.setDataSources(sources);
        return resp;
    }
}
