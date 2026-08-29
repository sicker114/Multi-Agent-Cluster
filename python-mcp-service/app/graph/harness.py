"""
LangGraph Harness 完整状态机（P1 增强版 · Self-RAG 反思重试 + 精准回退）。

图结构（PDA 感知-规划-执行-反思闭环）：
  START
    → manager_plan              (Perceive/Plan：意图解析 + 子任务拆分)
    → sql_agent                 (Act：查数据库，二次重试会读取 retry_instruction)
    → graphrag_agent            (Act：查文档知识库，二次重试会读取 retry_instruction)
    → statistics_agent          (Act：统计计算)
    → manager_aggregate         (Plan：HybridQA 实体对齐 + 溯源标注汇总)
    → judge_agent               (Reflect：四维评分 + 根因诊断，给出 retry_hint)
    → [条件边]
         need_retry=True 且 retry_hint="graphrag"  → graphrag_agent
         need_retry=True 且 retry_hint="sql"       → sql_agent
         need_retry=True 且 retry_hint="both"      → sql_agent（经 graphrag 继续）
         否则                                       → manager_finalize
    → manager_finalize
    → END

关键创新：
  - Judge 的 context_relevancy / consistency 短板 → 精确路由回最短板节点
  - 再次进入子 Agent 时自动携带 retry_instruction 聚焦检索
  - Checkpoint：SQLite 持久化每一步状态，按 thread_id (session_id) 断点恢复
"""
from __future__ import annotations

import logging
import os

from langgraph.graph import END, START, StateGraph

from app.agents.graphrag_agent import graphrag_agent_node
from app.agents.judge_agent import judge_agent_node
from app.agents.manager_agent import (
    manager_aggregate_node,
    manager_finalize_node,
    manager_plan_node,
)
from app.agents.sql_agent import sql_agent_node
from app.agents.statistics_agent import statistics_agent_node
from app.core.config import get_settings
from app.graph.state import AgentState

logger = logging.getLogger(__name__)


def _reflect_router(state: AgentState) -> str:
    """
    Judge 评审后精准路由。

    返回值：
      "retry_sql"       / "retry_graphrag" / "retry_both" — 触发反思重试闭环
      "finalize"                                            — 收尾
    """
    if not state.get("need_retry"):
        return "finalize"

    hint = (state.get("retry_hint") or "both").lower()
    logger.info("反思重试触发：第 %s 次，回退节点=%s 指令=%s",
                state.get("retry_count"), hint,
                (state.get("retry_instruction") or "")[:60])
    if hint == "sql":
        return "retry_sql"
    if hint == "graphrag":
        return "retry_graphrag"
    return "retry_both"


def _build_checkpointer():
    settings = get_settings()
    db_path = settings.checkpoint_db
    os.makedirs(os.path.dirname(db_path), exist_ok=True)
    try:
        from langgraph.checkpoint.sqlite import SqliteSaver
        import sqlite3

        conn = sqlite3.connect(db_path, check_same_thread=False)
        return SqliteSaver(conn)
    except Exception as e:  # noqa: BLE001
        logger.warning("SQLite Checkpoint 不可用，降级内存 Checkpoint: %s", e)
        from langgraph.checkpoint.memory import MemorySaver

        return MemorySaver()


def build_graph():
    graph = StateGraph(AgentState)

    # 注册节点
    graph.add_node("manager_plan", manager_plan_node)
    graph.add_node("sql_agent", sql_agent_node)
    graph.add_node("graphrag_agent", graphrag_agent_node)
    graph.add_node("statistics_agent", statistics_agent_node)
    graph.add_node("manager_aggregate", manager_aggregate_node)
    graph.add_node("judge_agent", judge_agent_node)
    graph.add_node("manager_finalize", manager_finalize_node)

    # 主链路（数据 → 文档 → 计算 → 汇总 → 校验）
    graph.add_edge(START, "manager_plan")
    graph.add_edge("manager_plan", "sql_agent")
    graph.add_edge("sql_agent", "graphrag_agent")
    graph.add_edge("graphrag_agent", "statistics_agent")
    graph.add_edge("statistics_agent", "manager_aggregate")
    graph.add_edge("manager_aggregate", "judge_agent")

    # 反思重试：根据 retry_hint 精准回退到最短板
    graph.add_conditional_edges(
        "judge_agent",
        _reflect_router,
        {
            # SQL 短板：先查库，再顺链路重走（文档/计算/汇总/Judge）
            "retry_sql": "sql_agent",
            # 文档短板：跳过 SQL（已拿过），直接重走文档链路
            "retry_graphrag": "graphrag_agent",
            # 两者都差：全链路重试（SQL 重新拉 → 重新走文档）
            "retry_both": "sql_agent",
            "finalize": "manager_finalize",
        },
    )
    graph.add_edge("manager_finalize", END)

    checkpointer = _build_checkpointer()
    compiled = graph.compile(checkpointer=checkpointer)
    logger.info(
        "LangGraph 状态图编译完成（Self-RAG 精准回退 + Checkpoint 断点恢复 + 反思重试闭环）"
    )
    return compiled


_compiled_graph = None


def get_graph():
    global _compiled_graph
    if _compiled_graph is None:
        _compiled_graph = build_graph()
    return _compiled_graph
