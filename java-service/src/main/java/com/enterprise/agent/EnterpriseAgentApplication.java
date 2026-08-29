package com.enterprise.agent;

import org.mybatis.spring.annotation.MapperScan;
import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.boot.autoconfigure.data.redis.RedisAutoConfiguration;
import org.springframework.boot.autoconfigure.data.redis.RedisRepositoriesAutoConfiguration;
import org.springframework.scheduling.annotation.EnableAsync;

/**
 * 多智能体企业数字员工数据分析集群 —— Java 主服务启动类。
 * <p>
 * Java 作为项目主体，承载权限、文件、业务数据库、四层记忆、MCP 客户端与对外接口；
 * Python LangGraph MCP 服务仅作为 AI 推理侧，通过标准 MCP 协议被本服务远程调用。
 *
 * <p><b>无 Redis 环境</b>：排除 Redis 自动配置，四层记忆走 {@link com.enterprise.agent.config.LocalMemoryStore}。
 * 恢复 Redis 时删除 exclude 即可。</p>
 *
 * @author enterprise-agent
 */
@EnableAsync
@MapperScan("com.enterprise.agent.mapper")
@SpringBootApplication(exclude = {
        RedisAutoConfiguration.class,
        RedisRepositoriesAutoConfiguration.class
})
public class EnterpriseAgentApplication {

    public static void main(String[] args) {
        SpringApplication.run(EnterpriseAgentApplication.class, args);
    }
}
