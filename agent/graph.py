"""
LangGraph 图编排（Graph）

做什么：
- 定义 LangGraph StateGraph：节点 + 边 + 路由
- 完整流程：
    perceive → dispatcher → [simple: call_llm] / [complex: analyst] / [boundary: reflect]
    analyst → [tools: execute_tools → strategist → reviewer → call_llm] / [call_llm]
    call_llm → reflect → END

不做什么：
- 不定义节点函数（在 nodes.py）
- 不定义 AgentState（在 state.py）
"""

import logging

from langgraph.graph import StateGraph, START, END

from agent.state import AgentState
from agent.nodes import (
    perceive,
    dispatcher,
    analyst,
    execute_tools,
    strategist,
    reviewer,
    call_llm,
    reflect,
    route_after_dispatcher,
    route_after_analyst,
)

logger = logging.getLogger(__name__)

# ============================================================
# 构建图
# ============================================================
graph_builder = StateGraph(AgentState)

graph_builder.add_node("perceive", perceive)
graph_builder.add_node("dispatcher", dispatcher)
graph_builder.add_node("analyst", analyst)
graph_builder.add_node("tools", execute_tools)
graph_builder.add_node("strategist", strategist)
graph_builder.add_node("reviewer", reviewer)
graph_builder.add_node("call_llm", call_llm)
graph_builder.add_node("reflect", reflect)

# ============================================================
# 边定义
# ============================================================

graph_builder.add_edge(START, "perceive")
graph_builder.add_edge("perceive", "dispatcher")

graph_builder.add_conditional_edges(
    "dispatcher",
    route_after_dispatcher,
    {
        "simple": "call_llm",
        "complex": "analyst",
        "boundary": "reflect",
    },
)

graph_builder.add_conditional_edges(
    "analyst",
    route_after_analyst,
    {
        "tools": "tools",
        "call_llm": "call_llm",
    },
)

graph_builder.add_edge("tools", "strategist")
graph_builder.add_edge("strategist", "reviewer")
graph_builder.add_edge("reviewer", "call_llm")
graph_builder.add_edge("call_llm", "reflect")
graph_builder.add_edge("reflect", END)

# ============================================================
# 编译图
# ============================================================
agent_graph = graph_builder.compile()

logger.info("[Graph] LangGraph 图已编译完成")
