"""
Redis 客户端

做什么：
- 懒连接 asyncio Redis
- 不可用时自动降级（返回 None），业务走文件/内存兜底
- 降级是**带冷却的**：冷却到期后重新试连，Redis 恢复则缓存/限流自动跟着恢复

不做什么：
- 不替代 MySQL 经营数据
- 不替代 LangGraph Checkpointer
"""

from __future__ import annotations

import logging
import time
from typing import Optional

from config import settings

logger = logging.getLogger(__name__)

# 降级后的重连间隔（秒）。粘滞降级会让演示机 Redis 抖一次就永久走本地兜底，
# 直到进程重启才恢复；但每次调用都重试又会在库挂掉时放大延迟。
# 想改配置可在 config 加 REDIS_RETRY_COOLDOWN_SEC，未加时用这个默认值。
_RETRY_COOLDOWN_SEC = float(getattr(settings, "REDIS_RETRY_COOLDOWN_SEC", 30) or 30)

_redis = None
_redis_failed = False
_retry_after = 0.0


def _in_cooldown() -> bool:
    """是否还在冷却期内（不再尝试连接）。"""
    if not _redis_failed:
        return False
    # _retry_after 为 0 表示状态由外部手工置位（单测强制降级），按持续降级处理
    return not _retry_after or time.monotonic() < _retry_after


async def get_redis():
    """获取 Redis 连接；失败或冷却中则返回 None（降级）。"""
    global _redis, _redis_failed, _retry_after

    if not settings.REDIS_ENABLED:
        return None
    if _in_cooldown():
        return None

    if _redis is not None:
        return _redis

    # 冷却结束（或首次调用）：清状态，真的再试一次
    _redis_failed = False
    _retry_after = 0.0

    try:
        from redis.asyncio import Redis

        client = Redis.from_url(
            settings.REDIS_URL,
            encoding="utf-8",
            decode_responses=True,
            socket_connect_timeout=1.5,
            socket_timeout=1.5,
            protocol=2,  # 兼容无 HELLO 的老 Redis（Windows 3.x）
        )
        await client.ping()
        _redis = client
        logger.info(f"[Redis] 已连接 {settings.REDIS_URL}")
        return _redis
    except Exception as e:
        _redis_failed = True
        _retry_after = time.monotonic() + _RETRY_COOLDOWN_SEC
        logger.warning(
            f"[Redis] 不可用，降级为本地（{_RETRY_COOLDOWN_SEC:.0f}s 后重试）：{e}"
        )
        return None


async def close_redis():
    global _redis, _redis_failed, _retry_after
    if _redis is not None:
        try:
            await _redis.aclose()
        except Exception:
            pass
    _redis = None
    _redis_failed = False
    _retry_after = 0.0


def reset_redis_for_tests():
    """单测重置连接状态。"""
    global _redis, _redis_failed, _retry_after
    _redis = None
    _redis_failed = False
    _retry_after = 0.0


async def redis_status() -> dict:
    """B6c：/health 与配置后台核对 Redis 开关是否真生效。"""
    enabled = bool(settings.REDIS_ENABLED)
    live = False
    if enabled:
        live = (await get_redis()) is not None
    return {"enabled": enabled, "live": live, "degraded": enabled and not live}
