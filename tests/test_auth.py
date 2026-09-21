"""B0-A2/A3/A6：API Bearer 鉴权、CORS 白名单、health 开关暴露。"""

from fastapi import FastAPI
from fastapi.testclient import TestClient

import agent.service as agent_service
from api.routes import router
from config import settings


def _client(monkeypatch, token, env="dev"):
    monkeypatch.setattr(settings, "AGENT_API_TOKEN", token)
    monkeypatch.setattr(settings, "APP_ENV", env)
    app = FastAPI()
    app.include_router(router)
    return TestClient(app)


def _fake_chat(monkeypatch):
    async def fake_chat(**kwargs):
        return {"reply": "ok", "session_id": kwargs["session_id"], "thread_id": kwargs["thread_id"]}

    monkeypatch.setattr(agent_service, "chat", fake_chat)


def test_api_open_when_token_unset(monkeypatch):
    _fake_chat(monkeypatch)
    client = _client(monkeypatch, "")
    resp = client.post("/api/agent/chat", json={"message": "hi"})
    assert resp.status_code == 200


def test_api_requires_bearer_token(monkeypatch):
    client = _client(monkeypatch, "secret-token")
    assert client.post("/api/agent/chat", json={"message": "hi"}).status_code == 401
    bad = client.post(
        "/api/agent/chat", json={"message": "hi"},
        headers={"Authorization": "Bearer wrong"},
    )
    assert bad.status_code == 401
    assert client.get("/api/agent/sessions").status_code == 401


def test_api_ok_with_correct_token(monkeypatch):
    _fake_chat(monkeypatch)
    client = _client(monkeypatch, "secret-token")
    resp = client.post(
        "/api/agent/chat", json={"message": "hi"},
        headers={"Authorization": "Bearer secret-token"},
    )
    assert resp.status_code == 200 and resp.json()["success"] is True


def test_prod_without_token_fails_closed(monkeypatch):
    """S14：prod 漏配 token 必须是「明确拒绝」，不能静默放行。"""
    _fake_chat(monkeypatch)
    client = _client(monkeypatch, "", env="prod")
    assert client.post("/api/agent/chat", json={"message": "hi"}).status_code == 503
    assert client.get("/api/agent/sessions").status_code == 503
    # /health 不受影响：它就是给运维排查用的
    assert client.get("/health").status_code == 200


def test_prod_with_token_still_requires_bearer(monkeypatch):
    _fake_chat(monkeypatch)
    client = _client(monkeypatch, "secret-token", env="prod")
    assert client.post("/api/agent/chat", json={"message": "hi"}).status_code == 401
    ok = client.post(
        "/api/agent/chat", json={"message": "hi"},
        headers={"Authorization": "Bearer secret-token"},
    )
    assert ok.status_code == 200


def test_health_reports_auth_mode(monkeypatch):
    assert _client(monkeypatch, "").get("/health").json()["auth_mode"] == "dev-open"
    assert _client(monkeypatch, "").get("/health").json()["env"] == "dev"
    assert _client(monkeypatch, "", env="prod").get("/health").json()["auth_mode"] == "prod-closed"
    assert _client(monkeypatch, "t").get("/health").json()["auth_mode"] == "token"


def test_health_stays_open_and_reports_auth(monkeypatch):
    client = _client(monkeypatch, "secret-token")
    body = client.get("/health").json()
    assert body["auth_enabled"] is True

    client_off = _client(monkeypatch, "")
    assert client_off.get("/health").json()["auth_enabled"] is False


def test_cors_whitelist_rejects_unknown_origin():
    import main as main_mod

    client = TestClient(main_mod.app)
    ok = client.get("/", headers={"Origin": "http://localhost:8888"})
    assert ok.headers.get("access-control-allow-origin") == "http://localhost:8888"

    evil = client.get("/", headers={"Origin": "http://evil.example"})
    assert "access-control-allow-origin" not in evil.headers


def test_forwarded_for_ignored_unless_trusted(monkeypatch):
    from api.routes import _client_ip

    class _FakeRequest:
        headers = {"x-forwarded-for": "1.2.3.4"}
        client = None

    monkeypatch.setattr(settings, "TRUST_PROXY_HEADERS", False)
    assert _client_ip(_FakeRequest()) == ""

    monkeypatch.setattr(settings, "TRUST_PROXY_HEADERS", True)
    assert _client_ip(_FakeRequest()) == "1.2.3.4"
