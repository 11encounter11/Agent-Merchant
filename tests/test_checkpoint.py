"""阶段 3：Checkpointer + thread_id 断点续跑（MemorySaver，不依赖 Sqlite/LLM）。"""

import asyncio

from typing_extensions import TypedDict
from langgraph.checkpoint.memory import MemorySaver
from langgraph.graph import StateGraph, START, END

from agent.checkpointing import thread_config, resume_if_pending, get_thread_snapshot
from agent.graph import build_agent_graph


class _S(TypedDict):
    n: int


def _build_toy_graph(checkpointer):
    def step_a(s: _S):
        return {"n": s["n"] + 1}

    def step_b(s: _S):
        return {"n": s["n"] + 10}

    g = StateGraph(_S)
    g.add_node("a", step_a)
    g.add_node("b", step_b)
    g.add_edge(START, "a")
    g.add_edge("a", "b")
    g.add_edge("b", END)
    return g.compile(checkpointer=checkpointer, interrupt_after=["a"])


def test_thread_config():
    cfg = thread_config("t-1")
    assert cfg["configurable"]["thread_id"] == "t-1"


def test_interrupt_and_resume_with_memory_saver():
    async def run():
        cp = MemorySaver()
        app = _build_toy_graph(cp)
        tid = "demo-thread"
        cfg = thread_config(tid)

        # 第一次：在 a 之后中断
        await app.ainvoke({"n": 0}, cfg)
        snap = await get_thread_snapshot(app, tid)
        assert snap.next == ("b",)
        assert snap.values["n"] == 1

        # 续跑
        result = await resume_if_pending(app, tid)
        assert result is not None
        assert result["n"] == 11

        snap2 = await get_thread_snapshot(app, tid)
        assert not snap2.next

    asyncio.run(run())


def test_build_agent_graph_with_memory_checkpointer():
    g = build_agent_graph(MemorySaver())
    assert g is not None
    nodes = set(g.get_graph().nodes)
    assert "supervisor" in nodes
    assert "reflect" in nodes
