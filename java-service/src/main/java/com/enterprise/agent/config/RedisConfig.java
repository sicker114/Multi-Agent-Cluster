package com.enterprise.agent.config;

/**
 * 记忆存储配置。
 * <p>当前环境无 Redis，使用 {@link LocalMemoryStore}（ConcurrentHashMap + TTL 定时清理）替代。
 * LocalMemoryStore 已标注 {@code @Component} 自动注册，无需额外 Bean 声明。</p>
 *
 * <p><b>恢复 Redis 时</b>：取消下方注释 + 删除 LocalMemoryStore +
 * 启动类去掉 RedisAutoConfiguration 排除 + application.yml 恢复 redis 配置即可。</p>
 *
 * @author enterprise-agent
 */
// @Configuration
public class RedisConfig {

    // ---- 以下为 Redis 恢复时的配置（当前注释掉，走 LocalMemoryStore） ----

    // @Bean
    // public RedisTemplate<String, Object> redisTemplate(RedisConnectionFactory factory) {
    //     RedisTemplate<String, Object> template = new RedisTemplate<>();
    //     template.setConnectionFactory(factory);
    //     StringRedisSerializer stringSerializer = new StringRedisSerializer();
    //     ObjectMapper mapper = new ObjectMapper();
    //     mapper.setVisibility(PropertyAccessor.ALL, JsonAutoDetect.Visibility.ANY);
    //     mapper.activateDefaultTyping(LaissezFaireSubTypeValidator.instance,
    //             ObjectMapper.DefaultTyping.NON_FINAL);
    //     GenericJackson2JsonRedisSerializer jsonSerializer =
    //             new GenericJackson2JsonRedisSerializer(mapper);
    //     template.setKeySerializer(stringSerializer);
    //     template.setHashKeySerializer(stringSerializer);
    //     template.setValueSerializer(jsonSerializer);
    //     template.setHashValueSerializer(jsonSerializer);
    //     template.afterPropertiesSet();
    //     return template;
    // }
}
