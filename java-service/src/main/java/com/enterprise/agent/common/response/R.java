package com.enterprise.agent.common.response;

import io.swagger.v3.oas.annotations.media.Schema;
import lombok.Data;

import java.io.Serializable;

/**
 * 全局统一返回体。所有 Controller 出参统一封装为该结构，便于前端解析。
 *
 * @param <T> 业务数据类型
 * @author enterprise-agent
 */
@Data
@Schema(description = "统一返回体")
public class R<T> implements Serializable {

    @Schema(description = "业务状态码，200 成功")
    private int code;

    @Schema(description = "提示信息")
    private String message;

    @Schema(description = "业务数据")
    private T data;

    @Schema(description = "服务端时间戳(ms)")
    private long timestamp;

    private R(int code, String message, T data) {
        this.code = code;
        this.message = message;
        this.data = data;
        this.timestamp = System.currentTimeMillis();
    }

    public static <T> R<T> success() {
        return new R<>(ResultCode.SUCCESS.getCode(), ResultCode.SUCCESS.getMessage(), null);
    }

    public static <T> R<T> success(T data) {
        return new R<>(ResultCode.SUCCESS.getCode(), ResultCode.SUCCESS.getMessage(), data);
    }

    public static <T> R<T> success(String message, T data) {
        return new R<>(ResultCode.SUCCESS.getCode(), message, data);
    }

    public static <T> R<T> failed(ResultCode resultCode) {
        return new R<>(resultCode.getCode(), resultCode.getMessage(), null);
    }

    public static <T> R<T> failed(ResultCode resultCode, String message) {
        return new R<>(resultCode.getCode(), message, null);
    }

    public static <T> R<T> failed(int code, String message) {
        return new R<>(code, message, null);
    }

    public boolean isSuccess() {
        return this.code == ResultCode.SUCCESS.getCode();
    }
}
