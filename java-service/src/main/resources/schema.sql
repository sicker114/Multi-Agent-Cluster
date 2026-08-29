-- =====================================================================
-- 多智能体企业数字员工数据分析集群 - MySQL 全量建表脚本
-- 数据库：enterprise_agent
-- 说明：包含 RBAC 权限体系、业务数据表、文档知识库、问答历史，
--       含索引与初始化管理员账号及演示数据。
-- =====================================================================

CREATE DATABASE IF NOT EXISTS `enterprise_agent`
    DEFAULT CHARACTER SET utf8mb4 COLLATE utf8mb4_general_ci;

USE `enterprise_agent`;

-- ---------------------------------------------------------------------
-- 部门表
-- ---------------------------------------------------------------------
DROP TABLE IF EXISTS `sys_dept`;
CREATE TABLE `sys_dept` (
    `id`          BIGINT       NOT NULL AUTO_INCREMENT COMMENT '部门ID',
    `dept_name`   VARCHAR(64)  NOT NULL COMMENT '部门名称',
    `parent_id`   BIGINT       NOT NULL DEFAULT 0 COMMENT '父部门ID，0为顶级',
    `sort`        INT          NOT NULL DEFAULT 0 COMMENT '排序',
    `status`      TINYINT      NOT NULL DEFAULT 1 COMMENT '状态 1启用 0停用',
    `create_time` DATETIME     NOT NULL DEFAULT CURRENT_TIMESTAMP COMMENT '创建时间',
    `update_time` DATETIME     NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP COMMENT '更新时间',
    `deleted`     TINYINT      NOT NULL DEFAULT 0 COMMENT '逻辑删除 0未删 1已删',
    PRIMARY KEY (`id`),
    KEY `idx_parent` (`parent_id`)
) ENGINE = InnoDB DEFAULT CHARSET = utf8mb4 COMMENT ='部门表';

-- ---------------------------------------------------------------------
-- 用户表
-- ---------------------------------------------------------------------
DROP TABLE IF EXISTS `sys_user`;
CREATE TABLE `sys_user` (
    `id`          BIGINT       NOT NULL AUTO_INCREMENT COMMENT '用户ID',
    `username`    VARCHAR(64)  NOT NULL COMMENT '登录账号',
    `password`    VARCHAR(128) NOT NULL COMMENT 'BCrypt 加密密码',
    `real_name`   VARCHAR(64)           DEFAULT NULL COMMENT '真实姓名',
    `phone`       VARCHAR(20)           DEFAULT NULL COMMENT '手机号',
    `dept_id`     BIGINT       NOT NULL COMMENT '所属部门ID（数据权限隔离依据）',
    `status`      TINYINT      NOT NULL DEFAULT 1 COMMENT '状态 1启用 0停用',
    `create_time` DATETIME     NOT NULL DEFAULT CURRENT_TIMESTAMP COMMENT '创建时间',
    `update_time` DATETIME     NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP COMMENT '更新时间',
    `deleted`     TINYINT      NOT NULL DEFAULT 0 COMMENT '逻辑删除',
    PRIMARY KEY (`id`),
    UNIQUE KEY `uk_username` (`username`),
    KEY `idx_dept` (`dept_id`)
) ENGINE = InnoDB DEFAULT CHARSET = utf8mb4 COMMENT ='用户表';

-- ---------------------------------------------------------------------
-- 角色表
-- ---------------------------------------------------------------------
DROP TABLE IF EXISTS `sys_role`;
CREATE TABLE `sys_role` (
    `id`          BIGINT      NOT NULL AUTO_INCREMENT COMMENT '角色ID',
    `role_name`   VARCHAR(64) NOT NULL COMMENT '角色名称',
    `role_code`   VARCHAR(64) NOT NULL COMMENT '角色编码 ADMIN/EMPLOYEE',
    `data_scope`  TINYINT     NOT NULL DEFAULT 2 COMMENT '数据范围 1全部 2本部门',
    `remark`      VARCHAR(255)         DEFAULT NULL COMMENT '备注',
    `create_time` DATETIME    NOT NULL DEFAULT CURRENT_TIMESTAMP COMMENT '创建时间',
    `deleted`     TINYINT     NOT NULL DEFAULT 0 COMMENT '逻辑删除',
    PRIMARY KEY (`id`),
    UNIQUE KEY `uk_role_code` (`role_code`)
) ENGINE = InnoDB DEFAULT CHARSET = utf8mb4 COMMENT ='角色表';

