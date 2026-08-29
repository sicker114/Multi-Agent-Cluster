"""
Embedding 客户端包装。

为什么自己包装：
  LlamaIndex 的 OpenAIEmbedding 对 model 名做 enum 校验，只认标准 OpenAI 模型名
  （text-embedding-3-small 等），不认阿里云 text-embedding-v3，导致初始化即报错：
  'text-embedding-v3' is not a valid OpenAIEmbeddingModelType。

  阿里云 DashScope 兼容 OpenAI /v1/embeddings 协议，但模型名不同，因此用 openai SDK
  直接调用，绕过 LlamaIndex 的 enum 校验。对外暴露与 LlamaIndex BaseEmbedding 一致的
  get_text_embedding / get_text_embedding_batch 接口，调用方无需修改。

  DeepSeek key 不能调 OpenAI embeddings 端点（401 重试卡死 graph），因此 embedding 走
  阿里云独立 key，与 LLM 的 DeepSeek key 分开。
"""
from __future__ import annotations

import logging
from typing import Any

from openai import OpenAI

from app.core.config import get_settings

logger = logging.getLogger(__name__)


class AliyunEmbedding:
    """
    阿里云 DashScope 嵌入包装（兼容 OpenAI 协议）。

    接口对齐 LlamaIndex 的 get_text_embedding / get_text_embedding_batch，
    调用方（graphrag_retriever / semantic_memory）无需改动。
    """

    def __init__(
        self,
        model: str,
        api_key: str,
        base_url: str,
        *,
        max_retries: int = 0,
        timeout: float = 30.0,
    ) -> None:
        self._model = model
        # max_retries=0 —— 阿里云 key 错误时立即失败，不要指数退避卡死 graph.stream()
        self._client = OpenAI(
            api_key=api_key,
            base_url=base_url,
            max_retries=max_retries,
            timeout=timeout,
        )
        logger.info(
            "AliyunEmbedding 就绪 model=%s base=%s max_retries=%d",
            model, base_url, max_retries,
        )

    # ---------------- LlamaIndex 兼容接口 ----------------
    def get_text_embedding(self, text: str) -> list[float]:
        """单条文本 → 向量。"""
        if not text:
            return []
        resp = self._client.embeddings.create(model=self._model, input=text)
        return list(resp.data[0].embedding)

    def get_text_embedding_batch(self, texts: list[str]) -> list[list[float]]:
        """批量文本 → 向量列表（阿里云单次最多 25 条，自动分批）。"""
        if not texts:
            return []
        results: list[list[float]] = []
        batch_size = 25
        for i in range(0, len(texts), batch_size):
            batch = texts[i: i + batch_size]
            resp = self._client.embeddings.create(model=self._model, input=batch)
            for item in resp.data:
                results.append(list(item.embedding))
        return results

    def get_query_embedding(self, query: str) -> list[float]:
        """查询向量（与文本向量同模型，阿里云不区分）。"""
        return self.get_text_embedding(query)

    def get_general_embedding(self, text: str) -> list[float]:
        """LlamaIndex 部分代码路径调用此方法，保持兼容。"""
        return self.get_text_embedding(text)


def build_embedding_from_settings() -> Any:
    """
    根据 settings.embedding_provider 构建 Embedding；不可用返回 None（降级 BM25）。

    provider 分支：
      - openai（默认）：阿里云 DashScope 兼容 OpenAI 接口
        DeepSeek key 不能调 OpenAI embeddings 端点，因此用阿里云独立 key。
      - huggingface（离线备用）：本地 sentence-transformers 推理，无外部网络依赖。
        需额外安装 torch / sentence-transformers（requirements.txt 默认不含，按需启用）。
    """
    settings = get_settings()
    provider = (settings.embedding_provider or "openai").lower()
    try:
        if provider == "huggingface":
            from llama_index.embeddings.huggingface import HuggingFaceEmbedding
            import os as _os
            _os.environ.setdefault("HF_ENDPOINT", settings.huggingface_endpoint)
            return HuggingFaceEmbedding(
                model_name=settings.embedding_model,
                cache_folder=settings.huggingface_cache_dir,
            )
        # 默认 openai 兼容分支（阿里云 DashScope）
        return AliyunEmbedding(
            model=settings.embedding_model,
            api_key=settings.embedding_api_key,
            base_url=settings.embedding_base_url,
        )
    except Exception as e:  # noqa: BLE001
        logger.warning("Embedding 初始化失败（provider=%s）： %s", provider, e)
        return None
