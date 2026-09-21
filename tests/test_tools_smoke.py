"""B1 冒烟测试：11 个工具。

不触真实 MySQL/网络/LLM：
- DB 工具：monkeypatch 各工具模块的 execute_query，喂固定行数据，验证 SQL 分支与计算组装。
- weather：假 httpx client；holiday：纯本地数据。
"""

import asyncio
from types import SimpleNamespace

import pytest

# 注意：各 tools 包的 __init__ 把同名模块重导出为工具对象，必须用 import_module 拿模块
from importlib import import_module

m_factor = import_module("agent.tools.analysis.factor_decomposition")
m_anomaly = import_module("agent.tools.analysis.anomaly_detection")
m_corr = import_module("agent.tools.analysis.correlation")
m_trend = import_module("agent.tools.analysis.time_series")
m_cost = import_module("agent.tools.analysis.cost_profit")
m_report = import_module("agent.tools.business.business_report")
m_menu = import_module("agent.tools.business.menu_optimization")
m_promo = import_module("agent.tools.business.promotion_planner")
m_prep = import_module("agent.tools.business.prep_plan")
m_holiday = import_module("agent.tools.external.calendar_tool")
m_weather = import_module("agent.tools.external.weather")
from config import settings

DB_MODULES_TOOLS = [
    (m_factor, m_factor.factor_decomposition, {}),
    (m_anomaly, m_anomaly.anomaly_detection, {}),
    (m_corr, m_corr.correlation_analysis, {}),
    (m_trend, m_trend.trend_analysis, {}),
    (m_cost, m_cost.cost_profit_analysis, {}),
    (m_report, m_report.business_report, {}),
    (m_menu, m_menu.menu_optimization, {}),
    (m_promo, m_promo.promotion_planner, {}),
    (m_prep, m_prep.prep_plan, {}),
]


class FakeQuery:
    """按调用次序返回预置结果，耗尽后返回 []；记录每次 (sql, params)。"""

    def __init__(self, *results):
        self._results = list(results)
        self.calls: list[tuple[str, tuple]] = []

    async def __call__(self, sql, params=None):
        self.calls.append((sql, tuple(params or ())))
        return self._results.pop(0) if self._results else []


def _patch(monkeypatch, module, fake):
    monkeypatch.setattr(module, "execute_query", fake)


def _run(tool, args):
    return asyncio.run(tool.ainvoke(args))


def test_factor_decomposition_ok(monkeypatch):
    cur = [{"order_count": 10, "total_amount": 500.0, "avg_amount": 50.0}]
    prev = [{"order_count": 8, "total_amount": 400.0, "avg_amount": 50.0}]
    cats_cur = [{"category_name": "主食", "category_amount": 300.0}]
    cats_prev = [{"category_name": "主食", "category_amount": 200.0}]
    fake = FakeQuery(cur, prev, cats_cur, cats_prev)
    _patch(monkeypatch, m_factor, fake)
    out = _run(m_factor.factor_decomposition, {})
    assert "因子分解" in out and "主食" in out
    assert len(fake.calls) == 4


def test_anomaly_detection_flags_spike(monkeypatch):
    # n=7 时单点尖峰 Z≈2.27 > 默认阈值 2.0，应被标记
    values = [100.0] * 6 + [500.0]
    rows = [{"order_date": f"2026-09-{i:02d}", "total": v} for i, v in enumerate(values, start=1)]
    _patch(monkeypatch, m_anomaly, FakeQuery(rows))
    out = _run(m_anomaly.anomaly_detection, {"days": 7})
    assert "异常检测" in out and "2026-09-07" in out


def test_correlation_analysis_ok(monkeypatch):
    rows = [
        {"order_date": f"2026-09-{i:02d}", "turnover": i * 100.0, "order_count": i * 4, "avg_price": 25.0}
        for i in range(1, 6)
    ]
    _patch(monkeypatch, m_corr, FakeQuery(rows))
    out = _run(m_corr.correlation_analysis, {"days": 5})
    assert "相关性分析" in out and "强正相关" in out


def test_trend_analysis_detects_rise(monkeypatch):
    rows = [{"order_date": f"2026-09-{i:02d}", "value": 100.0 + 20 * i} for i in range(1, 8)]
    _patch(monkeypatch, m_trend, FakeQuery(rows))
    out = _run(m_trend.trend_analysis, {"days": 7})
    assert "趋势分析" in out and "上升" in out


def test_cost_profit_analysis_ok(monkeypatch):
    cats = [{"category_name": "主食", "total_sold": 10, "total_revenue": 100.0}]
    dishes = [
        {"dish_name": "米饭", "category_name": "主食", "price": 10.0, "unit_cost": 4.0,
         "total_sold": 10, "total_revenue": 100.0}
    ]
    _patch(monkeypatch, m_cost, FakeQuery(cats, dishes))
    out = _run(m_cost.cost_profit_analysis, {})
    assert "成本利润分析" in out and "米饭" in out


