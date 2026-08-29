"""
LangSmith 全链路观测配置与步骤日志记录器。

记录每一步 Agent 思考、工具调用、执行耗时、幻觉分数，生成可视化流程日志。
即使未启用 LangSmith，也会在本地生成结构化 step_logs 追加到状态中。
"""
from __future__ import annotations

import logging
import os
import time
from contextlib import contextmanager
from typing import Any

from app.core.config import get_settings

logger = logging.getLogger(__name__)


def setup_langsmith() -> None:
    """初始化 LangSmith 环境变量（若启用）。"""
    settings = get_settings()
    if settings.langsmith_enabled and settings.langsmith_api_key:
        os.environ["LANGCHAIN_TRACING_V2"] = "true"
        os.environ["LANGCHAIN_API_KEY"] = settings.langsmith_api_key
        os.environ["LANGCHAIN_PROJECT"] = settings.langsmith_project
        os.environ["LANGCHAIN_ENDPOINT"] = settings.langsmith_endpoint
        logger.info("LangSmith 观测已启用 project=%s", settings.langsmith_project)
    else:
        logger.info("LangSmith 未启用，使用本地 step_logs 观测")


def make_step_log(agent: str, action: str, detail: Any = None,
                  cost_ms: int | None = None, extra: dict | None = None) -> dict:
    """构建一条结构化步骤日志。"""
    log = {
        "agent": agent,
        "action": action,
        "detail": _truncate(detail),
        "cost_ms": cost_ms,
        "ts": int(time.time() * 1000),
    }
    if extra:
        log.update(extra)
    logger.info("[STEP] agent=%s action=%s cost=%sms", agent, action, cost_ms)
    return log


def _truncate(detail: Any, limit: int = 500) -> Any:
    if isinstance(detail, str) and len(detail) > limit:
        return detail[:limit] + "...(truncated)"
    return detail


@contextmanager
def timed_step(agent: str, action: str):
    """
    计时上下文：yield 出可填充的 dict，退出时自动补充耗时并返回步骤日志。

    使用：
        with timed_step("SqlAgent", "query") as step:
            step["detail"] = "..."
    """
    start = time.time()
    holder: dict[str, Any] = {"agent": agent, "action": action, "detail": None}
    try:
        yield holder
    finally:
        holder["cost_ms"] = int((time.time() - start) * 1000)
        holder["ts"] = int(time.time() * 1000)
        holder["detail"] = _truncate(holder.get("detail"))
        logger.info("[STEP] agent=%s action=%s cost=%sms", agent, action, holder["cost_ms"])
