"""supervisor 节点：只包一层 decide_next_worker。调度规则改 supervisor.py。"""

from agent.state import AgentState
from agent.supervisor import decide_next_worker


def supervisor(state: AgentState) -> dict:
    """
    Supervisor：决定下一个 Worker（规则状态机 + Plan-and-Execute 计划表）。
    不调 LLM，保证可测、可控。
    """
    return decide_next_worker(state)


def route_after_supervisor(state: AgentState) -> str:
    """supervisor 后：按 next_worker 派发。"""
    nxt = state.get("next_worker") or "call_llm"
    if nxt not in ("analyst", "strategist", "reviewer", "call_llm"):
        return "call_llm"
    return nxt
