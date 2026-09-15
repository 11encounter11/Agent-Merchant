"""
演示：thread_id + Checkpointer 断点续跑

用法（在项目根目录）：
  .\\venv\\Scripts\\python.exe scripts\\demo_checkpoint_resume.py

说明：
- 使用 MemorySaver + interrupt_after=[\"tools\"] 的玩具调度，不调真实 LLM
- 对应面试话术：thread_id 标识一次执行线程；checkpoint 落盘后可从 next 节点续跑
"""

from __future__ import annotations

import asyncio
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from typing_extensions import TypedDict
from langgraph.checkpoint.memory import MemorySaver
from langgraph.graph import StateGraph, START, END

from agent.checkpointing import thread_config, get_thread_snapshot, resume_if_pending


class DemoState(TypedDict):
    step: str
    log: list


def node_perceive(s: DemoState):
    return {"step": "perceive", "log": s.get("log", []) + ["perceive"]}


def node_tools(s: DemoState):
    return {"step": "tools", "log": s.get("log", []) + ["tools"]}


def node_reply(s: DemoState):
    return {"step": "reply", "log": s.get("log", []) + ["reply"]}


def build_demo():
    g = StateGraph(DemoState)
    g.add_node("perceive", node_perceive)
    g.add_node("tools", node_tools)
    g.add_node("reply", node_reply)
    g.add_edge(START, "perceive")
    g.add_edge("perceive", "tools")
    g.add_edge("tools", "reply")
    g.add_edge("reply", END)
    return g.compile(checkpointer=MemorySaver(), interrupt_after=["tools"])


async def main():
    app = build_demo()
    thread_id = "interview-demo-thread"
    cfg = thread_config(thread_id)

    print("=== 1) 跑到 tools 后中断（模拟进程崩溃前最后一次落盘）===")
    await app.ainvoke({"step": "", "log": []}, cfg)
    snap = await get_thread_snapshot(app, thread_id)
    print(f"thread_id={thread_id}")
    print(f"values.step={snap.values.get('step')} log={snap.values.get('log')}")
    print(f"next={snap.next}  ← 未完成，下次用同一 thread_id 续跑")

    print("\n=== 2) 同 thread_id 续跑（ainvoke(None) / resume_if_pending）===")
    result = await resume_if_pending(app, thread_id)
    print(f"final.log={result.get('log') if result else None}")
    snap2 = await get_thread_snapshot(app, thread_id)
    print(f"next={snap2.next}  ← 应为空，表示已到 END")


if __name__ == "__main__":
    asyncio.run(main())
