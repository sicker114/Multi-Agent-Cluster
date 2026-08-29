"""
MCP Server 主入口（P0+ 增强服务基座 · 眼前一亮三件套）。

三大亮点：
  A) 注册 enterprise_analysis + stream_enterprise_analysis 两个 MCP 工具
     - 同步版走 graph.invoke() 返回 JSON
     - 流式版走 graph.stream() 逐节点产出 SSE 事件：
       event: planning / retrieving / computing / judging / report / done / error
       每个事件 push 原始文本，最后在 done 的 data 里带 finalJson={... McpAnalysisResult 结构}
  B) 暴露内部 HTTP 接口（仅 Java 侧用，X-Internal-Key 保护）：
     - POST /internal/rag/index-doc  ：文档上传后触发 GraphRAG Chroma 增量入库
     - POST /internal/rag/delete-doc ：文档删除后按 docId 删除向量片段
     - POST /internal/memory/semantic/hit   ：Java SemanticMemoryClient 命中查询
     - POST /internal/memory/semantic/index ：Java 高置信答案异步写回 Chroma
  C) 完全遵循 2026 MCP 标准协议：Java SpringAI MCP Client 自动发现本服务工具，
     严禁自建 HTTP 替代通道；上述内部 HTTP 仅用于"数据面"索引入库与记忆读写。
"""
from __future__ import annotations

import json
import logging
import time
import uuid

from mcp.server.fastmcp import FastMCP
from starlette.requests import Request
from starlette.responses import JSONResponse, Response, StreamingResponse

from app.core.config import get_settings
from app.graph.runner import get_runner
from app.graph.state import init_state
from app.graph.harness import get_graph
from app.memory.semantic_memory import get_semantic_store
from app.observability.langsmith_setup import setup_langsmith
from app.tools.graphrag_retriever import get_retriever
from app.core.java_client import JavaCallbackClient

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s - %(message)s",
)
logger = logging.getLogger(__name__)

settings = get_settings()
setup_langsmith()

mcp = FastMCP(
    settings.mcp_server_name,
    host=settings.mcp_http_host,
    port=settings.mcp_http_port,
)


# ================================================================
# Helpers：MCP 工具服务端通用
# ================================================================
def _to_java_result(result: dict) -> dict:
    """内部 snake_case 映射为 Java McpAnalysisResult camelCase。"""
    return {
        "success": bool(result.get("success")),
        "errorCode": result.get("error_code"),
        "errorMessage": result.get("error_message"),
        "report": result.get("report", ""),
        "confidenceScore": int(result.get("confidence_score", 0)),
        "dataSources": [
            {
                "type": s.get("type"),
                "reference": s.get("reference"),
                "evidence": s.get("evidence"),
            }
            for s in (result.get("data_sources") or [])
        ],
        "riskTags": result.get("risk_tags", []),
        "retryCount": int(result.get("retry_count", 0)),
        "tokenCost": int(result.get("token_total", 0)),
        "cacheHit": bool(result.get("cache_hit")),
    }


def _validate_internal_key(request: Request) -> bool:
    key = request.headers.get("x-internal-key")
    return key == settings.internal_api_key


# ================================================================
# 同步分析工具
# ================================================================
@mcp.tool()
def enterprise_analysis(
    question: str,
    user_id: int,
    dept_id: int,
    dept_ids: list[int] | None = None,
    session_id: str | None = None,
    callback_base_url: str | None = None,
    internal_api_key: str | None = None,
) -> str:
    """
    企业经营数据智能分析工具（多智能体协作 · 同步版）。

    输入用户自然语言复合业务需求，自动完成任务拆解、联合查询企业文档知识库 +
    业务数据库、统计计算、Judge 四维交叉校验，返回带数据来源与置信度的可信分析报告。
    如置信度未达标，Judge 会触发 Self-RAG 反思重试，精准回退到 GraphRAG/SQL 短板节点。

    :param question: 用户自然语言业务需求
    :param user_id: 用户 ID
    :param dept_id: 用户所属部门 ID
    :param dept_ids: 数据权限可访问部门列表（None 表示全量，用于管理员）
    :param session_id: 会话 ID（用于 Checkpoint 断点恢复）
    :param callback_base_url: Java 主服务内部接口地址
    :param internal_api_key: Java 内部接口密钥
    :return: 严格对齐 Java McpAnalysisResult 的 JSON 字符串
    """
    logger.info("收到分析请求 user=%s dept=%s question=%s", user_id, dept_id, question)
    runner = get_runner()
    result = runner.analyze(
        question=question,
        user_id=user_id,
        dept_id=dept_id,
        dept_ids=dept_ids,
        session_id=session_id,
        callback_base_url=callback_base_url,
        internal_api_key=internal_api_key,
    )
    return json.dumps(_to_java_result(result), ensure_ascii=False)


