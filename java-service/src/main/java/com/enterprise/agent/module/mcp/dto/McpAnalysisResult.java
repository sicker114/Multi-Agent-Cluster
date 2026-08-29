package com.enterprise.agent.module.mcp.dto;

import io.swagger.v3.oas.annotations.media.Schema;
import lombok.Data;

import java.util.List;

/**
 * Python Agent 集群通过 MCP 返回给 Java 的分析结果。
 *
 * @author enterprise-agent
 */
@Data
@Schema(description = "MCP 分析结果")
public class McpAnalysisResult {

    @Schema(description = "是否成功")
    private boolean success;

    @Schema(description = "错误标识（失败时）")
    private String errorCode;

    @Schema(description = "错误描述")
    private String errorMessage;

    @Schema(description = "完整业务分析报告全文")
    private String report;

    @Schema(description = "Judge 置信度 0-100")
    private Integer confidenceScore;

    @Schema(description = "数据来源溯源列表")
    private List<DataSource> dataSources;

    @Schema(description = "风险标注")
    private List<String> riskTags;

    @Schema(description = "反思重试次数")
    private Integer retryCount;

    @Schema(description = "Token 消耗")
    private Integer tokenCost;

    @Schema(description = "是否命中记忆缓存")
    private Boolean cacheHit;

    @Data
    @Schema(description = "数据来源")
    public static class DataSource {
        @Schema(description = "来源类型 document/database/computation")
        private String type;
        @Schema(description = "来源描述（文档名 / 表名 / 指标名）")
        private String reference;
        @Schema(description = "证据片段")
        private String evidence;
    }
}
