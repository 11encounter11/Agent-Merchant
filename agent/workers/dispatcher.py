"""dispatcher：只读 intent，写出条件边用的路由。改问候/越界分流改这里。"""

import logging

from agent.state import AgentState

logger = logging.getLogger(__name__)


def dispatcher(state: AgentState) -> dict:
    """根据意图决定路由，写入 state 供条件边使用。"""
    intent = state.get("intent", {})
    intent_type = intent.get("intent", "unknown")
    logger.info(f"[Dispatcher] 意图={intent_type}")
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
