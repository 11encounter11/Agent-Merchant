"""
多轮对话评测脚本（run_multiturn_eval.py）

测试 Agent 的多轮对话能力：上下文理解、指代消解、条件修改等。

与单轮评测的区别：
- 单轮：每题独立 session，互不干扰
- 多轮：同一组对话共享 session_id，测试上下文记忆

用法：
    python run_multiturn_eval.py              # 跑全部 15 组
    python run_multiturn_eval.py --ids MT01   # 只跑指定组
"""

import json
import time
import uuid
import argparse
import httpx
from datetime import datetime


# ============================================================
# 配置
# ============================================================
AGENT_URL = "http://localhost:8100/api/agent/chat"  # 非流式接口
DATASET_FILE = "eval_multiturn.json"
RESULT_DIR = "eval_results"
TIMEOUT = 60


def load_dataset(id_filter=None):
    """加载多轮对话评测集"""
    with open(DATASET_FILE, "r", encoding="utf-8") as f:
        data = json.load(f)
    
    if id_filter:
        data = [item for item in data if item["id"] in id_filter]
    
    return data


def ask_agent(question: str, session_id: str) -> dict:
    """
    向 Agent 发一条消息（带 session_id，保持上下文）。
    
    关键区别：多轮对话必须传同一个 session_id，
    这样 Agent 才能记住之前说了什么。
    """
    payload = {
        "message": question,
        "session_id": session_id
    }
    
    try:
        response = httpx.post(AGENT_URL, json=payload, timeout=TIMEOUT)
        response.raise_for_status()
        data = response.json()
        return {
            "success": True,
            "reply": data.get("reply", ""),
            "session_id": data.get("session_id", session_id)
        }
    except Exception as e:
        return {
            "success": False,
            "reply": f"[ERROR] {str(e)}",
            "session_id": session_id
        }


def run_multiturn_eval(id_filter=None):
    """
    主流程：加载评测集 → 逐组测试 → 生成报告
    
    每组测试的流程：
    1. 生成一个 session_id（本轮对话共享）
    2. 按顺序发送多轮消息
    3. 记录每轮的回复
    4. 标记为"待人工确认"
    """
    # 1. 加载评测集
    conversations = load_dataset(id_filter)
    print(f"\n{'='*60}")
    print(f"  苍穹外卖 Agent 多轮对话评测")
    print(f"  共 {len(conversations)} 组对话")
    print(f"  时间：{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print(f"{'='*60}\n")
    
    # 2. 逐组测试
    all_results = []
    total_turns = 0
    
    for i, conv in enumerate(conversations, 1):
        conv_id = conv["id"]
        description = conv.get("description", "")
        turns = conv["turns"]
        expect = conv.get("expect", "")
        
        print(f"[{i}/{len(conversations)}] {conv_id}: {description}")
        print(f"  预期: {expect}")
        
        # 生成 session_id（本轮对话共享）
        session_id = str(uuid.uuid4())
        
        conv_result = {
            "id": conv_id,
            "description": description,
            "expect": expect,
            "session_id": session_id,
            "turns": []
        }
        
        # 按顺序发送多轮消息
        for j, turn in enumerate(turns, 1):
            user_msg = turn["content"]
            total_turns += 1
            
            print(f"  [{j}/{len(turns)}] 用户: {user_msg}")
            
            start_time = time.time()
            response = ask_agent(user_msg, session_id)
            elapsed = round(time.time() - start_time, 1)
            
            reply_preview = response["reply"][:100].replace("\n", " ")
            status = "✅" if response["success"] else "❌"
            print(f"         {status} ({elapsed}s) {reply_preview}...")
            
            conv_result["turns"].append({
                "turn": j,
                "user": user_msg,
                "reply": response["reply"],
                "success": response["success"],
                "time": elapsed,
                "reason": "待人工确认" if response["success"] else "接口报错"
            })
            
            # 轮次间稍作间隔
            time.sleep(0.5)
        
        all_results.append(conv_result)
        print()
        
        # 组间间隔
        time.sleep(1)
    
    # 3. 生成报告
    print(f"\n{'='*60}")
    print(f"  多轮对话评测报告")
    print(f"{'='*60}")
    print(f"  总计: {len(conversations)} 组对话, {total_turns} 轮")
    
    # 统计成功/失败
    error_turns = 0
    for conv in all_results:
        for turn in conv["turns"]:
            if not turn["success"]:
                error_turns += 1
    
    success_turns = total_turns - error_turns
    print(f"  成功: {success_turns} 轮")
    print(f"  失败: {error_turns} 轮")
    print(f"{'='*60}\n")
    
    # 列出每组的详情
    print("  各组详情:")
    print(f"  {'─'*56}")
    for conv in all_results:
        print(f"\n  {conv['id']}: {conv['description']}")
        print(f"  预期: {conv['expect']}")
        for turn in conv["turns"]:
            status = "✅" if turn["success"] else "❌"
            print(f"    {status} 第{turn['turn']}轮: 用户='{turn['user']}'")
            print(f"       回复: {turn['reply'][:80]}...")
            if not turn["success"]:
                print(f"       原因: {turn['reason']}")
    
    # 4. 保存结果
    import os
    os.makedirs(RESULT_DIR, exist_ok=True)
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    result_file = f"{RESULT_DIR}/multiturn_{timestamp}.json"
    with open(result_file, "w", encoding="utf-8") as f:
        json.dump({
            "timestamp": timestamp,
            "total_conversations": len(conversations),
            "total_turns": total_turns,
            "error_turns": error_turns,
            "results": all_results
        }, f, ensure_ascii=False, indent=2)
    
    print(f"\n  详细结果已保存到: {result_file}")
    print(f"{'='*60}\n")


# ============================================================
# 命令行入口
# ============================================================
if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Agent 多轮对话评测脚本")
    parser.add_argument("--ids", "-i", help="按 ID 过滤（逗号分隔，如 MT01,MT02）")
    args = parser.parse_args()
    
    id_filter = None
    if args.ids:
        id_filter = [x.strip() for x in args.ids.split(",")]
    
    run_multiturn_eval(id_filter=id_filter)
