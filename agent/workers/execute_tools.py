"""execute_tools：真正跑 tool_calls（校验/超时/幂等）。SQL 结果不对改 tools/analysis。"""

import logging

from langchain_core.messages import ToolMessage

from agent.state import AgentState
from agent.security import is_tool_allowed, deny_tool_message
from agent.tools import ALL_TOOLS
from agent.guards import remaining_tool_quota, is_tool_steps_exceeded, invoke_tool_guarded

logger = logging.getLogger(__name__)


async def execute_tools(state: AgentState) -> dict:
    """执行 tool_calls：校验 / 超时重试 / 幂等，并累计 tool_steps。"""
    messages = list(state.get("messages") or [])
    if not messages:
        return {}

    last = messages[-1]
    tool_calls = list(getattr(last, "tool_calls", None) or [])
    if not tool_calls:
        return {}

    tool_steps = int(state.get("tool_steps") or 0)
    quota = remaining_tool_quota(tool_steps)
    if quota <= 0:
        logger.warning("[ExecuteTools] 步数耗尽，拒绝执行")
        return {"guard_reason": "max_tool_steps"}

    if len(tool_calls) > quota:
        tool_calls = tool_calls[:quota]

    tool_map = {t.name: t for t in ALL_TOOLS}
    session_id = state.get("session_id") or ""
    intent_type = (state.get("intent") or {}).get("intent") or "unknown"
    security = state.get("security") or {}
    tool_messages = []
    analysis = dict(state.get("analysis_result") or {})
    executed = 0
    guard_reason = state.get("guard_reason") or ""

    for tc in tool_calls:
        name = tc.get("name", "")
        args = tc.get("args") or {}
        call_id = tc.get("id") or name
        tool = tool_map.get(name)

        if not is_tool_allowed(intent_type, name, security):
            content = deny_tool_message(name)
            logger.warning(f"[ExecuteTools] {content}")
        elif tool is None:
            content = f"未知工具: {name}"
            logger.warning(f"[ExecuteTools] {content}")
        else:
            logger.info(f"[ExecuteTools] 调用 {name} args={args}")
            content = await invoke_tool_guarded(tool, name, args, session_id=session_id)
            if content.startswith("参数校验失败"):
                guard_reason = guard_reason or "tool_args_invalid"
            executed += 1

        tool_messages.append(
            ToolMessage(content=content, tool_call_id=call_id, name=name)
        )
        analysis[name] = content

    new_steps = tool_steps + executed
    logger.info(
        f"[ExecuteTools] 完成={list(analysis.keys())} steps={tool_steps}->{new_steps}"
    )
    out = {
        "messages": tool_messages,
        "analysis_result": analysis,
        "tool_steps": new_steps,
    }
    if is_tool_steps_exceeded(new_steps):
        out["guard_reason"] = "max_tool_steps"
    elif guard_reason:
        out["guard_reason"] = guard_reason
    return out
