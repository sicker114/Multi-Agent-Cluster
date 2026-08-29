package com.enterprise.agent.mapper;

import com.baomidou.mybatisplus.core.mapper.BaseMapper;
import com.enterprise.agent.entity.BizInventory;
import org.apache.ibatis.annotations.Mapper;
import org.apache.ibatis.annotations.Param;

import java.util.List;
import java.util.Map;

/**
 * 库存 Mapper。提供只读库存统计查询，供 SQL Agent 调用。
 *
 * @author enterprise-agent
 */
@Mapper
public interface BizInventoryMapper extends BaseMapper<BizInventory> {

    /**
     * 按部门查询库存明细（含安全库存对比，用于库存赤字识别）。
     *
     * @param deptIds  数据权限部门集合（null 或空表示不限）
     * @param category 产品分类（可空）
     * @param statDate 统计日期（可空，默认最新）
     * @return 库存明细
     */
    List<Map<String, Object>> statInventory(@Param("deptIds") List<Long> deptIds,
                                             @Param("category") String category,
                                             @Param("statDate") String statDate);
}
