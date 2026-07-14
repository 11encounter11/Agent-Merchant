"""
记忆模块（Memory Module）

职责：统一管理三类记忆（对照文章的三层记忆设计）。

对照文章的 7 大模块：
- 文章方案：Redis（工作记忆）+ PostgreSQL（短期记忆）+ Milvus（长期记忆）
- 我们方案：
  - 工作记忆：session.py（内存/JSON 文件）→ 当前对话上下文
  - 短期记忆：暂不实现（未来可存最近会话摘要）
  - 长期记忆：knowledge/（chromadb 向量库）→ RAG 知识库

为什么需要这个模块？
1. 统一管理所有记忆相关的操作
2. 在 call_llm 前组装完整上下文（会话历史 + 知识检索）
3. 让 chat_agent.py 不需要关心记忆的细节
"""

import logging
from typing import List
from langchain_core.messages import BaseMessage, HumanMessage

from agent.session import get_history, save_history
from agent.knowledge.knowledge_base import knowledge_base

logger = logging.getLogger(__name__)


class Memory:
    """
    记忆管理器：统一管理会话记忆和知识记忆。
    
    类比 Java：
    就像一个 Service 层，封装了多个 DAO 的调用：
    - sessionDao → 工作记忆
    - knowledgeDao → 长期记忆
    """
    
    def __init__(self):
        self.logger = logging.getLogger(self.__class__.__name__)
        self.kb = knowledge_base  # 长期记忆（RAG 知识库）
    
    def get_working_memory(self, session_id: str) -> List[BaseMessage]:
        """
        获取工作记忆（当前对话上下文）。
        
        参数：
            session_id: 会话 ID
        
        返回：
            历史消息列表
        
        类比 Java：
        SELECT * FROM session_history WHERE session_id = ? ORDER BY create_time
        """
        history = get_history(session_id)
        self.logger.info(f"[Memory] 获取工作记忆: session={session_id}, 消息数={len(history)}")
        return history
    
    def save_working_memory(self, session_id: str, messages: List[BaseMessage]):
        """
        保存工作记忆（更新对话历史）。
        
        参数：
            session_id: 会话 ID
            messages: 完整的消息列表（包含本次对话）
        
        类比 Java：
        INSERT INTO session_history (session_id, messages) VALUES (?, ?)
        ON DUPLICATE KEY UPDATE messages = ?
        """
        save_history(session_id, messages)
        self.logger.info(f"[Memory] 保存工作记忆: session={session_id}, 消息数={len(messages)}")
    
    def search_knowledge(self, query: str, top_k: int = 3) -> List[str]:
        """
        从知识库检索相关知识（长期记忆）。
        
        参数：
            query: 用户输入（检索关键词）
            top_k: 返回最相关的 top_k 条
        
        返回：
            相关知识文本列表
        
        类比 Java：
        调用 Milvus/ES 的向量检索接口
        """
        results = self.kb.search(query, top_k)
        self.logger.info(f"[Memory] 知识检索: query='{query}', 结果数={len(results)}")
        return results
    
    def build_context(self, session_id: str, user_input: str) -> List[BaseMessage]:
        """
        组装完整上下文：工作记忆 + 知识检索结果 → 拼成 messages。
        
        参数：
            session_id: 会话 ID
            user_input: 用户输入（清洗后）
        
        返回：
            完整的消息列表（System Prompt + 知识上下文 + 历史消息 + 当前输入）
        
        这个方法做什么：
        1. 从 session.py 获取历史消息
        2. 从知识库检索相关知识
        3. 把知识检索结果格式化为 SystemMessage（注入到 Prompt）
        4. 拼接：[历史消息] + [当前用户输入]
        
        类比 Java：
        就像在 Service 层组装 DTO：
        - 从多个数据源查数据
        - 拼装成一个完整的对象返回
        """
        # 1. 获取工作记忆
        history = self.get_working_memory(session_id)
        
        # 2. 从知识库检索相关知识
        knowledge_results = self.search_knowledge(user_input, top_k=3)
        
        # 3. 如果有相关知识，格式化为上下文消息
        if knowledge_results:
            knowledge_context = self._format_knowledge(knowledge_results)
            # 把知识上下文作为 SystemMessage 插入到历史消息前面
            # 这样 LLM 在看到历史消息之前，先看到相关知识
            knowledge_msg = HumanMessage(content=f"[参考信息]\n{knowledge_context}")
            messages = [knowledge_msg] + history
        else:
            messages = history
        
        # 4. 添加当前用户输入
        user_message = HumanMessage(content=user_input)
        messages.append(user_message)
        
        self.logger.info(f"[Memory] 组装上下文: session={session_id}, 总消息数={len(messages)}")
        
        return messages
    
    def _format_knowledge(self, results: List[str]) -> str:
        """
        把知识检索结果格式化为可注入 Prompt 的文本。
        
        参数：
            results: 知识检索结果列表
        
        返回：
            格式化后的文本字符串
        """
        if not results:
            return ""
        
        formatted = []
        for i, text in enumerate(results, 1):
            formatted.append(f"{i}. {text}")
        
        return "\n".join(formatted)


# 全局实例
memory = Memory()
