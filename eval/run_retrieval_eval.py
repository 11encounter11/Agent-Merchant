"""
检索质量离线评测（不调 LLM）。

为什么需要它：意图评测（run_eval.py）只能证明「路由对了」，证明不了
「知识召回了」。没有 question → 期望来源 的验收集，改 keywords、改切片、
改向量策略全凭手感，调参不可证伪。

指标：
- Recall@K  —— 期望来源是否出现在 top-K（召回是否够）
- MRR       —— 第一条命中来源的排名倒数均值（排得够不够前）
- 零命中率   —— 负例是否干净（无关问题不该注入参考信息）

用法：
    python eval/run_retrieval_eval.py                 # 仅关键词层（不需要任何 Key）
    python eval/run_retrieval_eval.py --vector        # 打开向量腿（需 EMBEDDING_API_KEY/LLM_API_KEY）
    python eval/run_retrieval_eval.py --ids H01,N01
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

from agent.knowledge.knowledge_base import KnowledgeBase  # noqa: E402
from agent.perception import classify_intent  # noqa: E402

DATASET = Path(__file__).resolve().parent / "retrieval_cases.json"
RESULT_DIR = Path(__file__).resolve().parent / "results"
TOP_K = 3


def load_cases() -> list[dict]:
    with open(DATASET, "r", encoding="utf-8") as f:
        return json.load(f).get("cases") or []


def build_kb(use_vector: bool) -> KnowledgeBase:
    kb = KnowledgeBase(enable_vector=use_vector)
    if use_vector:
        kb.warmup()
    else:
        kb.load_data()
    return kb


def evaluate(kb: KnowledgeBase, cases: list[dict], use_vector: bool) -> list[dict]:
    rows = []
    for case in cases:
        question = case["question"]
        intent = (classify_intent(question) or {}).get("intent") or "unknown"
        hits = kb.search_hits(question, top_k=TOP_K, use_vector=use_vector, intent_type=intent)
        got_sources = [h.get("source") or "" for h in hits]
        layers = sorted({h.get("layer") or "" for h in hits})

        expect = list(case.get("expect_sources") or [])
        if expect:
            rank = next((i + 1 for i, s in enumerate(got_sources) if s in expect), 0)
            passed = rank > 0
            reason = "命中" if passed else f"期望 {expect}，实际 {got_sources or '零命中'}"
        else:
            passed = not got_sources
            rank = 0
            reason = "零命中（正确）" if passed else f"不应命中却召回 {got_sources}"

        rows.append({
            "id": case["id"],
            "category": case.get("category", ""),
            "question": question,
            "intent": intent,
            "expect_sources": expect,
            "got_sources": got_sources,
            "layers": layers,
            "needs_vector": bool(case.get("needs_vector")),
            "rank": rank,
            "pass": passed,
            "reason": reason,
        })
    return rows


def summarize(rows: list[dict]) -> dict:
    pos = [r for r in rows if r["expect_sources"]]
    neg = [r for r in rows if not r["expect_sources"]]
    hit = [r for r in pos if r["pass"]]
    mrr = round(sum(1.0 / r["rank"] for r in hit) / len(hit), 4) if hit else 0.0
    semantic = [r for r in pos if r["needs_vector"]]
    semantic_hit = [r for r in semantic if r["pass"]]
    return {
        "total": len(rows),
        "passed": sum(1 for r in rows if r["pass"]),
        "positive": len(pos),
        "positive_hit": len(hit),
        "recall_at_k": round(len(hit) / len(pos) * 100, 1) if pos else 0.0,
        "mrr": mrr,
        "negative": len(neg),
        "negative_clean": sum(1 for r in neg if r["pass"]),
        "semantic_cases": len(semantic),
        "semantic_hit": len(semantic_hit),
        "vector_leg": any("vector" in r["layers"] for r in rows),
    }


def print_table(rows: list[dict], stats: dict, use_vector: bool) -> None:
    print()
    print(f"{'ID':<5} {'分类':<8} {'意图':<15} {'结果':<5} {'来源':<22} {'层':<16} 说明")
    print("-" * 108)
    for r in rows:
        mark = "PASS" if r["pass"] else "FAIL"
        print(
            f"{r['id']:<5} {r['category']:<8} {r['intent']:<15} {mark:<5} "
            f"{','.join(r['got_sources']) or '-':<22} {'+'.join(r['layers']) or '-':<16} {r['reason']}"
        )
    print("-" * 108)
    mode = "关键词 + 向量" if use_vector else "仅关键词（未开向量腿）"
    print(f"检索模式：{mode}")
    print(
        f"Recall@{TOP_K}：{stats['positive_hit']}/{stats['positive']} = {stats['recall_at_k']}%   "
        f"MRR：{stats['mrr']}   负例干净：{stats['negative_clean']}/{stats['negative']}"
    )
    if stats["semantic_cases"]:
        print(
            f"语义改写类（字面无关键词）：{stats['semantic_hit']}/{stats['semantic_cases']} 命中"
            + ("" if use_vector else "  ← 这批只能靠向量腿召回，需 --vector 才算完整")
        )
    print()


def save(rows: list[dict], stats: dict, use_vector: bool) -> Path:
    RESULT_DIR.mkdir(parents=True, exist_ok=True)
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    path = RESULT_DIR / f"retrieval_{ts}.json"
    payload = {
        "timestamp": ts,
        "top_k": TOP_K,
        "use_vector": bool(use_vector),
        "stats": stats,
        "results": rows,
    }
    with open(path, "w", encoding="utf-8") as f:
        json.dump(payload, f, ensure_ascii=False, indent=2)
    return path


def main() -> int:
    parser = argparse.ArgumentParser(description="检索质量评测：Recall@K / MRR / 负例干净度")
    parser.add_argument("--vector", action="store_true", help="启用向量腿（需 embedding Key）")
    parser.add_argument("--ids", help="按 ID 过滤，逗号分隔")
    args = parser.parse_args()

    cases = load_cases()
    if args.ids:
        keep = {x.strip() for x in args.ids.split(",")}
        cases = [c for c in cases if c["id"] in keep]
    if not cases:
        print("没有匹配到用例")
        return 1

    print("=" * 60)
    print("  检索质量评测（不调 LLM）")
    print(f"  {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print("=" * 60)

    kb = build_kb(args.vector)
    print(f"知识库状态：{kb.status()}")

    rows = evaluate(kb, cases, args.vector)
    stats = summarize(rows)
    print_table(rows, stats, args.vector)
    out = save(rows, stats, args.vector)
    print(f"详细结果: {out}")
    failed = [r for r in rows if not r["pass"]]
    return 0 if not failed else 1


if __name__ == "__main__":
    sys.exit(main())
