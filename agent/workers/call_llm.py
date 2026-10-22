"""call_llm：拼最终回复。改顾问口吻改 prompts.SYSTEM_PROMPT。"""

import logging

from langchain_core.messages import AIMessage, SystemMessage
from langchain_core.runnables import RunnableConfig

from agent.state import AgentState
from agent.prompts import SYSTEM_PROMPT
from agent.security import injection_system_note
from agent.messages import sanitize_tool_pairing
from agent.guards import is_token_budget_exceeded, merge_token_usage, guard_user_message
from agent.workers.common import try_invoke_routed
from config import settings

logger = logging.getLogger(__name__)


def call_llm(state: AgentState, config: RunnableConfig | None = None) -> dict:
    """调用 LLM 生成最终文本回复。"""
    messages = state.get("messages") or []
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
    widget_context = state.get("widget_context") or ""
    widget_facts = state.get("widget_facts") or ""
    if widget_context:
        extras.append(
            "## 图表上下文（服务端快照，优先使用）\n"
            f"{widget_context}\n"
            "数字事实已由系统置顶展示，正文不要重复具体金额/百分比，重点解释原因、影响与建议；"
            "如必须引用，原样引用置顶事实，不要换算或省略小数点。"
            "未出现护栏提示时，不要声称‘限流/截断/额度用尽’。"
            "如果用户要求快照之外的时间范围，明确说明需要切换看板区间或刷新后再查。"
        )
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

    response = try_invoke_routed(full_messages, tier=llm_tier, config=config)
    if response is None:
        text = guard_user_message("llm_unavailable")
        return {
            "messages": [AIMessage(content=text)],
            "token_usage": token_usage,
            "guard_reason": "llm_unavailable",
        }
    token_usage = merge_token_usage(token_usage, response)

    content = response.content or ""
    if widget_facts:
        # 金额/百分比由服务端置顶，避免模型转写小数（实测会把 659.00 写成 65900）
        content = f"数据事实（服务端快照）：{widget_facts}\n\n{content}"
        response = AIMessage(content=content, id=getattr(response, "id", None))
    return {"messages": [response], "token_usage": token_usage}
