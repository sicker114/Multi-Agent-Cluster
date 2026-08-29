"""
统计计算 Agent（独立子图节点）。

职责：
- 接收 SQL Agent 返回的销售 / 库存原始结构化数据
- 自动计算同比、环比、增长率、极值、占比等统计指标
- 识别销量暴跌、库存赤字等业务异常并标注风险等级
- 结果回填 state.compute_result / compute_risks

纯数值计算，不依赖 LLM，保证结果确定性与可复现（避免统计环节引入幻觉）。
严格独立入参出参：输入读取 state.sql_data，输出写入 compute_result / compute_risks。
"""
from __future__ import annotations

import logging
from typing import Any

from app.graph.state import AgentState, DataSource
from app.observability.langsmith_setup import timed_step

logger = logging.getLogger(__name__)

# 风险阈值
_SALES_DROP_THRESHOLD = -0.30      # 环比/同比下跌超 30% 视为销量暴跌
_INVENTORY_DEFICIT = 0             # 库存可用量 <= 0 视为库存赤字
_INVENTORY_WARN_RATIO = 0.2        # 可用量 / 安全库存 < 0.2 预警


class StatisticsAgent:
    """统计计算 Agent。"""

    NAME = "StatisticsAgent"

    def run(self, state: AgentState) -> dict:
        """
        执行统计计算子任务。

        :return: 需要合并回主状态的增量字段
        """
        rows = state.get("sql_data") or []
        with timed_step(self.NAME, "compute") as step:
            if not rows:
                step["detail"] = "无原始数据，跳过统计"
                return {
                    "compute_result": {},
                    "compute_risks": [],
                    "step_logs": [dict(step)],
                }
            try:
                result, risks = self._compute(rows)
                source: DataSource = {
                    "type": "computation",
                    "reference": "statistics",
                    "evidence": f"计算指标 {len(result)} 项，风险 {len(risks)} 项",
                }
                step["detail"] = {"metrics": list(result.keys()), "risks": risks}
                logger.info("统计 Agent 完成 metrics=%s risks=%s", len(result), len(risks))
                return {
                    "compute_result": result,
                    "compute_risks": risks,
                    "data_sources": [source],
                    "step_logs": [dict(step)],
                }
            except Exception as e:  # noqa: BLE001
                logger.exception("统计 Agent 异常")
                step["detail"] = f"error={e}"
                return {
                    "compute_result": {},
                    "compute_risks": [f"统计计算异常: {e}"],
                    "step_logs": [dict(step)],
                }

    # ---------------- 核心计算 ----------------
    def _compute(self, rows: list[dict]) -> tuple[dict, list[str]]:
        """根据数据字段特征，自适应计算销售 / 库存统计指标。"""
        sample = rows[0]
        keys = {k.lower() for k in sample.keys()}

        # 库存数据：含库存 / 安全库存字段
        if keys & {"available_qty", "availableqty", "stock", "safe_stock", "safestock"}:
            return self._compute_inventory(rows)
        # 销售数据：含金额 / 销售额字段
        return self._compute_sales(rows)

    def _compute_sales(self, rows: list[dict]) -> tuple[dict, list[str]]:
        """销售类指标：总额、极值、占比、同比、环比、增长率。"""
        amounts = [self._num(r, ["total_amount", "totalAmount", "amount", "sales", "sales_amount"]) for r in rows]
        amounts = [a for a in amounts if a is not None]
        risks: list[str] = []
        result: dict[str, Any] = {}

        if not amounts:
            return result, risks

        total = round(sum(amounts), 2)
        max_v = max(amounts)
        min_v = min(amounts)
        avg_v = round(total / len(amounts), 2)
        result.update({
            "type": "sales",
            "record_count": len(amounts),
            "total_amount": total,
            "max_amount": round(max_v, 2),
            "min_amount": round(min_v, 2),
            "avg_amount": avg_v,
        })

        # 占比（各记录占总额比例）
        if total > 0:
            result["ratio_distribution"] = [round(a / total, 4) for a in amounts]

        # 环比：相邻期比较（数据须按时间升序）
        if len(amounts) >= 2:
            prev, curr = amounts[-2], amounts[-1]
            mom = self._rate(curr, prev)
            result["mom_growth"] = mom
            if mom is not None and mom <= _SALES_DROP_THRESHOLD:
                risks.append(f"销量环比暴跌 {round(mom * 100, 2)}%，需重点关注")

        # 同比：跨 12 期比较（若数据足够）
        if len(amounts) >= 13:
            yoy = self._rate(amounts[-1], amounts[-13])
            result["yoy_growth"] = yoy
            if yoy is not None and yoy <= _SALES_DROP_THRESHOLD:
                risks.append(f"销量同比暴跌 {round(yoy * 100, 2)}%，触发风险预警")

        # 整体增长率（首末期）
        if len(amounts) >= 2:
            result["overall_growth"] = self._rate(amounts[-1], amounts[0])

        return result, risks

    def _compute_inventory(self, rows: list[dict]) -> tuple[dict, list[str]]:
        """库存类指标：总量、赤字识别、预警比。"""
        risks: list[str] = []
        result: dict[str, Any] = {"type": "inventory", "record_count": len(rows)}
        total_available = 0.0
        deficit_items: list[str] = []
        warn_items: list[str] = []

        for r in rows:
            name = str(r.get("product_name") or r.get("productName") or r.get("sku") or "未知商品")
            available = self._num(r, ["available_qty", "availableQty", "stock", "quantity"]) or 0.0
            safe = self._num(r, ["safe_stock", "safeStock", "safety_stock"]) or 0.0
            total_available += available
            if available <= _INVENTORY_DEFICIT:
                deficit_items.append(name)
            elif safe > 0 and (available / safe) < _INVENTORY_WARN_RATIO:
                warn_items.append(name)

        result["total_available"] = round(total_available, 2)
        result["deficit_items"] = deficit_items
        result["warn_items"] = warn_items

        if deficit_items:
            risks.append(f"库存赤字商品 {len(deficit_items)} 个：{', '.join(deficit_items[:5])}")
        if warn_items:
            risks.append(f"库存低于安全线预警商品 {len(warn_items)} 个：{', '.join(warn_items[:5])}")
        return result, risks

    # ---------------- 工具方法 ----------------
    @staticmethod
    def _num(row: dict, candidate_keys: list[str]) -> float | None:
        """从可能的多个字段名中取数值。"""
        lower_map = {k.lower(): v for k, v in row.items()}
        for key in candidate_keys:
            if key.lower() in lower_map:
                val = lower_map[key.lower()]
                try:
                    return float(val)
                except (TypeError, ValueError):
                    continue
        return None

    @staticmethod
    def _rate(curr: float, prev: float) -> float | None:
        """计算增长率 (curr - prev) / |prev|。"""
        if prev == 0:
            return None
        return round((curr - prev) / abs(prev), 4)


_stats_agent: StatisticsAgent | None = None


def get_statistics_agent() -> StatisticsAgent:
    global _stats_agent
    if _stats_agent is None:
        _stats_agent = StatisticsAgent()
    return _stats_agent


def statistics_agent_node(state: AgentState) -> dict:
    """LangGraph 节点入口。"""
    return get_statistics_agent().run(state)
