package com.enterprise.agent.config;

import org.springframework.ai.chat.client.ChatClient;
import org.springframework.ai.mcp.SyncMcpToolCallbackProvider;
import org.springframework.ai.tool.ToolCallbackProvider;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

/**
 * Spring AI ChatClient 配置。
 * <p>MCP Client Starter 会自动发现 Python MCP Server 注册的全部 Agent 工具，
 * 并以 {@link ToolCallbackProvider} 形式注入。此处将其绑定到 ChatClient，
 * 使 LLM 具备直接编排调用 Python 侧 Agent 工具的能力。</p>
 *
 * @author enterprise-agent
 */
@Configuration
public class ChatClientConfig {

    /**
     * 构建带 MCP 工具的 ChatClient。
     * <p>toolCallbackProvider 由 spring-ai-mcp-client-spring-boot-starter 自动装配，
     * 内部聚合了所有远程 MCP Server 暴露的工具（自动发现）。</p>
     */
    @Bean
    public ChatClient mcpChatClient(ChatClient.Builder builder,
                                    ToolCallbackProvider mcpToolCallbackProvider) {
        return builder
                .defaultSystem("""
                        你是企业数据分析助手。当需要分析企业经营数据时，必须调用已注册的
                        MCP 分析工具（enterprise_analysis）完成多智能体协作分析，
                        不得凭空编造数据，所有结论必须来源于工具返回的证据。
                        """)
                .defaultToolCallbacks(mcpToolCallbackProvider.getToolCallbacks())
                .build();
    }

    /**
     * 兜底：当上下文中未提供聚合 Provider 时，构造空 Provider，保证应用可启动。
     * <p>正常运行时会被 MCP Starter 自动装配的 Provider 覆盖。</p>
     */
    @Bean
    @org.springframework.boot.autoconfigure.condition.ConditionalOnMissingBean(ToolCallbackProvider.class)
    public ToolCallbackProvider fallbackToolCallbackProvider() {
        return new SyncMcpToolCallbackProvider(java.util.Collections.emptyList());
    }
}
