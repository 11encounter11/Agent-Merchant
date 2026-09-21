"""B7：一轮对话的落盘与成本口径（流式 / 非流式 / 失败 / 客户端中断）。

不依赖 LLM 与 MySQL：图与日志写入都被替换成记录器，会话文件用真实实现
（落盘是这条链路的重点，不能一起 mock 掉）。
"""

import asyncio
import json
import uuid

from langchain_core.messages import AIMessage

import agent.service as service
from agent.memory.session_memory import SESSION_DIR


class _Snapshot:
    def __init__(self, values=None, next_nodes=()):
        self.values = values or {}
        self.next = next_nodes


class _FakeGraph:
    """只实现 service 用到的最小接口：astream / aget_state / ainvoke。"""

    def __init__(self, reply="你好呀，我是经营顾问", tokens=42, fail_after_first=False):
        self.reply = reply
        self.tokens = tokens
        self.fail_after_first = fail_after_first
        self.invoke_calls = 0

    async def astream(self, state, cfg, stream_mode=None):
        yield AIMessage(content=self.reply), {"langgraph_node": "call_llm"}
        if self.fail_after_first:
            raise RuntimeError("图炸了")
        yield AIMessage(content="，还想看什么？"), {"langgraph_node": "call_llm"}

    async def aget_state(self, cfg):
        return _Snapshot({"token_usage": {"total_tokens": self.tokens}})

    async def ainvoke(self, state, cfg):
        self.invoke_calls += 1
        if self.fail_after_first:
            raise RuntimeError("图炸了")
        return {
            "messages": [AIMessage(content=self.reply)],
            "user_input": (state or {}).get("user_input") or "",
            "token_usage": {"total_tokens": self.tokens},
        }


def _patch(monkeypatch, graph, logs):
    """替换图 / 限流 / 对话日志 / 上下文组装，只留真实会话落盘。"""
    monkeypatch.setattr(service, "get_agent_graph", lambda: graph)

    async def allow(*args, **kwargs):
        return True, None

    monkeypatch.setattr(service, "check_rate_limit", allow)

    async def record(**kwargs):
        logs.append(kwargs)

    monkeypatch.setattr(service, "append_chat_log", record)

    async def no_context(session_id, user_input, intent_type=""):
        return [], []

    monkeypatch.setattr(service._context_builder, "abuild_context", no_context)


def _read_session(session_id):
    path = SESSION_DIR / f"{session_id}.json"
    if not path.exists():
        return []
    return json.loads(path.read_text(encoding="utf-8")).get("messages") or []


def _cleanup(session_id):
    path = SESSION_DIR / f"{session_id}.json"
    if path.exists():
        path.unlink()


def test_stream_persists_turn_and_token_total(monkeypatch):
    sid = f"t-{uuid.uuid4().hex[:8]}"
    logs: list[dict] = []
    _patch(monkeypatch, _FakeGraph(tokens=42), logs)

    async def run():
        events = []
        stream = await service.chat_stream("你好", sid)
        async for chunk in stream:
            events.append(chunk)
        return events

    try:
        events = asyncio.run(run())
        hist = _read_session(sid)  # 读盘必须在清理之前
    finally:
        _cleanup(sid)

    types = [e.get("type") for e in events if isinstance(e, dict)]
    assert "usage" in types                       # 流式路径也有成本口径
    usage = next(e for e in events if e.get("type") == "usage")
    assert usage["total_tokens"] == 42

    assert [m["role"] for m in hist] == ["human", "ai"]
    assert hist[0]["content"] == "你好"
    assert "经营顾问" in hist[1]["content"]

    ai_rows = [r for r in logs if r["role"] == "ai"]
    assert ai_rows and ai_rows[0]["token_total"] == 42
    assert any(r["role"] == "human" for r in logs)


def test_stream_persists_human_turn_when_graph_fails(monkeypatch):
    sid = f"t-{uuid.uuid4().hex[:8]}"
    logs: list[dict] = []
    _patch(monkeypatch, _FakeGraph(fail_after_first=True), logs)

    async def run():
        stream = await service.chat_stream("营业额怎么掉了", sid)
        async for _ in stream:
            pass

    try:
        try:
            asyncio.run(run())
        except RuntimeError:
            pass  # 图抛错由上层转成 error 事件，这里只看落盘
        hist = _read_session(sid)
    finally:
        _cleanup(sid)

    assert hist and hist[0]["content"] == "营业额怎么掉了"
    assert any(r["role"] == "human" for r in logs)


def test_stream_persists_human_turn_on_client_disconnect(monkeypatch):
    """客户端点停止（生成器被 aclose）时，这一问也必须留痕。"""
    sid = f"t-{uuid.uuid4().hex[:8]}"
    logs: list[dict] = []
    _patch(monkeypatch, _FakeGraph(), logs)

    async def run():
        stream = await service.chat_stream("端午那几天生意怎么样", sid)
        first = await stream.__anext__()
        await stream.aclose()
        return first

    try:
        asyncio.run(run())
        hist = _read_session(sid)
    finally:
        _cleanup(sid)

    assert hist and hist[0]["content"] == "端午那几天生意怎么样"


def test_chat_persists_human_turn_when_graph_fails(monkeypatch):
    sid = f"t-{uuid.uuid4().hex[:8]}"
    logs: list[dict] = []
    graph = _FakeGraph(fail_after_first=True)
    _patch(monkeypatch, graph, logs)

    try:
        try:
            asyncio.run(service.chat("退款多不多", sid))
        except RuntimeError:
            pass
        hist = _read_session(sid)
    finally:
        _cleanup(sid)

    assert hist and hist[0]["content"] == "退款多不多"


def test_chat_writes_token_total(monkeypatch):
    sid = f"t-{uuid.uuid4().hex[:8]}"
    logs: list[dict] = []
    _patch(monkeypatch, _FakeGraph(tokens=7), logs)

    try:
        reply = asyncio.run(service.chat("你好", sid))
    finally:
        _cleanup(sid)

    assert reply["token_usage"]["total_tokens"] == 7
    ai_rows = [r for r in logs if r["role"] == "ai"]
    assert ai_rows and ai_rows[0]["token_total"] == 7
