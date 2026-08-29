package com.enterprise.agent.common.annotation;

import java.lang.annotation.ElementType;
import java.lang.annotation.Retention;
import java.lang.annotation.RetentionPolicy;
import java.lang.annotation.Target;

/**
 * 接口限流注解。标注在 Controller 方法上，基于 Bucket4j 令牌桶按用户维度限流。
 *
 * @author enterprise-agent
 */
@Target(ElementType.METHOD)
@Retention(RetentionPolicy.RUNTIME)
public @interface RateLimit {

    /** 令牌桶容量，默认取全局配置。 */
    int capacity() default -1;

    /** 每分钟补充令牌数，默认取全局配置。 */
    int refillPerMinute() default -1;
}