# ================================================================
# 流式分析工具（SSE 逐节点推送）
# ================================================================
@mcp.tool()
async def stream_enterprise_analysis(
    question: str,
    user_id: int,
    dept_id: int,
    dept_ids: list[int] | None = None,
    session_id: str | None = None,
    callback_base_url: str | None = None,
    internal_api_key: str | None = None,
) -> str:
    """
    企业经营数据智能分析工具（多智能体协作 · 流式版）。

    返回增量 SSE 事件流字符串流（Java 侧 McpToolGatewayImpl#analyzeStream 逐块订阅后，
    再包装成 Spring ServerSentEvent 推给前端）。事件类型：

      event: planning    规划阶段 / 意图解析
      event: retrieving  GraphRAG 检索（含改写 / 混合 / 重排）
      event: computing   SQL 查询 + Statistics 计算
      event: judging     Judge 四维评审 + Self-RAG 反思决策
      event: report      文本增量（打字机效果的报告片段）
      event: done        结束，data 中含 finalJson = Java McpAnalysisResult JSON
      event: error       异常

    :param question: 用户自然语言业务需求
    :param user_id: 用户 ID
    :param dept_id: 用户所属部门 ID
    :param dept_ids: 数据权限可访问部门列表
    :param session_id: 会话 ID
    :param callback_base_url: Java 主服务内部接口地址
    :param internal_api_key: Java 内部接口密钥
    :return: 事件流（每个 chunk 本身就是 "event:xxx\ndata:yyy\n\n" 原文，供直接推送）
    """
    import asyncio

    logger.info("流式分析请求 user=%s dept=%s question=%s", user_id, dept_id, question)
    session_id = session_id or str(uuid.uuid4())
    start = time.time()

    # 先试长期记忆命中，立即返回 cacheHit + done
    runner = get_runner()
    cached = runner.memory.hit_long_term(user_id, question)
    if cached:
        cached = dict(cached)
        cached["cache_hit"] = True
        cached["cost_ms"] = int((time.time() - start) * 1000)
        java = _to_java_result(cached)
        done_data = {"costMs": cached["cost_ms"], "finalJson": java}
        cache_evt = f"event: cacheHit\ndata: {json.dumps(java, ensure_ascii=False)}\n\n"
        done_evt = f"event: done\ndata: {json.dumps(done_data, ensure_ascii=False)}\n\n"
        yield cache_evt  # type: ignore[misc]
        yield done_evt  # type: ignore[misc]
        return

    state = init_state(
        question=question,
        user_id=user_id,
        dept_id=dept_id,
        dept_ids=dept_ids,
        session_id=session_id,
        callback_base_url=callback_base_url or settings.java_callback_base_url,
        internal_api_key=internal_api_key or settings.internal_api_key,
        max_retry=settings.max_reflection_retry,
    )
    graph = get_graph()
    config = {"configurable": {"thread_id": session_id}}

    # 规划事件
    yield f"event: planning\ndata: Manager 正在解析意图与子任务\n\n"  # type: ignore[misc]

    report_parts: list[str] = []
    final_state: dict = {}

    try:
        # 因为 FastMCP 的 generator 工具允许同步/异步 yield 文本块，
        # 这里用 astream 异步 + 在事件循环 yield 原文字符串。
        async for chunk in graph.astream(state, config=config):
            node_name = list(chunk.keys())[-1] if chunk else ""
            data = chunk.get(node_name) if node_name else {}
            if node_name == "manager_plan":
                note = (data or {}).get("plan_note", "规划中")
                yield f"event: planning\ndata: {note}\n\n"  # type: ignore[misc]
            elif node_name == "sql_agent":
                err = (data or {}).get("sql_error")
                msg = "SQL Agent 查询业务数据：" + (
                    f"命中 {len((data or {}).get('sql_data') or [])} 条" if not err else f"失败 {err}"
                )
                yield f"event: computing\ndata: {msg}\n\n"  # type: ignore[misc]
            elif node_name == "graphrag_agent":
                ev = (data or {}).get("rag_evidence") or []
                msg = f"GraphRAG 增强检索：{len(ev)} 段（改写+混合RRF+Reranker完成）"
                yield f"event: retrieving\ndata: {msg}\n\n"  # type: ignore[misc]
            elif node_name == "statistics_agent":
                comp = (data or {}).get("compute_result") or {}
                metrics = ",".join(f"{k}={v}" for k, v in list(comp.items())[:6])
                msg = f"Statistics 计算完成：{metrics or 'N/A'}"
                yield f"event: computing\ndata: {msg}\n\n"  # type: ignore[misc]
            elif node_name == "manager_aggregate":
                msg = "Manager HybridQA 汇总：实体别名已归一 + 溯源三元组抽取完成"
                yield f"event: computing\ndata: {msg}\n\n"  # type: ignore[misc]
            elif node_name == "judge_agent":
                score = (data or {}).get("confidence_score", 0)
                retry = (data or {}).get("need_retry", False)
                hint = (data or {}).get("retry_hint", "") or ""
                breakdown = (data or {}).get("judge_breakdown") or {}
                msg = (
                    f"Judge 四维评审：综合 {score}/100；"
                    f"反思重试={retry}({hint or 'N/A'})；"
                    f"f={breakdown.get('faithfulness')} c={breakdown.get('context_relevancy')} "
                    f"a={breakdown.get('answer_relevancy')} k={breakdown.get('consistency')}"
                )
                yield f"event: judging\ndata: {msg}\n\n"  # type: ignore[misc]
            elif node_name == "manager_finalize":
                final_body = (data or {}).get("final_report") or ""
                # 按段落切，制造打字机效果
                paragraphs = [p for p in final_body.split("\n") if p.strip()]
                for p in paragraphs:
                    piece = p + "\n"
                    report_parts.append(piece)
                    yield f"event: report\ndata: {json.dumps(piece, ensure_ascii=False)}\n\n"  # type: ignore[misc]
                    await asyncio.sleep(0.02)
            if isinstance(data, dict):
                # 累积状态（以最后一个节点结果合并；astream 每次返回单节点输出）
                for k, v in data.items():
                    if isinstance(final_state.get(k), list) and isinstance(v, list):
                        final_state[k] = final_state[k] + v
                    else:
                        final_state[k] = v
    except Exception as e:  # noqa: BLE001
        logger.exception("流式分析异常")
        yield f"event: error\ndata: {str(e)[:500]}\n\n"  # type: ignore[misc]
        return

    # 若 final_state 缺 report（极端情况），兜底
    if not final_state.get("final_report") and report_parts:
        final_state["final_report"] = "".join(report_parts)

    final_struct = runner._to_result(final_state, session_id, start)  # type: ignore[assignment]
    # 达标结果写长期记忆（复用 runner 逻辑）
    try:
        if final_struct.get("success"):
            runner.memory.save_long_term(user_id, question, final_struct)
    except Exception as e:  # noqa: BLE001
        logger.debug("流式成功结果写长期记忆失败: %s", e)

    java = _to_java_result(final_struct)
    done_payload = {
        "costMs": final_struct.get("cost_ms", int((time.time() - start) * 1000)),
        "finalJson": java,
    }
    yield f"event: done\ndata: {json.dumps(done_payload, ensure_ascii=False)}\n\n"  # type: ignore[misc]


