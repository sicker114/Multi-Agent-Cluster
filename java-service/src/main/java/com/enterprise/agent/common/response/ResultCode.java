package com.enterprise.agent.common.response;

import lombok.Getter;

/**
 * 全局统一错误码枚举。
 * <p>规则：1xxx 通用；2xxx 鉴权与权限；3xxx 文件；4xxx 业务数据；5xxx MCP/AI 调用。</p>
 *
 * @author enterprise-agent
 */
@Getter
public enum ResultCode {

    /* ============ 通用 ============ */
    SUCCESS(200, "操作成功"),
    SYSTEM_ERROR(1000, "系统内部错误"),
    PARAM_INVALID(1001, "请求参数不合法"),
    RATE_LIMITED(1002, "请求过于频繁，请稍后再试"),

    /* ============ 鉴权与权限 ============ */
    UNAUTHORIZED(2000, "未登录或 Token 已失效"),
    TOKEN_INVALID(2001, "Token 非法"),
    LOGIN_FAILED(2002, "用户名或密码错误"),
    ACCESS_DENIED(2003, "无访问权限"),
    DATA_SCOPE_DENIED(2004, "越权访问：无该部门数据权限"),

    /* ============ 文件 ============ */
    FILE_EMPTY(3000, "上传文件为空"),
    FILE_TYPE_NOT_SUPPORT(3001, "不支持的文件类型"),
    FILE_UPLOAD_FAILED(3002, "文件上传失败"),
    FILE_NOT_FOUND(3003, "文件不存在"),
    FILE_READ_FAILED(3004, "文件读取失败"),

    /* ============ 业务数据 ============ */
    DATA_NOT_FOUND(4000, "未查询到对应业务数据"),
    SQL_DANGEROUS(4001, "检测到高危 SQL 操作，已拦截"),
    SQL_ONLY_READONLY(4002, "仅允许只读统计查询"),

    /* ============ MCP / AI ============ */
    MCP_TIMEOUT(5000, "AI 分析服务调用超时"),
    MCP_UNAVAILABLE(5001, "AI 分析服务暂不可用（熔断降级）"),
    MCP_CALL_FAILED(5002, "AI 分析服务调用失败"),
    AI_LOW_CONFIDENCE(5003, "AI 分析结果置信度不足");

    private final int code;
    private final String message;

    ResultCode(int code, String message) {
        this.code = code;
        this.message = message;
    }
}
