"""
Agent 自动化测试脚本

用法（先启动服务：python main.py）：
    python scripts/run_test.py              # 跑全部（单轮 + 多轮）
    python scripts/run_test.py --mode single
    python scripts/run_test.py --mode multi
    python scripts/run_test.py --ids A01,E02,M01
    python scripts/run_test.py --category 营业额
"""

from __future__ import annotations

import argparse
import json
import re
import sys
import time
from datetime import datetime
from pathlib import Path

import httpx

_ROOT = Path(__file__).resolve().parent.parent
DATASET_FILE = _ROOT / "eval" / "test_cases.json"
RESULT_DIR = _ROOT / "eval" / "results"
AGENT_URL = "http://localhost:8100/api/agent/chat"
TIMEOUT = 90
SLEEP_BETWEEN = 0.8


def load_dataset() -> dict:
    with open(DATASET_FILE, "r", encoding="utf-8") as f:
        return json.load(f)


def ask_agent(question: str, session_id: str | None = None) -> dict:
    payload = {"message": question}
    if session_id:
        payload["session_id"] = session_id
    try:
        resp = httpx.post(AGENT_URL, json=payload, timeout=TIMEOUT)
        # 业务层失败也会返回 200 + success=false（额度不足等）
        try:
            data = resp.json()
        except Exception:
            data = {}

        if resp.status_code >= 400:
            detail = data.get("reply") or data.get("detail") or resp.text[:300]
            return {
                "ok": False,
                "reply": f"[ERROR] HTTP {resp.status_code}: {detail}",
                "session_id": data.get("session_id") or session_id or "",
            }

        reply = data.get("reply") or ""
        ok = bool(data.get("success", True))
        # 额度/密钥等业务错误：success=false，仍保留可读 reply
        if not ok:
            return {
                "ok": False,
                "reply": reply or "[ERROR] success=false",
                "session_id": data.get("session_id") or session_id or "",
            }
        return {
            "ok": True,
            "reply": reply,
            "session_id": data.get("session_id") or "",
        }
    except Exception as e:
        return {"ok": False, "reply": f"[ERROR] {e}", "session_id": session_id or ""}


def _has_number(text: str) -> bool:
    return bool(re.search(r"\d+", text))


def judge(reply: str, checks: dict | None, request_ok: bool) -> dict:
    """按 checks 规则判题。返回 {pass, reason}。"""
    if not request_ok or reply.startswith("[ERROR]"):
        reason = "接口请求失败"
        if "免费额度" in reply or "FreeTier" in reply:
            reason = "通义千问免费额度已用完"
        elif "API Key" in reply:
            reason = "LLM API Key 无效"
        return {"pass": False, "reason": reason}

    if not (reply or "").strip():
        return {"pass": False, "reason": "回复为空"}

    checks = checks or {}

    if checks.get("must_have_number") and not _has_number(reply):
        return {"pass": False, "reason": "期望回复含数字，但没有"}

    must_any = checks.get("must_contain_any") or []
    if must_any and not any(k.lower() in reply.lower() for k in must_any):
        return {
            "pass": False,
            "reason": f"未命中任一关键词: {must_any}",
        }

    must_all = checks.get("must_contain_all") or []
    for k in must_all:
        if k.lower() not in reply.lower():
            return {"pass": False, "reason": f"缺少必含词: {k}"}

    forbidden = checks.get("must_not_contain") or []
    for k in forbidden:
        if k.lower() in reply.lower():
            return {"pass": False, "reason": f"出现禁用词: {k}"}

    return {"pass": True, "reason": "规则通过"}


def preview(text: str, n: int = 90) -> str:
    return (text or "").replace("\n", " ").strip()[:n]


def run_single(cases: list[dict]) -> list[dict]:
    results = []
    total = len(cases)
    for i, case in enumerate(cases, 1):
        print(f"[{i}/{total}] {case['id']} | {case['question']}")
        t0 = time.time()
        resp = ask_agent(case["question"])
        elapsed = round(time.time() - t0, 1)
        judgment = judge(resp["reply"], case.get("checks"), resp["ok"])

        item = {
            "id": case["id"],
            "category": case.get("category", ""),
            "mode": "single",
            "question": case["question"],
            "expect": case.get("expect", ""),
            "reply": resp["reply"][:800],
            "pass": judgment["pass"],
            "reason": judgment["reason"],
            "time": elapsed,
            "session_id": resp.get("session_id", ""),
        }
        results.append(item)

        mark = "PASS" if judgment["pass"] else "FAIL"
        print(f"  [{mark}] ({elapsed}s) {preview(resp['reply'])}")
        if not judgment["pass"]:
            print(f"  原因: {judgment['reason']}")
        print()
        time.sleep(SLEEP_BETWEEN)
    return results


