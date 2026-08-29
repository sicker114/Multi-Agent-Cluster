package com.enterprise.agent.module.mcp.dto;

import io.swagger.v3.oas.annotations.media.Schema;
import lombok.Data;

import java.util.List;

/**
 * Java 通过 MCP 下发给 Python Agent 集群的分析请求参数。
 * <p>与 Python 侧 MCP 工具 {@code enterprise_analysis} 的入参严格对应。</p>
 *
 * @author enterprise-agent
 */
@Data
@Schema(description = "MCP 分析请求")
public class McpAnalysisRequest {

    @Schema(description = "用户自然语言业务需求")
    private String question;

    @Schema(description = "用户ID")
    private Long userId;

    @Schema(description = "部门ID")
    private Long deptId;

    @Schema(description = "数据权限部门集合，null 表示全量")
    private List<Long> deptIds;

    @Schema(description = "会话ID，用于任务 Checkpoint 与多轮上下文")
    private String sessionId;

    @Schema(description = "Java 内部回调基础地址（Python 子 Agent 回调拉取文档/数据）")
    private String callbackBaseUrl;

    @Schema(description = "内部回调密钥")
    private String internalApiKey;
}
