"""Redis 降级必须能自愈：抖一次不能永久降级到进程重启（SPEC/03 G6）。"""

import asyncio
import time

import db.redis_client as rc


class _FakeRedis:
    """只记录尝试次数，按开关决定 ping 成败。"""

    attempts = 0
    reachable = False

    @classmethod
    def from_url(cls, url, **kwargs):
        cls.attempts += 1
        return cls()

    async def ping(self):
        if not _FakeRedis.reachable:
            raise ConnectionError("Connection refused")

    async def aclose(self):
        pass


def _setup(monkeypatch, cooldown=0.05):
    _FakeRedis.attempts = 0
    _FakeRedis.reachable = False
    rc.reset_redis_for_tests()
    monkeypatch.setattr(rc.settings, "REDIS_ENABLED", True, raising=False)
    monkeypatch.setattr(rc, "_RETRY_COOLDOWN_SEC", cooldown)
    import redis.asyncio as ra

    monkeypatch.setattr(ra, "Redis", _FakeRedis)


def test_failure_degrades_and_counts_one_attempt(monkeypatch):
    _setup(monkeypatch)
    assert asyncio.run(rc.get_redis()) is None
    assert _FakeRedis.attempts == 1


def test_cooldown_does_not_hammer_a_dead_redis(monkeypatch):
    _setup(monkeypatch, cooldown=60)
    asyncio.run(rc.get_redis())
    asyncio.run(rc.get_redis())
    asyncio.run(rc.get_redis())
    assert _FakeRedis.attempts == 1  # 冷却期内不再反复连
    assert asyncio.run(rc.redis_status()) == {
        "enabled": True,
        "live": False,
        "degraded": True,
    }


def test_recovers_after_cooldown_without_restart(monkeypatch):
    _setup(monkeypatch, cooldown=0.05)
    assert asyncio.run(rc.get_redis()) is None

    _FakeRedis.reachable = True
    assert asyncio.run(rc.get_redis()) is None  # 还在冷却，不该立刻连
    assert _FakeRedis.attempts == 1

    time.sleep(0.06)
    assert asyncio.run(rc.get_redis()) is not None  # 冷却到期自动重试
    assert _FakeRedis.attempts == 2
    assert asyncio.run(rc.redis_status())["live"] is True


def test_manually_forced_degradation_stays_forced(monkeypatch):
    """既有单测靠直接置 _redis_failed 强制降级，语义不能被冷却打破。"""
    _setup(monkeypatch)
    rc.reset_redis_for_tests()
    rc._redis_failed = True
    assert asyncio.run(rc.get_redis()) is None
    assert _FakeRedis.attempts == 0


def test_close_resets_cooldown(monkeypatch):
    _setup(monkeypatch, cooldown=60)
    asyncio.run(rc.get_redis())
    asyncio.run(rc.close_redis())
    _FakeRedis.reachable = True
    assert asyncio.run(rc.get_redis()) is not None