# ================================================================
# 健康检查工具
# ================================================================
@mcp.tool()
def health_check() -> str:
    """MCP 服务健康检查工具，返回服务状态与配置摘要。"""
    return json.dumps({
        "status": "UP",
        "server": settings.mcp_server_name,
        "transport": settings.mcp_transport,
        "llm_model": settings.llm_model,
        "confidence_threshold": settings.confidence_threshold,
        "max_reflection_retry": settings.max_reflection_retry,
        "features": [
            "enterprise_analysis",
            "stream_enterprise_analysis",
            "HybridQA alias normalize",
            "Judge 4-dim self-rag retry",
            "GraphRAG rewrite+hybrid(RRF)+reranker",
            "Semantic memory chroma index",
        ],
    }, ensure_ascii=False)


# ================================================================
# 内部 HTTP 路由（Java 回调：RAG 入库 / 语义记忆 / SSE 流式）
#   FastMCP 1.2.0 不暴露 app 属性，内部路由在 main() 中组合到
#   同一个 Starlette app 里，与 MCP SSE 路由共存。
# ================================================================

async def internal_rag_index(request: Request) -> Response:
    if not _validate_internal_key(request):
        return JSONResponse({"code": 401, "message": "INVALID_INTERNAL_KEY", "data": None}, status_code=401)
    try:
        body = await request.json()
    except Exception:  # noqa: BLE001
        return JSONResponse({"code": 400, "message": "BAD_JSON", "data": None}, status_code=400)
    doc_id = body.get("docId")
    dept_id = body.get("deptId") or 0
    if not doc_id:
        return JSONResponse({"code": 400, "message": "MISSING_DOC_ID", "data": None}, status_code=400)
    try:
        client = JavaCallbackClient(
            base_url=settings.java_callback_base_url,
            api_key=settings.internal_api_key,
        )
        content_data = client.fetch_document_content(int(doc_id))
        content = (content_data or {}).get("content", "")
        file_name = (content_data or {}).get("fileName", f"doc{doc_id}")
        doc_dept = int((content_data or {}).get("deptId", dept_id or 0))
        if not content:
            return JSONResponse({"code": 200, "message": "EMPTY_CONTENT", "data": {"chunks": 0}})
        n = get_retriever().build_index(int(doc_id), file_name, content, doc_dept)
        logger.info("内部回调 GraphRAG 入库完成 docId=%s chunks=%s", doc_id, n)
        return JSONResponse({"code": 200, "message": "OK", "data": {"chunks": n}})
    except Exception as e:  # noqa: BLE001
        logger.exception("内部回调 GraphRAG 入库失败 docId=%s", doc_id)
        return JSONResponse({"code": 500, "message": str(e)[:200], "data": None}, status_code=500)