-- ---------------------------------------------------------------------
-- 权限（菜单/接口）表
-- ---------------------------------------------------------------------
DROP TABLE IF EXISTS `sys_permission`;
CREATE TABLE `sys_permission` (
    `id`           BIGINT       NOT NULL AUTO_INCREMENT COMMENT '权限ID',
    `perm_name`    VARCHAR(64)  NOT NULL COMMENT '权限名称',
    `perm_code`    VARCHAR(128) NOT NULL COMMENT '权限标识 如 analysis:ask',
    `type`         TINYINT      NOT NULL DEFAULT 2 COMMENT '类型 1菜单 2接口',
    `create_time`  DATETIME     NOT NULL DEFAULT CURRENT_TIMESTAMP COMMENT '创建时间',
    PRIMARY KEY (`id`),
    UNIQUE KEY `uk_perm_code` (`perm_code`)
) ENGINE = InnoDB DEFAULT CHARSET = utf8mb4 COMMENT ='权限表';

-- ---------------------------------------------------------------------
-- 用户-角色关联表
-- ---------------------------------------------------------------------
DROP TABLE IF EXISTS `sys_user_role`;
CREATE TABLE `sys_user_role` (
    `id`      BIGINT NOT NULL AUTO_INCREMENT,
    `user_id` BIGINT NOT NULL COMMENT '用户ID',
    `role_id` BIGINT NOT NULL COMMENT '角色ID',
    PRIMARY KEY (`id`),
    UNIQUE KEY `uk_user_role` (`user_id`, `role_id`)
) ENGINE = InnoDB DEFAULT CHARSET = utf8mb4 COMMENT ='用户角色关联表';

-- ---------------------------------------------------------------------
-- 角色-权限关联表
-- ---------------------------------------------------------------------
DROP TABLE IF EXISTS `sys_role_permission`;
CREATE TABLE `sys_role_permission` (
    `id`      BIGINT NOT NULL AUTO_INCREMENT,
    `role_id` BIGINT NOT NULL COMMENT '角色ID',
    `perm_id` BIGINT NOT NULL COMMENT '权限ID',
    PRIMARY KEY (`id`),
    UNIQUE KEY `uk_role_perm` (`role_id`, `perm_id`)
) ENGINE = InnoDB DEFAULT CHARSET = utf8mb4 COMMENT ='角色权限关联表';

-- ---------------------------------------------------------------------
-- 订单销售表（业务数据，供 SQL Agent 只读统计）
-- ---------------------------------------------------------------------
DROP TABLE IF EXISTS `biz_sales_order`;
CREATE TABLE `biz_sales_order` (
    `id`           BIGINT         NOT NULL AUTO_INCREMENT COMMENT '订单ID',
    `order_no`     VARCHAR(64)    NOT NULL COMMENT '订单号',
    `dept_id`      BIGINT         NOT NULL COMMENT '归属部门（数据权限隔离）',
    `product_name` VARCHAR(128)   NOT NULL COMMENT '产品名称',
    `category`     VARCHAR(64)    NOT NULL COMMENT '产品分类',
    `quantity`     INT            NOT NULL DEFAULT 0 COMMENT '销售数量',
    `amount`       DECIMAL(14, 2) NOT NULL DEFAULT 0 COMMENT '销售金额',
    `order_date`   DATE           NOT NULL COMMENT '下单日期',
    `region`       VARCHAR(64)             DEFAULT NULL COMMENT '销售区域',
    `create_time`  DATETIME       NOT NULL DEFAULT CURRENT_TIMESTAMP COMMENT '创建时间',
    PRIMARY KEY (`id`),
    UNIQUE KEY `uk_order_no` (`order_no`),
    KEY `idx_dept_date` (`dept_id`, `order_date`),
    KEY `idx_category` (`category`)
) ENGINE = InnoDB DEFAULT CHARSET = utf8mb4 COMMENT ='订单销售表';

