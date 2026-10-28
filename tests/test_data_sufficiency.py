"""数据充分性闸门：全零/取不到时不许当结论（SPEC/03 G10）。"""

from langchain_core.messages import AIMessage, HumanMessage

from agent.data_sufficiency import (
    LEVEL_EMPTY,
    LEVEL_PARTIAL,
    LEVEL_SUFFICIENT,
    LEVEL_UNAVAILABLE,
    classify,
    insufficiency_note,
)
from agent.prompts import DATA_INSUFFICIENCY_RULE
import sys

import agent.workers  # noqa: F401  触发包内再导出，子模块进 sys.modules

# agent.workers.__init__ 把同名函数再导出，属性访问拿到的是函数，
# 打桩要拿真正的模块对象
cl = sys.modules["agent.workers.call_llm"]
st = sys.modules["agent.workers.strategist"]

DB_DOWN = "工具 revenue_daily 执行失败：经营数据库暂时不可用（连接被拒）。请如实告知用户「暂时取不到经营数据，请稍后重试」"
NO_RECORD = "最近 7 天没有数据。"
ZERO_WINDOW = "本期与对比期的有效订单数均为 0（status 3/4/5），无有效订单记录可分解。"
REAL_DATA = "=== 营业额 ===\n6 月 28 日：1234 元"


def _fake_llm(box):
    def invoke(msgs, tier=None, config=None):
        box["msgs"] = msgs
        box["tier"] = tier
        return AIMessage(
            content="好的",
            usage_metadata={"input_tokens": 1, "output_tokens": 1, "total_tokens": 2},
        )

    return invoke


def _state(analysis):
    return {
        "messages": [HumanMessage(content="我最近生意怎么样？")],
        "context": {"current_date": "2026-10-28", "weekday": "三"},
        "analysis_result": analysis,
        "strategy": {},
        "token_usage": {},
        "guard_reason": "",
        "llm_tier": "large",
        "security": {},
    }


# ---------- classify ----------

def test_classify_treats_real_numbers_as_sufficient():
    assert classify({"revenue_daily": REAL_DATA})["level"] == LEVEL_SUFFICIENT


def test_classify_separates_db_down_from_no_record():
    assert classify({"revenue_daily": DB_DOWN})["level"] == LEVEL_UNAVAILABLE
    assert classify({"time_series": NO_RECORD})["level"] == LEVEL_EMPTY
    assert classify({"factor_decomposition": ZERO_WINDOW})["level"] == LEVEL_EMPTY


def test_classify_partial_when_some_tool_has_data():
    v = classify({"revenue_daily": REAL_DATA, "anomaly_detection": NO_RECORD})
    assert v["level"] == LEVEL_PARTIAL
    assert v["has_data"] is True
    assert v["empty"] == ["anomaly_detection"]


def test_insufficiency_note_empty_when_sufficient():
    assert insufficiency_note(classify({"a": REAL_DATA})) == ""


def test_insufficiency_note_carries_reason_and_tool_names():
    note = insufficiency_note(classify({"revenue_daily": DB_DOWN}))
    assert "数据充分性约束" in note
    assert "revenue_daily" in note
    assert "取不到" in note


# ---------- call_llm 注入 ----------

def test_call_llm_injects_rule_when_data_unavailable(monkeypatch):
    box = {}
    monkeypatch.setattr(cl, "try_invoke_routed", _fake_llm(box))
    cl.call_llm(_state({"revenue_daily": DB_DOWN}))
    system = box["msgs"][0].content
    assert "数据充分性约束" in system
    assert "不得把 0、空值当成经营结论" in system


def test_call_llm_injects_rule_for_all_zero_window(monkeypatch):
    box = {}
    monkeypatch.setattr(cl, "try_invoke_routed", _fake_llm(box))
    cl.call_llm(_state({"factor_decomposition": ZERO_WINDOW}))
    assert "数据充分性约束" in box["msgs"][0].content


def test_call_llm_stays_clean_when_data_is_sufficient(monkeypatch):
    box = {}
    monkeypatch.setattr(cl, "try_invoke_routed", _fake_llm(box))
    cl.call_llm(_state({"revenue_daily": REAL_DATA}))
    assert "数据充分性约束" not in box["msgs"][0].content


# ---------- strategist：无数据不出建议 ----------

def test_strategist_skips_when_db_unavailable(monkeypatch):
    box = {}
    monkeypatch.setattr(st, "try_invoke_routed", _fake_llm(box))
    assert st.strategist(_state({"revenue_daily": DB_DOWN})) == {}
    assert "msgs" not in box  # 根本没叫模型


def test_strategist_skips_when_no_records(monkeypatch):
    box = {}
    monkeypatch.setattr(st, "try_invoke_routed", _fake_llm(box))
    assert st.strategist(_state({"time_series": NO_RECORD})) == {}
    assert "msgs" not in box


def test_strategist_runs_on_partial_and_states_constraint(monkeypatch):
    box = {}
    monkeypatch.setattr(st, "try_invoke_routed", _fake_llm(box))
    out = st.strategist(_state({"revenue_daily": REAL_DATA, "time_series": NO_RECORD}))
    assert out["strategy"]["source"] == "strategist"
    assert any(
        DATA_INSUFFICIENCY_RULE.splitlines()[0] in m.content for m in box["msgs"]
    )
