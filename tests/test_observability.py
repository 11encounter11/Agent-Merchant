"""Langfuse 观测：未配 Key 时不挂 Callback，主链路不变。"""

from agent.checkpointing import thread_config
from agent.observability import attach_tracing, tracing_enabled, tracing_ready
from config import settings


def test_tracing_off_without_keys():
    old_en = settings.LANGFUSE_ENABLED
    old_pk = settings.LANGFUSE_PUBLIC_KEY
    old_sk = settings.LANGFUSE_SECRET_KEY
    settings.LANGFUSE_ENABLED = True
    settings.LANGFUSE_PUBLIC_KEY = ""
    settings.LANGFUSE_SECRET_KEY = ""
    try:
        assert tracing_enabled() is False
        cfg = {"configurable": {"thread_id": "t"}}
        out = attach_tracing(cfg, session_id="s1")
        assert "callbacks" not in out
        assert tracing_ready() is False
    finally:
        settings.LANGFUSE_ENABLED = old_en
        settings.LANGFUSE_PUBLIC_KEY = old_pk
        settings.LANGFUSE_SECRET_KEY = old_sk


def test_tracing_disabled_by_flag():
    old = settings.LANGFUSE_ENABLED
    settings.LANGFUSE_ENABLED = False
    try:
        assert tracing_enabled() is False
        cfg = attach_tracing({"configurable": {"thread_id": "t"}}, session_id="s")
        assert "callbacks" not in cfg
    finally:
        settings.LANGFUSE_ENABLED = old


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
