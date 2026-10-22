"""错误契约：detail + error_code + request_id，成功响应保留 X-Request-ID。"""

import pytest
from fastapi.testclient import TestClient

import api.routes as base_routes
import api.workbench_routes as workbench_routes
import main
from db.database import DBUnavailable

client = TestClient(main.app)


@pytest.fixture(autouse=True)
def dev_auth(monkeypatch):
    monkeypatch.setattr(base_routes.settings, "AGENT_API_TOKEN", "")
    monkeypatch.setattr(base_routes.settings, "APP_ENV", "dev")


def test_success_echoes_request_id():
    resp = client.get("/", headers={"X-Request-ID": "req-test-1"})
    assert resp.status_code == 200
    assert resp.headers["X-Request-ID"] == "req-test-1"


def test_not_found_has_error_code_and_request_id():
    resp = client.get("/definitely-not-found", headers={"X-Request-ID": "req-test-2"})
    assert resp.status_code == 404
    body = resp.json()
    assert body["error_code"] == "NOT_FOUND"
    assert body["request_id"] == "req-test-2"
    assert resp.headers["X-Request-ID"] == "req-test-2"


def test_validation_error_is_422_with_code():
    resp = client.post("/api/workbench/preferences", json={"metric": "not_a_metric"})
    assert resp.status_code == 422
    body = resp.json()
    assert body["error_code"] == "VALIDATION_ERROR"
    assert body["request_id"]


def test_dashboard_invalid_range_has_code():
    resp = client.get("/api/workbench/dashboard?range=90d")
    assert resp.status_code == 400
    body = resp.json()
    assert body["error_code"] == "INVALID_ARGUMENT"
    assert "区间" in body["detail"]


def test_dashboard_db_unavailable_has_code(monkeypatch):
    async def boom(**kwargs):
        raise DBUnavailable("db down")

    monkeypatch.setattr(workbench_routes.planner, "build_dashboard", boom)
    resp = client.get("/api/workbench/dashboard?range=yesterday")
    assert resp.status_code == 503
    body = resp.json()
    assert body["error_code"] == "DB_UNAVAILABLE"
    assert "不是没有数据" in body["detail"]
