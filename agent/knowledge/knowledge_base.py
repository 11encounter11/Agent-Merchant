"""
RAG 知识库（命中来源可观测）

混合检索：JSON 关键词匹配 + chromadb 向量补齐。规则只维护在 data/*.json。
不换 Milvus：当前文档量小，Chroma 内存库足够；换库解决不了「召回不准先改哪层」。

召回不准时由近到远改：
1. 查询 / 触发：搜错场景 → 改 context_builder 触发词或用户问法
2. 关键词层：JSON keywords 漏配 → 补 keywords（本仓库最常见）
3. 向量层：embedding 失败或语义漂 → 查 Key / query，而不是换库
4. 切片：只有长文才有意义；切太碎/太大调 RAG_CHUNK_SIZE
5. 生成：命中对但模型没用上 → 改 Prompt
"""

from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any

from agent.knowledge.chunking import split_if_long
from config import settings

logger = logging.getLogger(__name__)


def compact_hits(hits: list[dict]) -> list[dict]:
    """API / SSE 用的精简命中（不含全文）。"""
    out = []
    for h in hits or []:
        text = h.get("text") or ""
        out.append({
            "source": h.get("source") or "",
            "layer": h.get("layer") or "",
            "score": h.get("score"),
            "matched_keyword": h.get("matched_keyword") or None,
            "chunk_id": h.get("chunk_id") or "",
            "preview": text[:80],
        })
    return out


