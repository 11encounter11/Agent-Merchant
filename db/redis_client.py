"""
Redis 客户端

做什么：
- 懒连接 asyncio Redis
- 不可用时自动降级（返回 None），业务走文件/内存兜底

不做什么：
- 不替代 MySQL 经营数据
- 不替代 LangGraph Checkpointer
"""

from __future__ import annotations

import logging
from typing import Optional

from config import settings

logger = logging.getLogger(__name__)

_redis = None
_redis_failed = False


async def get_redis():
    """获取 Redis 连接；失败则返回 None（降级）。"""
    global _redis, _redis_failed

    if not settings.REDIS_ENABLED:
        return None
    if _redis_failed:
        return None
    if _redis is not None:
        return _redis

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
        logger.warning(f"[Redis] 不可用，降级为本地：{e}")
        return None


async def close_redis():
    global _redis, _redis_failed
    if _redis is not None:
        try:
            await _redis.aclose()
        except Exception:
            pass
    _redis = None
    _redis_failed = False


def reset_redis_for_tests():
    """单测重置连接状态。"""
    global _redis, _redis_failed
    _redis = None
    _redis_failed = False


async def redis_status() -> dict:
    """B6c：/health 与配置后台核对 Redis 开关是否真生效。"""
    enabled = bool(settings.REDIS_ENABLED)
    live = False
    if enabled:
        live = (await get_redis()) is not None
    return {"enabled": enabled, "live": live, "degraded": enabled and not live}
