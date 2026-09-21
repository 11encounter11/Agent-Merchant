"""护栏单测（不依赖 LLM / DB）。"""

import asyncio

from agent.guards import (
    remaining_tool_quota,
    is_tool_steps_exceeded,
    is_token_budget_exceeded,
    make_idempotency_key,
    idempotency_get,
    idempotency_set,
    validate_tool_args,
    invoke_tool_guarded,
)
from config import settings


def test_tool_step_quota():
    assert remaining_tool_quota(0) == settings.MAX_TOOL_STEPS
    assert is_tool_steps_exceeded(settings.MAX_TOOL_STEPS)
    assert not is_tool_steps_exceeded(0)


def test_token_budget():
    assert not is_token_budget_exceeded({"total_tokens": 0})
    assert is_token_budget_exceeded({"total_tokens": settings.TOKEN_BUDGET})


def test_idempotency_roundtrip():
    key = make_idempotency_key("s1", "factor_decomposition", {"begin_date": "2026-01-01"})
    assert idempotency_get(key) is None
    idempotency_set(key, "ok-result")
    assert idempotency_get(key) == "ok-result"


class _FakeTool:
    name = "fake"
    args_schema = None
    calls = 0

    async def ainvoke(self, args):
        self.calls += 1
        return f"ran:{args}"


def test_invoke_tool_idempotent_no_double_side_effect():
    tool = _FakeTool()

    async def run():
        a = await invoke_tool_guarded(tool, "fake", {"x": 1}, session_id="sess")
        b = await invoke_tool_guarded(tool, "fake", {"x": 1}, session_id="sess")
        return a, b

    a, b = asyncio.run(run())
    assert tool.calls == 1
    assert "ran" in a
    assert b.startswith("[幂等复用]")


def test_validate_missing_schema_ok():
    tool = _FakeTool()
    assert validate_tool_args(tool, {"anything": True}) is None
