"""
LangGraph Harness 全局状态定义。

采用 PDA（Perceive-感知 / Plan-规划 / Act-执行 / Reflect-反思）闭环状态图。
所有 Agent 节点共享该状态，通过状态字段传递中间结果与控制信号。
"""
from __future__ import annotations

import operator
from typing import Annotated, Any, Literal, TypedDict

# 任务类型：文档查询 / 数据库统计 / 数值计算 / 合规校验
TaskType = Literal["DOCUMENT", "DATABASE", "COMPUTE", "COMPLIANCE"]


class SubTask(TypedDict):
    """Manager 拆分出的子任务。"""

    task_type: TaskType
    description: str
    depends_on: list[str]   # 依赖的其他子任务 id
    task_id: str
    status: str             # PENDING / DONE / FAILED


class DataSource(TypedDict):
    """数据来源溯源条目。"""

    type: str        # document / database / computation
    reference: str
    evidence: str


class AgentState(TypedDict, total=False):
    """
    多智能体共享状态。

    LangGraph 会在各节点间传递并合并本状态；带 Annotated[..., operator.add]
    的字段为累加型（多个 Agent 追加结果）。
    """

    # ----- 输入 -----
    question: str
    user_id: int
    dept_id: int
    dept_ids: list[int] | None
    session_id: str
    callback_base_url: str
    internal_api_key: str

    # ----- Manager 规划 -----
    intents: list[str]                 # 识别到的意图集合
    sub_tasks: list[SubTask]           # 有序子任务
    plan_note: str

    # ----- 子 Agent 执行结果 -----
    rag_evidence: list[dict]           # GraphRAG 检索证据（带来源）
    rag_error: str | None
    sql_data: list[dict]               # SQL 结构化数据
    sql_error: str | None
    compute_result: dict               # 统计计算结果
    compute_risks: list[str]           # 风险标注

    # ----- 汇总 -----
    aggregated_report: str             # Manager 汇总的原始分析内容
    data_sources: Annotated[list[DataSource], operator.add]

    # ----- Judge 评审 -----
    confidence_score: int              # 0-100
    judge_reason: str
    hallucination_detected: bool
    # Self-RAG 四维评分（0~1），便于观测与后续优化
    judge_breakdown: dict

    # ----- 反思重试控制 -----
    retry_count: int
    max_retry: int
    need_retry: bool
    # retry 回退节点提示：graphrag / sql / both
    retry_hint: str
    # Judge 给出的重试方向提示（供子 Agent 二次检索使用）
    retry_instruction: str

    # ----- 观测与统计 -----
    token_total: int
    step_logs: Annotated[list[dict], operator.add]
    cache_hit: bool

    # ----- 最终输出 -----
    final_report: str
    risk_tags: list[str]
    success: bool
    error_code: str | None
    error_message: str | None


def init_state(question: str, user_id: int, dept_id: int, dept_ids: list[int] | None,
               session_id: str, callback_base_url: str, internal_api_key: str,
               max_retry: int) -> AgentState:
    """初始化状态。"""
    return AgentState(
        question=question,
        user_id=user_id,
        dept_id=dept_id,
        dept_ids=dept_ids,
        session_id=session_id,
        callback_base_url=callback_base_url,
        internal_api_key=internal_api_key,
        intents=[],
        sub_tasks=[],
        plan_note="",
        rag_evidence=[],
        rag_error=None,
        sql_data=[],
        sql_error=None,
        compute_result={},
        compute_risks=[],
        aggregated_report="",
        data_sources=[],
        confidence_score=0,
        judge_reason="",
        hallucination_detected=False,
        judge_breakdown={},
        retry_count=0,
        max_retry=max_retry,
        need_retry=False,
        retry_hint="both",
        retry_instruction="",
        token_total=0,
        step_logs=[],
        cache_hit=False,
        final_report="",
        risk_tags=[],
        success=False,
        error_code=None,
        error_message=None,
    )
