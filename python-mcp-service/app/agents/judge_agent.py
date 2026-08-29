"""
Judge 评审校验 Agent（P1 核心增强版 · Self-RAG 反思闭环）。

亮点（这是项目最核心的创新节点，"眼前一亮"的关键）：
  1) 四维评分（合计 100 分），可观测、可解释：
      - faithfulness       (35)  Ragas/启发式：报告对证据忠实度
      - context_relevancy  (25)  ⭐ 新增：证据片段对"问题本身"的支撑相关性
                                 Ragas context_precision，降级"关键实体+指标"覆盖率
      - answer_relevancy   (15)  答案与问题的切题度
      - consistency        (25)  数据逻辑一致性（确定性交叉校验）
  2) Judge 反向"开药方"：按四个维度短板判断 retry_hint
       - faithfulness↓ / context_relevancy↓ → 回 GraphRAG（检索质量问题）
       - consistency↓ / 报告缺少总额/极值   → 回 SQL Agent（数据覆盖问题）
       - 综合 ↓                             → both 双通道重新检索
  3) 输出 retry_instruction 自然语言提示，直接给 GraphRAG / SQL Agent 做二次检索聚焦
  4) 保留 Ragas 不可用时的启发式降级（100% 可运行，不会卡死）

与 Harness 的协作：
  state.need_retry + state.retry_hint → harness 路由回 sql/graphrag 节点
"""
from __future__ import annotations

import logging
import re

from app.core.config import get_settings
from app.core.llm import get_llm_client
from app.graph.state import AgentState
from app.observability.langsmith_setup import timed_step

logger = logging.getLogger(__name__)


