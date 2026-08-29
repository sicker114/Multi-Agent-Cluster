package com.enterprise.agent.common.exception;

import com.enterprise.agent.common.response.R;
import com.enterprise.agent.common.response.ResultCode;
import jakarta.servlet.http.HttpServletRequest;
import lombok.extern.slf4j.Slf4j;
import org.springframework.http.HttpStatus;
import org.springframework.security.access.AccessDeniedException;
import org.springframework.security.core.AuthenticationException;
import org.springframework.validation.BindException;
import org.springframework.validation.FieldError;
import org.springframework.web.bind.MethodArgumentNotValidException;
import org.springframework.web.bind.annotation.ExceptionHandler;
import org.springframework.web.bind.annotation.ResponseStatus;
import org.springframework.web.bind.annotation.RestControllerAdvice;

import java.util.stream.Collectors;

/**
 * 全局统一异常处理器。
 * <p>捕获业务异常、参数校验异常、鉴权异常、系统异常，统一转换为 {@link R} 返回体，
 * 避免异常堆栈直接暴露给前端。</p>
 *
 * @author enterprise-agent
 */
@Slf4j
@RestControllerAdvice
public class GlobalExceptionHandler {

    /** 业务异常：可预期错误。 */
    @ExceptionHandler(BusinessException.class)
    public R<Void> handleBusinessException(BusinessException e, HttpServletRequest request) {
        log.warn("业务异常 uri={} code={} msg={}", request.getRequestURI(), e.getCode(), e.getMessage());
        return R.failed(e.getCode(), e.getMessage());
    }

    /** @RequestBody 参数校验失败。 */
    @ExceptionHandler(MethodArgumentNotValidException.class)
    public R<Void> handleValidException(MethodArgumentNotValidException e) {
        String msg = e.getBindingResult().getFieldErrors().stream()
                .map(FieldError::getDefaultMessage)
                .collect(Collectors.joining("; "));
        return R.failed(ResultCode.PARAM_INVALID, msg);
    }

    /** 表单参数绑定校验失败。 */
    @ExceptionHandler(BindException.class)
    public R<Void> handleBindException(BindException e) {
        String msg = e.getBindingResult().getFieldErrors().stream()
                .map(FieldError::getDefaultMessage)
                .collect(Collectors.joining("; "));
        return R.failed(ResultCode.PARAM_INVALID, msg);
    }

    /** Spring Security 鉴权失败（未登录 / Token 无效）。 */
    @ExceptionHandler(AuthenticationException.class)
    @ResponseStatus(HttpStatus.UNAUTHORIZED)
    public R<Void> handleAuthException(AuthenticationException e) {
        log.warn("鉴权失败: {}", e.getMessage());
        return R.failed(ResultCode.UNAUTHORIZED);
    }

    /** Spring Security 权限不足。 */
    @ExceptionHandler(AccessDeniedException.class)
    @ResponseStatus(HttpStatus.FORBIDDEN)
    public R<Void> handleAccessDenied(AccessDeniedException e) {
        log.warn("权限不足: {}", e.getMessage());
        return R.failed(ResultCode.ACCESS_DENIED);
    }

    /** 兜底：未预期的系统异常。 */
    @ExceptionHandler(Exception.class)
    public R<Void> handleException(Exception e, HttpServletRequest request) {
        log.error("系统异常 uri={}", request.getRequestURI(), e);
        return R.failed(ResultCode.SYSTEM_ERROR, "系统繁忙：" + e.getMessage());
    }
}
