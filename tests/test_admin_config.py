"""B6c：/health 运行时状态 + /api/admin/config 只读脱敏配置。"""

from fastapi import FastAPI
from fastapi.testclient import TestClient

from api.routes import router
from config import settings


def _client(monkeypatch, token=""):
    monkeypatch.setattr(settings, "AGENT_API_TOKEN", token)
    app = FastAPI()
    app.include_router(router)
    return TestClient(app)


def test_health_exposes_runtime_switches(monkeypatch):
    body = _client(monkeypatch).get("/health").json()
    rt = body["runtime"]
    assert isinstance(rt["redis"]["enabled"], bool)
    assert isinstance(rt["redis"]["live"], bool)
    assert rt["rate_limit"]["per_minute"] == settings.RATE_LIMIT_PER_MINUTE
    assert rt["checkpoint_backend"] == settings.CHECKPOINT_BACKEND
    assert "security_injection_enabled" in rt


def test_admin_config_masks_secrets(monkeypatch):
    monkeypatch.setattr(settings, "LLM_API_KEY", "super-secret-key-123")
    monkeypatch.setattr(settings, "DB_PASSWORD", "pwd-456")
    body = _client(monkeypatch).get("/api/admin/config").json()

    text = str(body)
    assert "super-secret-key-123" not in text and "pwd-456" not in text
    assert body["secrets_configured"]["LLM_API_KEY"] is True
    assert body["secrets_configured"]["DB_PASSWORD"] is True
    assert "LLM_API_KEY" not in body["config"]
    assert body["config"]["APP_VERSION"] == settings.APP_VERSION
    assert "runtime" in body


def test_admin_config_requires_token(monkeypatch):
    client = _client(monkeypatch, "secret")
    assert client.get("/api/admin/config").status_code == 401
    ok = client.get("/api/admin/config", headers={"Authorization": "Bearer secret"})
    assert ok.status_code == 200
