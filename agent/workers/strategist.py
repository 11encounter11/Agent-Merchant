"""strategist：根据分析结果写经营建议。改文风改 prompts.STRATEGIST_PROMPT。"""

import logging

from langchain_core.messages import HumanMessage, SystemMessage
from langchain_core.runnables import RunnableConfig

from agent.state import AgentState
from agent.prompts import STRATEGIST_PROMPT
from agent.guards import is_token_budget_exceeded, merge_token_usage
from agent.workers.common import try_invoke_routed

logger = logging.getLogger(__name__)


def strategist(state: AgentState, config: RunnableConfig | None = None) -> dict:
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

    response = try_invoke_routed(messages, tier="large", config=config)
    if response is None:
        return {"guard_reason": "llm_unavailable"}
    token_usage = merge_token_usage(token_usage, response)
    strategy_text = response.content or ""

    out = {
        "strategy": {"recommendations": strategy_text, "source": "strategist"},
        "token_usage": token_usage,
    }
    if is_token_budget_exceeded(token_usage):
        out["guard_reason"] = "token_budget"
    return out
