"""perceive：输入清洗、注入扫描、意图分类、模型路由、情境注入。规则本身在 perception / llm。"""

import logging

from agent.state import AgentState
from agent.llm import inspect_turn
from agent.perception import inject_context

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
