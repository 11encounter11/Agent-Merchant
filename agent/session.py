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

from langchain_core.messages import BaseMessage, HumanMessage, AIMessage, ToolMessage

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


def filter_messages_for_storage(messages: List[BaseMessage]) -> List[BaseMessage]:
    """
    只保留可回放的多轮对话消息。

    为什么要过滤：
    - ToolMessage / 带 tool_calls 的 AIMessage 一旦落盘再加载，
      tool_calls 会丢失，下一轮调用 LLM 会报：
      messages with role "tool" must be a response to a preceding message with "tool_calls"
    - RAG 注入的「[参考信息]」也不应写入会话历史
    """
    cleaned: List[BaseMessage] = []
    for msg in messages:
        if isinstance(msg, ToolMessage):
            continue
        if isinstance(msg, AIMessage):
            if getattr(msg, "tool_calls", None):
                continue
            if not msg.content:
                continue
            cleaned.append(AIMessage(content=msg.content))
            continue
        if isinstance(msg, HumanMessage):
            content = msg.content or ""
            if content.startswith("[参考信息]"):
                continue
            cleaned.append(HumanMessage(content=content))
    return cleaned


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
        # ToolMessage 等不应进入存储；兜底转成 human 文本
        return {"role": "human", "content": str(getattr(msg, "content", ""))}


def _dict_to_message(d: dict) -> BaseMessage:
    """把字典转回 LangChain Message 对象（永不还原为 ToolMessage）"""
    role = d.get("role")
    content = d.get("content", "")
    if role == "ai":
        return AIMessage(content=content)
    # human / unknown / tool 历史脏数据 → 一律当 human，避免再冒出 role=tool
    return HumanMessage(content=content)


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
        # 再次过滤，清掉历史上可能残留的非法串
        messages = filter_messages_for_storage(messages)
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
    
    # 先过滤掉 Tool 调用链，再截断
    conversational = filter_messages_for_storage(messages)
    truncated = conversational[-MAX_HISTORY:]
    
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
