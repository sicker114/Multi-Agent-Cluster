"""
四层记忆读取工具（Python 侧）。

通过 Java /internal/memory 通道共享长期业务记忆，复用历史问答结果减少 LLM 调用开销。
当前 Redis 未接入，仅走 Java 通道；恢复 Redis 后取消下方注释即可。

记忆 key 方案与 Java MemoryManager 严格对齐：
  mem:longterm:u{userId}:qa:{md5(question)}
"""
from __future__ import annotations

import hashlib
import json
import logging
from typing import Any

from app.core.config import get_settings
from app.core.java_client import JavaCallbackClient

logger = logging.getLogger(__name__)

# Redis 未接入，注释掉直连客户端
# import redis
# _redis_client = None  # 恢复时初始化


class MemoryTool:
    """四层记忆读取工具（Redis 暂未接入，仅走 Java 通道）。"""

    def __init__(self, java_client: JavaCallbackClient | None = None) -> None:
        self.settings = get_settings()
        self.java_client = java_client or JavaCallbackClient()
        # Redis 未接入，跳过初始化
        # try:
        #     self._redis = redis.Redis(
        #         host=self.settings.redis_host,
        #         port=self.settings.redis_port,
        #         password=self.settings.redis_password or None,
        #         db=self.settings.redis_db,
        #         decode_responses=True,
        #         socket_timeout=3,
        #     )
        #     self._redis.ping()
        # except Exception as e:
        #     logger.warning("Redis 直连不可用，仅走 Java 记忆通道: %s", e)
        #     self._redis = None
        self._redis = None

    @staticmethod
    def _fingerprint(question: str) -> str:
        normalized = "".join((question or "").split())
        return hashlib.md5(normalized.encode("utf-8")).hexdigest()

    def hit_long_term(self, user_id: int, question: str) -> dict | None:
        """查询长期记忆命中：仅走 Java 通道。"""
        try:
            data = self.java_client.hit_long_term_memory(user_id, question)
            if data and data.get("hit"):
                logger.info("长期记忆命中(Java 通道) user=%s", user_id)
                return data.get("value")
        except Exception as e:  # noqa: BLE001
            logger.warning("Java 记忆通道读取失败: %s", e)
        # Redis 未接入，跳过降级
        # if self._redis is not None:
        #     key = f"mem:longterm:u{user_id}:qa:{self._fingerprint(question)}"
        #     raw = self._redis.get(key)
        #     if raw:
        #         logger.info("长期记忆命中(Redis 降级) user=%s", user_id)
        #         try:
        #             return json.loads(raw)
        #         except json.JSONDecodeError:
        #             return None
        return None

    def save_long_term(self, user_id: int, question: str, value: Any) -> None:
        """写入长期记忆（走 Java 通道，保证一致性）。"""
        try:
            self.java_client.save_long_term_memory(user_id, question, value)
        except Exception as e:  # noqa: BLE001
            logger.warning("写长期记忆失败: %s", e)

    def save_hallucination(self, user_id: int, question: str, detail: Any) -> None:
        """记录幻觉案例，供反思规避。"""
        try:
            self.java_client.save_hallucination_case(user_id, question, detail)
        except Exception as e:  # noqa: BLE001
            logger.warning("记录幻觉案例失败: %s", e)

    # ---------- 技能库（Redis 未接入，返回 None） ----------
    def get_skill(self, skill_name: str) -> Any | None:
        # Redis 未接入
        return None

    def save_skill(self, skill_name: str, template: Any) -> None:
        # Redis 未接入
        pass
