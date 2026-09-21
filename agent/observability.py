"""
Langfuse 观测（Callback 挂到 LangGraph RunnableConfig）

做什么：
- 把一轮对话画成树：节点 → LLM generation → token / 耗时
- 用现有 session_id 聚合；不替代 agent_chat_log / eval

不做什么：
- 不改 graph 节点/边
- 没装包、没配 Key、开关关闭时静默降级，主链路不变
"""

from __future__ import annotations

import logging
import os
from typing import Any

from config import settings

logger = logging.getLogger(__name__)

_warned = False
_client_ready = False


def tracing_enabled() -> bool:
    if not settings.LANGFUSE_ENABLED:
        return False
    return bool(
        (settings.LANGFUSE_PUBLIC_KEY or "").strip()
        and (settings.LANGFUSE_SECRET_KEY or "").strip()
    )


def _ensure_langchain_stub() -> None:
    """Langfuse Callback 会 import langchain；本仓库只有 langchain-core，垫一个 v1 版本号即可。"""
    try:
        import langchain  # noqa: F401
        return
    except ImportError:
        pass
    import sys
    import types

    stub = types.ModuleType("langchain")
    stub.__version__ = "1.0.0"
    sys.modules["langchain"] = stub


def _ensure_client() -> bool:
    """把 Settings 写进环境变量并初始化 Langfuse 单例。失败则关闭本轮追踪。"""
    global _warned, _client_ready
    if not tracing_enabled():
        if settings.LANGFUSE_ENABLED and not _warned:
            logger.info("[Langfuse] 已开启但未配置 PUBLIC/SECRET KEY，跳过追踪")
            _warned = True
        return False
    if _client_ready:
        return True
    try:
        os.environ["LANGFUSE_PUBLIC_KEY"] = settings.LANGFUSE_PUBLIC_KEY.strip()
        os.environ["LANGFUSE_SECRET_KEY"] = settings.LANGFUSE_SECRET_KEY.strip()
        base = (settings.LANGFUSE_BASE_URL or "").strip() or "https://cloud.langfuse.com"
        os.environ["LANGFUSE_BASE_URL"] = base
        _ensure_langchain_stub()
        from langfuse import Langfuse

        Langfuse(
            public_key=settings.LANGFUSE_PUBLIC_KEY.strip(),
            secret_key=settings.LANGFUSE_SECRET_KEY.strip(),
            base_url=base,
        )
        _client_ready = True
        logger.info(f"[Langfuse] 追踪已启用 base={base}")
        return True
    except Exception as e:
        if not _warned:
            logger.warning(
                f"[Langfuse] 初始化失败，追踪不会出现在控制台: {e}。"
                "当前 Python 需安装 langfuse；项目 venv 已有，"
                r"可用 .\venv\Scripts\python.exe main.py 启动"
            )
            _warned = True
        return False


def tracing_ready() -> bool:
    """Key 已配且 SDK 初始化成功，才会真正上报。"""
    return _ensure_client()


def attach_tracing(
    cfg: dict[str, Any],
    *,
    session_id: str = "",
    tags: list[str] | None = None,
    metadata: dict[str, Any] | None = None,
    run_name: str = "agent-chat",
) -> dict[str, Any]:
    """在 RunnableConfig 上挂 CallbackHandler；失败则原样返回 cfg。"""
    if not _ensure_client():
        return cfg
    try:
        from langfuse.langchain import CallbackHandler

        handler = CallbackHandler()
        out = dict(cfg)
        callbacks = list(out.get("callbacks") or [])
        callbacks.append(handler)
        out["callbacks"] = callbacks
        out["run_name"] = run_name
        meta = dict(out.get("metadata") or {})
        if session_id:
            meta["langfuse_session_id"] = session_id
        tag_list = [t for t in (tags or []) if t]
        if tag_list:
            meta["langfuse_tags"] = tag_list
        if metadata:
            meta.update(metadata)
        out["metadata"] = meta
        return out
    except Exception as e:
        logger.warning(f"[Langfuse] 挂载 Callback 失败: {e}")
        return cfg


def flush_tracing() -> None:
    """进程退出前尽量把缓冲 span 发出去。"""
    if not _client_ready:
        return
    try:
        from langfuse import get_client

        get_client().flush()
    except Exception as e:
        logger.warning(f"[Langfuse] flush 失败: {e}")
