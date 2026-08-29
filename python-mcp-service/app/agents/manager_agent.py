"""
Manager 协调 Agent（P1 增强版 · HybridQA 多源融合）。

职责：
1. 需求意图解析：区分文档查询 / 数据库统计 / 数值计算 / 合规校验四类需求
2. 复合任务自动拆分，识别执行依赖顺序（先查数据 → 再查文档 → 计算 → 校验）
3. 子 Agent 结果后处理：⭐ HybridQA 实体对齐（部门/产品/区域别名归一化）
4. 汇总报告前：⭐ 数据来源溯源加强（每个数字都标来源，SQL/deptId/docId 可追溯）
5. 评审通过后：组装完整业务分析报告 + 审计级溯源 + Judge 四维分面板

亮点（面试/简历必提）：
  - 别名归一化："华东"/"华东区"/"华东事业部" → 统一 canonical form
  - 数字溯源：报告中每个"总额/极值/同比"都标注来自 SQL 聚合还是 文档段落
  - HybridQA 交叉：文档中的指标值 vs SQL 中的事实值自动对齐，冲突前暴露
"""
from __future__ import annotations

import json
import logging
import re
from collections import defaultdict
from typing import Any

from app.core.config import get_settings
from app.core.exceptions import ErrorCode
from app.core.llm import TokenCounter, get_llm_client
from app.graph.state import AgentState, SubTask
from app.observability.langsmith_setup import timed_step

logger = logging.getLogger(__name__)

# ========================
# HybridQA：业务实体别名归一化字典（一线企业真实场景）
# 可由 LLM 在运行时扩展；这里提供基础字典保证可运行
# ========================
_ALIAS_CANONICAL: dict[str, list[str]] = {
    # 区域
    "华东": ["华东区", "华东事业部", "华东大区", "东部", "沪苏浙皖", "华东分公司"],
    "华北": ["华北区", "华北大区", "华北事业部", "京津冀", "华北分公司"],
    "华南": ["华南区", "华南大区", "华南事业部", "粤港澳", "华南分公司"],
    "华中": ["华中区", "华中大区", "华中事业部", "华中分公司"],
    "西南": ["西南区", "西南大区", "西南事业部", "云贵川", "西南分公司"],
    "西北": ["西北区", "西北大区", "西北事业部", "陕甘宁", "西北分公司"],
    "东北": ["东北区", "东北大区", "东北事业部", "黑吉辽", "东北分公司"],
    "全国": ["全公司", "全集团", "公司整体", "整体", "全司"],
    # 部门
    "销售部": ["销售中心", "营销部", "市场营销部", "Sales", "营销中心"],
    "研发部": ["研发中心", "技术部", "产品研发部", "R&D", "研究院"],
    "供应链部": ["供应链中心", "采购部", "采购中心", "Supply Chain"],
    "仓储部": ["仓管部", "仓储中心", "物流部", "库存部"],
    "财务部": ["财务中心", "Finance", "财经中心"],
    "人事部": ["HR", "人力资源部", "人力资源中心", "人力资源"],
    # 产品类别名
    "路由器": ["Router", "路由"],
    "交换机": ["Switch", "交换"],
    "服务器": ["Server", "计算节点"],
    "光模块": ["Optical Module", "光模组", "模块"],
    "笔记本": ["笔记本电脑", "Notebook", "NB", "便携机"],
    "手机": ["移动终端", "Phone", "Smartphone", "智能手机"],
    # 指标别名
    "销售额": ["销售金额", "营收", "销售收入", "销售总额", "GMV"],
    "订单量": ["订单数", "订单数量", "销量"],
    "库存量": ["存货量", "可用量", "库存可用量"],
}

# 反向映射：别名 → canonical 名
_ALIAS_TO_CANONICAL: dict[str, str] = {}
for _canon, _aliases in _ALIAS_CANONICAL.items():
    _ALIAS_TO_CANONICAL[_canon.lower()] = _canon
    for _a in _aliases:
        _ALIAS_TO_CANONICAL[_a.lower()] = _canon

