"""
会话管理模块（持久化版本）

负责存储每个商家的对话历史，实现多轮对话。
改用 JSON 文件持久化存储，服务重启后对话历史不丢失。

存储结构：
  data/sessions/
  ├── abc-123-uuid.json    ← 会话A的历史
  ├── xyz-456-uuid.json    ← 会话B的历史
  └── ...

每个 JSON 文件格式：
  {
    "session_id": "abc-123",
    "created_at": "2026-07-14 22:30:00",
    "updated_at": "2026-07-14 22:35:00",
    "messages": [
      {"role": "human", "content": "今天营业额多少"},
      {"role": "ai", "content": "今天营业额为257元"},
      ...
    ]
  }
"""

import json
import logging
from datetime import datetime
from pathlib import Path
from typing import List, Optional

from langchain_core.messages import BaseMessage, HumanMessage, AIMessage

logger = logging.getLogger(__name__)

# 最大历史消息数（防止对话太长占满上下文窗口）
MAX_HISTORY = 20

# 会话存储目录
SESSION_DIR = Path(__file__).parent.parent / "data" / "sessions"


def _ensure_session_dir():
    """确保会话存储目录存在"""
    SESSION_DIR.mkdir(parents=True, exist_ok=True)


def _session_file(session_id: str) -> Path:
    """获取会话文件路径"""
    return SESSION_DIR / f"{session_id}.json"


def _message_to_dict(msg: BaseMessage) -> dict:
    """
    把 LangChain Message 对象转成可序列化的字典。
    
    为什么不直接用 msg.dict()？
    因为 LangChain 的 Message 对象包含很多内部字段，
    我们只需要 role 和 content 就够了。
    """
    if isinstance(msg, HumanMessage):
        return {"role": "human", "content": msg.content}
    elif isinstance(msg, AIMessage):
        return {"role": "ai", "content": msg.content}
    else:
        return {"role": "unknown", "content": str(msg.content)}


def _dict_to_message(d: dict) -> BaseMessage:
    """把字典转回 LangChain Message 对象"""
    if d.get("role") == "human":
        return HumanMessage(content=d["content"])
    elif d.get("role") == "ai":
        return AIMessage(content=d["content"])
    else:
        return HumanMessage(content=d["content"])


def get_history(session_id: str) -> List[BaseMessage]:
    """
    获取指定会话的历史消息。
    从 JSON 文件读取，如果文件不存在返回空列表。
    """
    _ensure_session_dir()
    filepath = _session_file(session_id)
    
    if not filepath.exists():
        return []
    
    try:
        with open(filepath, "r", encoding="utf-8") as f:
            data = json.load(f)
        
        messages = [_dict_to_message(m) for m in data.get("messages", [])]
        logger.info(f"[Session] 加载历史: session={session_id}, 消息数={len(messages)}")
        return messages
    except Exception as e:
        logger.error(f"[Session] 读取失败: session={session_id}, error={e}")
        return []


def save_history(session_id: str, messages: List[BaseMessage]):
    """
    保存指定会话的消息历史到 JSON 文件。
    只保留最近的 MAX_HISTORY 条消息，防止上下文过长。
    """
    _ensure_session_dir()
    filepath = _session_file(session_id)
    
    # 截断：只保留最近的消息
    truncated = messages[-MAX_HISTORY:]
    
    # 转为可序列化的字典列表
    msg_dicts = [_message_to_dict(m) for m in truncated]
    
    # 判断是新建还是更新
    is_new = not filepath.exists()
    
    # 读取已有数据（如果有）
    existing_data = {}
    if filepath.exists():
        try:
            with open(filepath, "r", encoding="utf-8") as f:
                existing_data = json.load(f)
        except:
            existing_data = {}
    
    # 构建要保存的数据
    data = {
        "session_id": session_id,
        "created_at": existing_data.get("created_at", datetime.now().strftime("%Y-%m-%d %H:%M:%S")),
        "updated_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "message_count": len(truncated),
        "messages": msg_dicts
    }
    
    try:
        with open(filepath, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
        
        action = "新建" if is_new else "更新"
        logger.info(f"[Session] {action}历史: session={session_id}, 消息数={len(truncated)}")
    except Exception as e:
        logger.error(f"[Session] 保存失败: session={session_id}, error={e}")


def clear_history(session_id: str):
    """清空指定会话的历史（删除 JSON 文件）"""
    filepath = _session_file(session_id)
    if filepath.exists():
        try:
            filepath.unlink()
            logger.info(f"[Session] 清空历史: session={session_id}")
        except Exception as e:
            logger.error(f"[Session] 删除失败: session={session_id}, error={e}")


def list_sessions() -> List[dict]:
    """
    列出所有会话（为前端会话列表做准备）。
    
    返回：
        会话列表，每个包含 session_id、created_at、updated_at、message_count
    """
    _ensure_session_dir()
    sessions = []
    
    for filepath in SESSION_DIR.glob("*.json"):
        try:
            with open(filepath, "r", encoding="utf-8") as f:
                data = json.load(f)
            sessions.append({
                "session_id": data.get("session_id", filepath.stem),
                "created_at": data.get("created_at", ""),
                "updated_at": data.get("updated_at", ""),
                "message_count": data.get("message_count", 0)
            })
        except Exception as e:
            logger.error(f"[Session] 读取失败: {filepath}, error={e}")
    
    # 按更新时间倒序（最新的在前）
    sessions.sort(key=lambda x: x["updated_at"], reverse=True)
    return sessions
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
