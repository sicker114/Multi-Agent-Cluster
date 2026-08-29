"""
LLM 客户端封装。

基于 OpenAI 兼容 SDK（DeepSeek/OpenAI），统一提供：
- 带超时、重试、限流处理的 chat 调用
- Token 消耗统计（用于量化记忆复用节省指标）
- LangChain ChatOpenAI 实例（供 LangGraph / Ragas 使用）
"""
from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Any

from openai import OpenAI, APITimeoutError, RateLimitError
from tenacity import retry, retry_if_exception_type, stop_after_attempt, wait_exponential

from app.core.config import get_settings
from app.core.exceptions import AgentException, ErrorCode, RetryableException

logger = logging.getLogger(__name__)


@dataclass
class TokenCounter:
    """全链路 Token 计数器。"""

    total_tokens: int = 0
    prompt_tokens: int = 0
    completion_tokens: int = 0
    call_count: int = 0
    _lock: Any = field(default=None, repr=False)

    def add(self, prompt: int, completion: int) -> None:
        self.prompt_tokens += prompt
        self.completion_tokens += completion
        self.total_tokens += prompt + completion
        self.call_count += 1


class LLMClient:
    """LLM 调用封装。"""

    def __init__(self) -> None:
        self.settings = get_settings()
        self._client = OpenAI(
            api_key=self.settings.llm_api_key,
            base_url=self.settings.llm_base_url,
            timeout=self.settings.llm_timeout,
        )

    @retry(
        retry=retry_if_exception_type(RetryableException),
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=1, max=8),
        reraise=True,
    )
    def chat(self, messages: list[dict], counter: TokenCounter | None = None,
             temperature: float | None = None) -> str:
        """
        执行 chat 调用，返回文本；对限流/超时进行指数退避重试。

        :param messages: OpenAI 消息列表
        :param counter: Token 计数器
        :param temperature: 采样温度
        :return: 模型输出文本
        """
        try:
            resp = self._client.chat.completions.create(
                model=self.settings.llm_model,
                messages=messages,
                temperature=self.settings.llm_temperature if temperature is None else temperature,
            )
            if counter is not None and resp.usage is not None:
                counter.add(resp.usage.prompt_tokens, resp.usage.completion_tokens)
            return resp.choices[0].message.content or ""
        except RateLimitError as e:
            logger.warning("LLM 限流，进入重试: %s", e)
            raise RetryableException(ErrorCode.LLM_RATE_LIMIT, str(e)) from e
        except APITimeoutError as e:
            logger.warning("LLM 超时，进入重试: %s", e)
            raise RetryableException(ErrorCode.LLM_TIMEOUT, str(e)) from e
        except Exception as e:  # noqa: BLE001
            logger.error("LLM 调用失败: %s", e)
            raise AgentException(ErrorCode.INTERNAL_ERROR, str(e)) from e

    def get_langchain_llm(self):
        """返回 LangChain ChatOpenAI，供 LangGraph 与 Ragas 复用。"""
        from langchain_openai import ChatOpenAI

        return ChatOpenAI(
            model=self.settings.llm_model,
            api_key=self.settings.llm_api_key,
            base_url=self.settings.llm_base_url,
            temperature=self.settings.llm_temperature,
            timeout=self.settings.llm_timeout,
        )


# 单例
_llm_client: LLMClient | None = None


def get_llm_client() -> LLMClient:
    global _llm_client
    if _llm_client is None:
        _llm_client = LLMClient()
    return _llm_client
