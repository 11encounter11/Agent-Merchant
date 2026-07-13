"""
多轮对话测试脚本

测试流程：
1. 发第一条消息 → 拿到 session_id
2. 用同一个 session_id 发第二条消息 → Agent 应该记住上下文
3. 再发第三条 → 继续记住
"""
import httpx
import json

BASE = "http://localhost:8100/api/agent/chat"

def ask(message, session_id=None):
    """发一条消息，打印结果"""
    payload = {"message": message}
    if session_id:
        payload["session_id"] = session_id

    r = httpx.post(BASE, json=payload, timeout=120.0)
    data = r.json()

    sid = data.get("session_id", "")
    reply = data.get("reply", "")

    print(f"\n{'='*50}")
    print(f"商家：{message}")
    print(f"Agent：{reply[:200]}")
    print(f"session_id：{sid[:20]}...")

    return sid


print("多轮对话测试开始！")
print("=" * 50)

# 第一轮：问今天的营业额
sid = ask("2025年的营业额是多少")

# 第二轮：用同一个 session_id 追问"那2024年呢"
# Agent 应该知道"2024年"也是在问营业额
ask("那2024年呢", sid)

# 第三轮：换个话题
ask("目前有多少用户", sid)

# 第四轮：再追问
ask("今年新增了多少", sid)

print(f"\n{'='*50}")
print("测试完成！如果 Agent 能正确理解'那2024年呢'和'今年新增了多少'")
print("说明多轮对话的记忆功能正常工作。")
