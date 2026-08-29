package com.enterprise.agent.common.aspect;

import cn.hutool.json.JSONUtil;
import jakarta.servlet.http.HttpServletRequest;
import lombok.extern.slf4j.Slf4j;
import org.aspectj.lang.ProceedingJoinPoint;
import org.aspectj.lang.annotation.Around;
import org.aspectj.lang.annotation.Aspect;
import org.aspectj.lang.annotation.Pointcut;
import org.slf4j.MDC;
import org.springframework.security.core.Authentication;
import org.springframework.security.core.context.SecurityContextHolder;
import org.springframework.stereotype.Component;
import org.springframework.web.context.request.RequestContextHolder;
import org.springframework.web.context.request.ServletRequestAttributes;

import java.util.UUID;

/**
 * 全局请求日志切面。
 * <p>记录每个 Controller 请求的：链路 traceId、请求用户、URI、入参、出参、耗时。</p>
 *
 * @author enterprise-agent
 */
@Slf4j
@Aspect
@Component
public class RequestLogAspect {

    @Pointcut("execution(public * com.enterprise.agent.module..controller..*(..))")
    public void controllerPointcut() {
    }

    @Around("controllerPointcut()")
    public Object around(ProceedingJoinPoint point) throws Throwable {
        long start = System.currentTimeMillis();
        String traceId = UUID.randomUUID().toString().replace("-", "").substring(0, 16);
        MDC.put("traceId", traceId);

        String uri = "-";
        String method = "-";
        ServletRequestAttributes attributes =
                (ServletRequestAttributes) RequestContextHolder.getRequestAttributes();
        if (attributes != null) {
            HttpServletRequest request = attributes.getRequest();
            uri = request.getRequestURI();
            method = request.getMethod();
        }
        String username = currentUsername();
        String args = safeJson(point.getArgs());

        log.info("==> [{}] {} {} user={} args={}", traceId, method, uri, username, args);
        try {
            Object result = point.proceed();
            long cost = System.currentTimeMillis() - start;
            log.info("<== [{}] {} {} user={} cost={}ms resp={}", traceId, method, uri, username, cost,
                    truncate(safeJson(result)));
            return result;
        } catch (Throwable ex) {
            long cost = System.currentTimeMillis() - start;
            log.error("<== [{}] {} {} user={} cost={}ms error={}", traceId, method, uri, username, cost,
                    ex.getMessage());
            throw ex;
        } finally {
            MDC.remove("traceId");
        }
    }

    private String currentUsername() {
        Authentication auth = SecurityContextHolder.getContext().getAuthentication();
        return auth == null ? "anonymous" : auth.getName();
    }

    private String safeJson(Object obj) {
        try {
            return JSONUtil.toJsonStr(obj);
        } catch (Exception e) {
            return String.valueOf(obj);
        }
    }

    /** 出参过长时截断，避免日志爆炸。 */
    private String truncate(String text) {
        if (text == null) {
            return null;
        }
        return text.length() > 2000 ? text.substring(0, 2000) + "...(truncated)" : text;
    }
}
