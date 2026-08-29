"""
Java 内部接口回调客户端。

Python 子 Agent 通过本客户端反向调用 Java 主服务的 /internal/** 接口：
- 拉取脱敏文档正文（GraphRAG Agent）
- 列出部门文档清单
- 执行只读安全数据查询（SQL Agent）
- 读写共享长期记忆

所有请求携带 X-Internal-Key 密钥头，内置超时与重试。
"""
from __future__ import annotations

import logging
from typing import Any

import httpx
from tenacity import retry, retry_if_exception_type, stop_after_attempt, wait_fixed

from app.core.config import get_settings
from app.core.exceptions import AgentException, ErrorCode, RetryableException

logger = logging.getLogger(__name__)


class JavaCallbackClient:
    """Java 内部接口回调客户端。"""

    def __init__(self, base_url: str | None = None, api_key: str | None = None) -> None:
        settings = get_settings()
        self.base_url = (base_url or settings.java_callback_base_url).rstrip("/")
        self.api_key = api_key or settings.internal_api_key
        self.timeout = settings.callback_timeout

    def _headers(self) -> dict:
        return {"X-Internal-Key": self.api_key, "Content-Type": "application/json"}

    @retry(
        retry=retry_if_exception_type(RetryableException),
        stop=stop_after_attempt(3),
        wait=wait_fixed(1.5),
        reraise=True,
    )
    def _get(self, path: str, params: dict | None = None) -> dict:
        try:
            with httpx.Client(timeout=self.timeout) as client:
                resp = client.get(self.base_url + path, params=params, headers=self._headers())
                return self._handle(resp)
        except httpx.TimeoutException as e:
            logger.warning("Java 回调 GET 超时 path=%s", path)
            raise RetryableException(ErrorCode.CALLBACK_TIMEOUT, str(e)) from e

    @retry(
        retry=retry_if_exception_type(RetryableException),
        stop=stop_after_attempt(3),
        wait=wait_fixed(1.5),
        reraise=True,
    )
    def _post(self, path: str, json_body: dict) -> dict:
        try:
            with httpx.Client(timeout=self.timeout) as client:
                resp = client.post(self.base_url + path, json=json_body, headers=self._headers())
                return self._handle(resp)
        except httpx.TimeoutException as e:
            logger.warning("Java 回调 POST 超时 path=%s", path)
            raise RetryableException(ErrorCode.CALLBACK_TIMEOUT, str(e)) from e

    @staticmethod
    def _handle(resp: httpx.Response) -> dict:
        if resp.status_code != 200:
            raise AgentException(ErrorCode.CALLBACK_ERROR, f"HTTP {resp.status_code}: {resp.text}")
        body = resp.json()
        if body.get("code") != 200:
            raise AgentException(ErrorCode.CALLBACK_ERROR, body.get("message", "回调返回失败"))
        return body.get("data")

    # ---------------- 文档相关（GraphRAG Agent 使用） ----------------
    def fetch_document_content(self, doc_id: int) -> dict:
        """拉取单个文档的脱敏正文。"""
        return self._get(f"/internal/doc/{doc_id}/content")

    def list_documents(self, dept_id: int | None) -> list[dict]:
        """列出部门文档清单。"""
        params = {"deptId": dept_id} if dept_id is not None else None
        data = self._get("/internal/doc/list", params=params)
        return data or []

    # ---------------- 业务数据（SQL Agent 使用） ----------------
    def safe_query(self, query_type: str, dept_ids: list[int] | None = None,
                   category: str | None = None, start_date: str | None = None,
                   end_date: str | None = None, stat_date: str | None = None,
                   raw_sql: str | None = None) -> list[dict]:
        """执行只读安全数据查询。"""
        body: dict[str, Any] = {"queryType": query_type}
        if dept_ids is not None:
            body["deptIds"] = dept_ids
        if category:
            body["category"] = category
        if start_date:
            body["startDate"] = start_date
        if end_date:
            body["endDate"] = end_date
        if stat_date:
            body["statDate"] = stat_date
        if raw_sql:
            body["rawSql"] = raw_sql
        data = self._post("/internal/data/query", body)
        return data or []

    # ---------------- 共享长期记忆 ----------------
    def hit_long_term_memory(self, user_id: int, question: str) -> dict:
        """查询长期记忆命中。"""
        return self._get("/internal/memory/longterm",
                         params={"userId": user_id, "question": question})

    def save_long_term_memory(self, user_id: int, question: str, value: Any) -> None:
        """写入长期记忆报告。"""
        self._post("/internal/memory/longterm",
                   {"userId": user_id, "question": question, "value": value})

    def save_hallucination_case(self, user_id: int, question: str, value: Any) -> None:
        """记录幻觉案例。"""
        self._post("/internal/memory/hallucination",
                   {"userId": user_id, "question": question, "value": value})
