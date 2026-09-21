"""B8：历史日志端点测试。"""

import asyncio
from unittest.mock import patch

import pytest

from db.chat_log import list_session_logs


@pytest.fixture
def mock_settings():
    with patch("db.chat_log.settings") as s:
        s.CHAT_LOG_ENABLED = True
        yield s


def test_list_session_logs_returns_empty_when_disabled():
    with patch("db.chat_log.settings") as s:
        s.CHAT_LOG_ENABLED = False
        result = asyncio.run(list_session_logs("sess-1"))
    assert result == {"logs": [], "total": 0}


def test_list_session_logs_returns_rows(mock_settings):
    fake_rows = [
        {"id": 1, "thread_id": "t1", "role": "human", "content": "你好",
         "token_total": 10, "created_at": "2026-09-21 10:00:00"},
        {"id": 2, "thread_id": "t1", "role": "ai", "content": "你好！",
         "token_total": 20, "created_at": "2026-09-21 10:00:01"},
    ]
    with patch("db.chat_log.execute_query") as eq:
        async def side_effect(sql, params=None):
            if "COUNT" in sql:
                return [{"cnt": 2}]
            return fake_rows
        eq.side_effect = side_effect
        result = asyncio.run(list_session_logs("sess-1", limit=10, offset=0))
    assert result["total"] == 2
    assert len(result["logs"]) == 2
    assert result["logs"][0]["role"] == "human"


def test_list_session_logs_db_unavailable_returns_empty(mock_settings):
    with patch("db.chat_log.execute_query", side_effect=RuntimeError("DB down")):
        result = asyncio.run(list_session_logs("sess-1"))
    assert result == {"logs": [], "total": 0}


def test_logs_endpoint_returns_chat_log_response(monkeypatch):
    from fastapi.testclient import TestClient
    from fastapi import FastAPI
    from api.routes import router

    app = FastAPI()
    app.include_router(router)
    client = TestClient(app)

    fake_result = {
        "logs": [
            {"id": 1, "thread_id": "t1", "role": "human", "content": "测试",
             "token_total": 5, "created_at": "2026-09-21 12:00:00"},
        ],
        "total": 1,
    }

    async def fake_list(session_id, *, limit=50, offset=0):
        return fake_result

    monkeypatch.setattr("db.chat_log.list_session_logs", fake_list)
    resp = client.get("/api/agent/sessions/test-session/logs?limit=10&offset=0")
    assert resp.status_code == 200
    body = resp.json()
    assert body["total"] == 1
    assert body["logs"][0]["role"] == "human"


def test_logs_endpoint_requires_auth(monkeypatch):
    from fastapi.testclient import TestClient
    from fastapi import FastAPI
    from api.routes import router

    monkeypatch.setattr("api.routes.settings.AGENT_API_TOKEN", "secret")
    app = FastAPI()
    app.include_router(router)
    client = TestClient(app)
    resp = client.get("/api/agent/sessions/test-session/logs")
    assert resp.status_code == 401


def test_logs_endpoint_blocks_path_traversal():
    from fastapi.testclient import TestClient
    from fastapi import FastAPI
    from api.routes import router

    app = FastAPI()
    app.include_router(router)
    client = TestClient(app)
    resp = client.get("/api/agent/sessions/..%5C..%5Cevil/logs")
    assert resp.status_code == 422
