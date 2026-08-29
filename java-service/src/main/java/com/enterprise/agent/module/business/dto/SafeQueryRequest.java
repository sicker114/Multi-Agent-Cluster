package com.enterprise.agent.module.business.dto;

import io.swagger.v3.oas.annotations.media.Schema;
import lombok.Data;

import java.util.List;

/**
 * 供 Python SQL Agent 调用的安全查询请求。
 * <p>推荐使用结构化参数（queryType + 过滤条件）；也支持传入原始只读 SQL，
 * 但会经过 {@code SqlSafetyGuard} 严格拦截。</p>
 *
 * @author enterprise-agent
 */
@Data
@Schema(description = "安全数据查询请求")
public class SafeQueryRequest {

    @Schema(description = "查询类型：SALES_PERIOD / SALES_TREND / INVENTORY / RAW_SQL")
    private String queryType;

    @Schema(description = "数据权限部门集合，null 表示全量（管理员）")
    private List<Long> deptIds;

    @Schema(description = "产品分类过滤")
    private String category;

    @Schema(description = "起始日期 yyyy-MM-dd")
    private String startDate;

    @Schema(description = "结束日期 yyyy-MM-dd")
    private String endDate;

    @Schema(description = "统计日期（库存查询用）")
    private String statDate;

    @Schema(description = "原始只读 SQL（queryType=RAW_SQL 时使用，需通过安全校验）")
    private String rawSql;
}
