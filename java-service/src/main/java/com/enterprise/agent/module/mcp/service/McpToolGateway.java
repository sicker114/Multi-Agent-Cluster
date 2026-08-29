package com.enterprise.agent.module.mcp.service;

import com.enterprise.agent.module.mcp.dto.McpAnalysisRequest;
import com.enterprise.agent.module.mcp.dto.McpAnalysisResult;
import reactor.core.publisher.Flux;

/**
 * MCP 工具调用网关。统一封装对 Python Agent 集群的标准 MCP 调用，
 * 屏蔽底层通信细节，向业务层提供稳定的分析能力。
 *
 * @author enterprise-agent
 */
public interface McpToolGateway {

    /**
     * 同步调用 Python MCP 服务的 enterprise_analysis 工具，执行多智能体分析。
     * <p>内置：超时控制、失败重试、熔断降级、全链路日志。</p>
     *
     * @param request 分析请求
     * @return 分析结果
     */
    McpAnalysisResult analyze(McpAnalysisRequest request);

    /**
     * 【增强】流式调用 Python MCP 的 stream_enterprise_analysis 工具。
     * <p>返回 SSE 事件流字符串（event/data 双行格式），业务层直接包装为 ServerSentEvent。
     * 事件类型：planning / retrieving / computing / judging / report(增量) / done / error 。</p>
     *
     * @param request 分析请求（与同步版相同）
     * @return Flux SSE 原始格式字符串流
     */
    Flux<String> analyzeStream(McpAnalysisRequest request);

    /**
     * 获取 analyzeStream() 完整执行完成后累积的最终结构化结果。
     * <p>业务层在 Flux complete 回调中调用，用于落库与写记忆。</p>
     *
     * @param request 用于关联（和刚才调用 analyzeStream 的同一请求对象）
     * @return 最终 MCP 分析结果
     */
    McpAnalysisResult lastStreamResult(McpAnalysisRequest request);

    /**
     * 列出当前已通过 MCP 自动发现的 Python 侧工具名称，用于健康检查与观测。
     *
     * @return 工具名称列表
     */
    java.util.List<String> discoveredTools();
}
