"""
LangGraph 节点函数

做什么：
- 定义节点函数，构成 LangGraph 图的执行流程
- perceive / dispatcher / analyst / execute_tools / strategist / reviewer / call_llm / reflect
- 阶段 1 护栏：步数、token 预算、工具超时重试与入参校验
- 阶段 5：模型路由（inspect_turn / invoke_routed）+ 工具门禁

不做什么：
- 不创建 LLM 实例（从 llm.py 获取）
- 不管理 Prompt（从 prompts.py 获取）
- 不定义 AgentState（从 state.py 获取）
"""

import logging

from langchain_core.messages import AIMessage, HumanMessage, SystemMessage, ToolMessage

from agent.state import AgentState
from agent.llm import get_llm, inspect_turn, invoke_routed
from agent.prompts import (
    SYSTEM_PROMPT,
    ANALYST_PROMPT,
    STRATEGIST_PROMPT,
    REVIEWER_PROMPT,
)
from agent.perception import inject_context
from agent.reflection import sanitize as reflect_sanitize
from agent.security import (
    filter_tools,
    is_tool_allowed,
    deny_tool_message,
    injection_system_note,
)
from agent.messages import sanitize_tool_pairing
from agent.tools import ALL_TOOLS
from agent.guards import (
    remaining_tool_quota,
    is_tool_steps_exceeded,
    is_token_budget_exceeded,
    merge_token_usage,
    invoke_tool_guarded,
    guard_user_message,
)
from agent.supervisor import decide_next_worker
from config import settings

logger = logging.getLogger(__name__)


def perceive(state: AgentState) -> dict:
    """输入清洗 + 注入扫描 + 意图分类 + 模型路由 + 情境注入。"""
    signals = inspect_turn(state.get("user_input", ""))
    context = inject_context()
    intent = signals["intent"]
    logger.info(
        f"[Perceive] 输入={signals['user_input']!r} "
        f"意图={intent.get('intent')} tier={signals['llm_tier']} "
        f"security={signals['security'].get('action')}"
    )
    return {
        "user_input": signals["user_input"],
        "intent": intent,
        "context": context,
        "llm_tier": signals["llm_tier"],
        "security": signals["security"],
    }


def dispatcher(state: AgentState) -> dict:
    """根据意图决定路由，写入 state 供条件边使用。"""
    intent = state.get("intent", {})
    intent_type = intent.get("intent", "unknown")
    logger.info(f"[Dispatcher] 意图={intent_type}")
    return {}


def supervisor(state: AgentState) -> dict:
    """
    Supervisor：决定下一个 Worker（规则状态机 + Plan-and-Execute 计划表）。
    不调 LLM，保证可测、可控。
    """
    return decide_next_worker(state)


def analyst(state: AgentState) -> dict:
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
        return {}

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
    response = invoke_routed(messages, tier="large", tools=gated_tools)
    token_usage = merge_token_usage(token_usage, response)

    tool_calls = list(getattr(response, "tool_calls", None) or [])
    quota = remaining_tool_quota(tool_steps)
    guard_reason = state.get("guard_reason") or ""

    gated_calls = [
        tc for tc in tool_calls
        if is_tool_allowed(intent_type, tc.get("name", ""), security)
    ]
    if len(gated_calls) < len(tool_calls):
        dropped = [tc.get("name") for tc in tool_calls if tc not in gated_calls]
        logger.warning(f"[Analyst] 工具门禁丢弃: {dropped}")
        tool_calls = gated_calls
        response = AIMessage(
            content=getattr(response, "content", "") or "",
            tool_calls=tool_calls,
            id=getattr(response, "id", None),
        )

    if tool_calls and len(tool_calls) > quota:
        logger.warning(
            f"[Analyst] tool_calls={len(tool_calls)} 超过剩余配额 {quota}，截断"
        )
        tool_calls = tool_calls[:quota]
        response = AIMessage(
            content=getattr(response, "content", "") or "",
            tool_calls=tool_calls,
            id=getattr(response, "id", None),
        )
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


def strategist(state: AgentState) -> dict:
    """结合分析结果生成策略建议。"""
    analysis = state.get("analysis_result", {})
    context = state.get("context", {})
    token_usage = state.get("token_usage") or {}

    if not analysis:
        logger.info("[Strategist] 无分析结果，跳过策略生成")
        return {}

    if is_token_budget_exceeded(token_usage):
        logger.warning("[Strategist] token 预算已满，跳过")
        return {"guard_reason": "token_budget"}

    logger.info("[Strategist] 生成策略建议")

    llm = get_llm()
    analysis_text = "\n\n".join(
        f"【{name}】\n{content}" for name, content in analysis.items()
    )
    messages = [
        SystemMessage(content=STRATEGIST_PROMPT),
        SystemMessage(content=f"当前情境：{context}"),
        HumanMessage(
            content=f"以下是数据分析结果，请基于此生成经营策略建议：\n{analysis_text}"
        ),
    ]

    response = llm.invoke(messages)
    token_usage = merge_token_usage(token_usage, response)
    strategy_text = response.content or ""

    out = {
        "strategy": {"recommendations": strategy_text, "source": "strategist"},
        "token_usage": token_usage,
    }
    if is_token_budget_exceeded(token_usage):
        out["guard_reason"] = "token_budget"
    return out


