"""
RAG 知识库（Knowledge Base）

混合检索：JSON 关键词匹配 + chromadb 向量检索。
规则只维护在 data/*.json，不在代码里再硬编码一份。
"""

import logging
import json
from typing import List, Dict
from pathlib import Path

from config import settings

logger = logging.getLogger(__name__)


class KnowledgeBase:
    """长期记忆：知识文档存储与检索。"""

    def __init__(self):
        self.logger = logging.getLogger(self.__class__.__name__)
        self._all_documents: List[Dict] = []
        self._initialized = False
        self.client = None
        self.collection = None

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
        """从 data/ 加载 JSON/TXT，向量化并缓存关键词文档。"""
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

        for file_path in data_path.glob("*"):
            if file_path.suffix == ".json":
                try:
                    with open(file_path, "r", encoding="utf-8") as f:
                        data = json.load(f)

                    if isinstance(data, list):
                        for i, item in enumerate(data):
                            if isinstance(item, dict) and "text" in item:
                                text = item["text"]
                                documents.append(text)
                                ids.append(f"{file_path.stem}_{i}")
                                self._all_documents.append({
                                    "text": text,
                                    "keywords": item.get("keywords", []),
                                    "source": file_path.stem,
                                })
                    elif isinstance(data, dict):
                        text = self._extract_text_from_dict(data)
                        if text:
                            documents.append(text)
                            ids.append(file_path.stem)
                            self._all_documents.append({
                                "text": text,
                                "keywords": [],
                                "source": file_path.stem,
                            })
                except Exception as e:
                    self.logger.error(f"[KnowledgeBase] 加载 {file_path} 失败: {e}")

            elif file_path.suffix == ".txt":
                try:
                    with open(file_path, "r", encoding="utf-8") as f:
                        text = f.read()
                    if text.strip():
                        documents.append(text)
                        ids.append(file_path.stem)
                        self._all_documents.append({
                            "text": text,
                            "keywords": [],
                            "source": file_path.stem,
                        })
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
                    )
                self.logger.info(
                    f"[KnowledgeBase] 成功加载 {len(documents)} 条知识（向量库，每批≤{batch_size}）"
                )
            except Exception as e:
                # embedding Key 无效时仍保留 JSON 关键词检索（阶段 A 验收依赖）
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

    def search_keywords(self, query: str, top_k: int = 3) -> List[str]:
        """仅 JSON keywords 匹配（零 embedding 成本）。"""
        results: List[str] = []
        seen: set = set()
        query_lower = query.lower()

        for doc in self._all_documents:
            for keyword in doc.get("keywords", []):
                if keyword.lower() in query_lower:
                    text = doc["text"]
                    if text not in seen:
                        results.append(text)
                        seen.add(text)
                        self.logger.info(f"[RAG] 关键词匹配: '{keyword}' → {text[:30]}...")
                    break
            if len(results) >= top_k:
                break

        return results[:top_k]

    def search(self, query: str, top_k: int = 3, use_vector: bool = True) -> List[str]:
        """
        混合检索：
        1. JSON keywords 关键词匹配
        2. 向量语义检索（可选；结果不足时补齐）
        """
        results = self.search_keywords(query, top_k=top_k)
        seen = set(results)

        if (
            use_vector
            and self._initialized
            and self.collection is not None
            and self.collection.count() > 0
            and len(results) < top_k
        ):
            try:
                remaining = top_k - len(results)
                vector_results = self.collection.query(
                    query_texts=[query],
                    n_results=remaining + len(results),
                )
                if vector_results and vector_results["documents"]:
                    for text in vector_results["documents"][0]:
                        if text not in seen and len(results) < top_k:
                            results.append(text)
                            seen.add(text)
            except Exception as e:
                self.logger.error(f"[KnowledgeBase] 向量检索失败: {e}")

        self.logger.info(f"[RAG] 检索完成: query='{query}', 结果数={len(results)}")
        return results[:top_k]

    def format_context(self, results: List[str]) -> str:
        """把检索结果格式化为可注入 Prompt 的文本。"""
        if not results:
            return ""
        formatted = ["以下是你可能需要的参考信息："]
        for i, text in enumerate(results, 1):
            formatted.append(f"{i}. {text}")
        return "\n".join(formatted)


knowledge_base = KnowledgeBase()
knowledge_base.load_data()
