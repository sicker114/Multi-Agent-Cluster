"""
统一异常与错误标识。

所有边界场景（无数据、检索无结果、LLM 幻觉、MCP 超时、LLM 限流等）
均通过明确的错误码向上层返回，支持二次重试判定。
"""
from __future__ import annotations

from enum import Enum


class ErrorCode(str, Enum):
    """Agent 集群错误码。"""

    SUCCESS = "SUCCESS"
    NO_DOCUMENT = "NO_DOCUMENT"           # 检索无匹配文档
    NO_DATA = "NO_DATA"                   # 数据库无对应业务数据
    FIELD_NOT_FOUND = "FIELD_NOT_FOUND"   # SQL 字段/表不存在
    HALLUCINATION = "HALLUCINATION"       # 检测到 LLM 幻觉
    LLM_RATE_LIMIT = "LLM_RATE_LIMIT"     # LLM 接口限流
    LLM_TIMEOUT = "LLM_TIMEOUT"           # LLM 调用超时
    CALLBACK_TIMEOUT = "CALLBACK_TIMEOUT" # Java 回调超时
    CALLBACK_ERROR = "CALLBACK_ERROR"     # Java 回调错误
    LOW_CONFIDENCE = "LOW_CONFIDENCE"     # 置信度不足
    INTERNAL_ERROR = "INTERNAL_ERROR"     # 内部错误


class AgentException(Exception):
    """Agent 业务异常。"""

    def __init__(self, code: ErrorCode, message: str = ""):
        self.code = code
        self.message = message or code.value
        super().__init__(self.message)


class RetryableException(AgentException):
    """可重试异常（超时、限流等）。"""


class NoDataException(AgentException):
    """无数据 / 无检索结果异常。"""

    def __init__(self, code: ErrorCode, message: str = ""):
        super().__init__(code, message)
