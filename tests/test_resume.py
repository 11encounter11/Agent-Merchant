"""B6b：service.resume_thread 单测（不触真实图/DB）。"""

import asyncio
from types import SimpleNamespace

from langchain_core.messages import AIMessage

import agent.service as svc


def test_resume_thread_no_pending(monkeypatch):
    async def fake_resume(graph, thread_id, *, session_id=""):
        return None

    monkeypatch.setattr(svc, "resume_if_pending", fake_resume)
    monkeypatch.setattr(svc, "get_agent_graph", lambda: object())

    out = asyncio.run(svc.resume_thread("t-none"))
    assert out["resumed"] is False and "没有" in out["message"]


def test_resume_thread_returns_final_reply(monkeypatch):
    async def fake_resume(graph, thread_id, *, session_id=""):
        return {
            "messages": [
                AIMessage(content="最终分析结果", tool_calls=[]),
            ]
        }

    appended = []

    async def fake_append_turn(session_id, user_text, ai_text=""):
        appended.append(("turn", session_id, ai_text))

    async def fake_log(**kwargs):
        appended.append(("log", kwargs["role"], kwargs["content"]))

    monkeypatch.setattr(svc, "resume_if_pending", fake_resume)
    monkeypatch.setattr(svc, "get_agent_graph", lambda: object())
    monkeypatch.setattr(svc.session_memory, "aappend_turn", fake_append_turn)
    monkeypatch.setattr(svc, "append_chat_log", fake_log)

    out = asyncio.run(svc.resume_thread("t-1", session_id="s-1"))
    assert out["resumed"] is True and out["reply"] == "最终分析结果"
    assert ("turn", "s-1", "最终分析结果") in appended
    assert ("log", "ai", "最终分析结果") in appended
