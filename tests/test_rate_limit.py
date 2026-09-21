"""限流（本地降级）单测，不依赖真实 Redis/MySQL。"""

import asyncio

from agent.memory import rate_limit as rl
from config import settings


def test_local_rate_limit_blocks_after_quota(monkeypatch):
    async def run():
        # 强制走本地字典路径
        from db import redis_client

        redis_client.reset_redis_for_tests()
        # 假装 Redis 不可用
        redis_client._redis_failed = True

        try:
            sid = "rl-test-session"
            for i in range(3):
                ok, _ = await rl.check_rate_limit(session_id=sid)
                assert ok, f"第 {i+1} 次应放行"
            ok, reason = await rl.check_rate_limit(session_id=sid)
            assert not ok
            assert "频繁" in (reason or "")
        finally:
            rl._local_windows.clear()
            redis_client.reset_redis_for_tests()

    monkeypatch.setattr(settings, "RATE_LIMIT_ENABLED", True)
    monkeypatch.setattr(settings, "RATE_LIMIT_PER_MINUTE", 3)
    rl._local_windows.clear()
    asyncio.run(run())


def test_rate_limit_can_disable(monkeypatch):
    async def run():
        ok, reason = await rl.check_rate_limit(session_id="x")
        assert ok and reason is None

    monkeypatch.setattr(settings, "RATE_LIMIT_ENABLED", False)
    asyncio.run(run())


def test_ip_bucket_blocks_session_hopping(monkeypatch):
    """B0-A4：同 IP 换 session_id 不得绕过限流。"""
    async def run():
        from db import redis_client

        redis_client.reset_redis_for_tests()
        redis_client._redis_failed = True
        try:
            for i in range(3):
                ok, _ = await rl.check_rate_limit(session_id=f"s{i}", client_ip="9.9.9.9")
                assert ok, f"第 {i+1} 次应放行"
            ok, reason = await rl.check_rate_limit(session_id="s-new", client_ip="9.9.9.9")
            assert not ok
            assert "频繁" in (reason or "")
        finally:
            rl._local_windows.clear()
            redis_client.reset_redis_for_tests()

    monkeypatch.setattr(settings, "RATE_LIMIT_ENABLED", True)
    monkeypatch.setattr(settings, "RATE_LIMIT_PER_MINUTE", 3)
    rl._local_windows.clear()
    asyncio.run(run())
