"""
会话管理模块

负责存储每个商家的对话历史，实现多轮对话。

为什么需要这个？
现在每次请求都是"失忆"的：
  商家问 "今天营业额多少" → Agent 查了，回复 "3580 元"
  商家问 "那昨天呢"       → Agent 不知道"昨天"是在问营业额，因为它没有之前的记忆

有了会话管理后：
  商家问 "今天营业额多少" → Agent 查了，回复 "3580 元" → 存入历史
  商家问 "那昨天呢"       → Agent 看到历史里有"营业额"，知道在问什么 → 查昨天的营业额
"""

from langchain_core.messages import BaseMessage


# 最大历史消息数（防止对话太长占满上下文窗口）
MAX_HISTORY = 20

# 会话存储：{session_id: [消息列表]}
"""
    {
  "会话A的uuid": [消息1, 消息2, ...],
  "会话B的uuid": [消息1, ...],
    }
"""
_sessions: dict[str, list[BaseMessage]] = {}



def get_history(session_id: str) -> list[BaseMessage]:
    """
    获取指定会话的历史消息。
    如果会话不存在，返回空列表。
    """
    return _sessions.get(session_id, [])


def save_history(session_id: str, messages: list[BaseMessage]):
    """
    保存指定会话的消息历史。
    只保留最近的 MAX_HISTORY 条消息，防止上下文过长。
    """
    # 截断：只保留最近的消息
    _sessions[session_id] = messages[-MAX_HISTORY:]


def clear_history(session_id: str):
    """清空指定会话的历史"""
    _sessions.pop(session_id, None)
