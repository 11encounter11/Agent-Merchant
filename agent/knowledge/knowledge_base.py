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
from typing import List, Dict
from pathlib import Path

from config import settings

logger = logging.getLogger(__name__)


# ============================================================
# 关键词规则（确定性匹配层）
# ============================================================
# 这些规则是"硬匹配"：只要用户输入包含关键词，就返回对应知识。
# 优点：100% 准确，不依赖 embedding 模型
# 适用场景：工单式查询、明确实体、已知别名
KEYWORD_RULES: List[Dict[str, str]] = [
    # 菜品别名
    {"keywords": ["素菜", "蔬菜", "青菜", "绿叶菜"], "text": "素菜类对应分类名：新鲜时蔬"},
    {"keywords": ["烤鱼"], "text": "烤鱼是一个菜品分类，包含：蜀味烤鱼"},
    {"keywords": ["牛蛙"], "text": "牛蛙是一个菜品分类，包含：蜀味牛蛙"},
    {"keywords": ["蒸菜"], "text": "蒸菜是一个菜品分类，对应分类名：特色蒸菜"},
    
    # 节假日
    {"keywords": ["端午节", "端午"], "text": "2026年端午节是6月19日至6月21日（农历五月初五）"},
    {"keywords": ["中秋节", "中秋"], "text": "2026年中秋节是9月25日至9月27日（农历八月十五）"},
    {"keywords": ["国庆节", "国庆"], "text": "2026年国庆节是10月1日至10月7日"},
    {"keywords": ["春节"], "text": "2026年春节是2月17日至2月23日（农历正月初一）"},
    
    # 身份
    {"keywords": ["谁开发", "你是谁", "什么模型", "GPT", "ChatGPT"], "text": "我是苍穹外卖的智能经营助手，由苍穹外卖团队开发"},
    
    # 边界
    {"keywords": ["营销文案", "写文章", "写报告"], "text": "这不在我的核心能力范围内，我主要擅长帮您查询经营数据、处理订单、管理菜品等"},
    
    # FAQ
    {"keywords": ["退款", "退单"], "text": "用户问退款多不多时，应默认查询今天的退款数据（状态7=退款），而不是反问用户时间范围"},
    {"keywords": ["打折", "折扣"], "text": "用户问打折后能赚多少时，应先主动查询最近的营业额数据，再基于数据进行推算"},
]


