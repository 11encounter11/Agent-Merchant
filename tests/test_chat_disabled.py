"""只读演示：CHAT_ENABLED=false 时，对话三端点直接返回说明，不进模型链路、不烧额度。"""

from fastapi import FastAPI
from fastapi.testclient import TestClient

import agent.service as agent_service
from api.routes import router
from config import settings

app = FastAPI()
app.include_router(router)
client = TestClient(app)


def _boom(*args, **kwargs):
    raise AssertionError("对话关闭时不应进入模型链路")


def test_chat_returns_readonly_when_llm_key_missing(monkeypatch):
    monkeypatch.setattr(settings, "CHAT_ENABLED", False)
    monkeypatch.setattr(agent_service, "chat", _boom)

    resp = client.post("/api/agent/chat", json={"message": "最近生意怎么样？"})

    assert resp.status_code == 200
    body = resp.json()
    assert body["success"] is True
    assert "只读演示" in body["reply"]
    assert body["session_id"]


def test_chat_stream_returns_readonly_and_terminates(monkeypatch):
    monkeypatch.setattr(settings, "CHAT_ENABLED", False)
    monkeypatch.setattr(agent_service, "chat_stream", _boom)

    resp = client.post("/api/agent/chat/stream", json={"message": "最近生意怎么样？"})

    assert resp.status_code == 200
    assert "event: session" in resp.text
    assert "只读演示" in resp.text
    assert "event: done" in resp.text
    assert resp.text.index("event: done") > resp.text.index("只读演示")


def test_resume_returns_readonly(monkeypatch):
    monkeypatch.setattr(settings, "CHAT_ENABLED", False)
    monkeypatch.setattr(agent_service, "resume_thread", _boom)

    resp = client.post(
        "/api/agent/chat/resume", json={"thread_id": "t-1", "session_id": "s-1"}
    )

    assert resp.status_code == 200
    body = resp.json()
    assert body["resumed"] is False
    assert "只读演示" in body["message"]


def test_chat_still_works_when_key_present(monkeypatch):
    """控制组：配了 Key 就不能被这道闸门误伤。"""

    async def fake_chat(**kwargs):
        return {
            "reply": "正常回复",
            "session_id": kwargs["session_id"],
            "thread_id": kwargs["thread_id"],
        }

    monkeypatch.setattr(settings, "CHAT_ENABLED", True)
    monkeypatch.setattr(agent_service, "chat", fake_chat)

    resp = client.post("/api/agent/chat", json={"message": "你好"})

    assert resp.json()["reply"] == "正常回复"
