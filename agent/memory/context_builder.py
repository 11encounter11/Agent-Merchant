"""
上下文组装（Context Builder）

做什么：
- 组装发给 LLM 的完整上下文：[RAG 参考信息] + [会话历史] + [情境信息] + [当前输入]
- 判断是否需要 RAG 检索（避免无用 embedding 请求）

不做什么：
- 不做会话存储（那是 session_memory 的事）
- 不做 RAG 检索（那是 knowledge_base 的事）
"""

import logging
from typing import List

from langchain_core.messages import BaseMessage, HumanMessage

from agent.memory.session_memory import session_memory

logger = logging.getLogger(__name__)

# 触发向量补齐的关键词（JSON keywords 匹配始终执行，不依赖本列表）
_KNOWLEDGE_TRIGGER_KW = [
    "端午", "中秋", "国庆", "元旦", "春节", "清明", "劳动节", "五一", "节日", "节假日",
    "素菜", "蔬菜", "荤菜", "烤鱼", "牛蛙", "汤", "蒸菜", "别名", "分类",
    "你是谁", "你叫什么", "什么模型", "GPT", "ChatGPT", "谁开发",
    "退款", "退单", "打折", "折扣",
    "接单", "拒单", "停售", "起售", "写文案", "营销文案",
]


class ContextBuilder:
    """上下文组装器。"""

    def __init__(self, knowledge_base=None):
        self.kb = knowledge_base

    def _needs_knowledge_search(self, query: str) -> bool:
        """判断是否需要 RAG 检索。"""
        query_lower = query.lower()
        return any(kw in query_lower for kw in _KNOWLEDGE_TRIGGER_KW)

    def build_context(self, session_id: str, user_input: str) -> List[BaseMessage]:
        """同步组装（读文件历史）。"""
        history = session_memory.get_history(session_id)
        return self._assemble(session_id, user_input, history)

    async def abuild_context(self, session_id: str, user_input: str) -> List[BaseMessage]:
        """异步组装（Redis 热缓存 → 文件）。"""
        history = await session_memory.aget_history(session_id)
        return self._assemble(session_id, user_input, history)

    def _assemble(
        self, session_id: str, user_input: str, history: List[BaseMessage]
    ) -> List[BaseMessage]:
        messages = list(history)

        if self.kb:
            use_vector = self._needs_knowledge_search(user_input)
            results = self.kb.search(user_input, top_k=3, use_vector=use_vector)
            if results:
                knowledge_text = self.kb.format_context(results)
                messages.insert(0, HumanMessage(content=f"[参考信息]\n{knowledge_text}"))

        messages.append(HumanMessage(content=user_input))
        logger.info(
            f"[ContextBuilder] 组装上下文: session={session_id}, 消息数={len(messages)}"
        )
        return messages
