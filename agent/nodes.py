"""
LangGraph 节点函数

做什么：
- 定义节点函数，构成 LangGraph 图的执行流程
- perceive: 输入清洗 + 意图分类 + 情境注入
- dispatcher: 根据意图决定路由（简单/复杂路径）
- analyst: LLM 选型并发出 tool_calls
- execute_tools: 执行工具并把结果写入 analysis_result
- strategist: 结合分析结果生成策略建议
- reviewer: 校验策略合理性
- call_llm: 调用 LLM 生成最终文本回复
- reflect: 输出安全校验

不做什么：
- 不创建 LLM 实例（从 llm.py 获取）
- 不管理 Prompt（从 prompts.py 获取）
- 不定义 AgentState（从 state.py 获取）
"""

import logging

from langchain_core.messages import AIMessage, HumanMessage, SystemMessage, ToolMessage

from agent.state import AgentState
from agent.llm import get_llm, get_llm_with_tools
from agent.prompts import (
    SYSTEM_PROMPT,
    ANALYST_PROMPT,
    STRATEGIST_PROMPT,
    REVIEWER_PROMPT,
)
from agent.perception import preprocess, classify_intent, inject_context
from agent.reflection import sanitize as reflect_sanitize
from agent.messages import sanitize_tool_pairing
from agent.tools import ALL_TOOLS

logger = logging.getLogger(__name__)


# ============================================================
# 节点 1：感知（perceive）
# ============================================================
def perceive(state: AgentState) -> dict:
    """输入清洗 + 意图分类 + 情境注入。"""
    user_input = state.get("user_input", "")
    cleaned = preprocess(user_input)
    intent = classify_intent(cleaned)
    context = inject_context()

    logger.info(f"[Perceive] 输入='{cleaned}', 意图={intent['intent']}")
    return {
        "user_input": cleaned,
        "intent": intent,
        "context": context,
    }


# ============================================================
# 节点 2：路由（dispatcher）
# ============================================================
def dispatcher(state: AgentState) -> dict:
    """根据意图决定路由，写入 state 供条件边使用。"""
    intent = state.get("intent", {})
    intent_type = intent.get("intent", "unknown")
    logger.info(f"[Dispatcher] 意图={intent_type}")
    return {}


# ============================================================
# 节点 3：分析（analyst）—— LLM 选型，发出 tool_calls
# ============================================================
def analyst(state: AgentState) -> dict:
    """让绑定工具的 LLM 决定调用哪些分析工具。"""
    user_input = state.get("user_input", "")
    context = state.get("context", {})
    intent = state.get("intent", {})

    logger.info(f"[Analyst] 开始数据分析, intent={intent.get('intent')}")

    llm = get_llm_with_tools(ALL_TOOLS)
    messages = [
        SystemMessage(content=ANALYST_PROMPT),
        SystemMessage(
            content=(
                f"当前日期：{context.get('current_date', '')} "
                f"星期{context.get('weekday', '')}"
            )
        ),
        HumanMessage(content=user_input),
    ]
    response = llm.invoke(messages)

    tool_names = []
    if hasattr(response, "tool_calls") and response.tool_calls:
        tool_names = [tc.get("name", "") for tc in response.tool_calls]
    logger.info(f"[Analyst] tool_calls={tool_names or '无'}")

    # 无工具时不写入 messages，避免「无需工具」占位污染最终回复上下文
    if not tool_names:
        return {}
    return {"messages": [response]}


# ============================================================
# 节点 3b：执行工具 + 汇总 analysis_result
# ============================================================
async def execute_tools(state: AgentState) -> dict:
    """执行 analyst 发出的 tool_calls，写入 messages + analysis_result。"""
    messages = list(state.get("messages") or [])
    if not messages:
        return {}

    last = messages[-1]
    tool_calls = getattr(last, "tool_calls", None) or []
    if not tool_calls:
        return {}

    tool_map = {t.name: t for t in ALL_TOOLS}
    tool_messages = []
    analysis = {}

    for tc in tool_calls:
        name = tc.get("name", "")
        args = tc.get("args") or {}
        call_id = tc.get("id") or name
        tool = tool_map.get(name)

        if tool is None:
            content = f"未知工具: {name}"
            logger.warning(f"[ExecuteTools] {content}")
        else:
            try:
                logger.info(f"[ExecuteTools] 调用 {name} args={args}")
                result = await tool.ainvoke(args)
                content = result if isinstance(result, str) else str(result)
            except Exception as e:
                content = f"工具 {name} 执行失败: {e}"
                logger.exception(f"[ExecuteTools] {name} 失败")

        tool_messages.append(
            ToolMessage(content=content, tool_call_id=call_id, name=name)
        )
        analysis[name] = content

    logger.info(f"[ExecuteTools] 完成: {list(analysis.keys())}")
    return {
        "messages": tool_messages,
        "analysis_result": analysis,
    }

