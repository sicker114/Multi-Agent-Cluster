package com.enterprise.agent.module.business.service.impl;

import cn.hutool.core.util.StrUtil;
import com.enterprise.agent.common.exception.BusinessException;
import com.enterprise.agent.common.response.ResultCode;
import com.enterprise.agent.common.utils.SqlSafetyGuard;
import com.enterprise.agent.mapper.BizInventoryMapper;
import com.enterprise.agent.mapper.BizSalesOrderMapper;
import com.enterprise.agent.module.business.dto.SafeQueryRequest;
import com.enterprise.agent.module.business.service.BusinessDataService;
import lombok.RequiredArgsConstructor;
import lombok.extern.slf4j.Slf4j;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

import java.util.Collections;
import java.util.List;
import java.util.Map;

/**
 * 业务数据安全查询服务实现。
 * <p>结构化查询走 MyBatis 参数化 SQL；RAW_SQL 走 {@link SqlSafetyGuard} 校验后的只读 JdbcTemplate。
 * 全程只读事务，杜绝任何写操作。</p>
 *
 * @author enterprise-agent
 */
@Slf4j
@Service
@RequiredArgsConstructor
public class BusinessDataServiceImpl implements BusinessDataService {

    private final BizSalesOrderMapper salesOrderMapper;
    private final BizInventoryMapper inventoryMapper;
    private final JdbcTemplate jdbcTemplate;

    /** RAW_SQL 单次最大返回行数，防止大表全表拉取。 */
    private static final int MAX_ROWS = 1000;

    @Override
    @Transactional(readOnly = true)
    public List<Map<String, Object>> safeQuery(SafeQueryRequest request) {
        if (request == null || StrUtil.isBlank(request.getQueryType())) {
            throw new BusinessException(ResultCode.PARAM_INVALID, "queryType 不能为空");
        }
        String type = request.getQueryType().toUpperCase();
        log.info("SQL Agent 安全查询 type={} category={} range=[{}~{}] deptIds={}",
                type, request.getCategory(), request.getStartDate(), request.getEndDate(), request.getDeptIds());

        return switch (type) {
            case "SALES_PERIOD" -> emptyToSignal(salesOrderMapper.statSalesByPeriod(
                    request.getDeptIds(), request.getCategory(), request.getStartDate(), request.getEndDate()));
            case "SALES_TREND" -> emptyToSignal(salesOrderMapper.statMonthlyTrend(
                    request.getDeptIds(), request.getCategory(), request.getStartDate(), request.getEndDate()));
            case "INVENTORY" -> emptyToSignal(inventoryMapper.statInventory(
                    request.getDeptIds(), request.getCategory(), request.getStatDate()));
            case "RAW_SQL" -> execRawSql(request.getRawSql());
            default -> throw new BusinessException(ResultCode.PARAM_INVALID, "不支持的 queryType：" + type);
        };
    }

    /**
     * 执行经安全校验的只读原始 SQL。
     */
    private List<Map<String, Object>> execRawSql(String rawSql) {
        if (StrUtil.isBlank(rawSql)) {
            throw new BusinessException(ResultCode.PARAM_INVALID, "rawSql 不能为空");
        }
        // 高危拦截：仅允许单条 SELECT/WITH 只读语句
        SqlSafetyGuard.check(rawSql);

        // 强制加 LIMIT，避免大结果集
        String finalSql = ensureLimit(rawSql.trim());
        try {
            List<Map<String, Object>> rows = jdbcTemplate.queryForList(finalSql);
            return emptyToSignal(rows);
        } catch (Exception e) {
            log.warn("RAW_SQL 执行失败 sql={} err={}", finalSql, e.getMessage());
            // 字段不存在等异常向上返回清晰标识
            throw new BusinessException(ResultCode.DATA_NOT_FOUND,
                    "SQL 执行异常（字段或表不存在）：" + e.getMessage());
        }
    }

    private String ensureLimit(String sql) {
        String noSemicolon = sql.endsWith(";") ? sql.substring(0, sql.length() - 1) : sql;
        if (noSemicolon.toLowerCase().contains(" limit ")) {
            return noSemicolon;
        }
        return noSemicolon + " LIMIT " + MAX_ROWS;
    }

    /**
     * 空结果转为空列表（由上层 SQL Agent 判定 “无数据” 边界场景）。
     */
    private List<Map<String, Object>> emptyToSignal(List<Map<String, Object>> rows) {
        return rows == null ? Collections.emptyList() : rows;
    }
}
