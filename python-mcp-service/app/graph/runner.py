"""
分析运行器：封装 LangGraph 状态图的执行，供 MCP 工具调用。

流程：
1. 命中长期记忆 → 直接复用历史结果（Token 消耗降低的量化来源）
2. 未命中 → 初始化状态，执行状态图（含反思重试闭环 + Checkpoint 断点恢复）
3. 汇总量化指标（token_total / confidence / retry_count / step_logs）
4. 达标结果写入长期记忆，供后续复用
"""
from __future__ import annotations

import logging
import time
import uuid

from app.core.config import get_settings
from app.graph.harness import get_graph
from app.graph.state import init_state
from app.memory.memory_tool import MemoryTool
from app.observability.langsmith_setup import make_step_log

logger = logging.getLogger(__name__)


class AnalysisRunner:
    """企业数据分析运行器。"""

    def __init__(self) -> None:
        self.settings = get_settings()
        self.memory = MemoryTool()

    def analyze(self, question: str, user_id: int, dept_id: int,
                dept_ids: list[int] | None, session_id: str | None,
                callback_base_url: str | None, internal_api_key: str | None) -> dict:
        """
        执行一次完整业务分析。

        :return: 结构化分析结果（供 Java 侧接收）
        """
        start = time.time()
        session_id = session_id or str(uuid.uuid4())

        # 1) 长期记忆命中 → 复用
        cached = self.memory.hit_long_term(user_id, question)
        if cached:
            logger.info("命中长期记忆，直接复用历史结果 user=%s", user_id)
            cached = dict(cached)
            cached["cache_hit"] = True
            cached["cost_ms"] = int((time.time() - start) * 1000)
            return cached

        # 2) 初始化状态并执行状态图
        state = init_state(
            question=question,
            user_id=user_id,
            dept_id=dept_id,
            dept_ids=dept_ids,
            session_id=session_id,
            callback_base_url=callback_base_url or self.settings.java_callback_base_url,
            internal_api_key=internal_api_key or self.settings.internal_api_key,
            max_retry=self.settings.max_reflection_retry,
        )

        graph = get_graph()
        # thread_id 绑定 session_id，实现 Checkpoint 断点恢复
        config = {"configurable": {"thread_id": session_id}}
        try:
            final_state = graph.invoke(state, config=config)
        except Exception as e:  # noqa: BLE001
            logger.exception("状态图执行失败")
            return self._error_result(question, session_id, start, str(e))

        result = self._to_result(final_state, session_id, start)

        # 3) 达标结果写入长期记忆
        if result["success"]:
            self.memory.save_long_term(user_id, question, result)
        elif result.get("hallucination_detected"):
            self.memory.save_hallucination(user_id, question, {
                "confidence": result["confidence_score"],
                "reason": result.get("judge_reason"),
            })
        return result

    @staticmethod
    def _to_result(state: dict, session_id: str, start: float) -> dict:
        return {
            "success": bool(state.get("success")),
            "session_id": session_id,
            "report": state.get("final_report", ""),
            "confidence_score": state.get("confidence_score", 0),
            "judge_reason": state.get("judge_reason", ""),
            "hallucination_detected": bool(state.get("hallucination_detected")),
            "risk_tags": state.get("risk_tags", []),
            "data_sources": state.get("data_sources", []),
            "retry_count": state.get("retry_count", 0),
            "token_total": state.get("token_total", 0),
            "step_logs": state.get("step_logs", []),
            "error_code": state.get("error_code"),
            "error_message": state.get("error_message"),
            "cache_hit": False,
            "cost_ms": int((time.time() - start) * 1000),
        }

    @staticmethod
    def _error_result(question: str, session_id: str, start: float, err: str) -> dict:
        return {
            "success": False,
            "session_id": session_id,
            "report": f"分析执行异常：{err}",
            "confidence_score": 0,
            "judge_reason": "",
            "hallucination_detected": False,
            "risk_tags": ["执行异常"],
            "data_sources": [],
            "retry_count": 0,
            "token_total": 0,
            "step_logs": [make_step_log("AnalysisRunner", "error", err)],
            "error_code": "INTERNAL_ERROR",
            "error_message": err,
            "cache_hit": False,
            "cost_ms": int((time.time() - start) * 1000),
        }


_runner: AnalysisRunner | None = None


def get_runner() -> AnalysisRunner:
    global _runner
    if _runner is None:
        _runner = AnalysisRunner()
    return _runner