async def internal_rag_delete(request: Request) -> Response:
    if not _validate_internal_key(request):
        return JSONResponse({"code": 401, "message": "INVALID_INTERNAL_KEY", "data": None}, status_code=401)
    try:
        body = await request.json()
    except Exception:  # noqa: BLE001
        return JSONResponse({"code": 400, "message": "BAD_JSON", "data": None}, status_code=400)
    doc_id = body.get("docId")
    if not doc_id:
        return JSONResponse({"code": 400, "message": "MISSING_DOC_ID", "data": None}, status_code=400)
    try:
        col = get_retriever()._get_collection()  # type: ignore[attr-defined]
        # 删除所有 id 以 "doc{doc_id}-" 前缀开头的片段
        try:
            got = col.get(
                where={"doc_id": int(doc_id)},
                include=[],
            )
            ids = got.get("ids") or []
            if ids:
                col.delete(ids=ids)
            removed = len(ids)
        except Exception:  # noqa: BLE001
            removed = 0
        logger.info("内部回调 GraphRAG 删除完成 docId=%s removed=%s", doc_id, removed)
        return JSONResponse({"code": 200, "message": "OK", "data": {"removed": removed}})
    except Exception as e:  # noqa: BLE001
        logger.exception("内部回调 GraphRAG 删除失败 docId=%s", doc_id)
        return JSONResponse({"code": 500, "message": str(e)[:200], "data": None}, status_code=500)


