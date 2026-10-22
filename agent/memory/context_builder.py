"""
上下文组装（Context Builder）

做什么：
- 组装发给 LLM 的完整上下文：[RAG 参考信息] + [会话历史] + [情境信息] + [当前输入]
- 把意图类型透传给知识库，由知识库决定要不要打 embedding 补向量
  （策略与理由见 knowledge_base._vector_allowed）
- 带回 rag_hits，便于日志 / SSE 标出命中来源与层级

不做什么：
- 不做会话存储（那是 session_memory 的事）
- 不做检索实现（那是 knowledge_base 的事）
"""

import logging
from typing import List, Tuple

from langchain_core.messages import BaseMessage, HumanMessage

from agent.memory.session_memory import session_memory
from agent.workbench.rule_rag import format_rule_context, search_rules, should_use_rules

logger = logging.getLogger(__name__)


class ContextBuilder:
    """上下文组装器。"""

    def __init__(self, knowledge_base=None):
        self.kb = knowledge_base
        self.last_hits: list[dict] = []

    def build_context(
        self, session_id: str, user_input: str, intent_type: str = "",
        widget_context: str = "",
    ) -> List[BaseMessage]:
        """同步组装（读文件历史）。"""
        history = session_memory.get_history(session_id)
        messages, _ = self._assemble(
            session_id, user_input, history, intent_type, widget_context
        )
        return messages

    async def abuild_context(
        self, session_id: str, user_input: str, intent_type: str = "",
        widget_context: str = "",
    ) -> Tuple[List[BaseMessage], list]:
        """异步组装，返回 (messages, rag_hits)。"""
        history = await session_memory.aget_history(session_id)
        return self._assemble(
            session_id, user_input, history, intent_type, widget_context
        )

    def _assemble(
        self,
        session_id: str,
        user_input: str,
        history: List[BaseMessage],
        intent_type: str = "",
        widget_context: str = "",
    ) -> Tuple[List[BaseMessage], list]:
        messages = list(history)
        rag_hits: list = []

        if self.kb:
            rag_hits = self.kb.search_hits(user_input, intent_type=intent_type)
            if rag_hits:
                knowledge_text = self.kb.format_context(rag_hits)
                messages.insert(0, HumanMessage(content=f"[参考信息]\n{knowledge_text}"))

        # 规则只在与规则/合规相关的问法里注入，避免污染普通查数问题
        if should_use_rules(user_input):
            rule_hits = search_rules(user_input)
            if rule_hits:
                messages.insert(0, HumanMessage(content=format_rule_context(rule_hits)))
                rag_hits = rule_hits + rag_hits

        self.last_hits = rag_hits
        if widget_context:
            # 只注入服务端校验/清洗后的选中键摘要，不接收前端数值
            messages.append(HumanMessage(content=widget_context))
        messages.append(HumanMessage(content=user_input))
        logger.info(
            f"[ContextBuilder] session={session_id} messages={len(messages)} "
            f"rag_hits={len(rag_hits)} layers={[h.get('layer') for h in rag_hits]}"
        )
        return messages, rag_hits
