package com.enterprise.agent.common.exception;

import com.enterprise.agent.common.response.ResultCode;
import lombok.Getter;

/**
 * 业务异常。所有可预期的业务错误统一抛出该异常，由全局异常处理器捕获转换为统一返回体。
 *
 * @author enterprise-agent
 */
@Getter
public class BusinessException extends RuntimeException {

    private final int code;

    public BusinessException(ResultCode resultCode) {
        super(resultCode.getMessage());
        this.code = resultCode.getCode();
    }

    public BusinessException(ResultCode resultCode, String message) {
        super(message);
        this.code = resultCode.getCode();
    }

    public BusinessException(int code, String message) {
        super(message);
        this.code = code;
    }
}
