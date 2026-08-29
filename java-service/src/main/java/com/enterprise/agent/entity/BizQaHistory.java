package com.enterprise.agent.entity;

import com.baomidou.mybatisplus.annotation.FieldFill;
import com.baomidou.mybatisplus.annotation.IdType;
import com.baomidou.mybatisplus.annotation.TableField;
import com.baomidou.mybatisplus.annotation.TableId;
import com.baomidou.mybatisplus.annotation.TableName;
import lombok.Data;

import java.io.Serializable;
import java.time.LocalDateTime;

/**
 * 问答历史记录实体，对应表 biz_qa_history。承载结果后置持久化与量化统计字段。
 *
 * @author enterprise-agent
 */
@Data
@TableName("biz_qa_history")
public class BizQaHistory implements Serializable {

    @TableId(type = IdType.AUTO)
    private Long id;

    private Long userId;

    private Long deptId;

    private String sessionId;

    private String question;

    private String answerReport;

    /** Judge 置信度 0-100。 */
    private Integer confidenceScore;

    /** 数据溯源信息(JSON)。 */
    private String dataSource;

    private String riskTags;

    /** 反思重试次数，用于统计幻觉率下降指标。 */
    private Integer retryCount;

    /** 本次 Token 消耗，用于统计记忆复用节省。 */
    private Integer tokenCost;

    /** 是否命中长期记忆缓存 0/1。 */
    private Integer cacheHit;

    private Long costMs;

    private String status;

    @TableField(fill = FieldFill.INSERT)
    private LocalDateTime createTime;
}