def reviewer(state: AgentState) -> dict:
    """校验策略的数据合理性和安全性。"""
    strategy = state.get("strategy", {})
    token_usage = state.get("token_usage") or {}
    if not strategy:
        return {}

    if is_token_budget_exceeded(token_usage):
        logger.warning("[Reviewer] token 预算已满，跳过校验")
        return {"guard_reason": "token_budget"}

    logger.info("[Reviewer] 校验策略合理性")

    llm = get_llm()
    strategy_text = strategy.get("recommendations", "")
    messages = [
        SystemMessage(content=REVIEWER_PROMPT),
        HumanMessage(content=f"请校验以下策略建议：\n{strategy_text}"),
    ]

    response = llm.invoke(messages)
    token_usage = merge_token_usage(token_usage, response)
    reviewed_text = response.content or strategy_text

    out = {
        "strategy": {"recommendations": reviewed_text, "source": "reviewer"},
        "token_usage": token_usage,
    }
    if is_token_budget_exceeded(token_usage):
        out["guard_reason"] = "token_budget"
    return out


def call_llm(state: AgentState) -> dict:
    """调用 LLM 生成最终文本回复。"""
    messages = state["messages"]
    context = state.get("context", {})
    strategy = state.get("strategy", {})
    analysis = state.get("analysis_result", {})
    token_usage = state.get("token_usage") or {}
    guard_reason = state.get("guard_reason") or ""

    prompt_with_date = SYSTEM_PROMPT.format(
        current_date=context.get("current_date", ""),
        weekday=context.get("weekday", ""),
    )

    extras = []
    if analysis:
        analysis_text = "\n\n".join(
            f"【{name}】\n{content}" for name, content in analysis.items()
        )
        extras.append(f"## 本轮数据分析结果\n{analysis_text}")
    if strategy.get("recommendations"):
        extras.append(f"## 策略建议（已校验）\n{strategy['recommendations']}")
    if guard_reason:
        extras.append(f"## 护栏提示\n{guard_user_message(guard_reason)}")

    plan = state.get("supervisor_plan") or []
    history = state.get("worker_history") or []
    if plan or history:
        extras.append(
            f"## 协作链路（Supervisor）\n"
            f"计划：{' → '.join(plan) if plan else '（无）'}；"
            f"已执行：{' → '.join(history) if history else '（无）'}"
        )

    system_content = prompt_with_date
    inj_note = injection_system_note(state.get("security") or {})
    if inj_note:
        extras.append(f"## 安全提示\n{inj_note}")

    if extras:
        system_content += "\n\n" + "\n\n".join(extras)
        system_content += (
            "\n\n请基于以上数据与策略，用经营顾问口吻给出最终回复。"
            "若有护栏提示，需自然告知商家本轮已限流/截断，不要暴露内部配置名。"
        )

    # 预算已满：不再调模型，直接用护栏文案收束
    if is_token_budget_exceeded(token_usage) and not (
        analysis or strategy.get("recommendations")
    ):
        text = guard_user_message("token_budget")
        return {
            "messages": [AIMessage(content=text)],
            "token_usage": token_usage,
            "guard_reason": "token_budget",
        }

    system_message = SystemMessage(content=system_content)
    safe_messages = sanitize_tool_pairing(list(messages))
    full_messages = [system_message] + safe_messages

    llm_tier = state.get("llm_tier") or "large"
    logger.info(
        f"[CallLLM] tier={llm_tier} 消息数={len(full_messages)} "
        f"tokens={token_usage.get('total_tokens', 0)}/{settings.TOKEN_BUDGET} "
        f"steps={state.get('tool_steps', 0)}/{settings.MAX_TOOL_STEPS}"
    )

    response = invoke_routed(full_messages, tier=llm_tier)
    token_usage = merge_token_usage(token_usage, response)

    return {"messages": [response], "token_usage": token_usage}


def reflect(state: AgentState) -> dict:
    """输出安全校验；boundary / 护栏无有效回复时补文案。"""
    messages = state["messages"]
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


def route_after_dispatcher(state: AgentState) -> str:
    """dispatcher 后：greeting→简单回复；boundary→拒绝；其余→Supervisor。"""
    intent = state.get("intent", {})
    intent_type = intent.get("intent", "unknown")

    if intent_type in ("greeting", "thanks", "knowledge"):
        return "simple"
    if intent_type in ("boundary", "security_block"):
        return "boundary"
    return "complex"


def route_after_supervisor(state: AgentState) -> str:
    """supervisor 后：按 next_worker 派发。"""
    nxt = state.get("next_worker") or "call_llm"
    if nxt not in ("analyst", "strategist", "reviewer", "call_llm"):
        return "call_llm"
    return nxt


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
