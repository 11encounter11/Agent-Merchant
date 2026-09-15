"""
Supervisor 调度（面经阶段 2）

模式：Supervisor–Worker（非 Peer 全网状）
- Supervisor 只负责「下一步派谁」，不查库、不写长文
- Worker：analyst / strategist / reviewer / call_llm
- 默认用规则状态机（稳、可测）；计划写入 state.supervisor_plan 便于演示 Plan-and-Execute

为何不用 Peer：经营顾问链路有明确先后（先查数 → 再建议 → 再校验），
Peer 容易互相叫、难控步数；Supervisor 更贴生产稳定性。
"""

from __future__ import annotations

import logging
from typing import Any

from agent.guards import is_token_budget_exceeded, is_tool_steps_exceeded
from config import settings

logger = logging.getLogger(__name__)

WORKERS = ("analyst", "strategist", "reviewer", "call_llm")


def build_plan(intent_type: str) -> list[str]:
    """
    Plan-and-Execute：先定计划再逐步执行。
    - 分析/报告：analyst → strategist → reviewer → call_llm
    - 其它复杂（unknown 等）：先尝试 analyst，无数据则 supervisor 会跳过策略直接 call_llm
    """
    if intent_type in ("query_analysis", "query_report"):
        return ["analyst", "strategist", "reviewer", "call_llm"]
    return ["analyst", "call_llm"]


def decide_next_worker(state: dict[str, Any]) -> dict[str, Any]:
    """
    根据当前成果与历史，决定下一个 worker。
    返回要 merge 进 AgentState 的字段。
    """
    intent = state.get("intent") or {}
    intent_type = intent.get("intent") or "unknown"
    analysis = state.get("analysis_result") or {}
    strategy = state.get("strategy") or {}
    history = list(state.get("worker_history") or [])
    plan = list(state.get("supervisor_plan") or [])
    token_usage = state.get("token_usage") or {}
    tool_steps = int(state.get("tool_steps") or 0)
    guard_reason = state.get("guard_reason") or ""

    if not plan:
        plan = build_plan(intent_type)

    # 护栏：预算/步数触顶 → 直接收束
    if is_token_budget_exceeded(token_usage):
        guard_reason = guard_reason or "token_budget"
        next_worker = "call_llm"
    elif is_tool_steps_exceeded(tool_steps) and "analyst" in history and not analysis:
        guard_reason = guard_reason or "max_tool_steps"
        next_worker = "call_llm"
    elif len(history) >= settings.MAX_SUPERVISOR_ROUNDS:
        logger.warning(
            f"[Supervisor] 轮次触顶 {len(history)}>={settings.MAX_SUPERVISOR_ROUNDS}"
        )
        next_worker = "call_llm"
    else:
        next_worker = _pick_worker(plan, history, analysis, strategy)

    # 防止死循环：同一 worker 连续重复
    if history and history[-1] == next_worker and next_worker != "call_llm":
        logger.warning(f"[Supervisor] 检测到重复派发 {next_worker}，强制 call_llm")
        next_worker = "call_llm"

    new_history = history + [next_worker]
    logger.info(
        f"[Supervisor] plan={plan} history={history} → next={next_worker} "
        f"analysis={bool(analysis)} strategy_src={strategy.get('source')}"
    )

    out: dict[str, Any] = {
        "supervisor_plan": plan,
        "worker_history": new_history,
        "next_worker": next_worker,
    }
    if guard_reason:
        out["guard_reason"] = guard_reason
    return out


def _pick_worker(
    plan: list[str],
    history: list[str],
    analysis: dict,
    strategy: dict,
) -> str:
    """按计划 + 成果推进；缺数据时跳过 strategist/reviewer。"""
    done = set(history)

    for step in plan:
        if step in done:
            continue

        if step == "analyst":
            return "analyst"

        if step == "strategist":
            # 必须先有分析结果，否则跳过
            if analysis:
                return "strategist"
            continue

        if step == "reviewer":
            # 有策略且尚未经 reviewer
            if strategy.get("recommendations") and strategy.get("source") != "reviewer":
                return "reviewer"
            continue

        if step == "call_llm":
            return "call_llm"

    return "call_llm"
