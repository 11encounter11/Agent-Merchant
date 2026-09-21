"""B6d：对话反馈端点冒烟（不触真实 MySQL）。"""

from fastapi import FastAPI
from fastapi.testclient import TestClient

import db.feedback as feedback_mod
from api.routes import router
from config import settings

app = FastAPI()
app.include_router(router)
client = TestClient(app)


def test_feedback_success(monkeypatch):
    saved = {}

    async def fake_append(**kwargs):
        saved.update(kwargs)
        return True

    monkeypatch.setattr(feedback_mod, "append_feedback", fake_append)
    resp = client.post(
        "/api/agent/feedback",
        json={"session_id": "s1", "thread_id": "t1", "rating": "down", "comment": "数字不对"},
    )
    body = resp.json()
    assert resp.status_code == 200 and body["success"] is True
    assert saved["rating"] == "down" and saved["comment"] == "数字不对"


def test_feedback_degrade_returns_hint(monkeypatch):
    async def fail_append(**kwargs):
        return False

    monkeypatch.setattr(feedback_mod, "append_feedback", fail_append)
    body = client.post("/api/agent/feedback", json={"session_id": "s1", "rating": "up"}).json()
    assert body["success"] is False and "降级" in body["message"]


def test_feedback_invalid_rating_422():
    resp = client.post("/api/agent/feedback", json={"session_id": "s1", "rating": "meh"})
    assert resp.status_code == 422


def test_feedback_requires_token(monkeypatch):
    monkeypatch.setattr(settings, "AGENT_API_TOKEN", "secret")
    resp = client.post("/api/agent/feedback", json={"session_id": "s1", "rating": "up"})
    assert resp.status_code == 401
