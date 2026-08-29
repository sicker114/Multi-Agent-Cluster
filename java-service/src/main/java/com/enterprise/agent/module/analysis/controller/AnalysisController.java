package com.enterprise.agent.module.analysis.controller;

import cn.hutool.core.util.StrUtil;
import com.baomidou.mybatisplus.extension.plugins.pagination.Page;
import com.enterprise.agent.common.annotation.RateLimit;
import com.enterprise.agent.common.response.R;
import com.enterprise.agent.common.utils.ExcelExportUtil;
import com.enterprise.agent.entity.BizQaHistory;
import com.enterprise.agent.module.analysis.dto.AnalysisAskRequest;
import com.enterprise.agent.module.analysis.dto.AnalysisResponse;
import com.enterprise.agent.module.analysis.service.AnalysisService;
import com.enterprise.agent.module.mcp.service.McpToolGateway;
import io.swagger.v3.oas.annotations.Operation;
import io.swagger.v3.oas.annotations.tags.Tag;
import jakarta.servlet.http.HttpServletResponse;
import jakarta.validation.Valid;
import lombok.RequiredArgsConstructor;
import lombok.extern.slf4j.Slf4j;
import org.springframework.http.MediaType;
import org.springframework.http.codec.ServerSentEvent;
import org.springframework.security.access.prepost.PreAuthorize;
import org.springframework.web.bind.annotation.*;
import reactor.core.publisher.Flux;

import java.io.IOException;
import java.net.URLEncoder;
import java.nio.charset.StandardCharsets;
import java.time.Duration;
import java.util.List;

/**
 * 业务分析控制器：提问、流式问答、历史查询、Excel 导出、MCP 健康检查。
 *
 * @author enterprise-agent
 */
@Slf4j
@Tag(name = "业务分析", description = "自然语言业务分析、问答历史与报表导出")
@RestController
@RequestMapping("/api/analysis")
@RequiredArgsConstructor
public class AnalysisController {

    private final AnalysisService analysisService;
    private final McpToolGateway mcpToolGateway;

    @Operation(summary = "发起业务分析提问",
            description = "鉴权+权限校验后，经标准 MCP 调用 Python 多智能体集群，返回可信分析报告")
    @PreAuthorize("hasAuthority('analysis:ask')")
    @RateLimit
    @PostMapping("/ask")
    public R<AnalysisResponse> ask(@Valid @RequestBody AnalysisAskRequest request) {
        return R.success("分析完成", analysisService.ask(request));
    }

    @Operation(summary = "流式业务分析（SSE）",
            description = "以 text/event-stream 实时推送分析事件：planning/retrieving/computing/judging/report/done。"
                    + "支持命中缓存时秒级返回 cacheHit 事件，支持流式打字机效果的 report 文本增量。")
    @PreAuthorize("hasAuthority('analysis:ask')")
    @RateLimit
    @PostMapping(value = "/stream", produces = MediaType.TEXT_EVENT_STREAM_VALUE)
    public Flux<ServerSentEvent<String>> stream(@Valid @RequestBody AnalysisAskRequest request) {
        log.info("收到流式分析请求 sessionId={} question={}", request.getSessionId(), request.getQuestion());
        return analysisService.askStream(request)
                .map(raw -> {
                    // analysisService 按 "event: xxx\ndata: yyy\n\n" 格式拼接原始字符串
                    int eventIdx = raw.indexOf("event: ");
                    int dataIdx = raw.indexOf("\ndata: ");
                    if (eventIdx != -1 && dataIdx != -1) {
                        String event = raw.substring(eventIdx + 7, dataIdx);
                        String data = raw.substring(dataIdx + 7, raw.length() - 2);
                        return ServerSentEvent.<String>builder()
                                .event(event.trim())
                                .data(data)
                                .build();
                    }
                    return ServerSentEvent.<String>builder().data(raw).build();
                })
                // SSE 心跳保活：防止中间代理（Nginx/Cloudflare）30s 无数据断连
                .mergeWith(Flux.interval(Duration.ofSeconds(15))
                        .map(tick -> ServerSentEvent.<String>builder().comment("hb").build())
                        .takeUntilOther(Flux.never()));
    }

    @Operation(summary = "分页查询问答历史")
    @PreAuthorize("hasAuthority('analysis:history')")
    @GetMapping("/history")
    public R<Page<BizQaHistory>> history(@RequestParam(defaultValue = "1") long pageNo,
                                         @RequestParam(defaultValue = "10") long pageSize) {
        return R.success(analysisService.history(pageNo, pageSize));
    }

    @Operation(summary = "导出分析报表 Excel",
            description = "传入 qaIds（逗号分隔）导出指定记录，不传则导出全部历史")
    @PreAuthorize("hasAuthority('analysis:export')")
    @GetMapping("/export")
    public void export(@RequestParam(required = false) String qaIds,
                       HttpServletResponse response) throws IOException {
        List<Long> ids = null;
        if (StrUtil.isNotBlank(qaIds)) {
            ids = java.util.Arrays.stream(qaIds.split(","))
                    .map(String::trim).filter(StrUtil::isNotBlank)
                    .map(Long::valueOf).toList();
        }
        List<BizQaHistory> records = analysisService.listForExport(ids);
        byte[] bytes = ExcelExportUtil.exportQaHistory(records);

        String fileName = URLEncoder.encode("分析报告历史.xlsx", StandardCharsets.UTF_8);
        response.setContentType(MediaType.APPLICATION_OCTET_STREAM_VALUE);
        response.setHeader("Content-Disposition", "attachment; filename*=UTF-8''" + fileName);
        response.setContentLength(bytes.length);
        response.getOutputStream().write(bytes);
        response.getOutputStream().flush();
    }

    @Operation(summary = "MCP 健康检查", description = "列出已通过标准 MCP 自动发现的 Python 工具")
    @GetMapping("/mcp/tools")
    public R<List<String>> mcpTools() {
        return R.success(mcpToolGateway.discoveredTools());
    }
}