-- ---------------------------------------------------------------------
-- 库存表（业务数据）
-- ---------------------------------------------------------------------
DROP TABLE IF EXISTS `biz_inventory`;
CREATE TABLE `biz_inventory` (
    `id`            BIGINT       NOT NULL AUTO_INCREMENT COMMENT '库存ID',
    `dept_id`       BIGINT       NOT NULL COMMENT '归属部门',
    `product_name`  VARCHAR(128) NOT NULL COMMENT '产品名称',
    `category`      VARCHAR(64)  NOT NULL COMMENT '产品分类',
    `stock_qty`     INT          NOT NULL DEFAULT 0 COMMENT '当前库存量',
    `safety_stock`  INT          NOT NULL DEFAULT 0 COMMENT '安全库存阈值',
    `warehouse`     VARCHAR(64)           DEFAULT NULL COMMENT '仓库',
    `stat_date`     DATE         NOT NULL COMMENT '统计日期',
    `create_time`   DATETIME     NOT NULL DEFAULT CURRENT_TIMESTAMP COMMENT '创建时间',
    PRIMARY KEY (`id`),
    KEY `idx_dept_date` (`dept_id`, `stat_date`),
    KEY `idx_category` (`category`)
) ENGINE = InnoDB DEFAULT CHARSET = utf8mb4 COMMENT ='库存表';

-- ---------------------------------------------------------------------
-- 文档知识库表（文件元数据，内容供 Python GraphRAG 拉取）
-- ---------------------------------------------------------------------
DROP TABLE IF EXISTS `biz_document`;
CREATE TABLE `biz_document` (
    `id`            BIGINT       NOT NULL AUTO_INCREMENT COMMENT '文档ID',
    `file_name`     VARCHAR(255) NOT NULL COMMENT '原始文件名',
    `file_type`     VARCHAR(16)  NOT NULL COMMENT '文件类型 pdf/docx/txt',
    `storage_type`  VARCHAR(16)  NOT NULL COMMENT '存储类型 local/minio',
    `storage_path`  VARCHAR(512) NOT NULL COMMENT '存储路径或对象key',
    `category`      VARCHAR(64)           DEFAULT '通用' COMMENT '文档分类',
    `dept_id`       BIGINT       NOT NULL COMMENT '权限范围部门ID',
    `uploader_id`   BIGINT       NOT NULL COMMENT '上传人ID',
    `uploader_name` VARCHAR(64)           DEFAULT NULL COMMENT '上传人姓名',
    `file_size`     BIGINT       NOT NULL DEFAULT 0 COMMENT '文件大小(byte)',
    `indexed`       TINYINT      NOT NULL DEFAULT 0 COMMENT '是否已构建GraphRAG索引 0否 1是',
    `create_time`   DATETIME     NOT NULL DEFAULT CURRENT_TIMESTAMP COMMENT '上传时间',
    `deleted`       TINYINT      NOT NULL DEFAULT 0 COMMENT '逻辑删除',
    PRIMARY KEY (`id`),
    KEY `idx_dept` (`dept_id`),
    KEY `idx_uploader` (`uploader_id`)
) ENGINE = InnoDB DEFAULT CHARSET = utf8mb4 COMMENT ='文档知识库表';

-- ---------------------------------------------------------------------
-- 问答历史记录表（结果后置持久化）
-- ---------------------------------------------------------------------
DROP TABLE IF EXISTS `biz_qa_history`;
CREATE TABLE `biz_qa_history` (
    `id`               BIGINT       NOT NULL AUTO_INCREMENT COMMENT '记录ID',
    `user_id`          BIGINT       NOT NULL COMMENT '提问用户ID',
    `dept_id`          BIGINT       NOT NULL COMMENT '用户部门ID',
    `session_id`       VARCHAR(64)  NOT NULL COMMENT '会话ID',
    `question`         TEXT         NOT NULL COMMENT '用户自然语言问题',
    `answer_report`    LONGTEXT              DEFAULT NULL COMMENT 'AI 分析报告全文',
    `confidence_score` INT          NOT NULL DEFAULT 0 COMMENT 'Judge 置信度 0-100',
    `data_source`      TEXT                  DEFAULT NULL COMMENT '数据溯源信息(JSON)',
    `risk_tags`        VARCHAR(512)          DEFAULT NULL COMMENT '风险标注',
    `retry_count`      INT          NOT NULL DEFAULT 0 COMMENT '反思重试次数',
    `token_cost`       INT          NOT NULL DEFAULT 0 COMMENT '本次 Token 消耗',
    `cache_hit`        TINYINT      NOT NULL DEFAULT 0 COMMENT '是否命中长期记忆缓存',
    `cost_ms`          BIGINT       NOT NULL DEFAULT 0 COMMENT '端到端耗时(ms)',
    `status`           VARCHAR(16)  NOT NULL DEFAULT 'SUCCESS' COMMENT '状态 SUCCESS/FAILED',
    `create_time`      DATETIME     NOT NULL DEFAULT CURRENT_TIMESTAMP COMMENT '创建时间',
    PRIMARY KEY (`id`),
    KEY `idx_user` (`user_id`),
    KEY `idx_session` (`session_id`),
    KEY `idx_create` (`create_time`)
) ENGINE = InnoDB DEFAULT CHARSET = utf8mb4 COMMENT ='问答历史记录表';

