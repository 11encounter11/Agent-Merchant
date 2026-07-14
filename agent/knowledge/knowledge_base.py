"""
RAG 知识库（Knowledge Base）

职责：长期记忆的存储和检索。用 chromadb 实现向量检索。

对照文章的 7 大模块：
- 文章方案：Milvus 向量库 + PostgreSQL 混合检索
- 我们方案：chromadb（纯 Python，无需额外部署，适合教学项目）

什么是 RAG？
RAG = Retrieval-Augmented Generation（检索增强生成）
简单说就是：用户提问时，先从知识库里检索相关信息，
把信息注入到 Prompt 里，再送给 LLM，让 LLM 基于真实数据回答。

为什么用 RAG 而不是全写在 Prompt 里？
1. Prompt 有长度限制（Token 上限）
2. 知识可以独立维护，不用改代码
3. 按需检索，只注入相关信息，节省 Token
4. 知识可以动态更新（加新文档不用重启服务）

chromadb 是什么？
一个轻量级的向量数据库，纯 Python 实现，不需要额外安装数据库服务。
适合教学项目和小规模应用。
"""

import logging
import json
import os
from typing import List
from pathlib import Path

logger = logging.getLogger(__name__)


class KnowledgeBase:
    """
    RAG 知识库：负责知识文档的存储和语义检索。
    
    类比 Java：
    就像一个 Repository 层，封装了对数据库的 CRUD 操作。
    只不过这里操作的是向量数据库。
    """
    
    def __init__(self):
        self.logger = logging.getLogger(self.__class__.__name__)
        
        # 初始化 chromadb 客户端
        # 当前用内存模式（进程重启后数据丢失）
        # 未来可以改为持久化模式（存到磁盘）
        try:
            import chromadb
            self.client = chromadb.Client()
            self.collection = self.client.create_collection(
                name="agent_knowledge",
                metadata={"description": "苍穹外卖 Agent 知识库"}
            )
            self.logger.info("[KnowledgeBase] chromadb 初始化成功")
            self._initialized = True
        except ImportError:
            self.logger.warning("[KnowledgeBase] chromadb 未安装，知识库功能禁用")
            self.logger.warning("[KnowledgeBase] 请运行: pip install chromadb")
            self._initialized = False
            self.client = None
            self.collection = None
    
    def load_data(self, data_dir: str = None):
        """
        从 data/ 目录加载知识文档，向量化后存入 chromadb。
        
        参数：
            data_dir: 知识文档目录，默认为 agent/knowledge/data/
        
        支持的格式：
        - JSON 文件：自动解析并提取文本
        - TXT 文件：直接读取文本
        
        类比 Java：
        就像应用启动时从 resources/ 目录加载配置文件
        """
        if not self._initialized:
            self.logger.warning("[KnowledgeBase] chromadb 未初始化，跳过加载")
            return
        
        if data_dir is None:
            # 默认路径：agent/knowledge/data/
            data_dir = Path(__file__).parent / "data"
        
        data_path = Path(data_dir)
        if not data_path.exists():
            self.logger.warning(f"[KnowledgeBase] 数据目录不存在: {data_dir}")
            return
        
        self.logger.info(f"[KnowledgeBase] 开始加载知识文档: {data_dir}")
        
        documents = []
        ids = []
        
        # 遍历 data/ 目录下的所有文件
        for file_path in data_path.glob("*"):
            if file_path.suffix == ".json":
                # JSON 文件
                try:
                    with open(file_path, "r", encoding="utf-8") as f:
                        data = json.load(f)
                    
                    # 根据 JSON 结构提取文本
                    if isinstance(data, list):
                        for i, item in enumerate(data):
                            if isinstance(item, dict) and "text" in item:
                                documents.append(item["text"])
                                ids.append(f"{file_path.stem}_{i}")
                    elif isinstance(data, dict):
                        # 单个对象，提取所有字符串值
                        text = self._extract_text_from_dict(data)
                        if text:
                            documents.append(text)
                            ids.append(file_path.stem)
                except Exception as e:
                    self.logger.error(f"[KnowledgeBase] 加载 {file_path} 失败: {e}")
            
            elif file_path.suffix == ".txt":
                # TXT 文件
                try:
                    with open(file_path, "r", encoding="utf-8") as f:
                        text = f.read()
                    if text.strip():
                        documents.append(text)
                        ids.append(file_path.stem)
                except Exception as e:
                    self.logger.error(f"[KnowledgeBase] 加载 {file_path} 失败: {e}")
        
        # 批量存入 chromadb
        if documents:
            self.collection.add(
                documents=documents,
                ids=ids
            )
            self.logger.info(f"[KnowledgeBase] 成功加载 {len(documents)} 条知识")
        else:
            self.logger.info("[KnowledgeBase] 没有找到知识文档")
    
    def _extract_text_from_dict(self, data: dict) -> str:
        """
        从字典中提取所有字符串值，拼接成文本。
        
        参数：
            data: 字典对象
        
        返回：
            拼接后的文本字符串
        """
        texts = []
        for key, value in data.items():
            if isinstance(value, str):
                texts.append(f"{key}: {value}")
            elif isinstance(value, list):
                for item in value:
                    if isinstance(item, str):
                        texts.append(item)
        return "\n".join(texts)
    
    def search(self, query: str, top_k: int = 3) -> List[str]:
        """
        语义检索：返回最相关的 top_k 条知识。
        
        参数：
            query: 用户输入（检索关键词）
            top_k: 返回结果数量
        
        返回：
            相关知识文本列表
        
        工作原理：
        1. 把 query 转成向量（chromadb 自动处理）
        2. 在向量库里找最相似的 top_k 条文档
        3. 返回文档文本
        
        类比 Java：
        就像 Elasticsearch 的全文检索，但用的是向量相似度而不是关键词匹配
        """
        if not self._initialized or self.collection.count() == 0:
            return []
        
        try:
            results = self.collection.query(
                query_texts=[query],
                n_results=top_k
            )
            
            # chromadb 返回格式：{"documents": [["doc1", "doc2", ...]], ...}
            if results and results["documents"]:
                return results["documents"][0]
            return []
        except Exception as e:
            self.logger.error(f"[KnowledgeBase] 检索失败: {e}")
            return []
    
    def format_context(self, results: List[str]) -> str:
        """
        把检索结果格式化为可注入 Prompt 的文本。
        
        参数：
            results: 知识检索结果列表
        
        返回：
            格式化后的文本字符串
        
        示例输出：
        "以下是你可能需要的参考信息：
        1. 2026年端午节是6月19日-6月21日
        2. 素菜类对应分类名：新鲜时蔬"
        """
        if not results:
            return ""
        
        formatted = ["以下是你可能需要的参考信息："]
        for i, text in enumerate(results, 1):
            formatted.append(f"{i}. {text}")
        
        return "\n".join(formatted)


# 全局实例
knowledge_base = KnowledgeBase()

# 启动时自动加载知识文档（如果 data/ 目录存在）
if knowledge_base._initialized:
    knowledge_base.load_data()
