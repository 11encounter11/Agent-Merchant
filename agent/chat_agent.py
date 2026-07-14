"""
Agent 核心逻辑（用 LangGraph 构建）

阶段 2 的图：[开始] → [call_llm] → [结束]
阶段 3 的图：[开始] → [call_llm] → 要不要调Tool? → 要 → [tool节点] → 回到 [call_llm]
                                          → 不要 → [结束]
阶段 7（7大模块架构）的图：
[开始] → [感知:预处理] → [记忆:组装上下文] → [call_llm] → 要不要调Tool?
                                                          ↓ 要           ↓ 不要
                                                    [tool节点]      [反思:校验输出] → [结束]
                                                      ↓
                                                  回到 [call_llm]
"""

import uuid
import logging
from datetime import datetime
from typing import Annotated, Sequence
from langgraph import graph
from typing_extensions import TypedDict

from langchain_core.messages import BaseMessage, SystemMessage, HumanMessage, AIMessage
from langchain_openai import ChatOpenAI
from langgraph.graph import StateGraph, START, END
from langgraph.graph.message import add_messages
from langgraph.prebuilt import ToolNode

from config import settings
from agent.prompts import SYSTEM_PROMPT_V2
from agent.session import get_history, save_history
from agent.tools.sales_tools import query_turnover, query_order_count, query_user_stats
from agent.tools.dish_tools import query_dish_list, query_dish_by_name
from agent.tools.order_action_tools import accept_order, reject_order, stop_dish, start_dish

# 导入 7 大模块
from agent.perception import perception
from agent.memory import memory
from agent.reflection import reflection
from agent.tools.tool_registry import tool_registry

# 配置日志
logger = logging.getLogger(__name__)


# ============================================================
# State 定义
# ============================================================
class AgentState(TypedDict):
    messages: Annotated[Sequence[BaseMessage], add_messages]
    user_input: str  # 用户原始输入（用于感知和反思模块）
    session_id: str  # 会话 ID（用于记忆模块）


# ============================================================
# 收集所有工具
# ============================================================
tools = [
    # 查询类（直接查数据库）
    query_turnover, query_order_count, query_user_stats,
    query_dish_list, query_dish_by_name,
    # 操作类（调用 Java 后端 API）
    accept_order, reject_order, stop_dish, start_dish,
]

# 初始化工具注册中心（7 大模块 - 工具模块）
for tool in tools:
    tool_registry.register(tool)


# ============================================================
# LLM 客户端（绑定工具）
# ============================================================
# bind_tools() 告诉 DeepSeek："你有这些工具可以用"。
# DeepSeek 会在回复中决定是否调用工具、调用哪个、传什么参数。
llm = ChatOpenAI(
    api_key=settings.LLM_API_KEY,
    base_url=settings.LLM_BASE_URL,
    model=settings.LLM_MODEL,
    temperature=0.7,
).bind_tools(tools)


# ============================================================
# 节点函数（7 大模块架构）
# ============================================================
def perceive(state: AgentState) -> dict:
    """
    感知节点：预处理用户输入。
    
    对应 7 大模块中的"感知模块"。
    """
    user_input = state.get("user_input", "")
    
    # 1. 清洗输入
    cleaned_input = perception.preprocess(user_input)
    
    # 2. 意图分类（当前由 LLM 处理，预留扩展点）
    intent = perception.classify_intent(cleaned_input)
    
    logger.info(f"[Perceive] 用户输入: '{cleaned_input}', 意图: {intent}")
    
    return {"user_input": cleaned_input}


def memorize(state: AgentState) -> dict:
    """
    记忆节点：组装完整上下文（会话历史 + 知识检索）。
    
    对应 7 大模块中的"记忆模块"。
    """
    session_id = state.get("session_id", "")
    user_input = state.get("user_input", "")
    
    # 从记忆模块获取完整上下文
    # 包括：会话历史 + RAG 知识检索结果
    context_messages = memory.build_context(session_id, user_input)
    
    logger.info(f"[Memorize] 组装上下文: session={session_id}, 消息数={len(context_messages)}")
    
    return {"messages": context_messages}


def call_llm(state: AgentState) -> dict:
    """
    调用 LLM 节点。LLM 会根据消息决定：直接回复 or 调用工具。
    
    对应 7 大模块中的"规划模块"（ReAct 循环的核心）。
    """
    messages = state["messages"]
    user_input = state.get("user_input", "")
    
    # 【教学说明】为什么需要动态注入日期？
    # LLM 没有内置时钟，不知道今天是几号。
    # 我们在每次调用时把当前日期填充到 Prompt 模板里，
    # 这样 LLM 就能理解"今天""这周""本月"等时间概念了。
    now = datetime.now()
    weekdays = ['一', '二', '三', '四', '五', '六', '日']
    
    prompt_with_date = SYSTEM_PROMPT_V2.format(
        current_date=now.strftime('%Y-%m-%d'),  # 例如 "2026-07-13"
        weekday=weekdays[now.weekday()]          # 例如 "一"
    )

    system_message = SystemMessage(content=prompt_with_date)
    full_messages = [system_message] + list(messages)
    
    logger.info(f"[CallLLM] 调用 LLM, 消息数: {len(full_messages)}")

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


