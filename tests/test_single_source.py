"""B2 单一真值回归：同一事实只允许一处定义（04 §1 S1–S5）。"""

import asyncio
from importlib import import_module

from fastapi.testclient import TestClient

from agent import constants
from agent import llm, perception, reflection, security
from config import settings


def test_boundary_kw_shared_identity():
    assert perception._BOUNDARY_KW is constants.BOUNDARY_KW
    assert reflection._BOUNDARY_KW is constants.BOUNDARY_KW
    # reflection 旧副本缺"写报告"——收敛后必须两边都在
    assert "写报告" in reflection._BOUNDARY_KW


def test_simple_intents_shared_identity():
    assert llm.SIMPLE_INTENTS is constants.SIMPLE_INTENTS
    assert security.SIMPLE_INTENTS is constants.SIMPLE_INTENTS


def test_holiday_tool_reads_json_single_source():
    # 旧内置 dict 把 2026 端午记为 05-31（错误）；holidays.json 为唯一真值
    m_holiday = import_module("agent.tools.external.calendar_tool")
    assert m_holiday._HOLIDAYS, "holidays.json 应加载成功"
    out = asyncio.run(m_holiday.query_holiday.ainvoke({"query": "端午"}))
    assert "06-19" in out and "05-31" not in out


def test_cost_ratio_single_source(monkeypatch):
    m_cost = import_module("agent.tools.analysis.cost_profit")
    monkeypatch.setattr(settings, "COST_RATIO_DEFAULT", 0.4)

    async def fake_query(sql, params=None):
        if "dish_name" in sql:
            return [{"dish_name": "米饭", "category_name": "主食", "price": 10.0,
                     "unit_cost": 4.0, "total_sold": 10, "total_revenue": 100.0}]
        return [{"category_name": "主食", "total_sold": 10, "total_revenue": 100.0}]

    monkeypatch.setattr(m_cost, "execute_query", fake_query)
    out = asyncio.run(m_cost.cost_profit_analysis.ainvoke({}))
    assert "成本率=40%" in out


def test_version_single_source():
    import main as main_mod

    assert main_mod.app.version == settings.APP_VERSION
    client = TestClient(main_mod.app)
    assert client.get("/health").json()["version"] == settings.APP_VERSION
