"""B1 冒烟测试：api/routes。

不跑 lifespan（不触 Redis/MySQL/LLM）：agent.service 的入口在测试内 monkeypatch。
"""

from fastapi import FastAPI
from fastapi.testclient import TestClient

import agent.service as agent_service
from api.routes import router

app = FastAPI()
app.include_router(router)
client = TestClient(app)


def test_health():
    resp = client.get("/health")
    assert resp.status_code == 200
    body = resp.json()
    assert body["status"] == "ok"
    assert isinstance(body["langfuse"], bool)


def test_root():
    resp = client.get("/")
    assert resp.status_code == 200
    assert "docs" in resp.json()


def test_chat_success(monkeypatch):
    async def fake_chat(**kwargs):
        return {
            "reply": "好的",
            "session_id": kwargs["session_id"],
            "thread_id": kwargs["thread_id"],
            "rag_hits": [],
        }

    monkeypatch.setattr(agent_service, "chat", fake_chat)
    resp = client.post("/api/agent/chat", json={"message": "你好", "session_id": "smoke-1"})
    body = resp.json()
    assert resp.status_code == 200
    assert body["success"] is True and body["reply"] == "好的"


def test_chat_error_maps_to_friendly_message(monkeypatch):
    async def boom(**kwargs):
        raise RuntimeError("401 invalid_api_key")

    monkeypatch.setattr(agent_service, "chat", boom)
    body = client.post("/api/agent/chat", json={"message": "x"}).json()
    assert body["success"] is False and "API Key" in body["reply"]


def test_chat_stream_events(monkeypatch):
    async def fake_stream(message, session_id, thread_id=None, client_ip=None):
        yield "你"
        yield "好"

    monkeypatch.setattr(agent_service, "chat_stream", fake_stream)
    resp = client.post("/api/agent/chat/stream", json={"message": "hi", "session_id": "smoke-s"})
    assert resp.status_code == 200
    text = resp.text
    assert '"type": "session"' in text
    assert '"type": "content"' in text
    assert '"type": "done"' in text


def test_sessions_list():
    body = client.get("/api/agent/sessions").json()
    assert isinstance(body["sessions"], list)
    assert body["total"] == len(body["sessions"])


def test_delete_session():
    resp = client.delete("/api/agent/sessions/smoke-not-exists")
    assert resp.status_code == 200
    assert resp.json()["success"] is True
