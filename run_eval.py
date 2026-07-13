"""
============================================================
Agent 评测脚本（run_eval.py）
============================================================

【教学说明】这个脚本做什么？
自动把评测集里的 50 道题逐题发给 Agent，记录每道题的回复，
最后生成一份评测报告，告诉你哪些题过了、哪些没过。

【用法】
    python run_eval.py                  # 跑全部 50 题
    python run_eval.py --category A     # 只跑 A 类（营业额查询）
    python run_eval.py --ids A01,A02    # 只跑指定题目

【企业里的做法】
企业通常用更完善的评测框架（如 promptfoo、ragas 等），
但核心思路和这个脚本一样：准备题目 → 跑测试 → 分析结果。
"""

import json
import time
import argparse
import httpx
from datetime import datetime


# ============================================================
# 配置
# ============================================================
AGENT_URL = "http://localhost:8100/api/agent/chat"  # 非流式接口（简单）
DATASET_FILE = "eval_dataset.json"                   # 评测集文件
RESULT_DIR = "eval_results"                          # 结果保存目录
TIMEOUT = 60                                         # 每题超时时间（秒）


def load_dataset(category_filter=None, id_filter=None):
    """
    加载评测集，支持按类别或 ID 过滤。

    【教学说明】为什么要加载到列表里？
    因为我们要逐题跑测试，需要把所有题目平铺成一个列表：
    [{"id": "A01", "question": "...", "expect": "...", "category": "..."}, ...]
    """
    with open(DATASET_FILE, "r", encoding="utf-8") as f:
        data = json.load(f)

    questions = []
    for group in data:
        cat = group["category"]

        # 按类别过滤
        if category_filter and not cat.startswith(category_filter):
            continue

        for q in group["questions"]:
            # 按 ID 过滤
            if id_filter and q["id"] not in id_filter:
                continue

            questions.append({
                "id": q["id"],
                "question": q["question"],
                "expect": q["expect"],
                "category": cat
            })

    return questions


def ask_agent(question: str, session_id: str = None) -> dict:
    """
    向 Agent 发一道题，返回回复。

    【教学说明】用非流式接口（/api/agent/chat）而不是流式，
    因为测试时我们只需要"最终答案"，不需要打字机效果。
    非流式更简单：发 POST → 等回复 → 拿到 JSON。
    """
    payload = {"message": question}
    if session_id:
        payload["session_id"] = session_id

    try:
        response = httpx.post(AGENT_URL, json=payload, timeout=TIMEOUT)
        response.raise_for_status()
        data = response.json()
        return {
            "success": True,
            "reply": data.get("reply", ""),
            "session_id": data.get("session_id", "")
        }
    except Exception as e:
        return {
            "success": False,
            "reply": f"[ERROR] {str(e)}",
            "session_id": ""
        }


def judge_result(question: dict, reply: str) -> dict:
    """
    判断一道题是否通过。

    【教学说明】自动判分 vs 人工判分
    这里用的是"关键词匹配"自动判分（简单但不完美）。
    企业里通常用"LLM-as-Judge"（让另一个 AI 来判断答案质量），
    但作为入门，关键词匹配已经够用了。

    判断逻辑：
    - 回复包含 [ERROR] → 失败（接口报错）
    - 回复为空 → 失败
    - 回复包含"还在学习中"或"暂时无法" → 失败（没调工具）
    - 其余 → 标记为"待人工确认"（需要你看一下回复是否合理）
    """
    # 接口报错
    if "[ERROR]" in reply:
        return {"pass": False, "reason": "接口报错"}

    # 回复为空
    if not reply.strip():
        return {"pass": False, "reason": "回复为空"}

    # 没调工具（说了不该说的话）
    bad_phrases = [
        "我还在学习中",
        "暂时无法",
        "我目前还不具备",
        "抱歉，我无法",
    ]
    for phrase in bad_phrases:
        if phrase in reply:
            return {"pass": False, "reason": f"说了'{phrase}'，可能没调工具"}

    # 其余标记为待确认
    return {"pass": True, "reason": "待人工确认"}


