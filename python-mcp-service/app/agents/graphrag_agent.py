"""
GraphRAG 检索 Agent（独立子图节点）。

职责：
- 读取 Java 存储的企业文档（按部门数据权限过滤）
- 惰性构建 / 复用知识图谱向量索引（LlamaIndex + Chroma）
- 多跳关联检索，过滤无关文档片段
- 返回带来源证据的文本内容，回填 state.rag_evidence

严格独立入参出参：输入读取 state 中的 question / dept_ids / dept_id，
输出写入 rag_evidence / rag_error / data_sources。
"""
from __future__ import annotations

import logging

from app.core.exceptions import AgentException, ErrorCode, NoDataException
from app.core.java_client import JavaCallbackClient
from app.graph.state import AgentState, DataSource
from app.tools.graphrag_retriever import get_retriever
from app.observability.langsmith_setup import timed_step

logger = logging.getLogger(__name__)


class GraphRagAgent:
    """GraphRAG 检索 Agent。"""

    NAME = "GraphRagAgent"

    def run(self, state: AgentState) -> dict:
        """
        执行文档知识库检索子任务。

        :return: 需要合并回主状态的增量字段
        """
        question = state["question"]
        dept_ids = state.get("dept_ids")
        retry_instruction = state.get("retry_instruction") or ""
        is_retry = bool(state.get("need_retry") or state.get("retry_count", 0) > 0)

        with timed_step(self.NAME, "retrieve") as step:
            try:
                client = JavaCallbackClient(
                    base_url=state.get("callback_base_url"),
                    api_key=state.get("internal_api_key"),
                )
                retriever = get_retriever()

                # 1) 惰性同步：确保 Java 侧文档已建立索引（幂等 upsert）
                self._ensure_indexed(client, retriever, state.get("dept_id"))

                # 2) P1 增强：若为反思重试（Judge 给了方向），把 retry_instruction 拼入 query
                #    让 GraphRAG 三件套（改写/混合/重排）更聚焦短板检索
                final_query = question
                if retry_instruction and is_retry:
                    final_query = f"{question}；{retry_instruction}"

                # 3) 改写+混合(RRF)+Rerank+多跳 增强检索
                chunks = retriever.retrieve(final_query, dept_ids)
                if not chunks:
                    raise NoDataException(ErrorCode.NO_DOCUMENT, "未检索到相关文档片段")

                evidence = [
                    {
                        "doc_id": c.doc_id,
                        "file_name": c.file_name,
                        "text": c.text,
                        "score": round(c.score, 4),
                    }
                    for c in chunks
                ]
                sources = [
                    self._to_source(c.file_name, c.doc_id, c.text)
                    for c in chunks[:3]
                ]
                step["detail"] = f"命中片段={len(evidence)}"
                logger.info("GraphRAG Agent 检索成功 chunks=%s", len(evidence))
                return {
                    "rag_evidence": evidence,
                    "rag_error": None,
                    "data_sources": sources,
                    "step_logs": [self._finish(step, ok=True, hits=len(evidence))],
                }
            except NoDataException as e:
                logger.warning("GraphRAG Agent 无检索结果: %s", e.message)
                return self._fail(step, e.code, e.message)
            except AgentException as e:
                logger.error("GraphRAG Agent 异常: %s", e.message)
                return self._fail(step, e.code, e.message)
            except Exception as e:  # noqa: BLE001
                logger.exception("GraphRAG Agent 未知异常")
                return self._fail(step, ErrorCode.INTERNAL_ERROR, str(e))

    # ---------------- 索引惰性同步 ----------------
    @staticmethod
    def _ensure_indexed(client: JavaCallbackClient, retriever, dept_id: int | None) -> None:
        """
        从 Java 拉取部门文档清单，对尚未入库的文档做幂等索引构建。
        upsert 保证重复调用不产生重复片段。
        """
        try:
            docs = client.list_documents(dept_id)
        except Exception as e:  # noqa: BLE001
            logger.warning("拉取文档清单失败，使用已有索引: %s", e)
            return
        for doc in docs or []:
            doc_id = doc.get("id") or doc.get("docId")
            if not doc_id:
                continue
            try:
                content_data = client.fetch_document_content(int(doc_id))
                content = (content_data or {}).get("content", "")
                file_name = (content_data or {}).get("fileName", str(doc_id))
                doc_dept = (content_data or {}).get("deptId", dept_id or 0)
                if content:
                    retriever.build_index(int(doc_id), file_name, content, int(doc_dept))
            except Exception as e:  # noqa: BLE001
                logger.warning("文档索引失败 doc_id=%s err=%s", doc_id, e)

    @staticmethod
    def _to_source(file_name: str, doc_id: int, text: str) -> DataSource:
        snippet = text[:120] + ("..." if len(text) > 120 else "")
        return {
            "type": "document",
            "reference": f"{file_name}#doc{doc_id}",
            "evidence": snippet,
        }

    # ---------------- 失败回填 ----------------
    def _fail(self, step: dict, code: ErrorCode, message: str) -> dict:
        return {
            "rag_evidence": [],
            "rag_error": f"{code.value}: {message}",
            "step_logs": [self._finish(step, ok=False, error=code.value)],
        }

    @staticmethod
    def _finish(step: dict, ok: bool, hits: int = 0, error: str | None = None) -> dict:
        step["detail"] = {"ok": ok, "hits": hits, "error": error}
        return dict(step)


_graphrag_agent: GraphRagAgent | None = None


def get_graphrag_agent() -> GraphRagAgent:
    global _graphrag_agent
    if _graphrag_agent is None:
        _graphrag_agent = GraphRagAgent()
    return _graphrag_agent


def graphrag_agent_node(state: AgentState) -> dict:
    """LangGraph 节点入口。"""
    return get_graphrag_agent().run(state)
