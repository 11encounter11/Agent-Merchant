"""
Agent 核心逻辑（用 LangGraph 构建）

阶段 2 的图：[开始] → [call_llm] → [结束]
阶段 3 的图：[开始] → [call_llm] → 要不要调Tool? → 要 → [tool节点] → 回到 [call_llm]
                                          → 不要 → [结束]
"""

import uuid
from typing import Annotated, Sequence
from typing_extensions import TypedDict

from langchain_core.messages import BaseMessage, SystemMessage, HumanMessage, AIMessage
from langchain_openai import ChatOpenAI
from langgraph.graph import StateGraph, START, END
from langgraph.graph.message import add_messages
from langgraph.prebuilt import ToolNode

from config import settings
from agent.prompts import SYSTEM_PROMPT_V2
from agent.tools.sales_tools import query_turnover, query_order_count, query_user_stats


# ============================================================
# State 定义
# ============================================================
class AgentState(TypedDict):
    messages: Annotated[Sequence[BaseMessage], add_messages]


# ============================================================
# 收集所有工具
# ============================================================
tools = [query_turnover, query_order_count, query_user_stats]


# ============================================================
# LLM 客户端（绑定工具）
# ============================================================
# bind_tools() 告诉 DeepSeek："你有这些工具可以用"。
# DeepSeek 会在回复中决定是否调用工具、调用哪个、传什么参数。
llm = ChatOpenAI(
    api_key=settings.DEEPSEEK_API_KEY,
    base_url=settings.DEEPSEEK_BASE_URL,
    model=settings.DEEPSEEK_MODEL,
    temperature=0.7,
).bind_tools(tools)


# ============================================================
# 节点函数
# ============================================================
def call_llm(state: AgentState) -> dict:
    """
    调用 LLM 节点。LLM 会根据消息决定：直接回复 or 调用工具。
    """
    messages = state["messages"]

    system_message = SystemMessage(content=SYSTEM_PROMPT_V2)
    full_messages = [system_message] + list(messages)

    response = llm.invoke(full_messages)
    return {"messages": [response]}


def should_continue(state: AgentState) -> str:
    """
    条件边函数：决定下一步走哪个节点。

    检查 LLM 最近的回复是否包含工具调用：
    - 有工具调用 → 走 "tools" 节点
    - 没有工具调用 → 走 "end"（结束）
    """
    last_message = state["messages"][-1]

    if hasattr(last_message, "tool_calls") and last_message.tool_calls:
        return "tools"
    return "end"


# ============================================================
# 构建图
# ============================================================
graph_builder = StateGraph(AgentState)

# 添加节点
graph_builder.add_node("call_llm", call_llm)
graph_builder.add_node("tools", ToolNode(tools))

# 添加边
graph_builder.add_edge(START, "call_llm")

# 条件边：call_llm 之后，根据 LLM 的回复决定走哪条路
graph_builder.add_conditional_edges(
    "call_llm",
    should_continue,
    {
        "tools": "tools",
        "end": END,
    }
)

# tools 执行完后，回到 call_llm 让 LLM 处理工具结果
graph_builder.add_edge("tools", "call_llm")

agent_graph = graph_builder.compile()


# ============================================================
# 对外接口函数
# ============================================================
async def chat(message: str, session_id: str = None) -> dict:
    """非流式对话（异步）"""
    if session_id is None:
        session_id = str(uuid.uuid4())

    user_message = HumanMessage(content=message)
    initial_state = {"messages": [user_message]}

    # 用 ainvoke 而不是 invoke，因为 Tool 是 async 函数
    result = await agent_graph.ainvoke(initial_state)

    ai_reply = result["messages"][-1].content

    return {
        "reply": ai_reply,
        "session_id": session_id
    }


def chat_stream(message: str, session_id: str = None):
    """流式对话（走图结构）"""
    if session_id is None:
        session_id = str(uuid.uuid4())

    user_message = HumanMessage(content=message)
    initial_state = {"messages": [user_message]}

    async def async_generator():
        async for chunk in agent_graph.astream(
            initial_state,
            stream_mode="messages"
        ):
            msg, metadata = chunk

            if msg.content and isinstance(msg, AIMessage):
                yield msg.content

    return async_generator()
