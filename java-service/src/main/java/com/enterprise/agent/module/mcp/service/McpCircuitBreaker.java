package com.enterprise.agent.module.mcp.service;

import com.enterprise.agent.config.EnterpriseProperties;
import lombok.RequiredArgsConstructor;
import lombok.extern.slf4j.Slf4j;
import org.springframework.stereotype.Component;

import java.util.concurrent.atomic.AtomicInteger;
import java.util.concurrent.atomic.AtomicLong;

/**
 * 轻量级熔断器。针对 MCP 调用：连续失败达到阈值后打开熔断，进入冷却期直接拒绝；
 * 冷却期结束进入半开，放行一次探测，成功则关闭，失败则重新打开。
 *
 * @author enterprise-agent
 */
@Slf4j
@Component
@RequiredArgsConstructor
public class McpCircuitBreaker {

    private final EnterpriseProperties properties;

    private enum State { CLOSED, OPEN, HALF_OPEN }

    private volatile State state = State.CLOSED;
    private final AtomicInteger failureCount = new AtomicInteger(0);
    private final AtomicLong openTimestamp = new AtomicLong(0);

    /**
     * 调用前检查是否允许通过。
     *
     * @return true 允许调用；false 熔断打开，应直接降级
     */
    public synchronized boolean allowRequest() {
        EnterpriseProperties.McpConf.CircuitBreaker conf = properties.getMcp().getCircuitBreaker();
        if (state == State.OPEN) {
            long elapsed = System.currentTimeMillis() - openTimestamp.get();
            if (elapsed >= conf.getOpenDurationMs()) {
                state = State.HALF_OPEN;
                log.warn("熔断器进入半开状态，放行一次探测请求");
                return true;
            }
            return false;
        }
        return true;
    }

    /** 调用成功回调。 */
    public synchronized void onSuccess() {
        failureCount.set(0);
        if (state != State.CLOSED) {
            log.info("熔断器恢复关闭状态");
            state = State.CLOSED;
        }
    }

    /** 调用失败回调。 */
    public synchronized void onFailure() {
        EnterpriseProperties.McpConf.CircuitBreaker conf = properties.getMcp().getCircuitBreaker();
        int failures = failureCount.incrementAndGet();
        if (state == State.HALF_OPEN || failures >= conf.getFailureThreshold()) {
            state = State.OPEN;
            openTimestamp.set(System.currentTimeMillis());
            log.error("熔断器打开：连续失败 {} 次，冷却 {}ms", failures, conf.getOpenDurationMs());
        }
    }

    public boolean isOpen() {
        return state == State.OPEN;
    }
}
