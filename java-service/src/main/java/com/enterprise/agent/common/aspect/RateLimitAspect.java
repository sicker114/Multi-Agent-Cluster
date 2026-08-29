package com.enterprise.agent.common.aspect;

import com.enterprise.agent.common.annotation.RateLimit;
import com.enterprise.agent.common.exception.BusinessException;
import com.enterprise.agent.common.response.ResultCode;
import com.enterprise.agent.config.EnterpriseProperties;
import io.github.bucket4j.Bandwidth;
import io.github.bucket4j.Bucket;
import io.github.bucket4j.Refill;
import lombok.RequiredArgsConstructor;
import org.aspectj.lang.annotation.Aspect;
import org.aspectj.lang.annotation.Before;
import org.aspectj.lang.reflect.MethodSignature;
import org.aspectj.lang.JoinPoint;
import org.springframework.security.core.Authentication;
import org.springframework.security.core.context.SecurityContextHolder;
import org.springframework.stereotype.Component;

import java.time.Duration;
import java.util.concurrent.ConcurrentHashMap;

/**
 * 接口限流切面，基于 Bucket4j 令牌桶，按 "用户 + 方法" 维度独立限流。
 *
 * @author enterprise-agent
 */
@Aspect
@Component
@RequiredArgsConstructor
public class RateLimitAspect {

    private final EnterpriseProperties properties;

    /** key = username:methodName -> 令牌桶 */
    private final ConcurrentHashMap<String, Bucket> bucketMap = new ConcurrentHashMap<>();

    @Before("@annotation(rateLimit)")
    public void before(JoinPoint joinPoint, RateLimit rateLimit) {
        int capacity = rateLimit.capacity() > 0
                ? rateLimit.capacity() : properties.getRateLimit().getCapacity();
        int refill = rateLimit.refillPerMinute() > 0
                ? rateLimit.refillPerMinute() : properties.getRateLimit().getRefillPerMinute();

        String method = ((MethodSignature) joinPoint.getSignature()).getMethod().getName();
        String key = currentUsername() + ":" + method;

        Bucket bucket = bucketMap.computeIfAbsent(key, k -> {
            Bandwidth limit = Bandwidth.classic(capacity,
                    Refill.greedy(refill, Duration.ofMinutes(1)));
            return Bucket.builder().addLimit(limit).build();
        });

        if (!bucket.tryConsume(1)) {
            throw new BusinessException(ResultCode.RATE_LIMITED);
        }
    }

    private String currentUsername() {
        Authentication auth = SecurityContextHolder.getContext().getAuthentication();
        return auth == null ? "anonymous" : auth.getName();
    }
}