# ================================================================
# 内部 HTTP：语义记忆（Java SemanticMemoryClient 调用）
# ================================================================

async def internal_semantic_hit(request: Request) -> Response:
    if not _validate_internal_key(request):
        return JSONResponse({"code": 401, "message": "INVALID_INTERNAL_KEY", "data": None}, status_code=401)
    try:
        body = await request.json()
    except Exception:  # noqa: BLE001
        return JSONResponse({"code": 400, "message": "BAD_JSON", "data": None}, status_code=400)
    store = get_semantic_store()
    res = store.hit(
        user_id=int(body.get("userId") or 0),
        question=str(body.get("question") or ""),
        threshold=float(body.get("threshold") or settings.semantic_hit_threshold_default),
    )
    return JSONResponse({"code": 200, "message": "OK", "data": res})



async def internal_semantic_index(request: Request) -> Response:
    if not _validate_internal_key(request):
        return JSONResponse({"code": 401, "message": "INVALID_INTERNAL_KEY", "data": None}, status_code=401)
    try:
        body = await request.json()
    except Exception:  # noqa: BLE001
        return JSONResponse({"code": 400, "message": "BAD_JSON", "data": None}, status_code=400)
    store = get_semantic_store()
    ok = store.index(
        user_id=int(body.get("userId") or 0),
        question=str(body.get("question") or ""),
        fingerprint=str(body.get("fingerprint") or ""),
        confidence_score=int(body.get("confidenceScore") or 0),
        value=body.get("value"),
    )
    return JSONResponse({"code": 200, "message": "OK", "data": {"ok": bool(ok)}})


# ================================================================
# 内部 HTTP：SSE 流式分析（Java WebClient 数据面调用）
#   说明：Spring AI 1.0.0 GA McpSyncClient 未暴露流式工具订阅 API，
#   因此 Java 侧"实时打字机 + 进度事件"直接走内部 HTTP SSE；
#   同步分析与工具发现仍然严格走 Spring AI MCP Client 标准协议。
# ================================================================