def run_eval(category_filter=None, id_filter=None):
    """
    主流程：加载题目 → 逐题测试 → 生成报告
    """
    # 1. 加载评测集
    questions = load_dataset(category_filter, id_filter)
    print(f"\n{'='*60}")
    print(f"  苍穹外卖 Agent 评测")
    print(f"  共 {len(questions)} 题")
    print(f"  时间：{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print(f"{'='*60}\n")

    # 2. 逐题测试
    results = []
    for i, q in enumerate(questions, 1):
        print(f"[{i}/{len(questions)}] {q['id']}: {q['question']}")

        start_time = time.time()
        response = ask_agent(q["question"])
        elapsed = round(time.time() - start_time, 1)

        # 判分
        judgment = judge_result(q, response["reply"])

        result = {
            "id": q["id"],
            "category": q["category"],
            "question": q["question"],
            "expect": q["expect"],
            "reply": response["reply"][:500],  # 只保留前500字
            "pass": judgment["pass"],
            "reason": judgment["reason"],
            "time": elapsed
        }
        results.append(result)

        # 打印即时结果
        status = "✅" if judgment["pass"] else "❌"
        reply_preview = response["reply"][:80].replace("\n", " ")
        print(f"  {status} ({elapsed}s) {reply_preview}...")
        if not judgment["pass"]:
            print(f"  原因: {judgment['reason']}")
        print()

        # 每题之间间隔 1 秒，避免请求太快
        time.sleep(1)

    # 3. 生成报告
    total = len(results)
    passed = sum(1 for r in results if r["pass"])
    failed = total - passed
    accuracy = round(passed / total * 100, 1) if total > 0 else 0

    print(f"\n{'='*60}")
    print(f"  评测报告")
    print(f"{'='*60}")
    print(f"  总计: {total} 题")
    print(f"  通过: {passed} 题 ✅")
    print(f"  失败: {failed} 题 ❌")
    print(f"  准确率: {accuracy}%")
    print(f"{'='*60}\n")

    # 按类别统计
    categories = {}
    for r in results:
        cat = r["category"]
        if cat not in categories:
            categories[cat] = {"total": 0, "passed": 0}
        categories[cat]["total"] += 1
        if r["pass"]:
            categories[cat]["passed"] += 1

    print("  分类准确率:")
    for cat, stats in categories.items():
        cat_acc = round(stats["passed"] / stats["total"] * 100, 1)
        bar = "█" * int(cat_acc / 10) + "░" * (10 - int(cat_acc / 10))
        print(f"  {cat}: {bar} {cat_acc}% ({stats['passed']}/{stats['total']})")

    # 列出失败的题目
    failed_items = [r for r in results if not r["pass"]]
    if failed_items:
        print(f"\n  失败题目详情:")
        print(f"  {'─'*56}")
        for r in failed_items:
            print(f"  {r['id']} | {r['question']}")
            print(f"       原因: {r['reason']}")
            print(f"       回复: {r['reply'][:100]}...")
            print()

    # 4. 保存结果到文件
    import os
    os.makedirs(RESULT_DIR, exist_ok=True)
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    result_file = f"{RESULT_DIR}/eval_{timestamp}.json"
    with open(result_file, "w", encoding="utf-8") as f:
        json.dump({
            "timestamp": timestamp,
            "total": total,
            "passed": passed,
            "accuracy": accuracy,
            "results": results
        }, f, ensure_ascii=False, indent=2)

    print(f"  详细结果已保存到: {result_file}")
    print(f"{'='*60}\n")


# ============================================================
# 命令行入口
# ============================================================
if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Agent 评测脚本")
    parser.add_argument("--category", "-c", help="按类别过滤（如 A、B、C）")
    parser.add_argument("--ids", "-i", help="按 ID 过滤（逗号分隔，如 A01,A02）")
    args = parser.parse_args()

    id_filter = None
    if args.ids:
        id_filter = [x.strip() for x in args.ids.split(",")]

    run_eval(category_filter=args.category, id_filter=id_filter)
