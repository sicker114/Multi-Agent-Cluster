package com.enterprise.agent.entity;

import com.baomidou.mybatisplus.annotation.IdType;
import com.baomidou.mybatisplus.annotation.TableId;
import com.baomidou.mybatisplus.annotation.TableName;
import lombok.Data;

import java.io.Serializable;
import java.math.BigDecimal;
import java.time.LocalDate;
import java.time.LocalDateTime;

/**
 * 订单销售业务实体，对应表 biz_sales_order。供 SQL Agent 只读统计。
 *
 * @author enterprise-agent
 */
@Data
@TableName("biz_sales_order")
public class BizSalesOrder implements Serializable {

    @TableId(type = IdType.AUTO)
    private Long id;

    private String orderNo;

    /** 归属部门，数据权限隔离。 */
    private Long deptId;

    private String productName;

    private String category;

    private Integer quantity;

    private BigDecimal amount;

    private LocalDate orderDate;

    private String region;

    private LocalDateTime createTime;
}