async def internal_analysis_stream(request: Request) -> Response:
    if not _validate_internal_key(request):
        return JSONResponse({"code": 401, "message": "INVALID_INTERNAL_KEY", "data": None}, status_code=401)
    try:
        body = await request.json()
    except Exception:  # noqa: BLE001
        return JSONResponse({"code": 400, "message": "BAD_JSON", "data": None}, status_code=400)

    question = str(body.get("question") or "")
    user_id = int(body.get("userId") or 0)
    dept_id = int(body.get("deptId") or 0)
    dept_ids = body.get("deptIds")
    session_id = body.get("sessionId") or str(uuid.uuid4())
    callback_base_url = body.get("callbackBaseUrl") or settings.java_callback_base_url
    internal_api_key = body.get("internalApiKey") or settings.internal_api_key
    max_retry = int(body.get("maxRetry") or settings.max_reflection_retry)

    def _gen():  # noqa: ANN202
        import time as _time

        start = time.time()
        # 先试长期/语义记忆命中，立即返回（Java 侧命中语义不会走到这里，Python 侧仍保险检查）
        runner = get_runner()
        cached = runner.memory.hit_long_term(user_id, question)
        if cached:
            cached = dict(cached)
            cached["cache_hit"] = True
            cached["cost_ms"] = int((time.time() - start) * 1000)
            java = _to_java_result(cached)
            done_data = {"costMs": cached["cost_ms"], "finalJson": java}
            yield f"event: cacheHit\ndata: {json.dumps(java, ensure_ascii=False)}\n\n"
            yield f"event: done\ndata: {json.dumps(done_data, ensure_ascii=False)}\n\n"
            return

        state = init_state(
            question=question,
            user_id=user_id,
            dept_id=dept_id,
            dept_ids=dept_ids,
            session_id=session_id,
            callback_base_url=callback_base_url,
            internal_api_key=internal_api_key,
            max_retry=max_retry,
        )
        graph = get_graph()
        config = {"configurable": {"thread_id": session_id}}

        yield "event: planning\ndata: Manager 正在解析意图与子任务\n\n"

        # 同步生成器：Starlette StreamingResponse 在 anyio threadpool 线程迭代，
        # graph.stream()（含同步 llm.chat 60s 超时）阻塞 threadpool 线程，不占用 uvicorn 事件循环，
        # 故 8001 端口可并发处理其他请求（GET/404 等），不会因 LLM 慢调用卡死。

        def _chunk_to_events(node_name: str, data: dict,
                             report_parts: list[str]) -> list[str]:
            events: list[str] = []
            if node_name == "manager_plan":
                note = (data or {}).get("plan_note", "规划中")
                events.append(f"event: planning\ndata: {note}\n\n")
            elif node_name == "sql_agent":
                err = (data or {}).get("sql_error")
                msg = "SQL Agent 查询业务数据：" + (
                    f"命中 {len((data or {}).get('sql_data') or [])} 条" if not err else f"失败 {err}"
                )
                events.append(f"event: computing\ndata: {msg}\n\n")
            elif node_name == "graphrag_agent":
                ev = (data or {}).get("rag_evidence") or []
                msg = f"GraphRAG 增强检索：{len(ev)} 段（改写+混合RRF+Reranker完成）"
                events.append(f"event: retrieving\ndata: {msg}\n\n")
            elif node_name == "statistics_agent":
                comp = (data or {}).get("compute_result") or {}
                metrics = ",".join(f"{k}={v}" for k, v in list(comp.items())[:6])
                msg = f"Statistics 计算完成：{metrics or 'N/A'}"
                events.append(f"event: computing\ndata: {msg}\n\n")
            elif node_name == "manager_aggregate":
                msg = "Manager HybridQA 汇总：实体别名已归一 + 溯源三元组抽取完成"
                events.append(f"event: computing\ndata: {msg}\n\n")
            elif node_name == "judge_agent":
                score = (data or {}).get("confidence_score", 0)
                retry = (data or {}).get("need_retry", False)
                hint = (data or {}).get("retry_hint", "") or ""
                breakdown = (data or {}).get("judge_breakdown") or {}
                msg = (
                    f"Judge 四维评审：综合 {score}/100；"
                    f"反思重试={retry}({hint or 'N/A'})；"
                    f"f={breakdown.get('faithfulness')} c={breakdown.get('context_relevancy')} "
                    f"a={breakdown.get('answer_relevancy')} k={breakdown.get('consistency')}"
                )
                events.append(f"event: judging\ndata: {msg}\n\n")
            elif node_name == "manager_finalize":
                final_body = (data or {}).get("final_report") or ""
                for p in [x for x in final_body.split("\n") if x.strip()]:
                    piece = p + "\n"
                    report_parts.append(piece)
                    events.append(f"event: report\ndata: {json.dumps(piece, ensure_ascii=False)}\n\n")
                    _time.sleep(0.02)
            return events

        report_parts: list[str] = []
        final_state: dict = {}
        try:
            for chunk in graph.stream(state, config=config):
                node_name = list(chunk.keys())[-1] if chunk else ""
                data = chunk.get(node_name) if node_name else {}
                for evt in _chunk_to_events(node_name, data, report_parts):
                    yield evt
                if isinstance(data, dict):
                    for k, v in data.items():
                        if isinstance(final_state.get(k), list) and isinstance(v, list):
                            final_state[k] = final_state[k] + v
                        else:
                            final_state[k] = v
        except Exception as e:  # noqa: BLE001
            logger.exception("内部 HTTP SSE 分析异常")
            yield f"event: error\ndata: {str(e)[:500]}\n\n"
            return

        if not final_state.get("final_report") and report_parts:
            final_state["final_report"] = "".join(report_parts)

        final_struct = runner._to_result(final_state, session_id, start)  # type: ignore[assignment]
        try:
            if final_struct.get("success"):
                runner.memory.save_long_term(user_id, question, final_struct)
        except Exception as e:  # noqa: BLE001
            logger.debug("流式成功结果写长期记忆失败: %s", e)

        java = _to_java_result(final_struct)
        done_payload = {
            "costMs": final_struct.get("cost_ms", int((_time.time() - start) * 1000)),
            "finalJson": java,
        }
        yield f"event: done\ndata: {json.dumps(done_payload, ensure_ascii=False)}\n\n"

    return StreamingResponse(_gen(), media_type="text/event-stream")


