"""
限流

固定窗口：每分钟最多 N 次（按 session_id 或 ip）。
优先 Redis INCR + EXPIRE；无 Redis 时用进程内字典（单机演示够用）。
"""

from __future__ import annotations

import logging
import time
from typing import Optional, Tuple

from config import settings
from db.redis_client import get_redis

logger = logging.getLogger(__name__)

# key -> (window_start_ts, count)
_local_windows: dict[str, tuple[int, int]] = {}


class RateLimitExceeded(Exception):
    def __init__(self, key: str, limit: int, retry_after: int = 60):
        self.key = key
        self.limit = limit
        self.retry_after = retry_after
        super().__init__(f"rate limit exceeded for {key}: {limit}/min")


async def check_rate_limit(
    *,
    session_id: str = "",
    client_ip: str = "",
) -> Tuple[bool, Optional[str]]:
    """
    返回 (allowed, reason)。
    allowed=False 时 reason 为给人看的说明。
    """
    if not settings.RATE_LIMIT_ENABLED:
        return True, None

    limit = max(1, int(settings.RATE_LIMIT_PER_MINUTE))
    identity = session_id or client_ip or "anonymous"
    bucket = f"session:{session_id}" if session_id else f"ip:{client_ip or 'unknown'}"

    try:
        allowed = await _hit(bucket, limit)
    except Exception as e:
        logger.warning(f"[RateLimit] 检查失败，放行: {e}")
        return True, None

    if allowed:
        return True, None
    return False, (
        f"请求过于频繁（限额 {limit} 次/分钟，标识 {identity}），请稍后再试。"
    )


async def _hit(bucket: str, limit: int) -> bool:
    r = await get_redis()
    window = int(time.time() // 60)
    key = f"agent:rl:{bucket}:{window}"

    if r is not None:
        count = await r.incr(key)
        if count == 1:
            await r.expire(key, 70)
        return count <= limit

    # 本地降级
    now_window = window
    start, count = _local_windows.get(key, (now_window, 0))
    if start != now_window:
        start, count = now_window, 0
    count += 1
    _local_windows[key] = (start, count)
    # 简单清理，避免字典无限涨
    if len(_local_windows) > 5000:
        _local_windows.clear()
    return count <= limit
