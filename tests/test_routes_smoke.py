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
        async def gen():
            yield "你"
            yield {"type": "rag", "hits": []}
        return gen()

    monkeypatch.setattr(agent_service, "chat_stream", fake_stream)
    resp = client.post("/api/agent/chat/stream", json={"message": "hi", "session_id": "smoke-s"})
    assert resp.status_code == 200
    text = resp.text
    assert "event: session" in text
    assert "event: content" in text and '"type": "content"' in text
    assert "event: rag" in text
    assert "event: done" in text


def test_chat_stream_error_event_not_disguised(monkeypatch):
    async def failing_stream(message, session_id, thread_id=None, client_ip=None):
        async def gen():
            raise RuntimeError("401 invalid_api_key")
        return gen()

    monkeypatch.setattr(agent_service, "chat_stream", failing_stream)
    text = client.post("/api/agent/chat/stream", json={"message": "x"}).text
    assert "event: error" in text
    assert "event: done" in text


def test_chat_resume_endpoint(monkeypatch):
    async def fake_resume(thread_id: str, session_id: str = ""):
        return {"resumed": True, "reply": "续跑结果", "message": "", "session_id": session_id or thread_id, "thread_id": thread_id}

    monkeypatch.setattr(agent_service, "resume_thread", fake_resume)
    resp = client.post("/api/agent/chat/resume", json={"thread_id": "t-1"})
    body = resp.json()
    assert resp.status_code == 200 and body["resumed"] is True and body["reply"] == "续跑结果"


def test_chat_resume_requires_token(monkeypatch):
    monkeypatch.setattr("api.routes.settings.AGENT_API_TOKEN", "secret")
    resp = client.post("/api/agent/chat/resume", json={"thread_id": "t-1"})
    assert resp.status_code == 401


def test_sessions_list():
    body = client.get("/api/agent/sessions").json()
    assert isinstance(body["sessions"], list)
    assert body["total"] == len(body["sessions"])


def test_delete_session():
    resp = client.delete("/api/agent/sessions/smoke-not-exists")
    assert resp.status_code == 200
    assert resp.json()["success"] is True
