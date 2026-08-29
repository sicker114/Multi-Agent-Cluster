package com.enterprise.agent.module.analysis.dto;

import io.swagger.v3.oas.annotations.media.Schema;
import lombok.Data;

import java.util.List;

/**
 * 业务分析响应（标准化前端展示结构）。
 *
 * @author enterprise-agent
 */
@Data
@Schema(description = "业务分析响应")
public class AnalysisResponse {

    @Schema(description = "问答记录ID")
    private Long qaId;

    @Schema(description = "会话ID")
    private String sessionId;

    @Schema(description = "用户问题")
    private String question;

    @Schema(description = "分析报告全文（结构化排版）")
    private String report;

    @Schema(description = "置信度 0-100")
    private Integer confidenceScore;

    @Schema(description = "风险标注")
    private List<String> riskTags;

    @Schema(description = "数据来源溯源")
    private List<SourceItem> dataSources;

    @Schema(description = "是否命中记忆缓存")
    private Boolean cacheHit;

    @Schema(description = "反思重试次数")
    private Integer retryCount;

    @Schema(description = "Token 消耗")
    private Integer tokenCost;

    @Schema(description = "端到端耗时(ms)")
    private Long costMs;

    @Data
    @Schema(description = "来源条目")
    public static class SourceItem {
        private String type;
        private String reference;
        private String evidence;
    }
}
