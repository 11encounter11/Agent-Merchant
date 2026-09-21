"""
上下文组装（Context Builder）

做什么：
- 组装发给 LLM 的完整上下文：[RAG 参考信息] + [会话历史] + [情境信息] + [当前输入]
- 判断是否需要向量补齐（JSON keywords 始终检索，避免无用 embedding）
- 带回 rag_hits，便于日志 / SSE 标出命中来源与层级

不做什么：
- 不做会话存储（那是 session_memory 的事）
- 不做检索实现（那是 knowledge_base 的事）
"""

import logging
from typing import List, Tuple

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
        self.last_hits: list[dict] = []

    def _needs_vector_search(self, query: str) -> bool:
        """关键词不足时才打 embedding。"""
        query_lower = query.lower()
        return any(kw in query_lower for kw in _KNOWLEDGE_TRIGGER_KW)

    def build_context(self, session_id: str, user_input: str) -> List[BaseMessage]:
        """同步组装（读文件历史）。"""
        history = session_memory.get_history(session_id)
        messages, _ = self._assemble(session_id, user_input, history)
        return messages

    async def abuild_context(
        self, session_id: str, user_input: str
    ) -> Tuple[List[BaseMessage], list]:
        """异步组装，返回 (messages, rag_hits)。"""
        history = await session_memory.aget_history(session_id)
        return self._assemble(session_id, user_input, history)

    def _assemble(
        self, session_id: str, user_input: str, history: List[BaseMessage]
    ) -> Tuple[List[BaseMessage], list]:
        messages = list(history)
        rag_hits: list = []

        if self.kb:
            use_vector = self._needs_vector_search(user_input)
            if hasattr(self.kb, "search_hits"):
                rag_hits = self.kb.search_hits(
                    user_input, use_vector=use_vector
                )
            else:
                texts = self.kb.search(user_input, top_k=3, use_vector=use_vector)
                rag_hits = [{"text": t, "source": "", "layer": "unknown"} for t in texts]
            if rag_hits:
                knowledge_text = self.kb.format_context(rag_hits)
                messages.insert(0, HumanMessage(content=f"[参考信息]\n{knowledge_text}"))

        self.last_hits = rag_hits
        messages.append(HumanMessage(content=user_input))
        logger.info(
            f"[ContextBuilder] session={session_id} messages={len(messages)} "
            f"rag_hits={len(rag_hits)}"
        )
        return messages, rag_hits
