"""工作台 API 契约测试：不跑 lifespan，不碰 MySQL/LLM。"""

import asyncio

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

import api.routes as base_routes
import api.workbench_routes as routes
from api.workbench_routes import router
from db.database import DBUnavailable

app = FastAPI()
app.include_router(router)
client = TestClient(app)


@pytest.fixture(autouse=True)
def dev_auth(monkeypatch):
    monkeypatch.setattr(base_routes.settings, "AGENT_API_TOKEN", "")
    monkeypatch.setattr(base_routes.settings, "APP_ENV", "dev")


def test_dashboard_ok(monkeypatch):
    async def fake_dashboard(**kwargs):
        return {"snapshot_id": "dash_test", "range": {"key": kwargs["range_key"]}, "widgets": []}

    monkeypatch.setattr(routes.planner, "build_dashboard", fake_dashboard)
    resp = client.get("/api/workbench/dashboard?range=last7&refresh=true")
    assert resp.status_code == 200
    assert resp.json()["snapshot_id"] == "dash_test"


def test_dashboard_invalid_range_is_400(monkeypatch):
    async def boom(**kwargs):
        raise ValueError("不支持的区间")

    monkeypatch.setattr(routes.planner, "build_dashboard", boom)
    resp = client.get("/api/workbench/dashboard?range=90d")
    assert resp.status_code == 400
    assert "区间" in resp.json()["detail"]


def test_dashboard_db_unavailable_is_503(monkeypatch):
    async def boom(**kwargs):
        raise DBUnavailable("db down")

    monkeypatch.setattr(routes.planner, "build_dashboard", boom)
    resp = client.get("/api/workbench/dashboard?range=yesterday")
    assert resp.status_code == 503
    assert "不是没有数据" in resp.json()["detail"]


def test_preferences_crud(monkeypatch):
    item = {
        "id": 1, "metric": "refund_rate", "chart_type": "line", "cadence": "daily",
        "range_key": "yesterday", "title": "退款率·每日", "active": True,
    }

    async def fake_list():
        return [item]

    async def fake_save(**kwargs):
        return item

    async def fake_delete(_id):
        return True

    monkeypatch.setattr(routes.preferences, "list_preferences", fake_list)
    monkeypatch.setattr(routes.preferences, "save_preference", fake_save)
    monkeypatch.setattr(routes.preferences, "delete_preference", fake_delete)

    assert client.get("/api/workbench/preferences").json()["total"] == 1
    created = client.post("/api/workbench/preferences", json={
        "metric": "refund_rate", "chart_type": "line",
        "cadence": "daily", "range_key": "yesterday",
    })
    assert created.status_code == 200 and created.json()["success"] is True
    assert client.delete("/api/workbench/preferences/1").json()["success"] is True


def test_rule_search_categories_and_detail():
    cats = client.get("/api/workbench/rules/categories").json()
    assert cats["categories"]
    assert sum(item["count"] for item in cats["categories"]) >= 12

    search = client.get("/api/workbench/rules/search?q=退款&size=5").json()
    assert search["total"] >= 1
    assert search["items"][0]["demo"] is True
    assert search["items"][0]["section"]

    all_rules = client.get("/api/workbench/rules/search?page=1&size=50").json()
    assert all_rules["total"] >= 12

    detail = client.get("/api/workbench/rules/refund-timeout").json()
    assert detail["rule_id"] == "refund-timeout"
    assert detail["demo"] is True
    assert detail["content"]

    missing = client.get("/api/workbench/rules/not-a-rule")
    assert missing.status_code == 404
    assert "规则不存在" in missing.json()["detail"]


def test_rules_feed_shape(monkeypatch):
    monkeypatch.setattr(routes.rules, "rule_feed", lambda: {
        "status": "empty",
        "reason": "RULE_CORPUS_MISSING",
        "rules": [],
        "activities": [],
        "activity_status": "empty",
        "calendar": [],
        "unavailable": [{"key": "platform_activity", "reason": "NO_ACTIVITY_FEED", "message": "空"}],
    })
    body = client.get("/api/workbench/rules").json()
    assert body["status"] == "empty"
    assert body["activity_status"] == "empty"
