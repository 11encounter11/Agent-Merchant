"""
离线评测（不启动服务、不调 LLM）。

检查：意图分类、小/大模型路由、工具门禁、提示注入、边界拒绝。
输出对错表，并写入 eval/results/。

用法：
    python eval/run_eval.py
    python eval/run_eval.py --ids I01,S01
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime
from pathlib import Path

_ROOT = Path(__file__).resolve().parent.parent
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from agent.llm import inspect_turn
from agent.workers.dispatcher import route_after_dispatcher
from agent.security import is_tool_allowed

DATASET = Path(__file__).resolve().parent / "cases.json"
RESULT_DIR = Path(__file__).resolve().parent / "results"


def load_cases() -> list[dict]:
    with open(DATASET, "r", encoding="utf-8") as f:
        return json.load(f).get("cases") or []


def judge(case: dict, turn: dict) -> tuple[bool, str]:
    intent = (turn.get("intent") or {}).get("intent")
    security = turn.get("security") or {}
    reasons: list[str] = []

    expected_intent = case.get("expect_intent")
    if expected_intent and intent != expected_intent:
        reasons.append(f"意图 {intent} != {expected_intent}")

    expected_tier = case.get("expect_llm_tier")
    if expected_tier and turn.get("llm_tier") != expected_tier:
        reasons.append(f"档位 {turn.get('llm_tier')} != {expected_tier}")

    expected_route = case.get("expect_route")
    if expected_route:
        actual_route = route_after_dispatcher(turn)
        if actual_route != expected_route:
            reasons.append(f"图路由 {actual_route} != {expected_route}")

    if "expect_injection" in case:
        actual = bool(security.get("injection"))
        if actual != bool(case["expect_injection"]):
            reasons.append(f"注入标记 {actual} != {case['expect_injection']}")

    expected_action = case.get("expect_action")
    if expected_action and security.get("action") != expected_action:
        reasons.append(f"动作 {security.get('action')} != {expected_action}")

    if case.get("expect_tools_empty"):
        if turn.get("allowed_tools"):
            reasons.append(f"期望无工具，实际 {turn.get('allowed_tools')}")

    probe = case.get("probe_tool")
    if probe:
        allowed = is_tool_allowed(intent or "unknown", probe, security)
        expect_allowed = bool(case.get("expect_tool_allowed"))
        if allowed != expect_allowed:
            reasons.append(
                f"工具 {probe} allowed={allowed} != {expect_allowed}"
            )

    if reasons:
        return False, "; ".join(reasons)
    return True, "通过"


def print_table(rows: list[dict]) -> None:
    total = len(rows)
    passed = sum(1 for r in rows if r["pass"])
    print()
    print(f"{'ID':<6} {'分类':<10} {'结果':<6} {'意图':<16} {'档位':<8} 说明")
    print("-" * 78)
    for r in rows:
        mark = "PASS" if r["pass"] else "FAIL"
        print(
            f"{r['id']:<6} {r['category']:<10} {mark:<6} "
            f"{r['intent']:<16} {r['llm_tier']:<8} {r['reason']}"
        )
    print("-" * 78)
    acc = round(passed / total * 100, 1) if total else 0.0
    print(f"通过 {passed}/{total}  通过率 {acc}%")
    print()


def save(rows: list[dict]) -> Path:
    RESULT_DIR.mkdir(parents=True, exist_ok=True)
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    path = RESULT_DIR / f"eval_{ts}.json"
    passed = sum(1 for r in rows if r["pass"])
    payload = {
        "timestamp": ts,
        "total": len(rows),
        "passed": passed,
        "accuracy": round(passed / len(rows) * 100, 1) if rows else 0.0,
        "results": rows,
    }
    with open(path, "w", encoding="utf-8") as f:
        json.dump(payload, f, ensure_ascii=False, indent=2)
    return path


def main() -> int:
    parser = argparse.ArgumentParser(description="离线评测：意图 / 路由 / 门禁 / 注入 / 边界")
    parser.add_argument("--ids", help="按 ID 过滤，逗号分隔")
    args = parser.parse_args()

    cases = load_cases()
    if args.ids:
        id_set = {x.strip() for x in args.ids.split(",")}
        cases = [c for c in cases if c["id"] in id_set]
    if not cases:
        print("没有匹配到用例")
        return 1

    print("=" * 60)
    print("  离线评测（不调 LLM）")
    print(f"  {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print("=" * 60)

    rows: list[dict] = []
    for case in cases:
        turn = inspect_turn(case["question"])
        ok, reason = judge(case, turn)
        rows.append({
            "id": case["id"],
            "category": case.get("category", ""),
            "question": case["question"],
            "intent": (turn.get("intent") or {}).get("intent"),
            "llm_tier": turn.get("llm_tier"),
            "allowed_tools": turn.get("allowed_tools"),
            "security": turn.get("security"),
            "pass": ok,
            "reason": reason,
        })

    print_table(rows)
    out = save(rows)
    print(f"详细结果: {out}")
    return 0 if all(r["pass"] for r in rows) else 1


if __name__ == "__main__":
    sys.exit(main())