def run_multi(groups: list[dict]) -> list[dict]:
    results = []
    total = len(groups)
    for i, group in enumerate(groups, 1):
        print(f"[{i}/{total}] {group['id']} | {group.get('title', '多轮')}")
        session_id = None
        turn_results = []
        group_pass = True

        for turn_idx, turn in enumerate(group.get("turns", []), 1):
            q = turn["question"]
            print(f"  回合{turn_idx}: {q}")
            t0 = time.time()
            resp = ask_agent(q, session_id=session_id)
            elapsed = round(time.time() - t0, 1)
            session_id = resp.get("session_id") or session_id
            judgment = judge(resp["reply"], turn.get("checks"), resp["ok"])
            if not judgment["pass"]:
                group_pass = False

            turn_results.append({
                "turn": turn_idx,
                "question": q,
                "reply": resp["reply"][:500],
                "pass": judgment["pass"],
                "reason": judgment["reason"],
                "time": elapsed,
            })
            mark = "PASS" if judgment["pass"] else "FAIL"
            print(f"    [{mark}] ({elapsed}s) {preview(resp['reply'])}")
            if not judgment["pass"]:
                print(f"    原因: {judgment['reason']}")
            time.sleep(SLEEP_BETWEEN)

        results.append({
            "id": group["id"],
            "category": group.get("category", "多轮"),
            "mode": "multi",
            "title": group.get("title", ""),
            "session_id": session_id,
            "pass": group_pass,
            "reason": "全部回合通过" if group_pass else "存在失败回合",
            "turns": turn_results,
            "time": round(sum(t["time"] for t in turn_results), 1),
        })
        print(f"  组结果: {'PASS' if group_pass else 'FAIL'}\n")
    return results


def print_report(results: list[dict]) -> None:
    total = len(results)
    passed = sum(1 for r in results if r["pass"])
    failed = total - passed
    accuracy = round(passed / total * 100, 1) if total else 0.0

    print("=" * 60)
    print("  测试报告")
    print("=" * 60)
    print(f"  总计: {total}")
    print(f"  通过: {passed}")
    print(f"  失败: {failed}")
    print(f"  通过率: {accuracy}%")
    print("=" * 60)

    by_cat: dict[str, dict] = {}
    for r in results:
        cat = r.get("category") or "未分类"
        by_cat.setdefault(cat, {"total": 0, "passed": 0})
        by_cat[cat]["total"] += 1
        if r["pass"]:
            by_cat[cat]["passed"] += 1

    print("\n  分类:")
    for cat, stats in by_cat.items():
        acc = round(stats["passed"] / stats["total"] * 100, 1)
        print(f"  - {cat}: {acc}% ({stats['passed']}/{stats['total']})")

    failed_items = [r for r in results if not r["pass"]]
    if failed_items:
        print("\n  失败详情:")
        for r in failed_items:
            q = r.get("question") or r.get("title") or ""
            print(f"  - {r['id']}: {q}")
            print(f"    原因: {r['reason']}")
    print()


def save_results(results: list[dict]) -> Path:
    RESULT_DIR.mkdir(parents=True, exist_ok=True)
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    path = RESULT_DIR / f"test_{ts}.json"
    total = len(results)
    passed = sum(1 for r in results if r["pass"])
    payload = {
        "timestamp": ts,
        "total": total,
        "passed": passed,
        "accuracy": round(passed / total * 100, 1) if total else 0.0,
        "results": results,
    }
    with open(path, "w", encoding="utf-8") as f:
        json.dump(payload, f, ensure_ascii=False, indent=2)
    return path


def health_check() -> bool:
    try:
        r = httpx.get("http://localhost:8100/health", timeout=5)
        return r.status_code == 200
    except Exception:
        return False


def main() -> int:
    parser = argparse.ArgumentParser(description="苍穹外卖 Agent 自动化测试")
    parser.add_argument(
        "--mode",
        choices=["all", "single", "multi"],
        default="all",
        help="测试模式：全部 / 仅单轮 / 仅多轮",
    )
    parser.add_argument("--ids", help="按 ID 过滤，逗号分隔，如 A01,E02,M01")
    parser.add_argument("--category", help="按类别过滤，如 营业额 / 菜品 / 多轮")
    args = parser.parse_args()

    if not health_check():
        print("错误：无法连接 http://localhost:8100/health")
        print("请先启动服务：python main.py")
        return 1

    data = load_dataset()
    id_set = {x.strip() for x in args.ids.split(",")} if args.ids else None

    single_cases = data.get("single", [])
    multi_groups = data.get("multi", [])

    if id_set:
        single_cases = [c for c in single_cases if c["id"] in id_set]
        multi_groups = [g for g in multi_groups if g["id"] in id_set]
    if args.category:
        single_cases = [c for c in single_cases if args.category in c.get("category", "")]
        multi_groups = [g for g in multi_groups if args.category in g.get("category", "")]

    results: list[dict] = []
    print("\n" + "=" * 60)
    print("  苍穹外卖 Agent 自动化测试")
    print(f"  时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print("=" * 60 + "\n")

    if args.mode in ("all", "single") and single_cases:
        print(f"--- 单轮 {len(single_cases)} 题 ---\n")
        results.extend(run_single(single_cases))

    if args.mode in ("all", "multi") and multi_groups:
        print(f"--- 多轮 {len(multi_groups)} 组 ---\n")
        results.extend(run_multi(multi_groups))

    if not results:
        print("没有匹配到任何用例，请检查 --ids / --category / --mode")
        return 1

    print_report(results)
    out = save_results(results)
    print(f"详细结果已保存: {out}")

    failed = sum(1 for r in results if not r["pass"])
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
