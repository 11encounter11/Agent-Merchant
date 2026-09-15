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
- analysis_result:   数据分析结果（analyst 写入）
- strategy:          策略建议（strategist 写入）
- token_usage:       Token 消耗统计（call_llm 写入）
"""

from typing import Annotated, Sequence

from langchain_core.messages import BaseMessage
from langgraph.graph.message import add_messages
from typing_extensions import TypedDict


class AgentState(TypedDict):
    """LangGraph 图的全局状态，每个节点通过它传递数据。"""

    # 对话消息（LangGraph 的 add_messages 会自动追加而非覆盖）
    messages: Annotated[Sequence[BaseMessage], add_messages]

    # 当前用户输入（perceive 清洗后写入）
    user_input: str

    # 会话 ID（用于关联多轮对话）
    session_id: str

    # 意图分类结果，perceive 写入
    # 格式：{"intent": "greeting|query_analysis|query_report|boundary|unknown", "confidence": 0.0~1.0}
    intent: dict

    # 情境信息：天气、日期、星期、温度等，perceive 写入
    context: dict

    # 数据分析结果，analyst 写入
    # 格式：{"tool": "factor_decomposition", "result": {...}, ...}
    analysis_result: dict

    # 策略建议，strategist 写入
    # 格式：{"recommendations": [...], "reasoning": "..."}
    strategy: dict

    # Token 消耗统计，call_llm 写入
    token_usage: dict
