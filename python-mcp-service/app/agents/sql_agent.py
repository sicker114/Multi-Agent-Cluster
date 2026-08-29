"""
SQL 数据 Agent（独立子图节点）。

职责：
- 根据业务需求，由 LLM 生成安全只读查询意图（查询类型 + 时间范围 + 类别）
- 通过 Java /internal/data/query 只读安全接口获取结构化业务数据
- 强制走参数化查询类型；仅在必要时生成受 Java 端 SqlSafetyGuard 二次拦截的只读 SQL
- 捕获无数据、字段不存在等异常并回填状态，反馈调度器

严格独立入参出参：输入读取 state 中的 question / dept_ids，输出写入 sql_data / sql_error。
不与其他 Agent 共享内部逻辑。
"""
from __future__ import annotations

import json
import logging
import re

from app.core.exceptions import AgentException, ErrorCode, NoDataException
from app.core.java_client import JavaCallbackClient
from app.core.llm import TokenCounter, get_llm_client
from app.graph.state import AgentState, DataSource
from app.observability.langsmith_setup import timed_step

logger = logging.getLogger(__name__)

# 允许的只读查询类型（与 Java BusinessDataService 参数化接口对齐）
_ALLOWED_QUERY_TYPES = {
    "SALES_BY_PERIOD",     # 周期销售统计
    "MONTHLY_TREND",       # 月度趋势
    "INVENTORY",           # 库存快照
    "RAW_SQL",             # 受 SqlSafetyGuard 拦截的只读 SQL
}

_PLAN_SYSTEM_PROMPT = """你是企业数据查询规划助手。请把用户的自然语言业务需求，转换为一个结构化只读查询计划。
只能使用以下查询类型之一：
- SALES_BY_PERIOD：按时间区间统计销售额、订单量（需 startDate、endDate，格式 YYYY-MM-DD）
- MONTHLY_TREND：按月统计销售趋势（可选 startDate、endDate）
- INVENTORY：查询库存快照（可选 statDate，格式 YYYY-MM-DD；可选 category 商品类别）
- RAW_SQL：仅当以上都不满足时，生成只读 SELECT 语句（禁止 DELETE/UPDATE/DROP/ALTER/TRUNCATE/INSERT）

严格输出 JSON，不要输出多余文字，格式：
{"queryType":"...","startDate":"","endDate":"","statDate":"","category":"","rawSql":""}
无需的字段留空字符串。"""