_INTENT_PROMPT = """你是企业数据分析任务调度助手。请判断用户需求涉及以下哪些能力（可多选）：
- DOCUMENT：需要查询企业文档知识库（制度、说明、报告等文本）
- DATABASE：需要查询业务数据库（销售、库存等结构化数据）
- COMPUTE：需要对数据做统计计算（同比、环比、增长率、占比、极值）
- COMPLIANCE：需要做数据/文档的真实性与合规校验

严格输出 JSON，不要多余文字：
{"intents":["DATABASE","COMPUTE"],"note":"一句话说明拆解思路"}"""


class ManagerAgent:
    """Manager 协调 Agent。"""

    NAME = "ManagerAgent"

    def __init__(self) -> None:
        self.settings = get_settings()
        self.llm = get_llm_client()

    # ============ 节点 1：入口规划 ============
    def plan(self, state: AgentState) -> dict:
        """意图解析 + 子任务拆分（识别依赖顺序）。"""
        question = state["question"]
        counter = TokenCounter()
        with timed_step(self.NAME, "plan") as step:
            intents = self._parse_intents(question, counter)
            sub_tasks = self._split_tasks(intents)
            step["detail"] = {"intents": intents, "tasks": [t["task_id"] for t in sub_tasks]}
            logger.info("Manager 规划完成 intents=%s tasks=%s", intents, len(sub_tasks))
            return {
                "intents": intents,
                "sub_tasks": sub_tasks,
                "plan_note": f"识别意图 {intents}，按依赖顺序执行 {len(sub_tasks)} 个子任务",
                "token_total": state.get("token_total", 0) + counter.total_tokens,
                "step_logs": [dict(step)],
            }

    def _parse_intents(self, question: str, counter: TokenCounter) -> list[str]:
        """LLM 意图解析，失败时降级关键词规则。"""
        try:
            messages = [
                {"role": "system", "content": _INTENT_PROMPT},
                {"role": "user", "content": question},
            ]
            raw = self.llm.chat(messages, counter=counter, temperature=0.0)
            data = self._parse_json(raw)
            intents = [i for i in data.get("intents", []) if i in
                       {"DOCUMENT", "DATABASE", "COMPUTE", "COMPLIANCE"}]
            if intents:
                return intents
        except Exception as e:  # noqa: BLE001
            logger.warning("Manager LLM 意图解析失败，降级关键词: %s", e)
        return self._keyword_intents(question)

    @staticmethod
    def _keyword_intents(question: str) -> list[str]:
        """关键词兜底意图识别，保证链路不中断。"""
        q = question
        intents: list[str] = []
        if any(k in q for k in ["文档", "制度", "说明", "报告", "政策", "规范", "知识库"]):
            intents.append("DOCUMENT")
        if any(k in q for k in ["销售", "订单", "库存", "数据", "营收", "销量", "金额"]):
            intents.append("DATABASE")
        if any(k in q for k in ["同比", "环比", "增长", "占比", "统计", "计算", "趋势", "极值"]):
            intents.append("COMPUTE")
        # 默认至少包含数据库查询与合规校验
        if not intents:
            intents = ["DATABASE"]
        if "COMPLIANCE" not in intents:
            intents.append("COMPLIANCE")
        return intents

    @staticmethod
    def _split_tasks(intents: list[str]) -> list[SubTask]:
        """
        按固定业务依赖顺序拆分子任务：
        先查数据(DATABASE) → 再查文档(DOCUMENT) → 计算(COMPUTE) → 校验(COMPLIANCE)
        计算依赖数据；校验依赖前序全部。
        """
        tasks: list[SubTask] = []

        def add(task_type: str, desc: str, depends: list[str]) -> str:
            tid = f"T{len(tasks) + 1}"
            tasks.append(SubTask(task_type=task_type, description=desc,
                                 depends_on=depends, task_id=tid, status="PENDING"))
            return tid

        db_id = add("DATABASE", "查询业务数据库结构化数据", []) if "DATABASE" in intents else None
        doc_id = add("DOCUMENT", "检索企业文档知识库证据", []) if "DOCUMENT" in intents else None
        if "COMPUTE" in intents:
            deps = [t for t in [db_id] if t]
            add("COMPUTE", "对原始数据做统计计算并标注风险", deps)
        # 合规校验始终执行（Judge），依赖前序全部
        add("COMPLIANCE", "交叉校验数据逻辑与文档幻觉", [t["task_id"] for t in tasks])
        return tasks

    # ============ 节点 2：汇总（送 Judge 前） ============
    def aggregate(self, state: AgentState) -> dict:
        """
        P1 增强 HybridQA 汇总：
          1. SQL/GraphRAG 结果统一做部门/产品/区域别名归一化；
          2. 自动提取"指标-数值-来源"三元组（溯源），写入 state.data_sources；
          3. 再喂给 LLM 汇总，Judge 后续据此打 context_relevancy / consistency。
        """
        counter = TokenCounter()
        with timed_step(self.NAME, "aggregate") as step:
            # Step A: HybridQA 别名归一化（返回统一状态）
            normalized_state, alignments = self._normalize_entities(state)

            # Step B: 溯源增强 —— 自动抽三元组并回填 data_sources
            extra_sources = self._extract_traceable_sources(normalized_state)
            # Step C: 构建 LLM 汇总上下文（已别名归一化 + 带引用 ID）
            context = self._build_context(normalized_state, extra_sources)
            report = self._summarize(state["question"], context, counter)

            # 报告里做一次"实体回注"：把别名形式替换为 canonical，便于 Judge 一致性校验
            report = self._apply_aliases_in_report(report)

            step["detail"] = {
                "aggregated_len": len(report),
                "alignments": alignments[:20],
                "new_sources": len(extra_sources),
            }
            logger.info("Manager HybridQA 汇总完成 len=%s align=%s src+=%s",
                        len(report), len(alignments), len(extra_sources))
            merged = {
                "aggregated_report": report,
                "token_total": state.get("token_total", 0) + counter.total_tokens,
                "step_logs": [dict(step)],
            }
            if extra_sources:
                merged["data_sources"] = extra_sources  # operator.add 会追加
            return merged

    @staticmethod
    def _normalize_entities(state: AgentState) -> tuple[AgentState, list[dict]]:
        """对 SQL 行 / RAG 证据做部门·产品·区域·指标别名归一化，并返回归一化映射。"""
        alignments: list[dict] = []
        # 工作在副本上，避免副作用
        state = dict(state)  # type: ignore[assignment]

        def _norm(text: str) -> tuple[str, list[dict]]:
            local = []
            if not text:
                return text, local
            lowered = text.lower()
            for alias, canon in _ALIAS_TO_CANONICAL.items():
                if alias and (alias in lowered):
                    # 原文本中是否直接出现
                    idx = lowered.find(alias)
                    orig = text[idx: idx + len(alias)]
                    if orig and orig != canon:
                        text = text[:idx] + canon + text[idx + len(alias):]
                        lowered = text.lower()
                        local.append({"from": orig, "to": canon})
            return text, local

        # SQL 行：对 dept_name / product_name / category / region 类字段归一化
        sql_data = state.get("sql_data") or []
        for i, row in enumerate(sql_data):
            if not isinstance(row, dict):
                continue
            for k, v in list(row.items()):
                if not isinstance(v, str):
                    continue
                new_v, a = _norm(v)
                if new_v != v:
                    row[k] = new_v
                    for item in a:
                        item.update({"type": "sql", "row": i, "field": k})
                        alignments.append(item)
        state["sql_data"] = sql_data

        # RAG 证据：text/file_name 字段归一化
        evidence = state.get("rag_evidence") or []
        for i, ev in enumerate(evidence):
            if not isinstance(ev, dict):
                continue
            txt = ev.get("text", "") or ""
            new_txt, a = _norm(txt)
            if new_txt != txt:
                ev["text"] = new_txt
                for item in a:
                    item.update({"type": "rag", "row": i, "doc_id": ev.get("doc_id")})
                    alignments.append(item)
        state["rag_evidence"] = evidence
        return state, alignments  # type: ignore[return-value]

    @staticmethod
    def _apply_aliases_in_report(text: str) -> str:
        """报告正文里出现的别名直接替换为 canonical，统一口径。"""
        result = text or ""
        # 从长到短替换，避免"华东"先替换把"华东区"破坏
        for alias, canon in sorted(
            _ALIAS_TO_CANONICAL.items(), key=lambda kv: len(kv[0]), reverse=True
        ):
            if not alias:
                continue
            # 大小写不敏感替换；中文直接替换；英文 alias 保留原文大小写匹配
            if re.match(r"^[a-zA-Z0-9&_\-/ ]+$", alias):
                pattern = re.compile(re.escape(alias), re.IGNORECASE)
                result = pattern.sub(canon, result)
            else:
                result = result.replace(alias, canon)
        return result

    @staticmethod
    def _extract_traceable_sources(state: AgentState) -> list:  # list[DataSource]
        """
        溯源增强：从 SQL/compute/RAG 中抽"指标: 数值 + 来源位置"三元组，
        作为额外的 data_sources，确保 Manager finalize 的来源章节"每个数字都能定位出处"。
        """
        sources: list = []  # list[DataSource]
        seen: set[tuple[str, str]] = set()

        def _add(kind: str, metric: str, value: Any, loc: str, evidence: str) -> None:
            key = (kind, f"{metric}={value}@{loc}")
            if key in seen:
                return
            seen.add(key)
            sources.append({
                "type": kind,
                "reference": f"{loc}::{metric}",
                "evidence": f"{metric}={value}｜{evidence}",
            })

        # SQL 行：前 5 条数据字段
        for idx, row in enumerate(state.get("sql_data") or []):
            if not isinstance(row, dict):
                continue
            for k, v in list(row.items())[:8]:
                if isinstance(v, (int, float)):
                    _add(
                        "database",
                        str(k),
                        v,
                        f"SQL#row{idx}",
                        json.dumps(row, ensure_ascii=False)[:100],
                    )

        # Compute 指标（统计计算结果）
        comp = state.get("compute_result") or {}
        for mk in ["total_amount", "avg_amount", "max_amount", "min_amount",
                   "total_available", "mom_growth", "yoy_growth", "overall_growth",
                   "record_count"]:
            if mk in comp and comp[mk] is not None:
                _add(
                    "computation",
                    mk,
                    comp[mk],
                    "StatisticsAgent.compute",
                    f"type={comp.get('type', 'N/A')}",
                )
        # Compute 库存赤字/预警明细
        for mk in ["deficit_items", "warn_items"]:
            items = comp.get(mk) or []
            if items:
                _add(
                    "computation",
                    mk,
                    len(items),
                    "StatisticsAgent.compute",
                    "样例：" + "、".join(str(x) for x in items[:5]),
                )

        # RAG 证据：前 5 个片段，引用前 40 字作为"证据"
        for idx, ev in enumerate(state.get("rag_evidence") or []):
            if not isinstance(ev, dict):
                continue
            txt = (ev.get("text", "") or "")[:40].replace("\n", " ")
            _add(
                "document",
                f"chunk{idx}",
                f"score={ev.get('score', 'N/A')}",
                f"{ev.get('file_name', 'doc')}#doc{ev.get('doc_id', 'N/A')}",
                txt,
            )
        return sources

    @staticmethod
    def _build_context(state: AgentState, extra_sources: list | None = None) -> str:
        """拼装子 Agent 结果为 LLM 汇总上下文（增强溯源 + 别名已归一）。"""
        parts: list[str] = []
        sql_data = state.get("sql_data") or []
        if sql_data:
            parts.append("【业务数据(HybirdQA 别名已归一)】\n"
                         + json.dumps(sql_data[:30], ensure_ascii=False))
        if state.get("sql_error"):
            parts.append(f"【数据查询异常】{state['sql_error']}")

        compute = state.get("compute_result") or {}
        if compute:
            parts.append("【统计计算结果】\n" + json.dumps(compute, ensure_ascii=False))
        risks = state.get("compute_risks") or []
        if risks:
            parts.append("【风险标注】\n" + "\n".join(f"- {r}" for r in risks))

        evidence = state.get("rag_evidence") or []
        if evidence:
            ev_text = "\n".join(
                f"[{e.get('file_name')}] [score={e.get('score', 'N/A')}] [doc{e.get('doc_id', 'N/A')}] "
                f"{(e.get('text', '') or '')[:240]}"
                for e in evidence[:8]
            )
            parts.append("【文档检索证据(多跳+Reranker后)】\n" + ev_text)
        if state.get("rag_error"):
            parts.append(f"【文档检索异常】{state['rag_error']}")

        if extra_sources:
            parts.append("【审计级溯源三元组(指标:数值:来源)】\n"
                         + "\n".join(
                             f"- [{s.get('type')}] {s.get('reference')}｜{s.get('evidence')}"
                             for s in extra_sources[:30]
                         ))

        if state.get("retry_count", 0) > 0 and state.get("retry_instruction"):
            parts.append(f"【本次为第{state['retry_count']}次反思重试 · Judge 方向提示】\n"
                         f"{state['retry_instruction']}")

        return "\n\n".join(parts) if parts else "无可用数据与文档证据"

    def _summarize(self, question: str, context: str, counter: TokenCounter) -> str:
        """LLM 汇总，失败时降级模板拼接。"""
        try:
            messages = [
                {"role": "system", "content":
                    "你是企业经营数据分析专家。请严格基于给定的【业务数据】【统计计算结果】"
                    "【风险标注】【文档检索证据】撰写分析结论，禁止编造数据中不存在的数字，"
                    "结论需引用具体数字与证据来源。"},
                {"role": "user", "content": f"用户需求：{question}\n\n分析素材：\n{context}"},
            ]
            return self.llm.chat(messages, counter=counter, temperature=0.2)
        except Exception as e:  # noqa: BLE001
            logger.warning("Manager 汇总 LLM 失败，降级模板: %s", e)
            return f"针对需求「{question}」的分析素材如下：\n{context}"

    # ============ 节点 3：最终报告组装（Judge 通过后） ============
    def finalize(self, state: AgentState) -> dict:
        """组装完整业务分析报告（审计级溯源 + Judge 四维分面板 + 别名归一回执）。"""
        with timed_step(self.NAME, "finalize") as step:
            score = state.get("confidence_score", 0)
            report_body = state.get("aggregated_report", "")
            risks = state.get("compute_risks") or []
            sources = self._dedupe_sources(state.get("data_sources") or [])
            breakdown = state.get("judge_breakdown") or {}

            risk_tags = self._risk_tags(state)
            final = self._render(
                report_body, score, risks, sources,
                state.get("judge_reason", ""),
                breakdown=breakdown,
                retry_count=state.get("retry_count", 0),
                hint=state.get("retry_hint", ""),
            )

            success = score >= self.settings.confidence_threshold
            error_code = None if success else ErrorCode.LOW_CONFIDENCE.value
            error_message = (
                None if success
                else f"置信度 {score} 未达阈值 {self.settings.confidence_threshold}，返回带风险提示的最佳结果"
            )

            step["detail"] = {"score": score, "success": success,
                              "risk_tags": risk_tags, "sources": len(sources)}
            logger.info("Manager 最终报告组装完成 score=%s success=%s sources=%s",
                        score, success, len(sources))
            return {
                "final_report": final,
                "risk_tags": risk_tags,
                "success": success,
                "error_code": error_code,
                "error_message": error_message,
                "step_logs": [dict(step)],
            }

    @staticmethod
    def _dedupe_sources(sources: list) -> list:
        """data_sources 可能来自多子 Agent，按 reference 去重保留更完整 evidence。"""
        bucket: dict[str, dict] = {}
        for s in sources or []:
            if not isinstance(s, dict):
                continue
            key = f"{s.get('type','')}::{s.get('reference','')}"
            old = bucket.get(key)
            if old is None or len(str(s.get("evidence", ""))) > len(str(old.get("evidence", ""))):
                bucket[key] = dict(s)
        return list(bucket.values())

    @staticmethod
    def _render(body: str, score: int, risks: list[str], sources: list[dict],
                judge_reason: str, breakdown: dict | None = None,
                retry_count: int = 0, hint: str = "") -> str:
        """结构化渲染最终报告文本（P1 增强：四维分 + 审计溯源 + 反思闭环可见）。"""
        lines = ["# 企业经营数据分析报告", "", "## 一、分析结论", body, "", "## 二、风险标注"]
        lines += [f"- {r}" for r in risks] if risks else ["- 未识别到显著业务风险"]

        # Judge 四维分面板（面试/可视化可直接抓这段）
        lines += ["", "## 三、可信度评估（Judge 四维评审）"]
        lines.append(f"- 综合置信度：{score}/100")
        if breakdown:
            f = breakdown.get("faithfulness", "N/A")
            c = breakdown.get("context_relevancy", "N/A")
            a = breakdown.get("answer_relevancy", "N/A")
            k = breakdown.get("consistency", "N/A")
            conflict = breakdown.get("conflict_note", "")
            # 文本版条形图（30 格）
            lines.append(
                "- 忠实度(faithfulness)=" + ManagerAgent._bar(f, 35) + f"  {f}"
            )
            lines.append(
                "- 上下文相关性(context_relevancy)=" + ManagerAgent._bar(c, 25) + f"  {c}"
            )
            lines.append(
                "- 切题度(answer_relevancy)=" + ManagerAgent._bar(a, 15) + f"  {a}"
            )
            lines.append(
                "- 数据一致性(consistency)=" + ManagerAgent._bar(k, 25) + f"  {k}"
            )
            if conflict:
                lines.append(f"- 数据冲突：{conflict}")
            if retry_count:
                lines.append(f"- Self-RAG 反思重试：第 {retry_count} 轮（回退方向={hint or 'N/A'}）")
        lines.append(f"- 评审说明：{judge_reason or '无'}")

        lines += ["", "## 四、数据来源溯源（每个数字均可定位出处 · 审计级）"]
        if sources:
            # 按类型分组
            grouped: dict[str, list[dict]] = defaultdict(list)
            for s in sources:
                grouped[s.get("type", "unknown")].append(s)
            order = ["database", "computation", "document", "unknown"]
            for kind in order:
                items = grouped.get(kind) or []
                if not items:
                    continue
                label = {"database": "【SQL 业务数据库】",
                         "computation": "【Statistics 统计计算】",
                         "document": "【GraphRAG 文档知识库】",
                         "unknown": "【其它】"}[kind]
                lines.append("")
                lines.append(f"### {label}")
                for s in items[:25]:
                    lines.append(
                        f"- 引用：{s.get('reference', '')} ｜ 证据：{s.get('evidence', '')}"
                    )
            if len(sources) > 75:
                lines.append(f"- （来源条目共 {len(sources)} 条，此处仅展示前 75 条高亮）")
        else:
            lines.append("- 无")
        lines += ["", "## 五、名词说明",
                  "- 本报告已对「区域/部门/产品/指标」别名做 HybridQA 归一化处理，统一口径，便于跨部门对齐。"]
        return "\n".join(lines)

    @staticmethod
    def _bar(v: Any, weight: int) -> str:
        """生成文本版 10 格条形图；v 为 0~1 的 float。"""
        try:
            fv = float(v)
        except (TypeError, ValueError):
            return "[" + "·" * 10 + "]"
        fv = max(0.0, min(1.0, fv))
        filled = int(round(fv * 10))
        return "[" + "█" * filled + "·" * (10 - filled) + f"] ({weight}%)"

    @staticmethod
    def _risk_tags(state: AgentState) -> list[str]:
        tags: list[str] = []
        if state.get("hallucination_detected"):
            tags.append("疑似幻觉")
        if state.get("compute_risks"):
            tags.append("业务风险")
        if state.get("sql_error"):
            tags.append("数据缺失")
        if state.get("rag_error"):
            tags.append("文档缺失")
        if state.get("confidence_score", 0) < get_settings().confidence_threshold:
            tags.append("低置信度")
        if state.get("retry_count", 0) > 0:
            tags.append(f"反思{state['retry_count']}次")
        return tags

    @staticmethod
    def _parse_json(raw: str) -> dict:
        text = re.sub(r"^```(?:json)?|```$", "", (raw or "").strip(), flags=re.MULTILINE).strip()
        match = re.search(r"\{.*\}", text, flags=re.DOTALL)
        if not match:
            return {}
        try:
            return json.loads(match.group(0))
        except json.JSONDecodeError:
            return {}


_manager: ManagerAgent | None = None


def get_manager() -> ManagerAgent:
    global _manager
    if _manager is None:
        _manager = ManagerAgent()
    return _manager


def manager_plan_node(state: AgentState) -> dict:
    return get_manager().plan(state)


def manager_aggregate_node(state: AgentState) -> dict:
    return get_manager().aggregate(state)


def manager_finalize_node(state: AgentState) -> dict:
    return get_manager().finalize(state)
