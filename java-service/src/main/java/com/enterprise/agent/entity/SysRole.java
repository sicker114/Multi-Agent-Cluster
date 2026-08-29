package com.enterprise.agent.entity;

import com.baomidou.mybatisplus.annotation.IdType;
import com.baomidou.mybatisplus.annotation.TableId;
import com.baomidou.mybatisplus.annotation.TableLogic;
import com.baomidou.mybatisplus.annotation.TableName;
import lombok.Data;

import java.io.Serializable;
import java.time.LocalDateTime;

/**
 * 角色实体，对应表 sys_role。data_scope：1 全部数据，2 本部门数据。
 *
 * @author enterprise-agent
 */
@Data
@TableName("sys_role")
public class SysRole implements Serializable {

    @TableId(type = IdType.AUTO)
    private Long id;

    private String roleName;

    private String roleCode;

    /** 数据范围：1 全部；2 本部门。 */
    private Integer dataScope;

    private String remark;

    private LocalDateTime createTime;

    @TableLogic
    private Integer deleted;
}
