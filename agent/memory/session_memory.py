"""
会话记忆（Session Memory）

做什么：
- 存储每个商家的对话历史，实现多轮对话
- JSON 文件持久化（data/sessions/），服务重启不丢失
- Redis 热缓存最近轮次（可用则读/写；不可用自动降级）
- 只存 human + ai 文本，不存 Tool 调用链

不做什么：
- 不做长期偏好记忆（那是 long_term_memory 的事）
- 不做 RAG 检索（那是 knowledge_base 的事）
"""

import json
import logging
from datetime import datetime
from pathlib import Path
from typing import List

from langchain_core.messages import AIMessage, BaseMessage, HumanMessage, ToolMessage

from config import settings

logger = logging.getLogger(__name__)

MAX_HISTORY = settings.MAX_HISTORY
SESSION_DIR = Path(__file__).parent.parent.parent / "data" / "sessions"


def _ensure_dir():
    SESSION_DIR.mkdir(parents=True, exist_ok=True)


def _session_file(session_id: str) -> Path:
    return SESSION_DIR / f"{session_id}.json"


def _redis_key(session_id: str) -> str:
    return f"agent:session:{session_id}"


def _filter_for_storage(messages: List[BaseMessage]) -> List[BaseMessage]:
    """过滤：只保留可回放的多轮对话消息（去掉 Tool 调用链和 RAG 注入）。"""
    cleaned = []
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


def _to_dict(msg: BaseMessage) -> dict:
    if isinstance(msg, HumanMessage):
        return {"role": "human", "content": msg.content}
    elif isinstance(msg, AIMessage):
        return {"role": "ai", "content": msg.content}
    return {"role": "human", "content": str(getattr(msg, "content", ""))}


def _from_dict(d: dict) -> BaseMessage:
    if d.get("role") == "ai":
        return AIMessage(content=d.get("content", ""))
    return HumanMessage(content=d.get("content", ""))


class SessionMemory:
    """会话记忆：文件为权威落盘，Redis 为热缓存。"""

    def get_history(self, session_id: str) -> List[BaseMessage]:
        """同步读：先尝试进程内已知文件；热路径请用 aget_history。"""
        return self._read_file(session_id)

    async def aget_history(self, session_id: str) -> List[BaseMessage]:
        """异步读：Redis → 文件 → 回填 Redis。"""
        cached = await self._redis_get(session_id)
        if cached is not None:
            return cached
        messages = self._read_file(session_id)
        if messages:
            await self._redis_set(session_id, messages)
        return messages

    def save_history(self, session_id: str, messages: List[BaseMessage]):
        """同步写文件（兼容旧调用）。"""
        self._write_file(session_id, messages)

    async def asave_history(self, session_id: str, messages: List[BaseMessage]):
        """异步：文件 + Redis。"""
        self._write_file(session_id, messages)
        await self._redis_set(session_id, messages)

    def append_turn(self, session_id: str, user_text: str, ai_text: str = ""):
        messages = list(self.get_history(session_id))
        if user_text:
            messages.append(HumanMessage(content=user_text))
        if ai_text and str(ai_text).strip():
            messages.append(AIMessage(content=str(ai_text).strip()))
        self.save_history(session_id, messages)

    async def aappend_turn(self, session_id: str, user_text: str, ai_text: str = ""):
        messages = list(await self.aget_history(session_id))
        if user_text:
            messages.append(HumanMessage(content=user_text))
        if ai_text and str(ai_text).strip():
            messages.append(AIMessage(content=str(ai_text).strip()))
        await self.asave_history(session_id, messages)

    def clear_history(self, session_id: str):
        filepath = _session_file(session_id)
        if filepath.exists():
            filepath.unlink()
        # 异步清 Redis 交给调用方；此处尽力同步触发不了 await
        try:
            import asyncio
            loop = asyncio.get_event_loop()
            if loop.is_running():
                loop.create_task(self._redis_delete(session_id))
            else:
                loop.run_until_complete(self._redis_delete(session_id))
        except Exception:
            pass

    def list_sessions(self) -> List[dict]:
        _ensure_dir()
        sessions = []
        for filepath in SESSION_DIR.glob("*.json"):
            try:
                with open(filepath, "r", encoding="utf-8") as f:
                    data = json.load(f)
                sessions.append({
                    "session_id": data.get("session_id", filepath.stem),
                    "created_at": data.get("created_at", ""),
                    "updated_at": data.get("updated_at", ""),
                    "message_count": data.get("message_count", 0),
                })
            except Exception as e:
                logger.error(f"[SessionMemory] 读取失败: {e}")
        sessions.sort(key=lambda x: x["updated_at"], reverse=True)
        return sessions

    # ---- 内部：文件 ----

    def _read_file(self, session_id: str) -> List[BaseMessage]:
        _ensure_dir()
        filepath = _session_file(session_id)
        if not filepath.exists():
            return []
        try:
            with open(filepath, "r", encoding="utf-8") as f:
                data = json.load(f)
            messages = [_from_dict(m) for m in data.get("messages", [])]
            return _filter_for_storage(messages)
        except Exception as e:
            logger.error(f"[SessionMemory] 读取失败: {e}")
            return []

    def _write_file(self, session_id: str, messages: List[BaseMessage]):
        _ensure_dir()
        filepath = _session_file(session_id)
        conversational = _filter_for_storage(messages)
        truncated = conversational[-MAX_HISTORY:]
        msg_dicts = [_to_dict(m) for m in truncated]

        existing = {}
        if filepath.exists():
            try:
                with open(filepath, "r", encoding="utf-8") as f:
                    existing = json.load(f)
            except Exception:
                pass

        data = {
            "session_id": session_id,
            "created_at": existing.get(
                "created_at", datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            ),
            "updated_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            "message_count": len(truncated),
            "messages": msg_dicts,
        }
        try:
            with open(filepath, "w", encoding="utf-8") as f:
                json.dump(data, f, ensure_ascii=False, indent=2)
        except Exception as e:
            logger.error(f"[SessionMemory] 保存失败: {e}")

    # ---- 内部：Redis ----

    async def _redis_get(self, session_id: str) -> List[BaseMessage] | None:
        try:
            from db.redis_client import get_redis

            r = await get_redis()
            if r is None:
                return None
            raw = await r.get(_redis_key(session_id))
            if not raw:
                return None
            data = json.loads(raw)
            messages = [_from_dict(m) for m in data]
            logger.debug(f"[SessionMemory] Redis 命中 session={session_id}")
            return _filter_for_storage(messages)
        except Exception as e:
            logger.warning(f"[SessionMemory] Redis 读取失败: {e}")
            return None

    async def _redis_set(self, session_id: str, messages: List[BaseMessage]) -> None:
        try:
            from db.redis_client import get_redis

            r = await get_redis()
            if r is None:
                return
            conversational = _filter_for_storage(messages)[-MAX_HISTORY:]
            payload = json.dumps(
                [_to_dict(m) for m in conversational], ensure_ascii=False
            )
            await r.set(
                _redis_key(session_id),
                payload,
                ex=settings.REDIS_SESSION_TTL_SEC,
            )
        except Exception as e:
            logger.warning(f"[SessionMemory] Redis 写入失败: {e}")

    async def _redis_delete(self, session_id: str) -> None:
        try:
            from db.redis_client import get_redis

            r = await get_redis()
            if r is None:
                return
            await r.delete(_redis_key(session_id))
        except Exception:
            pass


session_memory = SessionMemory()
