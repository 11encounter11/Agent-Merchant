"""
Agent 状态定义（AgentState）

定义 LangGraph 图中流转的完整状态结构。
每个节点通过读写这个 TypedDict 来传递数据。

字段说明：
- messages / user_input / session_id / intent / context
- analysis_result / strategy / token_usage / tool_steps / guard_reason
- next_worker / worker_history / supervisor_plan  （Supervisor 调度）
"""

from typing import Annotated, Sequence

from langchain_core.messages import BaseMessage
from langgraph.graph.message import add_messages
from typing_extensions import TypedDict


class AgentState(TypedDict):
    """LangGraph 图的全局状态，每个节点通过它传递数据。"""

    messages: Annotated[Sequence[BaseMessage], add_messages]
    user_input: str
    session_id: str
    intent: dict
    context: dict
    analysis_result: dict
    strategy: dict
    token_usage: dict
    tool_steps: int
    guard_reason: str
    # Supervisor–Worker
    next_worker: str
    worker_history: list
    supervisor_plan: list
