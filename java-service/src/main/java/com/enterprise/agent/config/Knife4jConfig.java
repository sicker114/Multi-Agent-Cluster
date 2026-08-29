package com.enterprise.agent.config;

import io.swagger.v3.oas.annotations.OpenAPIDefinition;
import io.swagger.v3.oas.annotations.enums.SecuritySchemeType;
import io.swagger.v3.oas.annotations.info.Contact;
import io.swagger.v3.oas.annotations.info.Info;
import io.swagger.v3.oas.annotations.security.SecurityRequirement;
import io.swagger.v3.oas.annotations.security.SecurityScheme;
import org.springframework.context.annotation.Configuration;

/**
 * Knife4j / OpenAPI3 接口文档配置。声明 Bearer Token 鉴权，方便文档页调试。
 *
 * @author enterprise-agent
 */
@Configuration
@OpenAPIDefinition(
        info = @Info(
                title = "多智能体企业数字员工数据分析集群 - Java 主服务 API",
                version = "1.0.0",
                description = "承载权限、文件、业务数据库、四层记忆、MCP 客户端与业务分析接口",
                contact = @Contact(name = "enterprise-agent")
        ),
        security = @SecurityRequirement(name = "Bearer")
)
@SecurityScheme(
        name = "Bearer",
        type = SecuritySchemeType.HTTP,
        scheme = "bearer",
        bearerFormat = "JWT"
)
public class Knife4jConfig {
}