-- =====================================================================
-- 初始化数据
-- =====================================================================
-- 部门
INSERT INTO `sys_dept` (`id`, `dept_name`, `parent_id`, `sort`) VALUES
    (1, '总公司', 0, 1),
    (2, '销售一部', 1, 2),
    (3, '销售二部', 1, 3),
    (4, '仓储物流部', 1, 4);

-- 角色（管理员看全部数据，员工只看本部门）
INSERT INTO `sys_role` (`id`, `role_name`, `role_code`, `data_scope`, `remark`) VALUES
    (1, '系统管理员', 'ADMIN', 1, '全部数据权限'),
    (2, '普通员工', 'EMPLOYEE', 2, '仅本部门数据权限');

-- 权限点
INSERT INTO `sys_permission` (`id`, `perm_name`, `perm_code`, `type`) VALUES
    (1, '发起业务分析', 'analysis:ask', 2),
    (2, '查询问答历史', 'analysis:history', 2),
    (3, '导出分析报表', 'analysis:export', 2),
    (4, '上传知识库文档', 'file:upload', 2),
    (5, '管理知识库文档', 'file:manage', 2),
    (6, '用户管理', 'system:user', 2);

-- 角色-权限：ADMIN 拥有全部，EMPLOYEE 拥有分析与上传相关
INSERT INTO `sys_role_permission` (`role_id`, `perm_id`) VALUES
    (1, 1), (1, 2), (1, 3), (1, 4), (1, 5), (1, 6),
    (2, 1), (2, 2), (2, 3), (2, 4);

-- 用户：密码均为 123456 的 BCrypt 值
-- admin(管理员, 总公司)  zhangsan(销售一部)  lisi(销售二部)
INSERT INTO `sys_user` (`id`, `username`, `password`, `real_name`, `phone`, `dept_id`) VALUES
    (1, 'admin', '$2a$10$7JB720yubVSZvUI0rEqK/.VqGOZTH.ulu33dHOiBE8ByOhJIrdAu2', '超级管理员', '13800000000', 1),
    (2, 'zhangsan', '$2a$10$7JB720yubVSZvUI0rEqK/.VqGOZTH.ulu33dHOiBE8ByOhJIrdAu2', '张三', '13800000001', 2),
    (3, 'lisi', '$2a$10$7JB720yubVSZvUI0rEqK/.VqGOZTH.ulu33dHOiBE8ByOhJIrdAu2', '李四', '13800000002', 3);

-- 用户-角色
INSERT INTO `sys_user_role` (`user_id`, `role_id`) VALUES
    (1, 1), (2, 2), (3, 2);

-- 销售演示数据（用于同比/环比/暴跌演示）
INSERT INTO `biz_sales_order` (`order_no`, `dept_id`, `product_name`, `category`, `quantity`, `amount`, `order_date`, `region`) VALUES
    ('SO2025010001', 2, '智能路由器X1', '网络设备', 120, 360000.00, '2025-01-15', '华东'),
    ('SO2025020001', 2, '智能路由器X1', '网络设备', 150, 450000.00, '2025-02-15', '华东'),
    ('SO2025030001', 2, '智能路由器X1', '网络设备', 60,  180000.00, '2025-03-15', '华东'),
    ('SO2024010001', 2, '智能路由器X1', '网络设备', 100, 300000.00, '2024-01-15', '华东'),
    ('SO2025010002', 3, '企业交换机S8', '网络设备', 80,  640000.00, '2025-01-20', '华南'),
    ('SO2025020002', 3, '企业交换机S8', '网络设备', 95,  760000.00, '2025-02-20', '华南'),
    ('SO2025030002', 3, '企业交换机S8', '网络设备', 110, 880000.00, '2025-03-20', '华南');

-- 库存演示数据（含库存赤字）
INSERT INTO `biz_inventory` (`dept_id`, `product_name`, `category`, `stock_qty`, `safety_stock`, `warehouse`, `stat_date`) VALUES
    (4, '智能路由器X1', '网络设备', 30,  100, '华东中心仓', '2025-03-31'),
    (4, '企业交换机S8', '网络设备', 200, 120, '华南中心仓', '2025-03-31'),
    (4, '光模块M2',    '网络设备', 5,   50,  '华东中心仓', '2025-03-31');
