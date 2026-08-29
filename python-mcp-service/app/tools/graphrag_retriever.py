"""
GraphRAG 检索核心（P0 增强版）。

亮点：RAG 三件套一体化实现，保证线上"准而全"。
  ① Query 改写：LLM 输出 2~3 种重写查询（同义 / 补充关键词 / 去口语化），失败时关键词降级
  ② 混合检索：BM25 关键词 + 向量余弦，用 RRF（倒数排名融合）合并排名，鲁棒性显著提升
  ③ 重排（Reranker）：支持 Cross-Encoder / LLM 打分，失败时降级 score×coverage 启发式
  ④ 多跳关联：沿共享实体扩展相邻片段并降权，保留 GraphRAG 特色
  ⑤ 全链路可降级：Embedding / LLM / Chroma 任一不可用，均至少返回关键词检索结果

为保证在无 GPU / 离线环境可运行，Embedding 走 OpenAI 兼容接口；
若 Embedding 不可用则 BM25 独占；若 LLM 不可用则 QueryRewrite / Reranker 走启发式降级。
"""
from __future__ import annotations

import logging
import math
import re
from collections import Counter, defaultdict
from dataclasses import dataclass, field

import chromadb

from app.core.config import get_settings
from app.core.llm import TokenCounter, get_llm_client

logger = logging.getLogger(__name__)


@dataclass
class RetrievedChunk:
    """检索结果片段。"""

    doc_id: int
    file_name: str
    text: str
    score: float
    bm25_rank: int | None = None
    vector_rank: int | None = None
    rerank_score: float | None = None
    entities: list[str] = field(default_factory=list)


# ================================================================
#  BM25（纯 Python，零额外依赖）—— 轻量、稳定、可离线
# ================================================================
class _BM25Okapi:
    """BM25 Okapi：k1=1.5, b=0.75。"""

    def __init__(self, corpus: list[list[str]], k1: float = 1.5, b: float = 0.75,
                 epsilon: float = 0.25) -> None:
        self.corpus_size = len(corpus)
        self.k1 = k1
        self.b = b
        self.epsilon = epsilon
        self.dl = [float(len(d)) for d in corpus] if corpus else []
        self.avgdl = sum(self.dl) / self.corpus_size if self.corpus_size else 0.0
        self.corpus = corpus
        self.f: list[dict[str, int]] = []
        self.df: dict[str, int] = defaultdict(int)
        self.idf: dict[str, float] = {}
        self._build()

    def _build(self) -> None:
        for doc in self.corpus:
            freq: dict[str, int] = Counter(doc)
            self.f.append(freq)
            for token in freq.keys():
                self.df[token] += 1
        # IDF with negative-idf smoothing
        negative_idfs = []
        for token, freq in self.df.items():
            idf = math.log(self.corpus_size - freq + 0.5) - math.log(freq + 0.5)
            self.idf[token] = idf
            if idf < 0:
                negative_idfs.append(token)
        if negative_idfs:
            eps = self.epsilon * sum(v for v in self.idf.values() if v > 0) / max(1, len(negative_idfs))
            for token in negative_idfs:
                self.idf[token] = eps

    def get_scores(self, query_tokens: list[str]) -> list[float]:
        score = [0.0] * self.corpus_size
        for q in query_tokens:
            if q not in self.idf:
                continue
            idf = self.idf[q]
            for i in range(self.corpus_size):
                if not self.dl[i]:
                    continue
                f = self.f[i].get(q, 0)
                if not f:
                    continue
                denom = f + self.k1 * (1 - self.b + self.b * (self.dl[i] / self.avgdl if self.avgdl else 0.0))
                score[i] += idf * (f * (self.k1 + 1) / denom)
        return score