def test_business_report_daily_ok(monkeypatch):
    cur = [{"order_count": 5, "total_amount": 250.0, "avg_amount": 50.0, "cancelled": 1}]
    prev = [{"order_count": 4, "total_amount": 200.0, "avg_amount": 50.0, "cancelled": 0}]
    cats = [{"category_name": "主食", "total_revenue": 100.0, "total_sold": 10}]
    _patch(monkeypatch, m_report, FakeQuery(cur, prev, cats))
    out = _run(m_report.business_report, {"report_type": "daily"})
    assert "日报" in out and "核心指标" in out


def test_menu_optimization_ok(monkeypatch):
    dishes = [
        {"dish_name": f"菜品{i}", "category_name": "主食", "price": 10.0, "unit_cost": 4.0,
         "total_sold": 30 - i, "total_revenue": float((30 - i) * 10)}
        for i in range(5)
    ]
    _patch(monkeypatch, m_menu, FakeQuery(dishes))
    out = _run(m_menu.menu_optimization, {})
    assert "菜品优化分析" in out and "A 类" in out


def test_promotion_planner_ok(monkeypatch):
    rows = [
        {"dish_name": "凉面", "category_name": "小吃", "price": 20.0, "unit_cost": 8.0,
         "total_sold": 60, "total_revenue": 1200.0, "order_count": 40}
    ]
    _patch(monkeypatch, m_promo, FakeQuery(rows))
    out = _run(m_promo.promotion_planner, {})
    assert "促销方案" in out and "凉面" in out


def test_prep_plan_ok(monkeypatch):
    totals = [{"dish_name": "米饭", "category_name": "主食", "total_sold": 28, "avg_per_order": 2.0}]
    weekday_dates = [{"order_date": "2026-09-14", "day_of_week": 1}]
    weekday_dishes = [{"dish_name": "米饭", "total_sold": 10}]
    _patch(monkeypatch, m_prep, FakeQuery(totals, weekday_dates, weekday_dishes))
    out = _run(m_prep.prep_plan, {"days": 14})
    assert "备货计划" in out and "米饭" in out


def test_weather_without_key(monkeypatch):
    monkeypatch.setattr(settings, "WEATHER_API_KEY", "")
    out = _run(m_weather.query_weather, {})
    assert "未配置" in out


class _FakeResp:
    def __init__(self, data):
        self._data = data

    def json(self):
        return self._data


class _FakeClient:
    def __init__(self, *a, **k):
        pass

    async def __aenter__(self):
        return self

    async def __aexit__(self, *a):
        return False

    async def get(self, url, params=None):
        if url.endswith("/weather/now"):
            return _FakeResp({"code": "200", "now": {
                "temp": "30", "feelsLike": "31", "text": "晴", "humidity": "60",
                "windDir": "南", "windScale": "2"}})
        return _FakeResp({"code": "200", "daily": [{
            "fxDate": "2026-09-22", "tempMin": "20", "tempMax": "31",
            "textDay": "晴", "textNight": "多云", "humidity": "55"}]})


def test_weather_ok_with_fake_http(monkeypatch):
    monkeypatch.setattr(settings, "WEATHER_API_KEY", "test-key")
    monkeypatch.setattr(settings, "WEATHER_API_URL", "https://example.dev")
    fake_httpx = SimpleNamespace(AsyncClient=_FakeClient, TimeoutException=TimeoutError)
    monkeypatch.setattr(m_weather, "httpx", fake_httpx)
    out = _run(m_weather.query_weather, {})
    assert "当前天气" in out and "未来 3 天预报" in out


def test_holiday_by_name():
    out = _run(m_holiday.query_holiday, {"query": "春节"})
    assert "春节" in out and "影响" in out


def test_holiday_upcoming():
    out = _run(m_holiday.query_holiday, {})
    assert "节假日" in out


@pytest.mark.parametrize("module,tool,args", DB_MODULES_TOOLS)
def test_tools_empty_data_returns_hint(module, tool, args, monkeypatch):
    """空数据不得抛异常，必须返回'没有/不足'类提示文案。"""
    _patch(monkeypatch, module, FakeQuery())
    out = _run(tool, args)
    assert isinstance(out, str) and out
    assert ("没有" in out) or ("不足" in out), out


@pytest.mark.parametrize("module,tool,args", DB_MODULES_TOOLS)
def test_all_db_queries_filter_merchant(module, tool, args, monkeypatch):
    """B6a 数据隔离：任何一条经营数据 SQL 都必须过滤 merchant_id。"""
    fake = FakeQuery()
    _patch(monkeypatch, module, fake)
    _run(tool, args)
    assert fake.calls, "工具应至少发起一次查询"
    for sql, params in fake.calls:
        assert "merchant_id = %s" in sql, sql[:80]
        assert settings.MERCHANT_ID in params, params