class KnowledgeBase:
    """
    RAG 知识库：负责知识文档的存储和语义检索。
    
    类比 Java：
    就像一个 Repository 层，封装了对数据库的 CRUD 操作。
    只不过这里操作的是向量数据库。
    """
    
    def __init__(self):
        self.logger = logging.getLogger(self.__class__.__name__)
        self._keyword_rules = KEYWORD_RULES  # 关键词匹配规则
        self._all_documents: List[Dict[str, str]] = []  # 所有文档（用于关键词匹配）
        
        # 初始化 chromadb 客户端 + DashScope 中文 embedding
        try:
            import chromadb
            from chromadb.utils import embedding_functions
            
            # 使用 DashScope 的中文 embedding 模型
            # text-embedding-v3 对中文语义理解比默认的英文模型好很多
            dashscope_ef = embedding_functions.OpenAIEmbeddingFunction(
                api_key=settings.LLM_API_KEY,
                api_base="https://dashscope.aliyuncs.com/compatible-mode/v1",
                model_name="text-embedding-v3"
            )
            
            self.client = chromadb.Client()
            self.collection = self.client.create_collection(
                name="agent_knowledge",
                metadata={"description": "苍穹外卖 Agent 知识库"},
                embedding_function=dashscope_ef
            )
            self.logger.info("[KnowledgeBase] chromadb 初始化成功（DashScope text-embedding-v3）")
            self._initialized = True
        except ImportError:
            self.logger.warning("[KnowledgeBase] chromadb 未安装，知识库功能禁用")
            self.logger.warning("[KnowledgeBase] 请运行: pip install chromadb")
            self._initialized = False
            self.client = None
            self.collection = None
        except Exception as e:
            self.logger.warning(f"[KnowledgeBase] embedding 初始化失败，退回默认: {e}")
            # 退回默认 embedding（英文模型）
            try:
                import chromadb
                self.client = chromadb.Client()
                self.collection = self.client.create_collection(
                    name="agent_knowledge",
                    metadata={"description": "苍穹外卖 Agent 知识库"}
                )
                self._initialized = True
            except:
                self._initialized = False
    
    def load_data(self, data_dir: str = None):
        """
        从 data/ 目录加载知识文档，向量化后存入 chromadb。
        同时把文档存入 _all_documents（用于关键词匹配层）。
        
        参数：
            data_dir: 知识文档目录，默认为 agent/knowledge/data/
        """
        if not self._initialized:
            self.logger.warning("[KnowledgeBase] chromadb 未初始化，跳过加载")
            return
        
        if data_dir is None:
            data_dir = Path(__file__).parent / "data"
        
        data_path = Path(data_dir)
        if not data_path.exists():
            self.logger.warning(f"[KnowledgeBase] 数据目录不存在: {data_dir}")
            return
        
        self.logger.info(f"[KnowledgeBase] 开始加载知识文档: {data_dir}")
        
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
                                # 同时存入 _all_documents（带关键词）
                                self._all_documents.append({
                                    "text": text,
                                    "keywords": item.get("keywords", []),
                                    "source": file_path.stem
                                })
                    elif isinstance(data, dict):
                        text = self._extract_text_from_dict(data)
                        if text:
                            documents.append(text)
                            ids.append(file_path.stem)
                            self._all_documents.append({"text": text, "keywords": [], "source": file_path.stem})
                except Exception as e:
                    self.logger.error(f"[KnowledgeBase] 加载 {file_path} 失败: {e}")
            
            elif file_path.suffix == ".txt":
                try:
                    with open(file_path, "r", encoding="utf-8") as f:
                        text = f.read()
                    if text.strip():
                        documents.append(text)
                        ids.append(file_path.stem)
                        self._all_documents.append({"text": text, "keywords": [], "source": file_path.stem})
                except Exception as e:
                    self.logger.error(f"[KnowledgeBase] 加载 {file_path} 失败: {e}")
        
        # 分批存入 chromadb（向量化 + 存储）
        # DashScope text-embedding-v3 单次 batch 上限为 10
        if documents:
            batch_size = 10
            for start in range(0, len(documents), batch_size):
                end = start + batch_size
                self.collection.add(
                    documents=documents[start:end],
                    ids=ids[start:end],
                )
            self.logger.info(f"[KnowledgeBase] 成功加载 {len(documents)} 条知识（向量库，每批≤{batch_size}）")
        else:
            self.logger.info("[KnowledgeBase] 没有找到知识文档")
        
        self.logger.info(f"[KnowledgeBase] 关键词规则: {len(self._keyword_rules)} 条")
        self.logger.info(f"[KnowledgeBase] 关键词文档: {len(self._all_documents)} 条")
    
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
        混合检索：关键词匹配 + 向量语义检索，合并去重后返回。
        
        参数：
            query: 用户输入
            top_k: 返回结果数量
        
        检索策略（三层）：
        1. 关键词规则匹配（KEYWORD_RULES，确定性最高）
        2. 文档关键词匹配（_all_documents 中的 keywords 字段）
        3. 向量语义检索（chromadb，处理模糊表达）
        
        合并去重后返回 top_k 条结果。
        """
        results: List[str] = []
        seen: set = set()  # 去重
        
        # ---- 第一层：关键词规则匹配（确定性最高）----
        for rule in self._keyword_rules:
            for keyword in rule["keywords"]:
                if keyword.lower() in query.lower():
                    text = rule["text"]
                    if text not in seen:
                        results.append(text)
                        seen.add(text)
                        self.logger.info(f"[RAG] 关键词匹配: '{keyword}' → {text[:30]}...")
                    break  # 一条规则只匹配一次
        
        # ---- 第二层：文档关键词匹配 ----
        for doc in self._all_documents:
            for keyword in doc.get("keywords", []):
                if keyword.lower() in query.lower():
                    text = doc["text"]
                    if text not in seen:
                        results.append(text)
                        seen.add(text)
                    break
        
        # ---- 第三层：向量语义检索（兜底，处理模糊表达）----
        if self._initialized and self.collection.count() > 0 and len(results) < top_k:
            try:
                remaining = top_k - len(results)
                vector_results = self.collection.query(
                    query_texts=[query],
                    n_results=remaining + len(results)  # 多取一些，用于去重
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
