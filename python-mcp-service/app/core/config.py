"""
全局配置模块。

从环境变量加载 LLM、Redis、Java 回调、LangSmith、GraphRAG 等配置，
供 MCP Server 与各 Agent 统一读取。所有敏感配置均可通过环境变量覆盖。
"""
from __future__ import annotations

import os
from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """服务全局配置。"""

    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    # ---------------- MCP Server ----------------
    mcp_server_name: str = "enterprise-agent-cluster"
    mcp_http_host: str = os.getenv("MCP_HTTP_HOST", "0.0.0.0")
    mcp_http_port: int = int(os.getenv("MCP_HTTP_PORT", "8000"))
    # 传输方式：stdio / sse（HTTP）
    mcp_transport: str = os.getenv("MCP_TRANSPORT", "sse")

    # ---------------- LLM（DeepSeek / OpenAI 兼容） ----------------
    llm_api_key: str = os.getenv("LLM_API_KEY", "sk-placeholder")
    llm_base_url: str = os.getenv("LLM_BASE_URL", "https://api.deepseek.com")
    llm_model: str = os.getenv("LLM_MODEL", "deepseek-chat")
    llm_temperature: float = float(os.getenv("LLM_TEMPERATURE", "0.2"))
    llm_timeout: int = int(os.getenv("LLM_TIMEOUT", "60"))
    # Embedding 模型（GraphRAG 向量化）
    # provider: openai（调外部 OpenAI 兼容 API）/ huggingface（本地推理，零外部依赖，备用）
    # 默认 openai 走阿里云 DashScope —— DeepSeek key 不能调 OpenAI embeddings 端点，
    # 阿里云 DashScope 兼容 OpenAI 接口，可直接用 OpenAIEmbedding 客户端
    embedding_provider: str = os.getenv("EMBEDDING_PROVIDER", "openai")
    # 阿里云 text-embedding-v3（1024 维，中文优化，DashScope 兼容 OpenAI 接口）
    embedding_model: str = os.getenv("EMBEDDING_MODEL", "text-embedding-v3")
    # 阿里云 DashScope 兼容 OpenAI 端点（与 LLM key 分开，避免误用）
    embedding_api_key: str = os.getenv(
        "EMBEDDING_API_KEY",
        "sk-xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx",  # 上传前替换为占位符，实际部署用环境变量
    )
    embedding_base_url: str = os.getenv(
        "EMBEDDING_BASE_URL", "https://dashscope.aliyuncs.com/compatible-mode/v1"
    )
    # HuggingFace 嵌入模型（仅 provider=huggingface 时使用，作为离线备用）
    huggingface_cache_dir: str = os.getenv("HF_HOME", os.getenv("TRANSFORMERS_CACHE", "./data/hf_cache"))
    huggingface_endpoint: str = os.getenv("HF_ENDPOINT", "https://hf-mirror.com")

    # ---------------- Java 内部回调 ----------------
    java_callback_base_url: str = os.getenv("CALLBACK_BASE_URL", "http://localhost:8080")
    internal_api_key: str = os.getenv("INTERNAL_API_KEY", "internal-secret-key-2026")
    callback_timeout: int = int(os.getenv("CALLBACK_TIMEOUT", "30"))

    # ---------------- Redis（四层记忆共享） ----------------
    redis_host: str = os.getenv("REDIS_HOST", "localhost")
    redis_port: int = int(os.getenv("REDIS_PORT", "6379"))
    redis_password: str = os.getenv("REDIS_PASSWORD", "")
    redis_db: int = int(os.getenv("REDIS_DB", "0"))

    # ---------------- GraphRAG / Chroma ----------------
    chroma_persist_dir: str = os.getenv("CHROMA_PERSIST_DIR", "./data/chroma")
    graphrag_top_k: int = int(os.getenv("GRAPHRAG_TOP_K", "5"))
    graphrag_max_hops: int = int(os.getenv("GRAPHRAG_MAX_HOPS", "2"))

    # ---------------- LangGraph Checkpoint ----------------
    checkpoint_db: str = os.getenv("CHECKPOINT_DB", "./data/checkpoints/graph_state.sqlite")

    # ---------------- LangSmith 观测 ----------------
    langsmith_enabled: bool = os.getenv("LANGCHAIN_TRACING_V2", "false").lower() == "true"
    langsmith_api_key: str = os.getenv("LANGCHAIN_API_KEY", "")
    langsmith_project: str = os.getenv("LANGCHAIN_PROJECT", "enterprise-agent-cluster")
    langsmith_endpoint: str = os.getenv("LANGCHAIN_ENDPOINT", "https://api.smith.langchain.com")

    # ---------------- Judge 评审阈值 ----------------
    confidence_threshold: int = int(os.getenv("CONFIDENCE_THRESHOLD", "60"))
    max_reflection_retry: int = int(os.getenv("MAX_REFLECTION_RETRY", "2"))


@lru_cache
def get_settings() -> Settings:
    """获取全局配置单例。"""
    return Settings()
