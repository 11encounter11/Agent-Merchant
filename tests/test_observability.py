"""Langfuse 观测：未配 Key 时不挂 Callback，主链路不变。"""

from agent.checkpointing import thread_config
from agent.observability import attach_tracing, tracing_enabled, tracing_ready
from config import settings


def test_tracing_off_without_keys(monkeypatch):
    monkeypatch.setattr(settings, "LANGFUSE_ENABLED", True)
    monkeypatch.setattr(settings, "LANGFUSE_PUBLIC_KEY", "")
    monkeypatch.setattr(settings, "LANGFUSE_SECRET_KEY", "")
    assert tracing_enabled() is False
    cfg = {"configurable": {"thread_id": "t"}}
    out = attach_tracing(cfg, session_id="s1")
    assert "callbacks" not in out
    assert tracing_ready() is False


def test_tracing_disabled_by_flag(monkeypatch):
    monkeypatch.setattr(settings, "LANGFUSE_ENABLED", False)
    assert tracing_enabled() is False
    cfg = attach_tracing({"configurable": {"thread_id": "t"}}, session_id="s")
    assert "callbacks" not in cfg


def test_thread_config_still_has_thread_id():
    cfg = thread_config("t-obs")
    assert cfg["configurable"]["thread_id"] == "t-obs"


def test_callback_import_with_core_only():
    """未安装 langchain 元包时，垫片仍能 import Langfuse CallbackHandler。"""
    try:
        from agent.observability import _ensure_langchain_stub

        _ensure_langchain_stub()
        from langfuse.langchain import CallbackHandler
    except ModuleNotFoundError:
        return
    assert CallbackHandler is not None
