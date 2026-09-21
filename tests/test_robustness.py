"""B3 健壮性回归（04 §4 R1–R10）。"""

import asyncio

from config import settings


# ---------- R1：analyst 门禁跳过必须留痕 ----------

def test_analyst_no_allowed_tools_sets_guard_reason():
    from agent.workers.analyst import analyst

    state = {
        "user_input": "帮我查营业额",
        "intent": {"intent": "query_analysis", "confidence": 0.9},
        "security": {"action": "downgrade", "tools_locked": True},
        "token_usage": {},
        "tool_steps": 0,
    }
    out = analyst(state)
    assert out.get("guard_reason") == "tools_locked"


# ---------- R2：步数触顶但已有分析结果 → 记原因且继续派工 ----------

def test_supervisor_keeps_guard_reason_when_analysis_exists():
    from agent.supervisor import decide_next_worker

    state = {
        "intent": {"intent": "query_analysis"},
        "analysis_result": {"trend_analysis": "结果"},
        "strategy": {},
        "worker_history": ["analyst"],
        "supervisor_plan": ["analyst", "strategist", "reviewer"],
        "token_usage": {},
        "tool_steps": settings.MAX_TOOL_STEPS,
    }
    out = decide_next_worker(state)
    assert out.get("guard_reason") == "max_tool_steps"
    assert out["next_worker"] == "strategist"


# ---------- R3：流式限流在拿到生成器前完成（首字节前校验） ----------

def test_chat_stream_rate_limit_precheck(monkeypatch):
    import agent.service as svc

    calls = []

    async def fake_check(*, session_id="", client_ip=""):
        calls.append(session_id)
        return False, "请求过于频繁，请稍后再试。"

    monkeypatch.setattr(svc, "check_rate_limit", fake_check)

    async def run():
        gen = await svc.chat_stream("你好", session_id="s-pre")
        # 检查发生在迭代之前
        assert calls == ["s-pre"]
        return [e async for e in gen]

    events = asyncio.run(run())
    assert events[0]["type"] == "content" and "频繁" in events[0]["content"]
    assert events[1]["type"] == "rate_limited"


# ---------- R4：幂等缓存 Redis 主存 + 本地降级 ----------

class _FakeRedis:
    def __init__(self):
        self.store = {}

    async def get(self, k):
        return self.store.get(k)

    async def setex(self, k, ttl, v):
        self.store[k] = v


def test_idempotency_uses_redis_when_available(monkeypatch):
    from agent import guards

    fake = _FakeRedis()

    async def fake_get_redis():
        return fake

    monkeypatch.setattr(guards, "get_redis", fake_get_redis)

    async def run():
        await guards.idempotency_set("k1", "v1")
        got = await guards.idempotency_get("k1")
        return got

    assert asyncio.run(run()) == "v1"
    assert fake.store.get("agent:idem:k1") == "v1"


def test_idempotency_falls_back_to_local(monkeypatch):
    from agent import guards

    async def no_redis():
        return None

    monkeypatch.setattr(guards, "get_redis", no_redis)
    guards._idempotency_store.clear()

    async def run():
        await guards.idempotency_set("k2", "v2")
        return await guards.idempotency_get("k2")

    assert asyncio.run(run()) == "v2"


# ---------- R6：知识库 import 零副作用，首次检索才加载 ----------

def test_knowledge_base_lazy_load():
    from agent.knowledge.knowledge_base import KnowledgeBase

    kb = KnowledgeBase(enable_vector=False)
    assert kb._ready is False and kb._loaded is False
    hits = kb.search_keyword_hits("退款")
    assert kb._ready and kb._loaded
    assert hits, "真实 data/ 含退款规则，懒加载后应命中"


# ---------- R7：旧图全局引用陷阱已移除 ----------

def test_no_stale_graph_export():
    import agent
    from agent import graph as gm

    assert not hasattr(agent, "agent_graph")
    assert not hasattr(gm, "agent_graph")
    assert gm.get_agent_graph() is gm.get_agent_graph()