# ============================================================
# 节点 4：策略（strategist）
# ============================================================
def strategist(state: AgentState) -> dict:
    """结合分析结果 + 知识库，生成策略建议。"""
    analysis = state.get("analysis_result", {})
    context = state.get("context", {})

    if not analysis:
        logger.info("[Strategist] 无分析结果，跳过策略生成")
        return {}

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
    strategy_text = response.content or ""

    return {
        "strategy": {"recommendations": strategy_text, "source": "strategist"},
    }


# ============================================================
# 节点 5：校验（reviewer）
# ============================================================
def reviewer(state: AgentState) -> dict:
    """校验策略的数据合理性和安全性。"""
    strategy = state.get("strategy", {})
    if not strategy:
        return {}

    logger.info("[Reviewer] 校验策略合理性")

    llm = get_llm()
    strategy_text = strategy.get("recommendations", "")
    messages = [
        SystemMessage(content=REVIEWER_PROMPT),
        HumanMessage(content=f"请校验以下策略建议：\n{strategy_text}"),
    ]

    response = llm.invoke(messages)
    reviewed_text = response.content or strategy_text

    return {
        "strategy": {"recommendations": reviewed_text, "source": "reviewer"},
    }


# ============================================================
# 节点 6：调用 LLM（call_llm）
# ============================================================
def call_llm(state: AgentState) -> dict:
    """调用 LLM 生成最终文本回复（不再绑工具，工具已由 analyst 完成）。"""
    messages = state["messages"]
    context = state.get("context", {})
    strategy = state.get("strategy", {})
    analysis = state.get("analysis_result", {})

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

    system_content = prompt_with_date
    if extras:
        system_content += "\n\n" + "\n\n".join(extras)
        system_content += (
            "\n\n请基于以上数据与策略，用经营顾问口吻给出最终回复。"
            "不要再说「我还在学习中」。"
        )

    system_message = SystemMessage(content=system_content)
    safe_messages = sanitize_tool_pairing(list(messages))
    full_messages = [system_message] + safe_messages

    logger.info(f"[CallLLM] 调用 LLM, 消息数: {len(full_messages)}")

    # 最终回复用纯文本 LLM；工具调用只发生在 analyst
    llm = get_llm()
    response = llm.invoke(full_messages)

    token_usage = {}
    if hasattr(response, "usage_metadata") and response.usage_metadata:
        usage = response.usage_metadata
        prompt_tokens = usage.get("input_tokens", 0) or usage.get("prompt_tokens", 0)
        completion_tokens = usage.get("output_tokens", 0) or usage.get("completion_tokens", 0)
        total_tokens = usage.get("total_tokens", 0) or (prompt_tokens + completion_tokens)
        token_usage = {
            "prompt_tokens": prompt_tokens,
            "completion_tokens": completion_tokens,
            "total_tokens": total_tokens,
        }
        logger.info(f"[CallLLM] Token 消耗: total={total_tokens}")

    return {"messages": [response], "token_usage": token_usage}


# ============================================================
# 节点 7：反思（reflect）
# ============================================================
def reflect(state: AgentState) -> dict:
    """输出安全校验；boundary 意图无回复时补一句拒绝。"""
    messages = state["messages"]
    user_input = state.get("user_input", "")
    intent = state.get("intent", {})

    if intent.get("intent") == "boundary":
        refusal = (
            "这不在我的核心能力范围内。"
            "我主要帮您做经营数据分析、诊断和下一步建议。"
        )
        logger.info("[Reflect] boundary 拒绝")
        return {"messages": [AIMessage(content=refusal)]}

    if not messages:
        return {}

    last_message = messages[-1]
    if not isinstance(last_message, AIMessage):
        return {}

    original = last_message.content
    sanitized = reflect_sanitize(original, user_input)

    if original != sanitized:
        logger.info("[Reflect] 输出被修改")
        return {"messages": [AIMessage(content=sanitized)]}

    return {}


# ============================================================
# 条件边函数
# ============================================================
def route_after_dispatcher(state: AgentState) -> str:
    """dispatcher 后的路由：根据意图决定走简单路径还是复杂路径。"""
    intent = state.get("intent", {})
    intent_type = intent.get("intent", "unknown")

    if intent_type in ("greeting", "thanks"):
        return "simple"

    if intent_type == "boundary":
        return "boundary"

    return "complex"


def route_after_analyst(state: AgentState) -> str:
    """analyst 后：有 tool_calls → tools，否则直接 call_llm。"""
    messages = state.get("messages") or []
    if not messages:
        return "call_llm"
    last = messages[-1]
    if hasattr(last, "tool_calls") and last.tool_calls:
        return "tools"
    return "call_llm"
