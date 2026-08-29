package com.enterprise.agent.config;

import lombok.Data;
import org.springframework.boot.context.properties.ConfigurationProperties;
import org.springframework.context.annotation.Configuration;

/**
 * 自定义业务配置绑定，对应 application.yml 中 {@code enterprise.*} 节点。
 *
 * @author enterprise-agent
 */
@Data
@Configuration
@ConfigurationProperties(prefix = "enterprise")
public class EnterpriseProperties {

    private Jwt jwt = new Jwt();
    private FileConf file = new FileConf();
    private MemoryConf memory = new MemoryConf();
    private McpConf mcp = new McpConf();
    private RateLimitConf rateLimit = new RateLimitConf();
    private InternalConf internal = new InternalConf();

    @Data
    public static class Jwt {
        private String secret;
        private long expireSeconds = 86400;
        private String header = "Authorization";
        private String prefix = "Bearer ";
    }

    @Data
    public static class FileConf {
        private String storageType = "local";
        private String localPath = "./upload-files";
        private String allowExtensions = "pdf,doc,docx,txt";
        /** 上传完成后是否异步触发 GraphRAG 向量化入库。 */
        private boolean autoIndexOnUpload = true;
        private Minio minio = new Minio();

        @Data
        public static class Minio {
            private String endpoint;
            private String accessKey;
            private String secretKey;
            private String bucket;
        }
    }

    @Data
    public static class MemoryConf {
        private long workingTtl = 600;
        private long sessionTtl = 3600;
        private long longTermTtl = 2592000;
        private long skillTtl = 0;
        /** 长期语义记忆：命中余弦相似度阈值（0-1）。 */
        private double semanticHitThreshold = 0.92;
    }

    @Data
    public static class McpConf {
        private String toolName = "enterprise_analysis";
        /** 流式分析 MCP 工具名（server.py 注册 stream_enterprise_analysis）。 */
        private String streamToolName = "stream_enterprise_analysis";
        private long timeoutMs = 60000;
        private int maxRetry = 2;
        private long retryIntervalMs = 1500;
        private CircuitBreaker circuitBreaker = new CircuitBreaker();
        /** Python MCP 服务内部 HTTP 基座（RAG 入库 / 语义记忆 / SSE 流式 数据面调用）。
         *  Python 的 /internal/** 路由运行在 MCP 端口 +1（默认 8001），与 MCP SSE 控制面（8000）分离。 */
        private String pythonBaseUrl = "http://localhost:8001";
        /** 上传完成后通知 Python 侧 GraphRAG 入库的内部回调 URL（相对 internal 路径）。 */
        private String notifyIndexPath = "/internal/rag/index-doc";

        @Data
        public static class CircuitBreaker {
            private int failureThreshold = 5;
            private long openDurationMs = 30000;
        }
    }

    @Data
    public static class RateLimitConf {
        private int capacity = 30;
        private int refillPerMinute = 30;
    }

    @Data
    public static class InternalConf {
        private String apiKey = "internal-secret-key-2026";
        private String callbackBaseUrl = "http://localhost:8080";
        /** 内部 HTTP 调用超时毫秒。 */
        private long httpTimeoutMs = 30000;
    }
}
