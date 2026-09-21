"""reflect：输出安全校验；越界/护栏无回复时补文案。规则在 reflection.py。"""

import logging

from langchain_core.messages import AIMessage

from agent.state import AgentState
from agent.reflection import sanitize as reflect_sanitize
from agent.guards import guard_user_message

logger = logging.getLogger(__name__)


def reflect(state: AgentState) -> dict:
    """输出安全校验；boundary / 护栏无有效回复时补文案。"""
    messages = state.get("messages") or []
    user_input = state.get("user_input", "")
    intent = state.get("intent", {})
    guard_reason = state.get("guard_reason") or ""

    if intent.get("intent") in ("boundary", "security_block"):
        if intent.get("intent") == "security_block":
            refusal = (
                "我无法执行这类请求。我是苍穹外卖的经营顾问，"
                "只处理经营数据查询、诊断和建议，不会忽略系统规则或泄露内部提示。"
            )
            logger.info("[Reflect] 注入拦截")
        else:
            refusal = (
                "这不在我的核心能力范围内。"
                "我主要帮您做经营数据分析、诊断和下一步建议。"
            )
            logger.info("[Reflect] boundary 拒绝")
        return {"messages": [AIMessage(content=refusal)]}

    if not messages:
        if guard_reason:
            return {"messages": [AIMessage(content=guard_user_message(guard_reason))]}
        return {}

    last_message = messages[-1]
    if not isinstance(last_message, AIMessage):
        if guard_reason:
            return {"messages": [AIMessage(content=guard_user_message(guard_reason))]}
        return {}

    original = last_message.content or ""
    if not original.strip() and guard_reason:
        return {"messages": [AIMessage(content=guard_user_message(guard_reason))]}

    sanitized = reflect_sanitize(original, user_input)
    if original != sanitized:
        logger.info("[Reflect] 输出被修改")
        return {"messages": [AIMessage(content=sanitized)]}

    return {}
