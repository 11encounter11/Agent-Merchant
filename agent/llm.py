"""
LLM 工厂 + 模型路由

做什么：
- 集中创建和管理 LLM 实例（大模型 / 小模型）
- 按意图路由：greeting/thanks/纯知识 → 小模型；分析/复杂 → 大模型
- 路由不准（低置信度）或小模型调用失败 → 回退大模型

不做什么：
- 不在这里调用业务 Prompt（Prompt 在 prompts.py）
- 不在这里做意图分类（perception.py）
"""

from __future__ import annotations

import logging
from typing import Any

import httpx
from langchain_openai import ChatOpenAI

from config import settings
from agent.constants import SIMPLE_INTENTS  # S2 单一真值：与 security 共用

logger = logging.getLogger(__name__)

# (tier, model, bind_key) → ChatOpenAI | RunnableBinding
_llm_cache: dict[tuple, Any] = {}


def model_for_tier(tier: str) -> str:
    """tier=simple|large → 实际模型名。"""
    if tier == "simple":
        return (settings.LLM_MODEL_SIMPLE or "").strip() or settings.LLM_MODEL
    return settings.LLM_MODEL


def resolve_llm_tier(intent: dict | None) -> str:
    """
    简单意图走小模型；分析/复杂/未知走大模型。
    置信度低于阈值时视为路由不准，回退大模型。
    """
    intent = intent or {}
    intent_type = intent.get("intent") or "unknown"
    confidence = float(intent.get("confidence") or 0.0)

    if intent_type not in SIMPLE_INTENTS:
        return "large"

    if settings.LLM_ROUTE_FALLBACK_TO_LARGE and confidence < settings.LLM_ROUTE_CONFIDENCE_MIN:
        logger.info(
            f"[LLM] 路由不准 intent={intent_type} conf={confidence:.2f} "
            f"< {settings.LLM_ROUTE_CONFIDENCE_MIN}，回退大模型"
        )
        return "large"

    return "simple"


def inspect_turn(user_input: str) -> dict:
    """
    感知信号：清洗 → 注入扫描 → 意图 → 模型档位 → 工具白名单。
    perceive 节点与最小评测共用，避免两套逻辑漂移。
    """
    from agent.perception import preprocess, classify_intent
    from agent.security import (
        scan_user_input,
        apply_security_to_intent,
        allowed_tool_names,
    )

    cleaned = preprocess(user_input)
    security = scan_user_input(cleaned)
    intent = classify_intent(cleaned)
    intent, security = apply_security_to_intent(intent, security)
    llm_tier = resolve_llm_tier(intent)
    allowed = sorted(allowed_tool_names(intent.get("intent") or "unknown", security))
    logger.info(
        f"[LLM] 路由 intent={intent.get('intent')} conf={intent.get('confidence')} "
        f"tier={llm_tier} model={model_for_tier(llm_tier)} "
        f"injection={security.get('action')} tools={allowed or '无'}"
    )
    return {
        "user_input": cleaned,
        "intent": intent,
        "security": security,
        "llm_tier": llm_tier,
        "allowed_tools": allowed,
    }


_CONNECT_MARKERS = (
    "connection error",
    "connecterror",
    "connecttimeout",
    "ssl",
    "eof occurred",
    "timed out",
    "timeout",
    "temporarily unavailable",
    "name or service not known",
)


def is_llm_connect_error(exc: BaseException) -> bool:
    """网络/代理/SSL 类错误：节点应收束而不是把图卡在 checkpoint。"""
    if isinstance(exc, (TimeoutError, ConnectionError, OSError, httpx.TransportError)):
        return True
    name = type(exc).__name__.lower()
    if any(x in name for x in ("connect", "timeout", "ssl")):
        return True
    text = str(exc).lower()
    return any(m in text for m in _CONNECT_MARKERS)


def _make_http_clients() -> tuple[httpx.Client, httpx.AsyncClient]:
    """显式 httpx client，避免 langchain-openai 自动改走系统代理。"""
    timeout = httpx.Timeout(60.0, connect=20.0)
    trust = bool(settings.LLM_HTTP_TRUST_ENV)
    return (
        httpx.Client(trust_env=trust, timeout=timeout),
        httpx.AsyncClient(trust_env=trust, timeout=timeout),
    )


def _make_chat(model: str) -> ChatOpenAI:
    sync_client, async_client = _make_http_clients()
    logger.info(
        f"[LLM] HTTP client trust_env={settings.LLM_HTTP_TRUST_ENV} model={model}"
    )
    return ChatOpenAI(
        api_key=settings.LLM_API_KEY,
        base_url=settings.LLM_BASE_URL,
        model=model,
        temperature=settings.LLM_TEMPERATURE,
        http_client=sync_client,
        http_async_client=async_client,
    )


def get_llm(tier: str = "large") -> ChatOpenAI:
    """
    获取基础 LLM（不绑定工具）。
    strategist / reviewer 固定传 large；call_llm 按 state.llm_tier。
    """
    model = model_for_tier(tier)
    key = (tier, model, "base")
    if key not in _llm_cache:
        _llm_cache[key] = _make_chat(model)
        logger.info(f"[LLM] 基础 LLM 已创建: tier={tier} model={model}")
    return _llm_cache[key]


def get_llm_with_tools(tools: list, tier: str = "large") -> Any:
    """
    获取绑定了工具的 LLM。analyst 默认 large。
    按工具名集合缓存，门禁子集不会误用全量绑定。
    """
    model = model_for_tier(tier)
    names = tuple(getattr(t, "name", str(t)) for t in tools)
    key = (tier, model, "tools", names)
    if key not in _llm_cache:
        _llm_cache[key] = _make_chat(model).bind_tools(tools)
        logger.info(
            f"[LLM] 工具 LLM 已创建: tier={tier} model={model}, 绑定 {len(tools)} 个工具"
        )
    return _llm_cache[key]


def invoke_routed(
    messages: list,
    *,
    tier: str,
    tools: list | None = None,
    config: Any = None,
) -> Any:
    """
    按档位调用；小模型失败且与大模型不同名时回退大模型。
    config 传入图运行时的 RunnableConfig，便于 Langfuse 挂到 generation。
    """
    llm = get_llm_with_tools(tools, tier) if tools is not None else get_llm(tier)
    kwargs: dict[str, Any] = {}
    if config is not None:
        kwargs["config"] = config
    try:
        return llm.invoke(messages, **kwargs)
    except Exception as e:
        if is_llm_connect_error(e) and not settings.LLM_HTTP_TRUST_ENV:
            logger.warning(
                "[LLM] 连接失败。若本机开了系统代理仍被劫持，"
                "把 open.bigmodel.cn 加入代理绕过列表。"
            )
        simple_model = model_for_tier("simple")
        large_model = model_for_tier("large")
        if tier != "simple" or simple_model == large_model:
            raise
        logger.warning(f"[LLM] 小模型 {simple_model} 调用失败，回退 {large_model}: {e}")
        fallback = (
            get_llm_with_tools(tools, "large") if tools is not None else get_llm("large")
        )
        return fallback.invoke(messages, **kwargs)
