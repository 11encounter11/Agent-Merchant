"""reviewer：校验策略的数据合理性与安全性。Prompt 在 REVIEWER_PROMPT。"""

import logging

from langchain_core.messages import HumanMessage, SystemMessage
from langchain_core.runnables import RunnableConfig

from agent.state import AgentState
from agent.prompts import REVIEWER_PROMPT
from agent.guards import is_token_budget_exceeded, merge_token_usage
from agent.workers.common import try_invoke_routed

logger = logging.getLogger(__name__)


def reviewer(state: AgentState, config: RunnableConfig | None = None) -> dict:
    """校验策略的数据合理性和安全性。"""
    strategy = state.get("strategy", {})
    token_usage = state.get("token_usage") or {}
    if not strategy:
        return {}

    if is_token_budget_exceeded(token_usage):
        logger.warning("[Reviewer] token 预算已满，跳过校验")
        return {"guard_reason": "token_budget"}

    logger.info("[Reviewer] 校验策略合理性")

    strategy_text = strategy.get("recommendations", "")
    messages = [
        SystemMessage(content=REVIEWER_PROMPT),
        HumanMessage(content=f"请校验以下策略建议：\n{strategy_text}"),
    ]

    response = try_invoke_routed(messages, tier="large", config=config)
    if response is None:
        return {"guard_reason": "llm_unavailable"}
    token_usage = merge_token_usage(token_usage, response)
    reviewed_text = response.content or strategy_text

    out = {
        "strategy": {"recommendations": reviewed_text, "source": "reviewer"},
        "token_usage": token_usage,
    }
    if is_token_budget_exceeded(token_usage):
        out["guard_reason"] = "token_budget"
    return out
