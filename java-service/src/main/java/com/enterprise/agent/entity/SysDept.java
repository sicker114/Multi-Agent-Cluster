package com.enterprise.agent.entity;

import com.baomidou.mybatisplus.annotation.IdType;
import com.baomidou.mybatisplus.annotation.TableId;
import com.baomidou.mybatisplus.annotation.TableLogic;
import com.baomidou.mybatisplus.annotation.TableName;
import lombok.Data;

import java.io.Serializable;
import java.time.LocalDateTime;

/**
 * 部门实体，对应表 sys_dept。
 *
 * @author enterprise-agent
 */
@Data
@TableName("sys_dept")
public class SysDept implements Serializable {

    @TableId(type = IdType.AUTO)
    private Long id;

    private String deptName;

    private Long parentId;

    private Integer sort;

    private Integer status;

    private LocalDateTime createTime;

    private LocalDateTime updateTime;

    @TableLogic
    private Integer deleted;
}
