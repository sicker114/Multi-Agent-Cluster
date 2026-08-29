"""
GraphRAG 图谱初始化脚本。

自动解析 Java 存储的 PDF/Word/TXT 文档，抽取实体、关系构建知识图谱，
写入 Chroma 向量库 + 图谱存储，供 GraphRAG 检索 Agent 多跳检索。

支持两种数据来源：
1. 从 Java /internal/doc 接口拉取全部部门文档正文（默认，脱敏后）
2. 从本地目录解析文档文件（--local-dir 指定）

用法：
    python -m scripts.init_graphrag                 # 从 Java 拉取
    python -m scripts.init_graphrag --local-dir ./docs
"""
from __future__ import annotations

import argparse
import logging
import os
import sys

# 允许脚本直接运行时导入 app 包
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.core.java_client import JavaCallbackClient  # noqa: E402
from app.tools.graphrag_retriever import get_retriever  # noqa: E402

logging.basicConfig(level=logging.INFO,
                    format="%(asctime)s [%(levelname)s] %(name)s - %(message)s")
logger = logging.getLogger(__name__)


def init_from_java(dept_id: int | None) -> int:
    """从 Java 内部接口拉取文档并建立索引。"""
    client = JavaCallbackClient()
    retriever = get_retriever()
    docs = client.list_documents(dept_id)
    if not docs:
        logger.warning("未获取到任何文档，图谱初始化跳过")
        return 0
    total_chunks = 0
    for doc in docs:
        doc_id = doc.get("id") or doc.get("docId")
        if not doc_id:
            continue
        try:
            content_data = client.fetch_document_content(int(doc_id))
            content = (content_data or {}).get("content", "")
            file_name = (content_data or {}).get("fileName", str(doc_id))
            doc_dept = (content_data or {}).get("deptId", dept_id or 0)
            if not content:
                logger.warning("文档正文为空 doc_id=%s", doc_id)
                continue
            n = retriever.build_index(int(doc_id), file_name, content, int(doc_dept))
            total_chunks += n
            logger.info("已索引文档 doc_id=%s file=%s chunks=%s", doc_id, file_name, n)
        except Exception as e:  # noqa: BLE001
            logger.error("文档索引失败 doc_id=%s err=%s", doc_id, e)
    logger.info("图谱初始化完成，共写入 %s 个片段", total_chunks)
    return total_chunks


def init_from_local(local_dir: str) -> int:
    """从本地目录解析文档文件并建立索引。"""
    retriever = get_retriever()
    total_chunks = 0
    doc_id = 90000  # 本地文档 ID 起始（避免与 Java 库冲突）
    for root, _, files in os.walk(local_dir):
        for name in files:
            path = os.path.join(root, name)
            content = _extract(path)
            if not content:
                continue
            doc_id += 1
            n = retriever.build_index(doc_id, name, content, 0)
            total_chunks += n
            logger.info("已索引本地文档 file=%s chunks=%s", name, n)
    logger.info("本地图谱初始化完成，共写入 %s 个片段", total_chunks)
    return total_chunks


def _extract(path: str) -> str:
    """按扩展名解析 PDF/Word/TXT 文本。"""
    lower = path.lower()
    try:
        if lower.endswith(".txt"):
            with open(path, "r", encoding="utf-8", errors="ignore") as f:
                return f.read()
        if lower.endswith(".pdf"):
            from PyPDF2 import PdfReader

            reader = PdfReader(path)
            return "\n".join((page.extract_text() or "") for page in reader.pages)
        if lower.endswith(".docx"):
            from docx import Document

            doc = Document(path)
            return "\n".join(p.text for p in doc.paragraphs)
    except Exception as e:  # noqa: BLE001
        logger.error("解析文档失败 path=%s err=%s", path, e)
    return ""


def main() -> None:
    parser = argparse.ArgumentParser(description="GraphRAG 图谱初始化")
    parser.add_argument("--dept-id", type=int, default=None, help="仅初始化指定部门文档")
    parser.add_argument("--local-dir", type=str, default=None, help="从本地目录解析文档")
    args = parser.parse_args()

    if args.local_dir:
        init_from_local(args.local_dir)
    else:
        init_from_java(args.dept_id)


if __name__ == "__main__":
    main()
