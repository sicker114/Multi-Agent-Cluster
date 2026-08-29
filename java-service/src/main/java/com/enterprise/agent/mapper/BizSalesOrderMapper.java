package com.enterprise.agent.mapper;

import com.baomidou.mybatisplus.core.mapper.BaseMapper;
import com.enterprise.agent.entity.BizSalesOrder;
import org.apache.ibatis.annotations.Mapper;
import org.apache.ibatis.annotations.Param;
import org.apache.ibatis.annotations.Select;

import java.util.List;
import java.util.Map;

/**
 * 销售订单 Mapper。提供受控的只读聚合统计查询，供 SQL Agent 通过 Java 安全接口调用。
 *
 * @author enterprise-agent
 */
@Mapper
public interface BizSalesOrderMapper extends BaseMapper<BizSalesOrder> {

    /**
     * 按部门 + 时间区间聚合销售额与销量（只读统计）。
     * <p>使用参数化查询，杜绝 SQL 注入；deptIds 为空表示管理员全量。</p>
     *
     * @param deptIds   数据权限部门集合（null 或空表示不限）
     * @param category  产品分类（可空）
     * @param startDate 起始日期 yyyy-MM-dd
     * @param endDate   结束日期 yyyy-MM-dd
     * @return 聚合结果列表
     */
    List<Map<String, Object>> statSalesByPeriod(@Param("deptIds") List<Long> deptIds,
                                                 @Param("category") String category,
                                                 @Param("startDate") String startDate,
                                                 @Param("endDate") String endDate);

    /**
     * 按月聚合销售趋势（供同比/环比计算）。
     */
    List<Map<String, Object>> statMonthlyTrend(@Param("deptIds") List<Long> deptIds,
                                                @Param("category") String category,
                                                @Param("startDate") String startDate,
                                                @Param("endDate") String endDate);
}
