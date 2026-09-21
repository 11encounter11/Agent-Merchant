"""analyst：只负责让模型选出 tool_calls。查库不在这里，在 execute_tools。"""

import logging

from langchain_core.messages import AIMessage, HumanMessage, SystemMessage
from langchain_core.runnables import RunnableConfig

from agent.state import AgentState
from agent.prompts import ANALYST_PROMPT
from agent.security import filter_tools, is_tool_allowed, injection_system_note
from agent.tools import ALL_TOOLS
from agent.guards import (
    remaining_tool_quota,
    is_tool_steps_exceeded,
    is_token_budget_exceeded,
    merge_token_usage,
)
from agent.workers.common import try_invoke_routed

logger = logging.getLogger(__name__)


def _response_with_calls(response, tool_calls: list) -> AIMessage:
    return AIMessage(
        content=getattr(response, "content", "") or "",
        tool_calls=tool_calls,
        id=getattr(response, "id", None),
    )


def analyst(state: AgentState, config: RunnableConfig | None = None) -> dict:
    """让绑定工具的 LLM 决定调用哪些分析工具（受步数/token 护栏约束）。"""
    user_input = state.get("user_input", "")
    context = state.get("context", {})
    intent = state.get("intent", {})
    token_usage = state.get("token_usage") or {}
    tool_steps = int(state.get("tool_steps") or 0)

    if is_token_budget_exceeded(token_usage):
        logger.warning("[Analyst] token 预算已满，跳过选型")
        return {"guard_reason": "token_budget"}

    if is_tool_steps_exceeded(tool_steps):
        logger.warning("[Analyst] 工具步数已满，跳过选型")
        return {"guard_reason": "max_tool_steps"}

    security = state.get("security") or {}
    intent_type = (intent or {}).get("intent") or "unknown"
    gated_tools = filter_tools(ALL_TOOLS, intent_type, security)
    if not gated_tools:
        logger.info(f"[Analyst] 工具门禁：intent={intent_type} 无可用工具，跳过")
        return {"guard_reason": "tools_locked"}

    logger.info(
        f"[Analyst] 开始数据分析, intent={intent_type} "
        f"tools={[t.name for t in gated_tools]}"
    )

    extra_sys = [
        f"当前日期：{context.get('current_date', '')} "
        f"星期{context.get('weekday', '')}。"
        f"本轮剩余可调工具步数：{remaining_tool_quota(tool_steps)}。"
    ]
    inj_note = injection_system_note(security)
    if inj_note:
        extra_sys.append(inj_note)

    messages = [
        SystemMessage(content=ANALYST_PROMPT),
        SystemMessage(content="\n".join(extra_sys)),
        HumanMessage(content=user_input),
    ]
    response = try_invoke_routed(messages, tier="large", tools=gated_tools, config=config)
    if response is None:
        return {"guard_reason": "llm_unavailable"}
    token_usage = merge_token_usage(token_usage, response)

    tool_calls = list(getattr(response, "tool_calls", None) or [])
    quota = remaining_tool_quota(tool_steps)
    guard_reason = state.get("guard_reason") or ""

    gated_calls = [
        tc for tc in tool_calls
        if is_tool_allowed(intent_type, tc.get("name", ""), security)
    ]
    if len(gated_calls) < len(tool_calls):
        gated_ids = {id(tc) for tc in gated_calls}
        dropped = [tc.get("name") for tc in tool_calls if id(tc) not in gated_ids]
        logger.warning(f"[Analyst] 工具门禁丢弃: {dropped}")
        tool_calls = gated_calls
        response = _response_with_calls(response, tool_calls)

    if tool_calls and len(tool_calls) > quota:
        logger.warning(
            f"[Analyst] tool_calls={len(tool_calls)} 超过剩余配额 {quota}，截断"
        )
        tool_calls = tool_calls[:quota]
        response = _response_with_calls(response, tool_calls)
        guard_reason = "max_tool_steps"

    tool_names = [tc.get("name", "") for tc in tool_calls]
    logger.info(f"[Analyst] tool_calls={tool_names or '无'}")

    if is_token_budget_exceeded(token_usage):
        guard_reason = guard_reason or "token_budget"

    if not tool_calls:
        out = {"token_usage": token_usage}
        if guard_reason:
            out["guard_reason"] = guard_reason
        return out

    out = {"messages": [response], "token_usage": token_usage}
    if guard_reason:
        out["guard_reason"] = guard_reason
    return out


def route_after_analyst(state: AgentState) -> str:
    """analyst 后：有 tool_calls → tools；否则回 Supervisor 继续调度。"""
    if is_tool_steps_exceeded(int(state.get("tool_steps") or 0)):
        return "supervisor"

    messages = state.get("messages") or []
    if not messages:
        return "supervisor"
    last = messages[-1]
    if hasattr(last, "tool_calls") and last.tool_calls:
        return "tools"
    return "supervisor"
