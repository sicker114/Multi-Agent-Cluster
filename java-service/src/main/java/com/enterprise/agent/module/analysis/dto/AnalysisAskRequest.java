package com.enterprise.agent.module.analysis.dto;

import io.swagger.v3.oas.annotations.media.Schema;
import jakarta.validation.constraints.NotBlank;
import jakarta.validation.constraints.Size;
import lombok.Data;

/**
 * 业务分析提问请求。
 *
 * @author enterprise-agent
 */
@Data
@Schema(description = "业务分析提问请求")
public class AnalysisAskRequest {

    @Schema(description = "自然语言业务需求", example = "分析2025年第一季度智能路由器X1的销售同比与库存风险")
    @NotBlank(message = "问题不能为空")
    @Size(max = 1000, message = "问题长度不能超过1000字")
    private String question;

    @Schema(description = "会话ID，可选，不传则自动生成新会话")
    private String sessionId;
}
