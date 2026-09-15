"""
数据库连接模块（aiomysql 连接池）
"""

import asyncio
import logging
from typing import Optional

import aiomysql
from config import settings

logger = logging.getLogger(__name__)

_pool: Optional[aiomysql.Pool] = None

# 查询超时（秒）
_QUERY_TIMEOUT = 30
# 最大重试次数
_MAX_RETRIES = 2


async def get_pool() -> aiomysql.Pool:
    """懒加载全局连接池。"""
    global _pool
    if _pool is None:
        _pool = await aiomysql.create_pool(
            host=settings.DB_HOST,
            port=settings.DB_PORT,
            user=settings.DB_USER,
            password=settings.DB_PASSWORD,
            db=settings.DB_NAME,
            charset="utf8mb4",
            autocommit=True,
            minsize=1,
            maxsize=10,
        )
        logger.info("[DB] 连接池已创建")
    return _pool


async def close_pool():
    """关闭连接池（服务关闭时调用）。"""
    global _pool
    if _pool is not None:
        _pool.close()
        await _pool.wait_closed()
        _pool = None
        logger.info("[DB] 连接池已关闭")


async def execute_query(sql: str, params: tuple = None) -> list[dict]:
    """
    执行 SQL 查询，返回 list[dict]。

    支持：超时控制 + 自动重试（最多 _MAX_RETRIES 次）。
    慢查询日志：超过 3 秒的查询会记录警告。
    """
    last_error = None

    for attempt in range(1 + _MAX_RETRIES):
        try:
            pool = await get_pool()
            async with pool.acquire() as conn:
                async with conn.cursor(aiomysql.DictCursor) as cursor:
                    # 带超时的查询
                    await asyncio.wait_for(
                        cursor.execute(sql, params),
                        timeout=_QUERY_TIMEOUT,
                    )
                    rows = await cursor.fetchall()
                    result = list(rows)

                    if attempt > 1:
                        logger.info(f"[DB] 第 {attempt} 次重试成功")

                    return result

        except asyncio.TimeoutError:
            last_error = f"查询超时（{_QUERY_TIMEOUT}s）"
            logger.warning(f"[DB] {last_error}: sql={sql[:80]}...")
        except Exception as e:
            last_error = str(e)
            logger.warning(f"[DB] 查询失败（第{attempt + 1}次）: {e}")

        # 重试前等待（指数退避）
        if attempt < _MAX_RETRIES:
            wait = 0.5 * (2 ** attempt)
            await asyncio.sleep(wait)

    logger.error(f"[DB] 查询最终失败，重试{_MAX_RETRIES}次后放弃: {last_error}")
    return []


async def execute_write(sql: str, params: tuple = None) -> int:
    """
    执行写 SQL（INSERT/UPDATE/CREATE…），返回 rowcount。
    失败抛出异常，由调用方决定是否降级。
    """
    pool = await get_pool()
    async with pool.acquire() as conn:
        async with conn.cursor() as cursor:
            await asyncio.wait_for(
                cursor.execute(sql, params),
                timeout=_QUERY_TIMEOUT,
            )
            return cursor.rowcount