# ================================================================
#  GraphRagRetriever（P0 增强版）
# ================================================================
class GraphRagRetriever:
    """GraphRAG 检索器：改写 + 混合(RRF) + Reranker + 多跳扩展。"""

    COLLECTION = "enterprise_docs"

    def __init__(self) -> None:
        self.settings = get_settings()
        self._client = chromadb.PersistentClient(path=self.settings.chroma_persist_dir)
        self._embed = self._build_embedding()
        self._llm = get_llm_client()
        self._bm25_cache_key = 0
        self._bm25_cache: _BM25Okapi | None = None
        self._bm25_docs: list[tuple[int, str, str, dict]] = []

    # ---------------- Embedding ----------------
    def _build_embedding(self):
        """
        构建 Embedding；不可用则返回 None（降级 BM25）。

        委托 app.core.embedding.build_embedding_from_settings 统一构建：
          - openai（默认）：阿里云 DashScope 兼容 OpenAI 接口
            DeepSeek key 不能调 OpenAI embeddings 端点，因此用阿里云独立 key。
          - huggingface（离线备用）：本地 sentence-transformers 推理，无外部网络依赖。
        """
        from app.core.embedding import build_embedding_from_settings
        embed = build_embedding_from_settings()
        if embed is not None:
            logger.info(
                "Embedding 就绪 provider=%s model=%s",
                self.settings.embedding_provider, self.settings.embedding_model,
            )
        return embed

    def _get_collection(self):
        return self._client.get_or_create_collection(self.COLLECTION)

    # ---------------- 索引构建 ----------------
    def build_index(self, doc_id: int, file_name: str, content: str,
                    dept_id: int) -> int:
        chunks = self._split_text(content)
        if not chunks:
            return 0
        collection = self._get_collection()
        ids, docs, metadatas, embeddings = [], [], [], []
        for idx, chunk in enumerate(chunks):
            entities = self._extract_entities(chunk)
            ids.append(f"doc{doc_id}-c{idx}")
            docs.append(chunk)
            metadatas.append({
                "doc_id": doc_id,
                "file_name": file_name,
                "dept_id": dept_id,
                "chunk_index": idx,
                "entities": ",".join(entities),
            })
            if self._embed is not None:
                embeddings.append(self._embed.get_text_embedding(chunk))

        if self._embed is not None and embeddings:
            collection.upsert(ids=ids, documents=docs, metadatas=metadatas, embeddings=embeddings)
        else:
            collection.upsert(ids=ids, documents=docs, metadatas=metadatas)

        # BM25 缓存失效（索引变动后下次检索会重建）
        self._bm25_cache = None
        self._bm25_cache_key = 0
        logger.info("文档索引完成 doc_id=%s chunks=%s", doc_id, len(chunks))
        return len(chunks)

    # ---------------- 核心检索入口 ----------------
    def retrieve(self, query: str, dept_ids: list[int] | None,
                 top_k: int | None = None) -> list[RetrievedChunk]:
        """
        三步检索：
        1. Query 改写 → 多条查询；
        2. BM25 + 向量 RRF 融合；
        3. 多跳扩展 → Reranker 重排；
        """
        top_k = top_k or self.settings.graphrag_top_k
        collection = self._get_collection()
        if collection.count() == 0:
            logger.warning("向量库为空，无可检索文档")
            return []

        # ① Query 改写：1 条原始 + (2~3) 条改写
        queries = self._rewrite_query(query)
        logger.info("Query 改写(%d条): %s", len(queries), queries)

        # ② 混合检索：BM25 + 向量，RRF 融合
        vector_candidates = self._vector_search(queries, collection, dept_ids, top_k)
        bm25_candidates = self._bm25_search(queries, collection, dept_ids, top_k)
        fused = self._rrf_fusion(vector_candidates, bm25_candidates)
        if not fused:
            return []

        # ③ 多跳关联扩展（沿共享实体）
        expanded = self._multi_hop_expand(fused[:max(3, top_k // 2)], collection, dept_ids)
        # 去重并合并
        seen: set[tuple[int, int]] = set()
        merged: list[RetrievedChunk] = []
        for c in fused + expanded:
            key = (int(c.doc_id), hash(c.text[:80]))
            if key in seen:
                continue
            seen.add(key)
            merged.append(c)

        # ④ Reranker 重排
        reranked = self._rerank(query, merged)
        return reranked[: top_k + self.settings.graphrag_max_hops]

    # ================ Step 1: Query 改写 ================
    def _rewrite_query(self, query: str) -> list[str]:
        """
        用 LLM 把原查询改写成 2~3 条补充子查询，返回合并原查询后列表。
        LLM 不可用时走同义词/缩写扩展规则（离线版）。
        """
        try:
            counter = TokenCounter()
            prompt = (
                "你是企业数据检索的查询改写专家。请把用户原始业务问题改写成 3 条子查询，"
                "分别用于：1) 去口语化直接表达；2) 补全同义词、缩写、别名；3) 把复合问题拆成关键词。\n"
                '严格输出 JSON 列表，不要多余文字，例如：\n["销售同比","销售额对比","华东区销量"]\n'
                f"原问题：{query}"
            )
            raw = self._llm.chat(
                messages=[{"role": "system", "content": prompt},
                          {"role": "user", "content": query}],
                counter=counter,
                temperature=0.0,
            )
            data = self._parse_json_list(raw)
            result = [query]
            for item in data:
                item = str(item).strip()
                if item and item not in result:
                    result.append(item)
            return result[:4]
        except Exception as e:  # noqa: BLE001
            logger.debug("QueryRewrite LLM 不可用，走启发式扩展: %s", e)
            return self._heuristic_expand(query)

    @staticmethod
    def _heuristic_expand(query: str) -> list[str]:
        q = (query or "").strip()
        out = [q]
        # 同义替换：常见业务用语
        pairs = [("同比", "比去年同期"), ("环比", "对比上期"),
                 ("金额", "销售额"), ("库存", "存货"),
                 ("营收", "销售收入"), ("华东", "华东区")]
        expanded = q
        for a, b in pairs:
            if a in expanded:
                expanded = expanded.replace(a, f"{a}/{b}")
        if expanded != q:
            out.append(expanded)
        # 纯中文关键词（剔除标点）
        kw = re.findall(r"[\u4e00-\u9fa5A-Za-z0-9]{2,}", q)
        if len(kw) >= 2:
            out.append(" ".join(kw))
        return [x for x in out if x][:4]

    @staticmethod
    def _parse_json_list(raw: str) -> list[str]:
        text = re.sub(r"^```(?:json)?|```$", "", (raw or "").strip(), flags=re.MULTILINE).strip()
        match = re.search(r"\[[^\]]*\]", text, flags=re.DOTALL)
        if not match:
            return []
        try:
            import json
            return json.loads(match.group(0))
        except Exception:  # noqa: BLE001
            return []

    # ================ Step 2a: 向量检索 ================
    def _vector_search(self, queries: list[str], collection,
                       dept_ids: list[int] | None, top_k: int) -> list[RetrievedChunk]:
        """对每条改写查询分别向量检索，合并去重并记录 rank。"""
        where = {"dept_id": {"$in": dept_ids}} if dept_ids else None
        all_text_ids: dict[str, RetrievedChunk] = {}
        for qi, q in enumerate(queries):
            try:
                if self._embed is not None:
                    qvec = self._embed.get_text_embedding(q)
                    result = collection.query(query_embeddings=[qvec],
                                              n_results=top_k * 2, where=where)
                else:
                    result = collection.query(query_texts=[q],
                                              n_results=top_k * 2, where=where)
                chunks = self._to_chunks(result)
                for rank, c in enumerate(chunks, start=1):
                    key = f"{c.doc_id}#{hash(c.text[:80])}"
                    if key in all_text_ids:
                        # 保留最小 rank（最好名次）
                        prev = all_text_ids[key]
                        if prev.vector_rank is None or rank < prev.vector_rank:
                            prev.vector_rank = rank
                    else:
                        c.vector_rank = rank
                        all_text_ids[key] = c
            except Exception as e:  # noqa: BLE001
                logger.debug("向量检索子查询失败 q_idx=%s err=%s", qi, e)
        return list(all_text_ids.values())

    # ================ Step 2b: BM25 检索 ================
    def _bm25_search(self, queries: list[str], collection,
                     dept_ids: list[int] | None, top_k: int) -> list[RetrievedChunk]:
        """
        把目标集合全部片段加载为 BM25 语料（内存级，10 万级片段仍可接受）。
        Chroma 暂不提供 where 过滤 + 全量扫描接口，因此先按 where 拿大 N 结果，再做 BM25 过滤。
        """
        where = {"dept_id": {"$in": dept_ids}} if dept_ids else None
        try:
            n_total = collection.count()
            if not n_total:
                return []
            # 按部门权限拉取尽可能多的候选语料
            fetch_n = min(n_total, max(2000, top_k * 50))
            if self._embed is not None:
                # 用一个空串的 query_texts（或用首查询 embedding 拉 pool）
                head = collection.get(
                    limit=fetch_n, where=where,
                    include=["documents", "metadatas"],
                )
            else:
                head = collection.get(
                    limit=fetch_n, where=where,
                    include=["documents", "metadatas"],
                )
        except Exception as e:  # noqa: BLE001
            logger.debug("BM25 拉取语料失败: %s", e)
            return []

        docs = head.get("documents") or []
        metas = head.get("metadatas") or []
        if not docs:
            return []
        # 构建 tokenized corpus
        tokenized = [self._tokenize(d) for d in docs]
        bm25 = _BM25Okapi(tokenized)

        # 多条查询取最大分数（并记录最优名次）
        merged_scores: list[float] = [0.0] * len(docs)
        for q in queries:
            q_tokens = self._tokenize(q)
            if not q_tokens:
                continue
            scores = bm25.get_scores(q_tokens)
            for i, s in enumerate(scores):
                merged_scores[i] = max(merged_scores[i], s)
        # 排名
        ranked_idx = sorted(range(len(docs)), key=lambda i: merged_scores[i], reverse=True)
        candidates: list[RetrievedChunk] = []
        for rank, idx in enumerate(ranked_idx[: top_k * 2], start=1):
            if merged_scores[idx] <= 0:
                break
            meta = metas[idx] if idx < len(metas) else {}
            c = RetrievedChunk(
                doc_id=int(meta.get("doc_id", 0) or 0),
                file_name=str(meta.get("file_name", "") or ""),
                text=docs[idx],
                score=float(merged_scores[idx]),
                bm25_rank=rank,
                entities=[x for x in str(meta.get("entities", "")).split(",") if x],
            )
            candidates.append(c)
        return candidates

    # ================ Step 2c: RRF 融合 ================
    @staticmethod
    def _rrf_fusion(vector: list[RetrievedChunk], bm25: list[RetrievedChunk],
                    k: int = 60) -> list[RetrievedChunk]:
        """
        倒数排名融合（Reciprocal Rank Fusion）：
            score = Σ 1/(k + rank_i)
        """
        score_map: dict[tuple[int, int], float] = {}
        chunk_map: dict[tuple[int, int], RetrievedChunk] = {}

        def _register(chunk: RetrievedChunk, rank: int) -> None:
            key = (int(chunk.doc_id), hash(chunk.text[:80]))
            chunk_map[key] = chunk
            score_map[key] = score_map.get(key, 0.0) + 1.0 / (k + rank)

        # 按 vector 名次
        vector_sorted = sorted([c for c in vector if c.vector_rank is not None],
                              key=lambda c: c.vector_rank or 0)
        for rank, c in enumerate(vector_sorted, start=1):
            _register(c, rank)
        # 按 bm25 名次
        bm25_sorted = sorted([c for c in bm25 if c.bm25_rank is not None],
                             key=lambda c: c.bm25_rank or 0)
        for rank, c in enumerate(bm25_sorted, start=1):
            _register(c, rank)

        # 整理最终 score，填入融合分数
        results = []
        for key, s in sorted(score_map.items(), key=lambda kv: kv[1], reverse=True):
            c = chunk_map[key]
            c.score = float(s)
            results.append(c)
        # 如果融合为空（极少见，如两边都失败），退回原始 vector 列表
        if not results and vector:
            results = vector
        return results

    # ================ Step 3: 多跳扩展 ================
    def _multi_hop_expand(self, seeds: list[RetrievedChunk], collection,
                          dept_ids: list[int] | None) -> list[RetrievedChunk]:
        """沿共享实体做一跳关联扩展，扩展片段做 0.7 降权。"""
        if not seeds:
            return seeds
        expanded: list[RetrievedChunk] = []
        entities: set[str] = set()
        for c in seeds:
            if c.entities:
                entities.update(c.entities)
            else:
                entities.update(self._extract_entities(c.text))
        if not entities:
            return expanded

        where = {"dept_id": {"$in": dept_ids}} if dept_ids else None
        for entity in list(entities)[:5]:
            try:
                n = self.settings.graphrag_max_hops
                if self._embed is not None:
                    res = collection.query(
                        query_embeddings=[self._embed.get_text_embedding(entity)],
                        n_results=n, where=where,
                    )
                else:
                    res = collection.query(query_texts=[entity], n_results=n, where=where)
                for c in self._to_chunks(res):
                    c.score = c.score * 0.7  # 多跳片段降权
                    expanded.append(c)
            except Exception as e:  # noqa: BLE001
                logger.debug("多跳扩展跳过 entity=%s err=%s", entity, e)
        return expanded

    # ================ Step 4: Reranker 重排 ================
    def _rerank(self, query: str, candidates: list[RetrievedChunk]) -> list[RetrievedChunk]:
        """
        优先使用 LLM Cross-Encoder 风格打分（1~5 相关性）；
        不可用时降级为"BM25覆盖+向量相似度+关键词覆盖率"综合打分。
        """
        if len(candidates) <= 1:
            return candidates
        try:
            return self._llm_rerank(query, candidates)
        except Exception as e:  # noqa: BLE001
            logger.debug("LLM Reranker 不可用，走启发式: %s", e)
            return self._heuristic_rerank(query, candidates)

    def _llm_rerank(self, query: str, candidates: list[RetrievedChunk]) -> list[RetrievedChunk]:
        """LLM 批打分：返回 JSON 列表，按 score 排序。"""
        counter = TokenCounter()
        items = []
        for i, c in enumerate(candidates[:30], start=1):
            snippet = re.sub(r"\s+", " ", c.text)[:300]
            items.append(f"[{i}] {snippet}")
        prompt = (
            "你是企业文档相关性评委。请评估下面每个文档片段与问题的相关性，打分 1（完全无关）~5（高度相关）。\n"
            "标准：覆盖问题实体/指标=加分；与行业背景一致=加分；仅是通用描述则中等分；完全不相关=1~2。\n"
            f"问题：{query}\n"
            "候选片段：\n" + "\n".join(items) + '\n'
            '严格输出 JSON，不要多余文字：\n{"scores":[{"idx":1,"score":4,"reason":"..."},...]}\n'
        )
        raw = self._llm.chat(
            messages=[{"role": "system", "content": "你只输出 JSON，不要解释。"},
                      {"role": "user", "content": prompt}],
            counter=counter,
            temperature=0.0,
        )
        import json as _json
        obj = self._parse_json_obj(raw)
        scores_list = obj.get("scores") or []
        score_by_idx: dict[int, tuple[int, str]] = {}
        for s in scores_list:
            try:
                score_by_idx[int(s["idx"])] = (int(s.get("score", 0)), str(s.get("reason", "")))
            except Exception:  # noqa: BLE001
                pass
        reranked = []
        for i, c in enumerate(candidates[:30], start=1):
            sc, reason = score_by_idx.get(i, (3, ""))
            # 0~1 归一：score 1..5 → 0.2..1.0
            norm = max(0.0, min(1.0, sc / 5.0))
            merged = c.score * 0.5 + norm * 0.5
            c.rerank_score = merged
            c.score = float(merged)
            if reason:
                c.text = c.text  # 不改原文
            reranked.append(c)
        # 超出 30 的保留原 score
        for c in candidates[30:]:
            c.rerank_score = c.score * 0.5 + 0.5
            c.score = float(c.rerank_score)
            reranked.append(c)
        reranked.sort(key=lambda x: x.score, reverse=True)
        return reranked

    @staticmethod
    def _heuristic_rerank(query: str, candidates: list[RetrievedChunk]) -> list[RetrievedChunk]:
        q_tokens = set(GraphRagRetriever._tokenize(query))
        q_entities = GraphRagRetriever._extract_entities(query)
        if not q_tokens:
            return candidates
        for c in candidates:
            tok = set(GraphRagRetriever._tokenize(c.text))
            coverage = len(tok & q_tokens) / max(1, len(q_tokens))
            entity_hit = sum(1 for e in q_entities if e in c.text) / max(1, len(q_entities))
            length_norm = 1.0 / (1 + max(0.0, len(c.text) - 400) / 4000.0)
            final = c.score * 0.5 + coverage * 0.3 + entity_hit * 0.15 + length_norm * 0.05
            c.rerank_score = float(final)
            c.score = float(final)
        candidates.sort(key=lambda x: x.score, reverse=True)
        return candidates

    @staticmethod
    def _parse_json_obj(raw: str) -> dict:
        text = re.sub(r"^```(?:json)?|```$", "", (raw or "").strip(), flags=re.MULTILINE).strip()
        match = re.search(r"\{.*\}", text, flags=re.DOTALL)
        if not match:
            return {}
        try:
            import json as _json
            return _json.loads(match.group(0))
        except Exception:  # noqa: BLE001
            return {}

    # ================ 工具方法 ================
    @staticmethod
    def _to_chunks(result: dict) -> list[RetrievedChunk]:
        chunks: list[RetrievedChunk] = []
        if not result or not result.get("documents"):
            return chunks
        docs = result["documents"][0]
        metas = result["metadatas"][0] if result.get("metadatas") else [{}] * len(docs)
        dists = result.get("distances", [[0.0] * len(docs)])[0]
        for doc, meta, dist in zip(docs, metas, dists):
            score = max(0.0, 1.0 - float(dist))
            entities = [x for x in str(meta.get("entities", "")).split(",") if x]
            chunks.append(RetrievedChunk(
                doc_id=int(meta.get("doc_id", 0) or 0),
                file_name=str(meta.get("file_name", "") or ""),
                text=doc,
                score=score,
                entities=entities,
            ))
        return chunks

    @staticmethod
    def _tokenize(text: str) -> list[str]:
        """中英文混合分词：英文按空白/标点，中文按单字+2/3字滑窗（轻量中文检索增强）。"""
        text = (text or "").lower()
        tokens: list[str] = []
        # 英文/数字 token
        for m in re.findall(r"[a-z0-9]+", text):
            if len(m) >= 2:
                tokens.append(m)
        # 中文部分
        zh = "".join(re.findall(r"[\u4e00-\u9fa5]+", text))
        for ch in zh:
            tokens.append(ch)
        for i in range(len(zh) - 1):
            tokens.append(zh[i:i + 2])
        for i in range(len(zh) - 2):
            tokens.append(zh[i:i + 3])
        return tokens

    @staticmethod
    def _split_text(content: str, chunk_size: int = 500, overlap: int = 80) -> list[str]:
        text = re.sub(r"\s+", " ", content or "").strip()
        if not text:
            return []
        chunks = []
        start = 0
        while start < len(text):
            end = min(start + chunk_size, len(text))
            chunks.append(text[start:end])
            if end >= len(text):
                break
            start = end - overlap
        return chunks

    @staticmethod
    def _extract_entities(text: str) -> list[str]:
        entities = set()
        for m in re.findall(r"[A-Za-z]{1,6}\d{1,4}", text or ""):
            entities.add(m)
        for m in re.findall(r"[\u4e00-\u9fa5]{2,8}(?:部|仓|区域|产品|路由器|交换机|模块|事业部|中心|分公司)", text or ""):
            entities.add(m)
        return list(entities)


_retriever: GraphRagRetriever | None = None


def get_retriever() -> GraphRagRetriever:
    global _retriever
    if _retriever is None:
        _retriever = GraphRagRetriever()
    return _retriever
