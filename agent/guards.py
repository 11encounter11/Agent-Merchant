"""
工程护栏（面经阶段 1）

做什么：
- 最大工具步数 / token 预算判断
- 工具入参校验、超时重试
- 幂等缓存（同 session + 同工具 + 同参数 → 不重复执行副作用）

不做什么：
- 不做业务决策（那是 analyst/strategist）
- 不替代 reflect 的安全文案清洗
"""

from __future__ import annotations

import asyncio
import hashlib
import json
import logging
import time
from typing import Any, Optional

from config import settings

logger = logging.getLogger(__name__)

# 有副作用、重试时必须走幂等的工具名（只读分析工具可进缓存但非强制）
SIDE_EFFECT_TOOLS = frozenset({
    # 预留：未来写操作（改价、推送等）必须列入
})

# session|tool|args_hash → (expires_at, result_str)
_idempotency_store: dict[str, tuple[float, str]] = {}


def remaining_tool_quota(tool_steps: int) -> int:
    return max(0, settings.MAX_TOOL_STEPS - int(tool_steps or 0))


def is_tool_steps_exceeded(tool_steps: int) -> bool:
    return remaining_tool_quota(tool_steps) <= 0


def total_tokens(token_usage: dict | None) -> int:
    if not token_usage:
        return 0
    return int(token_usage.get("total_tokens") or 0)


def is_token_budget_exceeded(token_usage: dict | None) -> bool:
    return total_tokens(token_usage) >= settings.TOKEN_BUDGET


def merge_token_usage(prev: dict | None, response) -> dict:
    """把单次 LLM response 的 usage 累加进 state.token_usage。"""
    prev = dict(prev or {})
    add_p = add_c = add_t = 0
    if hasattr(response, "usage_metadata") and response.usage_metadata:
        usage = response.usage_metadata
        add_p = usage.get("input_tokens", 0) or usage.get("prompt_tokens", 0) or 0
        add_c = usage.get("output_tokens", 0) or usage.get("completion_tokens", 0) or 0
        add_t = usage.get("total_tokens", 0) or (add_p + add_c)
    merged = {
        "prompt_tokens": int(prev.get("prompt_tokens") or 0) + int(add_p),
        "completion_tokens": int(prev.get("completion_tokens") or 0) + int(add_c),
        "total_tokens": int(prev.get("total_tokens") or 0) + int(add_t),
    }
    return merged


def validate_tool_args(tool, args: dict) -> Optional[str]:
    """
    用工具自带的 args_schema（Pydantic）校验。
    返回 None 表示通过；返回字符串为错误说明。
    """
    schema = getattr(tool, "args_schema", None)
    if schema is None:
        return None
    try:
        if hasattr(schema, "model_validate"):
            schema.model_validate(args or {})
        else:
            schema(**(args or {}))
        return None
    except Exception as e:
        return str(e)


def make_idempotency_key(session_id: str, tool_name: str, args: dict) -> str:
    raw = json.dumps(args or {}, sort_keys=True, ensure_ascii=False, default=str)
    digest = hashlib.sha256(raw.encode("utf-8")).hexdigest()[:16]
    return f"{session_id or 'anon'}|{tool_name}|{digest}"


def idempotency_get(key: str) -> Optional[str]:
    item = _idempotency_store.get(key)
    if not item:
        return None
    expires_at, value = item
    if time.time() > expires_at:
        _idempotency_store.pop(key, None)
        return None
    return value


def idempotency_set(key: str, value: str) -> None:
    ttl = settings.IDEMPOTENCY_TTL_SEC
    _idempotency_store[key] = (time.time() + ttl, value)


async def invoke_tool_guarded(
    tool,
    tool_name: str,
    args: dict,
    session_id: str = "",
) -> str:
    """
    校验 → 幂等命中 → 超时+有限重试 → 写回幂等缓存。
    """
    err = validate_tool_args(tool, args)
    if err:
        logger.warning(f"[Guards] 参数校验失败 {tool_name}: {err}")
        return f"参数校验失败，已拒绝执行（Pydantic）：{err}"

    key = make_idempotency_key(session_id, tool_name, args)
    cached = idempotency_get(key)
    if cached is not None:
        logger.info(f"[Guards] 幂等命中 {tool_name} key={key}")
        return f"[幂等复用] {cached}"

    timeout = settings.TOOL_TIMEOUT_SEC
    retries = settings.TOOL_MAX_RETRIES
    last_err: Any = None

    for attempt in range(1 + retries):
        try:
            result = await asyncio.wait_for(tool.ainvoke(args or {}), timeout=timeout)
            content = result if isinstance(result, str) else str(result)
            # 只读工具也缓存，便于演示「重试不重复打库」；副作用工具强制缓存
            idempotency_set(key, content)
            if attempt > 0:
                logger.info(f"[Guards] {tool_name} 第 {attempt + 1} 次尝试成功")
            return content
        except asyncio.TimeoutError:
            last_err = f"超时（>{timeout}s）"
            logger.warning(f"[Guards] {tool_name} {last_err} attempt={attempt + 1}")
        except Exception as e:
            last_err = e
            logger.warning(f"[Guards] {tool_name} 失败 attempt={attempt + 1}: {e}")
            # 非超时错误：副作用工具不盲目重试，避免重复下单类问题
            if tool_name in SIDE_EFFECT_TOOLS:
                break

    return f"工具 {tool_name} 执行失败（已重试）：{last_err}"


def guard_user_message(reason: str) -> str:
    """护栏触发时给用户的收束文案。"""
    mapping = {
        "max_tool_steps": (
            f"本轮工具调用已达上限（{settings.MAX_TOOL_STEPS} 步），"
            "已停止继续调工具，下面基于已有信息作答。"
        ),
        "token_budget": (
            f"本轮 Token 已接近预算（{settings.TOKEN_BUDGET}），"
            "已停止继续调用模型，下面基于已有信息作答。"
        ),
        "tool_args_invalid": "部分工具参数不合法，已跳过无效调用。",
    }
    return mapping.get(reason, f"本轮已触发护栏（{reason}），停止继续执行。")
