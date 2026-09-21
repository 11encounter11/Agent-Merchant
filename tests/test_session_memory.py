"""会话记忆文件路径（不依赖 Redis）。"""

import uuid
from pathlib import Path

from agent.memory.session_memory import SessionMemory, SESSION_DIR


def test_append_and_read_file_roundtrip():
    sm = SessionMemory()
    sid = f"test-{uuid.uuid4().hex[:8]}"
    try:
        sm.append_turn(sid, "你好", "您好，我是经营顾问")
        hist = sm.get_history(sid)
        assert len(hist) >= 2
        assert "经营顾问" in (hist[-1].content or "")
    finally:
        sm.clear_history(sid)
        f = SESSION_DIR / f"{sid}.json"
        if f.exists():
            f.unlink()
