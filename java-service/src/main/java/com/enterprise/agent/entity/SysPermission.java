package com.enterprise.agent.entity;

import com.baomidou.mybatisplus.annotation.IdType;
import com.baomidou.mybatisplus.annotation.TableId;
import com.baomidou.mybatisplus.annotation.TableName;
import lombok.Data;

import java.io.Serializable;
import java.time.LocalDateTime;

/**
 * 权限实体，对应表 sys_permission。
 *
 * @author enterprise-agent
 */
@Data
@TableName("sys_permission")
public class SysPermission implements Serializable {

    @TableId(type = IdType.AUTO)
    private Long id;

    private String permName;

    /** 权限标识，如 analysis:ask。 */
    private String permCode;

    private Integer type;

    private LocalDateTime createTime;
}
