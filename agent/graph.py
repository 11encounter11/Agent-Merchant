"""
LangGraph 图编排（Graph）

流程（阶段 2 Supervisor–Worker）：
    perceive → dispatcher
      → simple: call_llm → reflect → END
      → boundary: reflect → END
      → complex: supervisor ⇄ (analyst → tools? → supervisor
                              | strategist → supervisor
                              | reviewer → supervisor
                              | call_llm → reflect → END)

不做什么：
- 不定义节点函数（在 nodes.py / supervisor.py）
- 不定义 AgentState（在 state.py）
"""

import logging

from langgraph.graph import StateGraph, START, END

from agent.state import AgentState
from agent.nodes import (
    perceive,
    dispatcher,
    supervisor,
    analyst,
    execute_tools,
    strategist,
    reviewer,
    call_llm,
    reflect,
    route_after_dispatcher,
    route_after_supervisor,
    route_after_analyst,
)

logger = logging.getLogger(__name__)

graph_builder = StateGraph(AgentState)

graph_builder.add_node("perceive", perceive)
graph_builder.add_node("dispatcher", dispatcher)
graph_builder.add_node("supervisor", supervisor)
graph_builder.add_node("analyst", analyst)
graph_builder.add_node("tools", execute_tools)
graph_builder.add_node("strategist", strategist)
graph_builder.add_node("reviewer", reviewer)
graph_builder.add_node("call_llm", call_llm)
graph_builder.add_node("reflect", reflect)

graph_builder.add_edge(START, "perceive")
graph_builder.add_edge("perceive", "dispatcher")

graph_builder.add_conditional_edges(
    "dispatcher",
    route_after_dispatcher,
    {
        "simple": "call_llm",
        "complex": "supervisor",
        "boundary": "reflect",
    },
)

graph_builder.add_conditional_edges(
    "supervisor",
    route_after_supervisor,
    {
        "analyst": "analyst",
        "strategist": "strategist",
        "reviewer": "reviewer",
        "call_llm": "call_llm",
    },
)

graph_builder.add_conditional_edges(
    "analyst",
    route_after_analyst,
    {
        "tools": "tools",
        "supervisor": "supervisor",
    },
)

# 工具执行完交回 Supervisor，由它决定是否 strategist / reviewer
graph_builder.add_edge("tools", "supervisor")
graph_builder.add_edge("strategist", "supervisor")
graph_builder.add_edge("reviewer", "supervisor")
graph_builder.add_edge("call_llm", "reflect")
graph_builder.add_edge("reflect", END)

agent_graph = graph_builder.compile()

logger.info("[Graph] LangGraph 图已编译完成（Supervisor–Worker）")