def reflect(state: AgentState) -> dict:
    """
    反思节点：对 LLM 输出做后置校验。
    
    对应 7 大模块中的"反思模块"。
    只在不调用工具时执行（即 LLM 直接回复时）。
    """
    messages = state["messages"]
    user_input = state.get("user_input", "")
    
    if not messages:
        return {}
    
    # 获取最后一条 AI 消息
    last_message = messages[-1]
    if not isinstance(last_message, AIMessage):
        return {}
    
    # 用反思模块校验输出
    original_content = last_message.content
    sanitized_content = reflection.sanitize(original_content, user_input)
    
    if original_content != sanitized_content:
        logger.info(f"[Reflect] 输出被修改")
        # 替换为清洗后的内容
        sanitized_message = AIMessage(content=sanitized_content)
        return {"messages": [sanitized_message]}
    
    return {}


# ============================================================
# 构建图（7 大模块架构）
# ============================================================
graph_builder = StateGraph(AgentState)

# 添加节点（对应 7 大模块）
graph_builder.add_node("perceive", perceive)      # 感知模块
graph_builder.add_node("memorize", memorize)      # 记忆模块
graph_builder.add_node("call_llm", call_llm)      # 规划模块
graph_builder.add_node("tools", ToolNode(tools))  # 工具模块
graph_builder.add_node("reflect", reflect)        # 反思模块

# 添加边
graph_builder.add_edge(START, "perceive")         # 开始 → 感知
graph_builder.add_edge("perceive", "memorize")    # 感知 → 记忆
graph_builder.add_edge("memorize", "call_llm")    # 记忆 → 调用 LLM

# 条件边：call_llm 之后，根据 LLM 的回复决定走哪条路
graph_builder.add_conditional_edges(
    "call_llm",
    should_continue,
    {
        "tools": "tools",    # 要调工具 → tools 节点
        "end": "reflect",    # 不调工具 → 反思节点（校验输出）
    }
)

# tools 执行完后，回到 call_llm 让 LLM 处理工具结果
graph_builder.add_edge("tools", "call_llm")

# reflect 执行完后，结束
graph_builder.add_edge("reflect", END)

agent_graph = graph_builder.compile()

graph_png = agent_graph.get_graph(xray=True).draw_mermaid_png()
with open("flow_graph_v3.png", "wb") as f:
    f.write(graph_png)
print("流程图已保存为 flow_graph_v3.png")

# ============================================================
# 对外接口函数
# ============================================================
async def chat(message: str, session_id: str = None) -> dict:
    """非流式对话（异步，支持多轮对话，集成 7 大模块）"""
    if session_id is None:
        session_id = str(uuid.uuid4())

    logger.info(f"[Chat] 非流式对话: session={session_id}, message='{message}'")
    
    # 构建初始状态（包含 user_input 和 session_id）
    initial_state = {
        "messages": [],
        "user_input": message,
        "session_id": session_id
    }

    # 用 ainvoke 而不是 invoke，因为 Tool 是 async 函数
    result = await agent_graph.ainvoke(initial_state)

    # 保存更新后的历史（包含本次的用户消息和 AI 回复）
    # 注意：这里需要从 result 中提取完整的消息列表
    final_messages = result.get("messages", [])
    if final_messages:
        memory.save_working_memory(session_id, final_messages)

    ai_reply = final_messages[-1].content if final_messages else ""

    return {
        "reply": ai_reply,
        "session_id": session_id
    }


def chat_stream(message: str, session_id: str = None):
    """流式对话（走图结构，支持多轮对话，集成 7 大模块）"""
    if session_id is None:
        session_id = str(uuid.uuid4())

    logger.info(f"[ChatStream] 流式对话: session={session_id}, message='{message}'")
    
    # 构建初始状态
    initial_state = {
        "messages": [],
        "user_input": message,
        "session_id": session_id
    }

    async def async_generator():
        # 收集本次对话产生的所有消息（用于保存历史）
        collected = []

        async for chunk in agent_graph.astream(
            initial_state,
            stream_mode="messages"
        ):
            msg, metadata = chunk

            if msg.content and isinstance(msg, AIMessage):
                collected.append(msg)
                yield msg.content

        # 保存历史（用记忆模块）
        if collected:
            memory.save_working_memory(session_id, collected)

    return async_generator()
