"""模型路由（不调真实 LLM）。"""

from agent.llm import (
    resolve_llm_tier,
    model_for_tier,
    inspect_turn,
    is_llm_connect_error,
    _make_chat,
)
from agent.workers.perceive import perceive
from agent.workers.dispatcher import route_after_dispatcher
from config import settings


def test_simple_intent_uses_small_model():
    assert resolve_llm_tier({"intent": "greeting", "confidence": 0.8}) == "simple"
    assert resolve_llm_tier({"intent": "thanks", "confidence": 0.9}) == "simple"
    assert resolve_llm_tier({"intent": "knowledge", "confidence": 0.75}) == "simple"


def test_complex_intent_uses_large_model():
    assert resolve_llm_tier({"intent": "query_analysis", "confidence": 0.8}) == "large"
    assert resolve_llm_tier({"intent": "query_report", "confidence": 0.8}) == "large"
    assert resolve_llm_tier({"intent": "unknown", "confidence": 0.0}) == "large"


def test_low_confidence_falls_back_to_large(monkeypatch):
    monkeypatch.setattr(settings, "LLM_ROUTE_FALLBACK_TO_LARGE", True)
    assert resolve_llm_tier({"intent": "greeting", "confidence": 0.1}) == "large"


def test_disable_fallback_keeps_simple(monkeypatch):
    monkeypatch.setattr(settings, "LLM_ROUTE_FALLBACK_TO_LARGE", False)
    assert resolve_llm_tier({"intent": "greeting", "confidence": 0.1}) == "simple"


def test_simple_model_defaults_to_large_name():
    assert model_for_tier("simple") == (settings.LLM_MODEL_SIMPLE or settings.LLM_MODEL)
    assert model_for_tier("large") == settings.LLM_MODEL


def test_perceive_greeting_routes_simple():
    out = perceive({"user_input": "你好"})
    assert out["intent"]["intent"] == "greeting"
    assert out["llm_tier"] == "simple"
    assert route_after_dispatcher(out) == "simple"


def test_perceive_analysis_routes_complex_large():
    out = perceive({"user_input": "为什么最近营业额下降"})
    assert out["intent"]["intent"] == "query_analysis"
    assert out["llm_tier"] == "large"
    assert route_after_dispatcher(out) == "complex"


def test_inspect_unknown_falls_back_large():
    turn = inspect_turn("随便聊聊天气之外的事啊")
    assert turn["intent"]["intent"] == "unknown"
    assert turn["llm_tier"] == "large"


def test_connect_error_detection():
    assert is_llm_connect_error(ConnectionError("Connection error."))
    assert is_llm_connect_error(Exception("Connection error."))
    assert is_llm_connect_error(Exception("[SSL: UNEXPECTED_EOF_WHILE_READING] EOF"))
    assert not is_llm_connect_error(ValueError("bad tool args"))


def test_http_client_skips_env_proxy_by_default():
    assert settings.LLM_HTTP_TRUST_ENV is False
    llm = _make_chat("dummy-model")
    client = getattr(llm, "http_client", None) or getattr(llm, "client", None)
    # langchain-openai 把 httpx.Client 挂在 ChatOpenAI.http_client 或 openai client
    trust = getattr(llm, "http_client", None)
    if trust is not None:
        assert trust.trust_env is False
    else:
        inner = getattr(llm.client, "_client", None)
        assert inner is not None
        assert inner.trust_env is False
