"""
Checkpoint 辅助

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

from agent.observability import attach_tracing

logger = logging.getLogger(__name__)


def thread_config(
    thread_id: str,
    *,
    checkpoint_id: str | None = None,
    session_id: str = "",
    tags: list[str] | None = None,
    metadata: dict[str, Any] | None = None,
) -> dict:
    """LangGraph RunnableConfig：thread_id + 可选 Langfuse Callback。"""
    cfg: dict[str, Any] = {"configurable": {"thread_id": thread_id}}
    if checkpoint_id:
        cfg["configurable"]["checkpoint_id"] = checkpoint_id
    return attach_tracing(
        cfg,
        session_id=session_id or thread_id,
        tags=tags,
        metadata=metadata,
    )


async def get_thread_snapshot(graph, thread_id: str):
    """读取线程最新 checkpoint（StateSnapshot）。"""
    return await graph.aget_state(thread_config(thread_id))


async def _skip_pending(graph, cfg: dict) -> None:
    """续跑失败时把卡住的 next 节点标成已完成，避免新一轮对话被拖死。"""
    for _ in range(20):
        snap = await graph.aget_state(cfg)
        if not snap or not snap.next:
            return
        node = snap.next[0]
        logger.warning(f"[Checkpoint] 跳过未完成节点 {node}")
        await graph.aupdate_state(cfg, {}, as_node=node)


async def resume_if_pending(
    graph, thread_id: str, *, session_id: str = ""
) -> Optional[dict]:
    """
    若该 thread 上次执行未到 END（snap.next 非空），则从断点续跑到结束。
    返回续跑后的最终 state；若无需续跑返回 None。
    续跑抛错时跳过卡住节点，返回 None，让新一轮对话继续。
    """
    cfg = thread_config(thread_id, session_id=session_id or thread_id)
    snap = await graph.aget_state(cfg)
    if not snap or not snap.next:
        return None

    logger.warning(
        f"[Checkpoint] 发现未完成线程 thread_id={thread_id} next={list(snap.next)}，开始续跑"
    )
    result = None
    try:
        # 防御极端环：最多续跑若干次 invoke
        for _ in range(20):
            snap = await graph.aget_state(cfg)
            if not snap.next:
                break
            result = await graph.ainvoke(None, cfg)
    except Exception as e:
        logger.warning(f"[Checkpoint] 续跑失败，放弃未完成节点: {e}")
        try:
            await _skip_pending(graph, cfg)
        except Exception as skip_err:
            logger.warning(f"[Checkpoint] 跳过卡住节点失败: {skip_err}")
        return None
    logger.info(f"[Checkpoint] 续跑完成 thread_id={thread_id}")
    return result
