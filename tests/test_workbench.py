"""AI 工作台：区间、偏好意图、规则空态、上下文事实、本地存储。"""

import asyncio
import json
from datetime import date

import pytest

from agent.workbench import data, planner, rules as rules_module, store
from agent.workbench.period import Period, requested_period, with_fallback
from agent.workbench.preferences import detect_preference_intent
from agent.workbench.rule_rag import search_rules, should_use_rules
from agent.workbench.rules import rule_feed


def test_requested_period_yesterday_and_fallback():
    requested = requested_period("yesterday", today=date(2026, 10, 20))
    assert requested.start == date(2026, 10, 19)
    assert requested.end == date(2026, 10, 20)

    effective = with_fallback(
        requested, date(2026, 7, 28), has_data=False, fallback_days=7
    )
    assert effective.start == date(2026, 7, 22)
    assert effective.end == date(2026, 7, 29)
    assert effective.gap is True
    assert effective.fallback_reason == "NO_DATA_IN_REQUESTED_WINDOW"


def test_requested_period_keeps_window_when_data_exists():
    requested = requested_period("last7", today=date(2026, 10, 20))
    effective = with_fallback(requested, date(2026, 10, 19), has_data=True)
    assert effective.start == requested.start
    assert effective.end == requested.end
    assert effective.gap is False


def test_preference_intent_add_remove_and_negatives():
    add = detect_preference_intent("以后每天给我看退款趋势，用折线图。")
    assert add is not None
    assert add.action == "add"
    assert add.metric == "refund_rate"
    assert add.chart_type == "line"
    assert add.cadence == "daily"

    dish = detect_preference_intent("下次推送菜品销量柱状图")
    assert dish is not None
    assert dish.metric == "dish_sales"
    assert dish.chart_type == "bar"

    remove = detect_preference_intent("取消每天退款图。")
    assert remove is not None
    assert remove.action == "remove"
    assert remove.metric == "refund_rate"

    assert detect_preference_intent("今天营业额多少？") is None
    assert detect_preference_intent("以后退款规则怎么规定？") is None


def test_preference_intent_help_when_metric_missing():
    intent = detect_preference_intent("帮我设置一下首页看板")
    assert intent is not None
    assert intent.action == "help"
    assert "指标" in intent.reply


def test_rules_feed_is_empty_without_corpus(tmp_path, monkeypatch):
    monkeypatch.setattr(rules_module, "RULES_DIR", tmp_path / "rules")
    monkeypatch.setattr(rules_module, "ACTIVITIES_DIR", tmp_path / "activities")
    feed = rule_feed()
    assert feed["status"] == "empty"
    assert feed["rules"] == []
    assert any(item["key"] == "platform_activity" for item in feed["unavailable"])


def test_demo_rules_are_labeled_and_searchable():
    feed = rule_feed()
    assert feed["status"] == "ok"
    assert feed["rules"]
    assert all(rule["demo"] for rule in feed["rules"])
    hits = search_rules("平台退款规则怎么规定")
    assert hits
    assert any(hit["rule_id"].startswith("refund") for hit in hits)
    assert should_use_rules("发票怎么开") is True
    assert should_use_rules("退款率为什么高") is False


def test_activity_feed_scans_real_files(tmp_path, monkeypatch):
    monkeypatch.setattr(rules_module, "ACTIVITIES_DIR", tmp_path)
    (tmp_path / "summer.json").write_text(json.dumps({
        "activity_key": "summer-2026",
        "title": "夏日满减",
        "start_date": "2026-07-01",
        "end_date": "2099-12-31",
        "status": "active",
        "description": "满 30 减 5",
        "source": "平台活动中心",
    }, ensure_ascii=False), encoding="utf-8")

    feed = rules_module.rule_feed()
    assert feed["activity_status"] == "ok"
    assert feed["activities"][0]["title"] == "夏日满减"
    assert not any(item["key"] == "platform_activity" for item in feed["unavailable"])