class KnowledgeBase:
    """长期记忆：知识文档存储与检索。"""

    def __init__(self, enable_vector: bool = True):
        self.logger = logging.getLogger(self.__class__.__name__)
        self._all_documents: list[dict] = []
        self._initialized = False
        self.client = None
        self.collection = None
        self.last_hits: list[dict] = []

        if not enable_vector:
            return

        try:
            import chromadb
            from chromadb.utils import embedding_functions

            embedding_key = settings.EMBEDDING_API_KEY or settings.LLM_API_KEY
            if not embedding_key:
                raise ValueError("未配置 EMBEDDING_API_KEY / LLM_API_KEY")

            dashscope_ef = embedding_functions.OpenAIEmbeddingFunction(
                api_key=embedding_key,
                api_base=settings.EMBEDDING_BASE_URL,
                model_name=settings.EMBEDDING_MODEL,
            )

            self.client = chromadb.Client()
            self.collection = self.client.create_collection(
                name="agent_knowledge",
                metadata={"description": "苍穹外卖 Agent 知识库"},
                embedding_function=dashscope_ef,
            )
            self.logger.info(
                f"[KnowledgeBase] chromadb 初始化成功（{settings.EMBEDDING_MODEL}）"
            )
            self._initialized = True
        except ImportError:
            self.logger.warning("[KnowledgeBase] chromadb 未安装，知识库向量功能禁用")
            self.logger.warning("[KnowledgeBase] 请运行: pip install chromadb")
        except Exception as e:
            self.logger.warning(f"[KnowledgeBase] embedding 初始化失败，退回默认: {e}")
            try:
                import chromadb

                self.client = chromadb.Client()
                self.collection = self.client.create_collection(
                    name="agent_knowledge",
                    metadata={"description": "苍穹外卖 Agent 知识库"},
                )
                self._initialized = True
            except Exception as fallback_err:
                self.logger.error(f"[KnowledgeBase] chromadb 初始化失败: {fallback_err}")
                self._initialized = False

    def load_data(self, data_dir: str = None):
        """从 data/ 加载 JSON/TXT；长文按 RAG_CHUNK_SIZE 切片。"""
        if data_dir is None:
            data_dir = Path(__file__).parent / "data"

        data_path = Path(data_dir)
        if not data_path.exists():
            self.logger.warning(f"[KnowledgeBase] 数据目录不存在: {data_dir}")
            return

        self.logger.info(f"[KnowledgeBase] 开始加载知识文档: {data_dir}")
        self._all_documents = []

        documents = []
        ids = []
        metadatas = []

        for file_path in data_path.glob("*"):
            if file_path.suffix == ".json":
                try:
                    with open(file_path, "r", encoding="utf-8") as f:
                        data = json.load(f)
                    self._ingest_json(file_path, data, documents, ids, metadatas)
                except Exception as e:
                    self.logger.error(f"[KnowledgeBase] 加载 {file_path} 失败: {e}")
            elif file_path.suffix == ".txt":
                try:
                    with open(file_path, "r", encoding="utf-8") as f:
                        text = f.read()
                    self._ingest_text(
                        source=file_path.stem,
                        text=text,
                        keywords=[],
                        item_index=0,
                        documents=documents,
                        ids=ids,
                        metadatas=metadatas,
                    )
                except Exception as e:
                    self.logger.error(f"[KnowledgeBase] 加载 {file_path} 失败: {e}")

        if self._initialized and documents:
            try:
                batch_size = 10
                for start in range(0, len(documents), batch_size):
                    end = start + batch_size
                    self.collection.add(
                        documents=documents[start:end],
                        ids=ids[start:end],
                        metadatas=metadatas[start:end],
                    )
                self.logger.info(
                    f"[KnowledgeBase] 成功加载 {len(documents)} 条知识（向量库，每批≤{batch_size}）"
                )
            except Exception as e:
                self.logger.warning(
                    f"[KnowledgeBase] 向量写入失败，退回仅关键词模式: {e}"
                )
                self._initialized = False
                self.collection = None
        elif documents:
            self.logger.info(
                f"[KnowledgeBase] 已加载 {len(documents)} 条知识（仅关键词，无向量库）"
            )
        else:
            self.logger.info("[KnowledgeBase] 没有找到知识文档")

        self.logger.info(f"[KnowledgeBase] 关键词文档: {len(self._all_documents)} 条")

    def _ingest_json(
        self,
        file_path: Path,
        data: Any,
        documents: list,
        ids: list,
        metadatas: list,
    ) -> None:
        if isinstance(data, list):
            for i, item in enumerate(data):
                if isinstance(item, dict) and "text" in item:
                    self._ingest_text(
                        source=file_path.stem,
                        text=item["text"],
                        keywords=item.get("keywords") or [],
                        item_index=i,
                        documents=documents,
                        ids=ids,
                        metadatas=metadatas,
                    )
        elif isinstance(data, dict):
            text = self._extract_text_from_dict(data)
            if text:
                self._ingest_text(
                    source=file_path.stem,
                    text=text,
                    keywords=[],
                    item_index=0,
                    documents=documents,
                    ids=ids,
                    metadatas=metadatas,
                )

    def _ingest_text(
        self,
        *,
        source: str,
        text: str,
        keywords: list,
        item_index: int,
        documents: list,
        ids: list,
        metadatas: list,
    ) -> None:
        pieces = split_if_long(
            text,
            settings.RAG_CHUNK_SIZE,
            settings.RAG_CHUNK_OVERLAP,
        )
        for ci, piece in enumerate(pieces):
            chunk_id = (
                f"{source}_{item_index}"
                if len(pieces) == 1
                else f"{source}_{item_index}_c{ci}"
            )
            documents.append(piece)
            ids.append(chunk_id)
            metadatas.append({"source": source, "chunk_id": chunk_id})
            self._all_documents.append({
                "text": piece,
                "keywords": keywords,
                "source": source,
                "chunk_id": chunk_id,
            })

    def _extract_text_from_dict(self, data: dict) -> str:
        texts = []
        for key, value in data.items():
            if isinstance(value, str):
                texts.append(f"{key}: {value}")
            elif isinstance(value, list):
                for item in value:
                    if isinstance(item, str):
                        texts.append(item)
        return "\n".join(texts)

    def search_keywords(self, query: str, top_k: int = 3) -> list[str]:
        """兼容旧接口：只返回文本。"""
        return [h["text"] for h in self.search_keyword_hits(query, top_k=top_k)]

    def search_keyword_hits(self, query: str, top_k: int = 3) -> list[dict]:
        """JSON keywords 匹配，带来源。"""
        hits: list[dict] = []
        seen: set[str] = set()
        query_lower = query.lower()

        for doc in self._all_documents:
            for keyword in doc.get("keywords") or []:
                if keyword.lower() in query_lower:
                    text = doc["text"]
                    if text in seen:
                        break
                    seen.add(text)
                    hits.append({
                        "text": text,
                        "source": doc.get("source") or "",
                        "layer": "keyword",
                        "score": 1.0,
                        "chunk_id": doc.get("chunk_id") or "",
                        "matched_keyword": keyword,
                    })
                    self.logger.info(
                        f"[RAG] 关键词命中 source={doc.get('source')} "
                        f"kw={keyword!r} chunk={doc.get('chunk_id')}"
                    )
                    break
            if len(hits) >= top_k:
                break
        return hits[:top_k]

    def search_hits(
        self,
        query: str,
        top_k: int | None = None,
        use_vector: bool = True,
    ) -> list[dict]:
        """
        混合检索，返回结构化命中：
        source / layer(keyword|vector) / score / chunk_id / matched_keyword / text
        """
        top_k = top_k if top_k is not None else settings.RAG_TOP_K
        hits = self.search_keyword_hits(query, top_k=top_k)
        seen = {h["text"] for h in hits}

        if (
            use_vector
            and self._initialized
            and self.collection is not None
            and self.collection.count() > 0
            and len(hits) < top_k
        ):
            try:
                remaining = top_k - len(hits)
                vector_results = self.collection.query(
                    query_texts=[query],
                    n_results=remaining + len(hits),
                    include=["documents", "distances", "metadatas"],
                )
                docs = (vector_results.get("documents") or [[]])[0]
                dists = (vector_results.get("distances") or [[]])[0]
                metas = (vector_results.get("metadatas") or [[]])[0]
                ids = (vector_results.get("ids") or [[]])[0]
                for i, text in enumerate(docs):
                    if text in seen or len(hits) >= top_k:
                        continue
                    meta = metas[i] if i < len(metas) and metas[i] else {}
                    dist = dists[i] if i < len(dists) else None
                    score = None
                    if dist is not None:
                        try:
                            score = round(1.0 / (1.0 + float(dist)), 4)
                        except (TypeError, ValueError):
                            score = None
                    chunk_id = (meta or {}).get("chunk_id") or (
                        ids[i] if i < len(ids) else ""
                    )
                    source = (meta or {}).get("source") or ""
                    hits.append({
                        "text": text,
                        "source": source,
                        "layer": "vector",
                        "score": score,
                        "chunk_id": chunk_id,
                        "matched_keyword": "",
                    })
                    seen.add(text)
                    self.logger.info(
                        f"[RAG] 向量补齐 source={source} score={score} chunk={chunk_id}"
                    )
            except Exception as e:
                self.logger.error(f"[KnowledgeBase] 向量检索失败: {e}")

        by_layer: dict[str, int] = {}
        for h in hits:
            by_layer[h["layer"]] = by_layer.get(h["layer"], 0) + 1
        sources = ",".join(sorted({h["source"] for h in hits if h.get("source")}))
        self.logger.info(
            f"[RAG] 检索完成 query={query!r} hits={len(hits)} "
            f"layers={by_layer or '-'} sources={sources or '-'}"
        )
        self.last_hits = hits
        return hits[:top_k]

    def search(self, query: str, top_k: int = 3, use_vector: bool = True) -> list[str]:
        """兼容旧接口：只返回文本列表。"""
        return [h["text"] for h in self.search_hits(query, top_k=top_k, use_vector=use_vector)]

    def format_context(self, results: list) -> str:
        """把检索结果格式化为可注入 Prompt 的文本（带来源/层级）。"""
        if not results:
            return ""
        formatted = [
            "以下是参考信息（已标注来源与召回层；请优先采用，不要编造来源）："
        ]
        for i, item in enumerate(results, 1):
            if isinstance(item, dict):
                source = item.get("source") or "unknown"
                layer = item.get("layer") or "?"
                kw = item.get("matched_keyword") or ""
                extra = f" | 命中:{kw}" if kw else ""
                text = item.get("text") or ""
                formatted.append(f"{i}. [来源:{source} | 层:{layer}{extra}] {text}")
            else:
                formatted.append(f"{i}. {item}")
        return "\n".join(formatted)


knowledge_base = KnowledgeBase()
knowledge_base.load_data()