# ================================================================
# settings 动态字段兜底（允许未在 config.py 写的字段）
# ================================================================
def _ensure_settings() -> None:
    if not hasattr(settings, "semantic_hit_threshold_default"):
        object.__setattr__(settings, "semantic_hit_threshold_default", 0.92)


_ensure_settings()


def _build_internal_app():
    """构建 internal HTTP Starlette app（供主进程与独立子进程复用）。"""
    from starlette.applications import Starlette
    from starlette.routing import Route

    return Starlette(
        debug=True,
        routes=[
            Route("/internal/rag/index-doc", internal_rag_index, methods=["POST"]),
            Route("/internal/rag/delete-doc", internal_rag_delete, methods=["POST"]),
            Route("/internal/memory/semantic/hit", internal_semantic_hit, methods=["POST"]),
            Route("/internal/memory/semantic/index", internal_semantic_index, methods=["POST"]),
            Route("/internal/analysis/stream", internal_analysis_stream, methods=["POST"]),
        ],
    )


def _run_internal_http_only() -> None:
    """独立进程入口：在主线程跑 internal HTTP uvicorn（端口 8001）。
    必须独立进程跑——若与主进程 mcp.run(sse) 同处一个进程的子线程，
    FastMCP 的 asyncio 会干扰子线程 uvicorn，导致 8001 端口假死（连 GET / 都不响应）。
    """
    import uvicorn

    internal_app = _build_internal_app()
    port = settings.mcp_http_port + 1  # 8001
    print(f"[internal-http] 独立进程启动 {settings.mcp_http_host}:{port}", flush=True)
    logger.info("Internal HTTP server (独立进程) 启动 %s:%s", settings.mcp_http_host, port)
    uvicorn.run(
        internal_app,
        host=settings.mcp_http_host,
        port=port,
        log_level="info",
    )


def _start_internal_http_server() -> None:
    """用 subprocess 启动独立进程跑 internal HTTP server（端口 8001）。
    独立进程避免主进程 FastMCP asyncio 干扰 uvicorn 事件循环。
    """
    import os
    import subprocess
    import sys

    venv_python = sys.executable
    cwd = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))  # python-mcp-service 目录
    env = os.environ.copy()
    env["PYTHONUNBUFFERED"] = "1"
    try:
        subprocess.Popen(
            [venv_python, "-m", "app.server", "--internal-only"],
            cwd=cwd,
            env=env,
        )
        logger.info("Internal HTTP server 已作为独立子进程启动 on port %s",
                    settings.mcp_http_port + 1)
        print(f"[mcp] internal HTTP 子进程已启动 on port {settings.mcp_http_port + 1}", flush=True)
    except Exception as e:  # noqa: BLE001
        logger.exception("启动 internal HTTP 子进程失败: %s", e)
        print(f"[mcp] internal HTTP 子进程启动失败: {e}", flush=True)


def main() -> None:
    import sys

    # 独立子进程模式：只跑 internal HTTP uvicorn，不启动 MCP SSE
    if "--internal-only" in sys.argv:
        _run_internal_http_only()
        return

    transport = settings.mcp_transport.lower()
    if transport == "stdio":
        logger.info("Start MCP Server (STDIO) name=%s", settings.mcp_server_name)
        mcp.run(transport="stdio")
        return

    # Start internal HTTP server on port 8001 (独立子进程，避免 asyncio 干扰)
    _start_internal_http_server()

    # Start MCP SSE server on port 8000 using FastMCP built-in (main thread, blocks)
    logger.info("Start MCP Server (SSE) %s:%s  internal-http:%s",
                settings.mcp_http_host, settings.mcp_http_port, settings.mcp_http_port + 1)
    mcp.run(transport="sse")


if __name__ == "__main__":
    main()