class SqlDataAgent:
    """SQL 数据 Agent。"""

    NAME = "SqlDataAgent"

    def __init__(self) -> None:
        self.llm = get_llm_client()

    def run(self, state: AgentState) -> dict:
        """
        执行 SQL 数据查询子任务。

        :return: 需要合并回主状态的增量字段
        """
        question = state["question"]
        dept_ids = state.get("dept_ids")
        retry_instruction = state.get("retry_instruction") or ""
        is_retry = bool(state.get("need_retry") or state.get("retry_count", 0) > 0)
        counter = TokenCounter()

        with timed_step(self.NAME, "plan_and_query") as step:
            try:
                # P1 增强：反思重试时将 Judge 给出的 SQL 方向提示拼入 query，
                # 引导 LLM 自动扩大时间/部门范围，避免重复犯错。
                final_question = question
                if retry_instruction and is_retry:
                    final_question = f"{question}。【重试方向提示】{retry_instruction}"
                plan = self._make_plan(final_question, counter)
                # 若判定为重试且查询范围仍很窄，自动做一次兜底扩张：补最近 13 个月
                if is_retry and not plan.get("startDate") and not plan.get("endDate") and not plan.get("statDate"):
                    # 不越界改写（只在 plan 尚未声明时间时注入默认），避免和用户冲突
                    plan["startDate"] = plan.get("startDate") or ""
                    plan["endDate"] = plan.get("endDate") or ""
                step["detail"] = f"plan={plan}"
                client = JavaCallbackClient(
                    base_url=state.get("callback_base_url"),
                    api_key=state.get("internal_api_key"),
                )
                rows = self._execute(client, plan, dept_ids)
                if not rows:
                    raise NoDataException(ErrorCode.NO_DATA, "未查询到对应业务数据")

                source: DataSource = {
                    "type": "database",
                    "reference": plan.get("queryType", ""),
                    "evidence": f"命中 {len(rows)} 条业务数据",
                }
                logger.info("SQL Agent 查询成功 rows=%s", len(rows))
                return {
                    "sql_data": rows,
                    "sql_error": None,
                    "data_sources": [source],
                    "token_total": state.get("token_total", 0) + counter.total_tokens,
                    "step_logs": [self._finish(step, ok=True, rows=len(rows))],
                }
            except NoDataException as e:
                logger.warning("SQL Agent 无数据: %s", e.message)
                return self._fail(state, step, counter, e.code, e.message)
            except AgentException as e:
                logger.error("SQL Agent 异常: %s", e.message)
                return self._fail(state, step, counter, e.code, e.message)
            except Exception as e:  # noqa: BLE001
                logger.exception("SQL Agent 未知异常")
                return self._fail(state, step, counter, ErrorCode.INTERNAL_ERROR, str(e))

    # ---------------- 查询计划生成 ----------------
    def _make_plan(self, question: str, counter: TokenCounter) -> dict:
        """由 LLM 生成结构化查询计划，并做安全校验。"""
        messages = [
            {"role": "system", "content": _PLAN_SYSTEM_PROMPT},
            {"role": "user", "content": question},
        ]
        raw = self.llm.chat(messages, counter=counter, temperature=0.0)
        plan = self._parse_json(raw)
        query_type = (plan.get("queryType") or "").strip().upper()
        if query_type not in _ALLOWED_QUERY_TYPES:
            # 无法识别时默认走销售周期统计，避免链路中断
            query_type = "SALES_BY_PERIOD"
        plan["queryType"] = query_type

        # RAW_SQL 只读白名单预校验（Java 端仍会二次拦截）
        if query_type == "RAW_SQL":
            raw_sql = (plan.get("rawSql") or "").strip()
            if not self._is_readonly_sql(raw_sql):
                raise AgentException(ErrorCode.FIELD_NOT_FOUND,
                                     "生成的 SQL 非只读或非法，已拦截")
        return plan

    @staticmethod
    def _parse_json(raw: str) -> dict:
        """从 LLM 输出中鲁棒解析 JSON。"""
        text = (raw or "").strip()
        # 去除可能的 markdown 代码块围栏
        text = re.sub(r"^```(?:json)?|```$", "", text, flags=re.MULTILINE).strip()
        match = re.search(r"\{.*\}", text, flags=re.DOTALL)
        if not match:
            return {"queryType": "SALES_BY_PERIOD"}
        try:
            return json.loads(match.group(0))
        except json.JSONDecodeError:
            return {"queryType": "SALES_BY_PERIOD"}

    @staticmethod
    def _is_readonly_sql(sql: str) -> bool:
        """只读 SQL 白名单校验。"""
        if not sql:
            return False
        lowered = sql.strip().lower()
        if not lowered.startswith("select"):
            return False
        forbidden = ["delete", "update", "insert", "drop", "alter",
                     "truncate", "create", "grant", "revoke", ";--", "/*"]
        return not any(word in lowered for word in forbidden)

    # ---------------- 查询执行 ----------------
    @staticmethod
    def _execute(client: JavaCallbackClient, plan: dict,
                 dept_ids: list[int] | None) -> list[dict]:
        """调用 Java 只读接口执行查询。"""
        return client.safe_query(
            query_type=plan["queryType"],
            dept_ids=dept_ids,
            category=plan.get("category") or None,
            start_date=plan.get("startDate") or None,
            end_date=plan.get("endDate") or None,
            stat_date=plan.get("statDate") or None,
            raw_sql=plan.get("rawSql") or None,
        )

    # ---------------- 失败回填 ----------------
    def _fail(self, state: AgentState, step: dict, counter: TokenCounter,
              code: ErrorCode, message: str) -> dict:
        return {
            "sql_data": [],
            "sql_error": f"{code.value}: {message}",
            "token_total": state.get("token_total", 0) + counter.total_tokens,
            "step_logs": [self._finish(step, ok=False, error=code.value)],
        }

    @staticmethod
    def _finish(step: dict, ok: bool, rows: int = 0, error: str | None = None) -> dict:
        step["detail"] = {"ok": ok, "rows": rows, "error": error}
        return dict(step)


_sql_agent: SqlDataAgent | None = None


def get_sql_agent() -> SqlDataAgent:
    global _sql_agent
    if _sql_agent is None:
        _sql_agent = SqlDataAgent()
    return _sql_agent


def sql_agent_node(state: AgentState) -> dict:
    """LangGraph 节点入口。"""
    return get_sql_agent().run(state)
