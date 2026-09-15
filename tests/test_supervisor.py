"""Supervisor 调度单测（不依赖 LLM）。"""

from agent.supervisor import build_plan, decide_next_worker


def test_build_plan_analysis():
    assert build_plan("query_analysis") == [
        "analyst",
        "strategist",
        "reviewer",
        "call_llm",
    ]


def test_build_plan_unknown():
    assert build_plan("unknown") == ["analyst", "call_llm"]


def test_decide_first_step_is_analyst():
    out = decide_next_worker(
        {
            "intent": {"intent": "query_analysis"},
            "analysis_result": {},
            "strategy": {},
            "worker_history": [],
            "supervisor_plan": [],
            "token_usage": {},
            "tool_steps": 0,
            "guard_reason": "",
        }
    )
    assert out["next_worker"] == "analyst"
    assert out["supervisor_plan"][0] == "analyst"
    assert out["worker_history"] == ["analyst"]


def test_decide_after_analysis_goes_strategist():
    out = decide_next_worker(
        {
            "intent": {"intent": "query_analysis"},
            "analysis_result": {"factor_decomposition": "ok"},
            "strategy": {},
            "worker_history": ["analyst"],
            "supervisor_plan": [
                "analyst",
                "strategist",
                "reviewer",
                "call_llm",
            ],
            "token_usage": {},
            "tool_steps": 1,
            "guard_reason": "",
        }
    )
    assert out["next_worker"] == "strategist"


def test_decide_skip_strategist_without_analysis():
    out = decide_next_worker(
        {
            "intent": {"intent": "query_analysis"},
            "analysis_result": {},
            "strategy": {},
            "worker_history": ["analyst"],
            "supervisor_plan": [
                "analyst",
                "strategist",
                "reviewer",
                "call_llm",
            ],
            "token_usage": {},
            "tool_steps": 0,
            "guard_reason": "",
        }
    )
    assert out["next_worker"] == "call_llm"


def test_decide_after_strategy_goes_reviewer():
    out = decide_next_worker(
        {
            "intent": {"intent": "query_analysis"},
            "analysis_result": {"factor_decomposition": "ok"},
            "strategy": {"recommendations": "建议降价", "source": "strategist"},
            "worker_history": ["analyst", "strategist"],
            "supervisor_plan": [
                "analyst",
                "strategist",
                "reviewer",
                "call_llm",
            ],
            "token_usage": {},
            "tool_steps": 1,
            "guard_reason": "",
        }
    )
    assert out["next_worker"] == "reviewer"


def test_decide_after_reviewer_goes_call_llm():
    out = decide_next_worker(
        {
            "intent": {"intent": "query_analysis"},
            "analysis_result": {"factor_decomposition": "ok"},
            "strategy": {"recommendations": "建议降价", "source": "reviewer"},
            "worker_history": ["analyst", "strategist", "reviewer"],
            "supervisor_plan": [
                "analyst",
                "strategist",
                "reviewer",
                "call_llm",
            ],
            "token_usage": {},
            "tool_steps": 1,
            "guard_reason": "",
        }
    )
    assert out["next_worker"] == "call_llm"
