"""输入白名单：session_id / thread_id 会被拼成文件路径，必须挡住穿越与绝对路径。

背景：这些字段是用户可控字符串，而 session_memory 用 f"{session_id}.json" 落盘。
不做白名单时 `..%5C..%5Ceval%5Ccases` 这类 id 能删/写仓库里的任意 .json。
"""

import uuid

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from agent.memory.session_memory import SESSION_DIR, _session_file
from api.routes import router
from config import settings


def _client(monkeypatch, token=""):
    monkeypatch.setattr(settings, "AGENT_API_TOKEN", token)
    app = FastAPI()
    app.include_router(router)
    return TestClient(app)


@pytest.mark.parametrize(
    "bad",
    [
        "../shops",
        "..\\..\\config",
        "C:/Windows/Temp/x",
        "a/b",
        "a.b",
        "",
        "x" * 65,
    ],
)
def test_session_file_rejects_unsafe_ids(bad):
    with pytest.raises(ValueError):
        _session_file(bad)


def test_session_file_accepts_uuid_and_plain_id():
    sid = str(uuid.uuid4())
    path = _session_file(sid)
    assert path.parent == SESSION_DIR
    assert path.name == f"{sid}.json"
    assert _session_file("smoke-1").name == "smoke-1.json"


def test_delete_session_rejects_backslash_traversal(monkeypatch):
    """%5C 是反斜杠：在 Windows 上是路径分隔符，且不含 / 所以能过路由正则。"""
    client = _client(monkeypatch)
    resp = client.delete("/api/agent/sessions/..%5C..%5Ceval%5Cretrieval_cases")
    assert resp.status_code == 422


def test_delete_session_rejects_forward_slash_traversal(monkeypatch):
    client = _client(monkeypatch)
    resp = client.delete("/api/agent/sessions/..%2F..%2Feval%2Fretrieval_cases")
    assert resp.status_code in (404, 422)


def test_delete_session_still_works_for_safe_id(monkeypatch):
    client = _client(monkeypatch)
    resp = client.delete("/api/agent/sessions/no-such-session-id")
    assert resp.status_code == 200
    assert resp.json()["success"] is True


def test_chat_rejects_traversal_session_id(monkeypatch):
    client = _client(monkeypatch)
    resp = client.post("/api/agent/chat", json={"message": "hi", "session_id": "../../config"})
    assert resp.status_code == 422


def test_chat_rejects_overlong_message(monkeypatch):
    client = _client(monkeypatch)
    resp = client.post("/api/agent/chat", json={"message": "x" * 4001})
    assert resp.status_code == 422


def test_resume_rejects_traversal_thread_id(monkeypatch):
    client = _client(monkeypatch)
    resp = client.post("/api/agent/chat/resume", json={"thread_id": "..\\..\\x"})
    assert resp.status_code == 422


def test_feedback_rejects_traversal_session_id(monkeypatch):
    client = _client(monkeypatch)
    resp = client.post("/api/agent/feedback", json={"session_id": "../x", "rating": "up"})
    assert resp.status_code == 422
