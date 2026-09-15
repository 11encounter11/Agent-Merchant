"""
Checkpoint 辅助（面经阶段 3）

做什么：
- thread_id 与 session_id 对齐（可单独覆盖）
- 未跑完的线程：先 resume 再接新一轮
- 提供「读当前 checkpoint」便于演示断点恢复

不做什么：
- 不替代 session_memory 的对话落盘
"""

from __future__ import annotations

import logging
from typing import Any, Optional

logger = logging.getLogger(__name__)


def thread_config(thread_id: str, *, checkpoint_id: str | None = None) -> dict:
    """LangGraph RunnableConfig：thread_id 必填；可选 checkpoint_id 定位历史快照。"""
    cfg: dict[str, Any] = {"configurable": {"thread_id": thread_id}}
    if checkpoint_id:
        cfg["configurable"]["checkpoint_id"] = checkpoint_id
    return cfg


async def get_thread_snapshot(graph, thread_id: str):
    """读取线程最新 checkpoint（StateSnapshot）。"""
    return await graph.aget_state(thread_config(thread_id))


async def resume_if_pending(graph, thread_id: str) -> Optional[dict]:
    """
    若该 thread 上次执行未到 END（snap.next 非空），则从断点续跑到结束。
    返回续跑后的最终 state；若无需续跑返回 None。
    """
    cfg = thread_config(thread_id)
    snap = await graph.aget_state(cfg)
    if not snap or not snap.next:
        return None

    logger.warning(
        f"[Checkpoint] 发现未完成线程 thread_id={thread_id} next={list(snap.next)}，开始续跑"
    )
    result = None
    # 防御极端环：最多续跑若干次 invoke
    for _ in range(20):
        snap = await graph.aget_state(cfg)
        if not snap.next:
            break
        result = await graph.ainvoke(None, cfg)
    logger.info(f"[Checkpoint] 续跑完成 thread_id={thread_id}")
    return result
