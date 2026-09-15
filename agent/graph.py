"""
LangGraph 图编排（Graph）

流程（阶段 2 Supervisor–Worker + 阶段 3 Checkpointer）：
    perceive → dispatcher → supervisor ⇄ workers → call_llm → reflect → END

编译时注入 checkpointer；thread_id 由 service 传入 RunnableConfig。
"""

import logging

from langgraph.checkpoint.memory import MemorySaver
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


def _build_state_graph() -> StateGraph:
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

    graph_builder.add_edge("tools", "supervisor")
    graph_builder.add_edge("strategist", "supervisor")
    graph_builder.add_edge("reviewer", "supervisor")
    graph_builder.add_edge("call_llm", "reflect")
    graph_builder.add_edge("reflect", END)
    return graph_builder


def build_agent_graph(checkpointer=None, *, interrupt_after: list[str] | None = None):
    """
    编译图。
    - checkpointer: MemorySaver / AsyncSqliteSaver 等；默认 MemorySaver（导入期可用）
    - interrupt_after: 演示断点用，如 [\"tools\"]；生产默认 None
    """
    builder = _build_state_graph()
    if checkpointer is None:
        checkpointer = MemorySaver()
        logger.info("[Graph] 使用 MemorySaver（进程内，重启即丢）")

    kwargs = {"checkpointer": checkpointer}
    if interrupt_after:
        kwargs["interrupt_after"] = interrupt_after
        logger.info(f"[Graph] interrupt_after={interrupt_after}")

    compiled = builder.compile(**kwargs)
    logger.info("[Graph] LangGraph 图已编译（Supervisor–Worker + Checkpointer）")
    return compiled


# 模块导入时先挂 MemorySaver；FastAPI lifespan 可替换为 Sqlite
agent_graph = build_agent_graph()


def get_agent_graph():
    """始终取当前进程内最新编译图（lifespan 替换后生效）。"""
    return agent_graph
