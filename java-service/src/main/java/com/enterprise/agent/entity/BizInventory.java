package com.enterprise.agent.entity;

import com.baomidou.mybatisplus.annotation.IdType;
import com.baomidou.mybatisplus.annotation.TableId;
import com.baomidou.mybatisplus.annotation.TableName;
import lombok.Data;

import java.io.Serializable;
import java.time.LocalDate;
import java.time.LocalDateTime;

/**
 * 库存业务实体，对应表 biz_inventory。供 SQL Agent 只读统计。
 *
 * @author enterprise-agent
 */
@Data
@TableName("biz_inventory")
public class BizInventory implements Serializable {

    @TableId(type = IdType.AUTO)
    private Long id;

    private Long deptId;

    private String productName;

    private String category;

    private Integer stockQty;

    /** 安全库存阈值，低于该值视为库存赤字风险。 */
    private Integer safetyStock;

    private String warehouse;

    private LocalDate statDate;

    private LocalDateTime createTime;
}
