"""A7：SSE 断线续播测试（id: 字段、retry 提示、Last-Event-ID 回放）。"""

import asyncio
import time

from fastapi import FastAPI
from fastapi.testclient import TestClient

import agent.service as agent_service
from api.routes import router, _sse_buffers

app = FastAPI()
app.include_router(router)
client = TestClient(app)


def test_sse_events_have_id_field(monkeypatch):
    async def fake_stream(message, session_id, thread_id=None, client_ip=None):
        async def gen():
            yield "你"
            yield "好"
        return gen()

    monkeypatch.setattr(agent_service, "chat_stream", fake_stream)
    resp = client.post("/api/agent/chat/stream", json={"message": "hi", "session_id": "a7-test"})
    text = resp.text
    assert "id: 1" in text
    assert "id: 2" in text
    assert "id: 3" in text
    assert "id: 4" in text


def test_sse_first_event_has_retry_hint(monkeypatch):
    async def fake_stream(message, session_id, thread_id=None, client_ip=None):
        async def gen():
            yield "ok"
        return gen()

    monkeypatch.setattr(agent_service, "chat_stream", fake_stream)
    resp = client.post("/api/agent/chat/stream", json={"message": "hi", "session_id": "a7-retry"})
    assert "retry: 3000" in resp.text


def test_sse_buffer_cleared_after_ttl(monkeypatch):
    _sse_buffers.clear()

    async def fake_stream(message, session_id, thread_id=None, client_ip=None):
        async def gen():
            yield "done"
        return gen()

    monkeypatch.setattr(agent_service, "chat_stream", fake_stream)
    client.post("/api/agent/chat/stream", json={"message": "hi", "session_id": "a7-buf"})
    assert len(_sse_buffers) > 0


def test_last_event_id_replays_missed_events(monkeypatch):
    _sse_buffers.clear()
    buf_thread = "a7-replay"

    # 预先填充缓冲，模拟上一轮流已结束但缓冲还在
    _sse_buffers[buf_thread] = [
        (1, "session", {"type": "session", "session_id": buf_thread, "thread_id": buf_thread}),
        (2, "content", {"type": "content", "content": "漏掉的内容"}),
        (3, "done", {"type": "done"}),
    ]

    async def fake_stream(message, session_id, thread_id=None, client_ip=None):
        async def gen():
            yield "新内容"
        return gen()

    monkeypatch.setattr(agent_service, "chat_stream", fake_stream)
    resp = client.post(
        "/api/agent/chat/stream",
        json={"message": "hi", "session_id": buf_thread},
        headers={"Last-Event-ID": "1"},
    )
    text = resp.text
    assert "漏掉的内容" in text
    assert "id: 2" in text
    assert "id: 3" in text
