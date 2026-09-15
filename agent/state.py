"""
Agent 状态定义（AgentState）

定义 LangGraph 图中流转的完整状态结构。
每个节点通过读写这个 TypedDict 来传递数据。

字段说明：
- messages:          对话消息列表（LangGraph 自动合并）
- user_input:        当前用户输入（清洗后）
- session_id:        会话 ID
- intent:            意图分类结果（perceive 写入）
- context:           情境信息：天气、日期、温度等（perceive 写入）
- analysis_result:   数据分析结果（analyst / execute_tools 写入）
- strategy:          策略建议（strategist 写入）
- token_usage:       Token 消耗累计（各 LLM 节点累加）
- tool_steps:        本轮已执行工具次数（护栏）
- guard_reason:      护栏触发原因（空字符串表示未触发）
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
