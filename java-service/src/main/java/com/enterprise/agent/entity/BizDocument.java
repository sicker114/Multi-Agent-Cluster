package com.enterprise.agent.entity;

import com.baomidou.mybatisplus.annotation.*;
import lombok.Data;

import java.io.Serializable;
import java.time.LocalDateTime;

/**
 * 文档知识库实体，对应表 biz_document。存储文件元数据，内容供 Python GraphRAG 拉取。
 *
 * @author enterprise-agent
 */
@Data
@TableName("biz_document")
public class BizDocument implements Serializable {

    @TableId(type = IdType.AUTO)
    private Long id;

    private String fileName;

    private String fileType;

    private String storageType;

    private String storagePath;

    private String category;

    /** 权限范围部门ID。 */
    private Long deptId;

    private Long uploaderId;

    private String uploaderName;

    private Long fileSize;

    /** 是否已构建 GraphRAG 索引：0 否 1 是。 */
    private Integer indexed;

    @TableField(fill = FieldFill.INSERT)
    private LocalDateTime createTime;

    @TableLogic
    private Integer deleted;
}