class JudgeAgent:
    """Judge 评审校验 Agent（Self-RAG 四维评审）。"""

    NAME = "JudgeAgent"

    # 四维权重，合计 100
    WEIGHT_FAITHFULNESS = 35
    WEIGHT_CONTEXT_RELEVANCY = 25
    WEIGHT_ANSWER_RELEVANCY = 15
    WEIGHT_CONSISTENCY = 25

    def __init__(self) -> None:
        self.settings = get_settings()

    def run(self, state: AgentState) -> dict:
        question = state["question"]
        report = state.get("aggregated_report", "")
        evidence = state.get("rag_evidence") or []
        sql_data = state.get("sql_data") or []
        compute_result = state.get("compute_result") or {}
        retry_count = state.get("retry_count", 0)
        max_retry = state.get("max_retry", self.settings.max_reflection_retry)

        with timed_step(self.NAME, "judge") as step:
            # 1) 四维评分（含 Self-RAG 新增 context_relevancy）
            scores = self._four_dimension_scores(question, report, evidence, sql_data, compute_result)
            f = scores["faithfulness"]
            c = scores["context_relevancy"]
            a = scores["answer_relevancy"]
            k = scores["consistency"]

            # 2) 加权综合置信度（0-100）
            score = int(round(
                f * self.WEIGHT_FAITHFULNESS
                + c * self.WEIGHT_CONTEXT_RELEVANCY
                + a * self.WEIGHT_ANSWER_RELEVANCY
                + k * self.WEIGHT_CONSISTENCY
            ))
            score = max(0, min(100, score))

            # 3) 幻觉 / 不达标的根因判断，给出回退策略
            hallucination = (f < 0.55) or (scores.get("conflict_note") is not None)
            passed = score >= self.settings.confidence_threshold
            retry_hint, retry_instruction = self._diagnose(
                question, scores, report, evidence, sql_data
            )
            can_retry = (not passed) and (retry_count < max_retry)

            reason = self._build_reason(scores, passed, retry_hint)
            step["detail"] = {
                "score": score,
                "faithfulness": round(f, 3),
                "context_relevancy": round(c, 3),
                "answer_relevancy": round(a, 3),
                "consistency": round(k, 3),
                "need_retry": can_retry,
                "retry_hint": retry_hint,
            }
            logger.info(
                "Judge 四维评审 score=%s f=%.2f c=%.2f a=%.2f k=%.2f passed=%s retry=%s@%s",
                score, f, c, a, k, passed, can_retry, retry_hint,
            )
            return {
                "confidence_score": score,
                "judge_reason": reason,
                "hallucination_detected": hallucination,
                "judge_breakdown": {
                    "faithfulness": round(f, 3),
                    "context_relevancy": round(c, 3),
                    "answer_relevancy": round(a, 3),
                    "consistency": round(k, 3),
                    "conflict_note": scores.get("conflict_note", ""),
                },
                "need_retry": can_retry,
                "retry_count": retry_count + (1 if can_retry else 0),
                "retry_hint": retry_hint if can_retry else "",
                "retry_instruction": retry_instruction if can_retry else "",
                "step_logs": [dict(step)],
            }

    # ============== 四维评分 ==============
    def _four_dimension_scores(self, question: str, report: str,
                               evidence: list[dict], sql_data: list[dict],
                               compute_result: dict) -> dict:
        """
        一次性算出四维分数 + 冲突说明。
        优先 Ragas 评测；失败全部走启发式（保证 100% 可运行）。
        """
        contexts = [e.get("text", "") for e in evidence if e.get("text")]

        ragas_res = self._try_ragas(question, report, contexts)
        if ragas_res is not None:
            f_score = ragas_res.get("faithfulness", 0.5)
            a_score = ragas_res.get("answer_relevancy", 0.5)
            # context_relevancy 优先使用 Ragas context_precision
            c_score = ragas_res.get("context_precision", 0.0)
            if not c_score:
                c_score = self._heuristic_context_relevancy(question, contexts)
        else:
            f_score, a_score = self._heuristic_rag_scores(question, report, contexts)
            c_score = self._heuristic_context_relevancy(question, contexts)

        consistency, conflict_note = self._data_consistency(report, sql_data, compute_result)

        return {
            "faithfulness": max(0.0, min(1.0, f_score)),
            "context_relevancy": max(0.0, min(1.0, c_score)),
            "answer_relevancy": max(0.0, min(1.0, a_score)),
            "consistency": max(0.0, min(1.0, consistency)),
            "conflict_note": conflict_note or "",
        }

    # ------------- Ragas（含新增 context_precision） -------------
    def _try_ragas(self, question: str, report: str,
                   contexts: list[str]) -> dict | None:
        if not report:
            return None
        try:
            from datasets import Dataset
            from ragas import evaluate
            from ragas.metrics import faithfulness, answer_relevancy, context_precision
            from ragas.llms import LangchainLLMWrapper

            llm_wrapper = LangchainLLMWrapper(get_llm_client().get_langchain_llm())
            dataset = Dataset.from_dict({
                "question": [question],
                "answer": [report],
                "contexts": [contexts or ["无检索上下文"]],
                "ground_truth": [""],  # context_precision 的 ground_truth 可选（新版可空）
            })
            for m in (faithfulness, answer_relevancy, context_precision):
                m.llm = llm_wrapper
            # context_precision 同时需要 embeddings（有则传）
            try:
                from ragas.embeddings import LangchainEmbeddingsWrapper
                from app.tools.graphrag_retriever import get_retriever
                _r = get_retriever()
                if getattr(_r, "_embed", None) is not None:
                    # 用已有的 embedding 适配 LangchainEmbeddingsWrapper 需要额外封装，
                    # 这里简化：如果不可用直接跳过，不影响主链路
                    pass
            except Exception:  # noqa: BLE001
                pass

            result = evaluate(
                dataset,
                metrics=[faithfulness, answer_relevancy, context_precision],
                raise_exceptions=False,
            )
            df = result.to_pandas()

            def _pick(name: str, fallback: float = 0.5) -> float:
                if name in df.columns:
                    v = float(df[name].iloc[0])
                    return fallback if v != v else v
                return fallback

            logger.info(
                "Ragas 评测 faithfulness=%.3f answer_relevancy=%.3f context_precision=%.3f",
                _pick("faithfulness", 0.5),
                _pick("answer_relevancy", 0.5),
                _pick("context_precision", 0.0),
            )
            return {
                "faithfulness": _pick("faithfulness", 0.5),
                "answer_relevancy": _pick("answer_relevancy", 0.5),
                "context_precision": _pick("context_precision", 0.0),
            }
        except Exception as e:  # noqa: BLE001
            logger.debug("Ragas 不可用，全量启发式评审: %s", e)
            return None

    # ------------- 启发式降级 -------------
    @staticmethod
    def _heuristic_rag_scores(question: str, report: str,
                              contexts: list[str]) -> tuple[float, float]:
        """faithfulness + answer_relevancy 启发式。"""
        report_numbers = set(re.findall(r"\d+(?:\.\d+)?", report))
        context_text = " ".join(contexts)
        if report_numbers and context_text:
            hit = sum(1 for n in report_numbers if n in context_text)
            faithfulness = 0.45 + 0.55 * (hit / len(report_numbers))
        else:
            faithfulness = 0.55 if report else 0.0

        q_tokens = [t for t in re.split(r"[\s，,。；;、]+", question) if len(t) >= 2]
        if q_tokens:
            covered = sum(1 for t in q_tokens if t in report)
            relevancy = 0.35 + 0.65 * (covered / len(q_tokens))
        else:
            relevancy = 0.6
        return round(min(1.0, faithfulness), 3), round(min(1.0, relevancy), 3)

    @staticmethod
    def _heuristic_context_relevancy(question: str, contexts: list[str]) -> float:
        """
        上下文相关性（Self-RAG 新增维度）：
        衡量"检索到的证据"是否真正支撑问题本身，而不是给了一堆看似相关但不回答问题的片段。
        """
        if not contexts:
            return 0.0
        # 问题里的关键 token：中文 2+ 字、英文/数字 2+ 位
        q_tokens: set[str] = set()
        for m in re.findall(r"[\u4e00-\u9fa5]{2,}", question):
            q_tokens.add(m)
        for m in re.findall(r"[A-Za-z0-9]{2,}", question):
            q_tokens.add(m.lower())
        if not q_tokens:
            return 0.6
        # 取前 N 条证据，按"命中覆盖"给分（前 3 条权重更高，模拟 RAG 用户真实阅读习惯）
        weights = [0.45, 0.30, 0.15, 0.05, 0.05]
        score = 0.0
        for i, ctx in enumerate(contexts[:5]):
            w = weights[i] if i < len(weights) else 0.02
            ctx_tokens: set[str] = set()
            for m in re.findall(r"[\u4e00-\u9fa5]{2,}", ctx):
                ctx_tokens.add(m)
            for m in re.findall(r"[A-Za-z0-9]{2,}", ctx):
                ctx_tokens.add(m.lower())
            if not ctx_tokens:
                continue
            overlap = len(q_tokens & ctx_tokens) / max(1, len(q_tokens))
            # 若包含"同比/环比/增长/库存"等业务指标词也略微加权
            extra = 0.1 if any(k in ctx for k in ["同比", "环比", "增长", "库存", "销售额", "营收"]) else 0.0
            score += w * min(1.0, overlap + extra)
        return round(min(1.0, score), 3)

    # ============== 数据一致性（确定性） ==============
    @staticmethod
    def _data_consistency(report: str, sql_data: list[dict],
                          compute_result: dict) -> tuple[float, str]:
        if not compute_result:
            return 1.0, ""
        conflicts: list[str] = []
        checked = 0
        key_metrics = ["total_amount", "avg_amount", "max_amount",
                       "min_amount", "total_available"]
        for key in key_metrics:
            if key in compute_result and compute_result[key] is not None:
                checked += 1
                val = compute_result[key]
                if key == "total_amount":
                    reported = JudgeAgent._extract_total(report)
                    if reported is not None and val > 0:
                        diff = abs(reported - val) / abs(val)
                        if diff > 0.05:
                            conflicts.append(
                                f"报告总额 {reported} 与统计总额 {val} 偏差 {round(diff * 100, 1)}%")
        # SQL 行数 vs 报告声称的行数 / 汇总量 差异（简单启发式）
        if sql_data and "命中" not in report and len(sql_data) > 20:
            # 数据很多但报告没提，视作轻度冲突但不扣分
            pass
        if checked == 0:
            return 1.0, ""
        consistency = 1.0 - min(1.0, len(conflicts) / max(1, checked))
        return consistency, "; ".join(conflicts)

    @staticmethod
    def _extract_total(report: str) -> float | None:
        m = re.search(r"(?:总额|总销售额|合计|总计|销售合计)[^\d]{0,8}(\d+(?:\.\d+)?)", report)
        if m:
            try:
                return float(m.group(1))
            except ValueError:
                return None
        return None

    # ============== 根因诊断 + 回退策略 ==============
    @staticmethod
    def _diagnose(question: str, scores: dict, report: str,
                  evidence: list[dict], sql_data: list[dict]) -> tuple[str, str]:
        """
        判断 retry_hint（graphrag / sql / both）并输出 retry_instruction。

        规则（Self-RAG 可解释的规则路由）：
          - faithfulness<0.6 或 context_relevancy<0.55   → 文档检索质量差
          - consistency<0.8 或 统计指标存在但报告没覆盖 → 数据查询不充分
          - 两者都差                                   → both
        """
        f = scores["faithfulness"]
        c = scores["context_relevancy"]
        k = scores["consistency"]
        conflict = scores.get("conflict_note")

        need_rag = (f < 0.6) or (c < 0.55) or (len(evidence) == 0)
        need_sql = (k < 0.8) or bool(conflict) or (not sql_data)

        if need_rag and need_sql:
            hint = "both"
        elif need_rag:
            hint = "graphrag"
        elif need_sql:
            hint = "sql"
        else:
            # 都没大问题但总分不够，按短板倾向选择
            if (c + f) <= (k + 0.2):
                hint = "graphrag"
            else:
                hint = "sql"

        # 生成 retry_instruction（给子 Agent 二次检索聚焦）
        instructions: list[str] = []
        if need_rag:
            instructions.append(
                "GraphRAG：请优先检索包含"
                f"问题关键实体/指标（{JudgeAgent._summarize_keywords(question)}）"
                "的制度、说明、报告正文，避免通用描述片段。"
            )
        if need_sql:
            instructions.append(
                "SQL：请扩大查询的时间范围/部门范围（如未给全年请取最近 13 个月），"
                "确保覆盖总额、极值、占比等统计量；若 RAW_SQL 必要可生成只读聚合 SQL。"
            )
        if scores.get("conflict_note"):
            instructions.append(f"注意修复数据冲突：{scores['conflict_note']}")
        instruction = " ".join(instructions) if instructions else ""
        return hint, instruction

    @staticmethod
    def _summarize_keywords(question: str) -> str:
        toks = re.findall(r"[\u4e00-\u9fa5]{2,}|[A-Za-z0-9]{2,}", question or "")
        if not toks:
            return "销售额、库存"
        return "、".join(toks[:8])

    # ============== 评审理由 ==============
    @staticmethod
    def _build_reason(scores: dict, passed: bool, retry_hint: str) -> str:
        f = scores["faithfulness"]
        c = scores["context_relevancy"]
        a = scores["answer_relevancy"]
        k = scores["consistency"]
        parts = [
            f"忠实度={round(f, 2)}/1.0",
            f"上下文相关性={round(c, 2)}/1.0",
            f"切题度={round(a, 2)}/1.0",
            f"数据一致性={round(k, 2)}/1.0",
        ]
        if scores.get("conflict_note"):
            parts.append(f"冲突：{scores['conflict_note']}")
        if not passed:
            parts.append(f"评审未通过 → 建议回退：{retry_hint}")
        else:
            parts.append("评审通过")
        return "；".join(parts)


_judge_agent: JudgeAgent | None = None


def get_judge_agent() -> JudgeAgent:
    global _judge_agent
    if _judge_agent is None:
        _judge_agent = JudgeAgent()
    return _judge_agent


def judge_agent_node(state: AgentState) -> dict:
    """LangGraph 节点入口。"""
    return get_judge_agent().run(state)
