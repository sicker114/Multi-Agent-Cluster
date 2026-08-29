package com.enterprise.agent.module.memory;

import cn.hutool.crypto.digest.DigestUtil;
import com.enterprise.agent.config.EnterpriseProperties;
import lombok.RequiredArgsConstructor;
import lombok.extern.slf4j.Slf4j;
import org.springframework.stereotype.Component;

import java.util.List;

/**
 * 四层分层记忆统一读写工具（Redis 暂未接入，方法空实现，功能降级但不阻塞主链路）。
 * <p>恢复 Redis 时：取消 RedisConfig 注释 + 启动类去掉 RedisAutoConfiguration 排除 +
 * application.yml 恢复 redis 配置 + 本类注入 RedisTemplate 替换空实现即可。</p>
 *
 * @author enterprise-agent
 */
@Slf4j
@Component
@RequiredArgsConstructor
public class MemoryManager {

    private final EnterpriseProperties properties;

    private String buildKey(MemoryLayer layer, Long userId, String bizKey) {
        return layer.getPrefix() + ":u" + userId + ":" + bizKey;
    }

    public void put(MemoryLayer layer, Long userId, String bizKey, Object value) {
        // Redis 未接入，空实现
    }

    @SuppressWarnings("unchecked")
    public <T> T get(MemoryLayer layer, Long userId, String bizKey, Class<T> clazz) {
        return null;
    }

    public void appendSessionHistory(Long userId, String sessionId, Object turn) {
        // Redis 未接入，空实现
    }

    public List<Object> getSessionHistory(Long userId, String sessionId) {
        return List.of();
    }

    public String questionFingerprint(String question) {
        String normalized = question == null ? "" : question.trim().replaceAll("\\s+", "");
        return DigestUtil.md5Hex(normalized);
    }

    public Object hitLongTermCache(Long userId, String question) {
        return null;
    }

    public void saveLongTermQa(Long userId, String question, Object result) {
        // Redis 未接入，空实现
    }

    public void saveHallucinationCase(Long userId, String question, Object caseDetail) {
        // Redis 未接入，空实现
    }

    public void saveSkill(String skillName, Object template) {
        // Redis 未接入，空实现
    }

    public Object getSkill(String skillName) {
        return null;
    }

    public void clearWorking(Long userId, String taskId) {
        // Redis 未接入，空实现
    }

    public void putWorking(Long userId, String taskId, Object context) {
        // Redis 未接入，空实现
    }
}