def test_widget_context_uses_server_facts_not_model_numbers(monkeypatch):
    plan = {
        "data_status": {"effective_start": "2026-07-22", "effective_end": "2026-07-29"},
        "widgets": [{
            "widget_id": "kpi_cards",
            "data": {"cards": [
                {"key": "revenue", "label": "营业额", "value": 659.0,
                 "unit": "CNY", "previous": 453.0, "change_rate": 0.455},
                {"key": "orders", "label": "完成订单", "value": 7,
                 "unit": "order", "previous": 6, "change_rate": 0.1667},
                {"key": "aov", "label": "客单价", "value": 94.14,
                 "unit": "CNY", "previous": 75.5, "change_rate": 0.2469},
            ]},
        }],
    }

    async def fake_snapshot(_snapshot_id):
        return plan

    monkeypatch.setattr(planner, "get_snapshot", fake_snapshot)
    result = asyncio.run(planner.validate_widget_context({
        "widget_id": "kpi_cards",
        "snapshot_id": "dash_test",
        "selection": {"metric": "revenue", "evil_key": "1"},
    }))
    assert result["verified"] is True
    assert result["selection"] == {"metric": "revenue"}
    assert result["facts"].startswith("营业额：本期 ¥659.00；上期 ¥453.00；环比 +45.5%")
    assert "营业额归因" in result["facts"]
    # 数字只通过 facts 置顶；模型只拿到“谁最大”的定性提示
    assert "659.00" not in result["text"]
    assert "客单价效应最大" in result["text"]


def test_widget_context_drops_invalid_selection(monkeypatch):
    async def fake_snapshot(_snapshot_id):
        return {"data_status": {}, "widgets": [{"widget_id": "sales_trend", "data": {}}]}

    monkeypatch.setattr(planner, "get_snapshot", fake_snapshot)
    result = asyncio.run(planner.validate_widget_context({
        "widget_id": "sales_trend",
        "snapshot_id": "dash_test",
        "selection": {"date": "not-a-date", "widget_id": "x"},
    }))
    assert result["selection"] == {}
    assert result["facts"] == ""


def test_refund_spike_detects_fixed_and_median_thresholds():
    days = [
        {"date": f"2026-07-{day:02d}", "revenue": 100.0, "completed_orders": 10, "paid_orders": 100}
        for day in range(10, 18)
    ]
    refunds = [
        {"date": f"2026-07-{day:02d}", "amount": 10.0, "orders": 1}
        for day in range(10, 17)
    ]
    refunds.append({"date": "2026-07-17", "amount": 80.0, "orders": 8})
    events = data.refund_spikes(days, refunds)
    assert events and events[-1]["date"] == "2026-07-17"
    assert events[-1]["type"] == "refund_spike"


def test_dashboard_reuses_snapshot(monkeypatch):
    period = Period(
        key="yesterday", label="昨日",
        start=date(2026, 7, 22), end=date(2026, 7, 29),
        requested_start=date(2026, 10, 19), requested_end=date(2026, 10, 20),
        latest_data_date=date(2026, 7, 28),
        fallback_reason="NO_DATA_IN_REQUESTED_WINDOW",
    )

    async def fake_period(_range):
        return period

    async def fake_prefs():
        return []

    async def fake_snapshot(_snapshot_id):
        return {
            "snapshot_id": "dash_cached",
            "plan_version": planner.PLAN_VERSION,
            "widgets": [],
            "range": {"key": "yesterday"},
        }

    async def explode(*args, **kwargs):
        raise AssertionError("缓存命中时不应查库")

    monkeypatch.setattr(planner.data, "resolve_effective_period", fake_period)
    monkeypatch.setattr(planner, "list_preferences", fake_prefs)
    monkeypatch.setattr(planner, "get_snapshot", fake_snapshot)
    monkeypatch.setattr(planner.data, "kpi_summary", explode)

    plan = asyncio.run(planner.build_dashboard("yesterday", refresh=False))
    assert plan["snapshot_id"] == "dash_cached"
    assert plan["reused"] is True
    assert plan["contract_version"] == planner.CONTRACT_VERSION


def test_local_preferences_and_snapshot_roundtrip(tmp_path, monkeypatch):
    data_dir = tmp_path / "workbench"
    monkeypatch.setattr(store, "DATA_DIR", data_dir)
    monkeypatch.setattr(store, "PREFS_FILE", data_dir / "preferences.json")
    monkeypatch.setattr(store, "SNAP_DIR", data_dir / "snapshots")

    item = {"metric": "refund_rate", "chart_type": "line", "cadence": "daily",
            "range_key": "yesterday", "title": "退款率·每日"}
    saved = store.upsert_preference(1, item)
    assert saved["id"] == 1
    assert store.load_preferences(1)[0]["title"] == "退款率·每日"
    assert store.load_preferences(2) == []

    updated = store.upsert_preference(1, {**item, "chart_type": "bar", "title": "退款率·柱状"})
    assert updated["id"] == 1
    assert store.load_preferences(1)[0]["chart_type"] == "bar"

    assert store.save_snapshot("dash_test", 1, {"snapshot_id": "dash_test"})
    assert store.load_snapshot("dash_test", 1) == {"snapshot_id": "dash_test"}
    assert store.load_snapshot("dash_test", 2) is None

    assert store.delete_by_metric(1, "refund_rate", "daily") == 1
    assert store.load_preferences(1) == []
