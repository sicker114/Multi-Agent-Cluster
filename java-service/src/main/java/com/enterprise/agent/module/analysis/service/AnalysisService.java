package com.enterprise.agent.module.analysis.service;

import com.baomidou.mybatisplus.extension.plugins.pagination.Page;
import com.enterprise.agent.entity.BizQaHistory;
import com.enterprise.agent.module.analysis.dto.AnalysisAskRequest;
import com.enterprise.agent.module.analysis.dto.AnalysisResponse;
import reactor.core.publisher.Flux;

import java.util.List;

/**
 * 业务分析服务：编排完整业务链路（鉴权已在上层完成）。
 *
 * @author enterprise-agent
 */
public interface AnalysisService {

    /**
     * 发起业务分析：先尝试「语义记忆」命中；否则经 MCP 调用 Python Agent 集群，
     * 结果持久化并写入长期记忆（指纹 + 语义双通道）。
     *
     * @param request 提问请求
     * @return 分析响应
     */
    AnalysisResponse ask(AnalysisAskRequest request);

    /**
     * 【增强】流式业务分析。返回 SSE（text/event-stream）事件流：
     * <ul>
     *   <li>event: planning / retrieving / computing / judging / report / done / error</li>
     *   <li>data: 事件 payload（JSON 字符串或文本片段）</li>
     * </ul>
     * 通过 Spring AI MCP 的 stream_callTool 实时推送 Python 侧流式输出。
     * 命中语义记忆时直接发送 cacheHit + done 事件，秒级返回。
     *
     * @param request 提问请求
     * @return SSE 事件流
     */
    Flux<String> askStream(AnalysisAskRequest request);

    /**
     * 分页查询当前用户问答历史。
     */
    Page<BizQaHistory> history(long pageNo, long pageSize);

    /**
     * 按ID查询问答历史（含越权校验）。
     */
    List<BizQaHistory> listForExport(List<Long> qaIds);
}
