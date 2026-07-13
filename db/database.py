"""
数据库连接模块

负责创建和管理 MySQL 的异步连接。
所有 Tool 都通过这个模块查询数据库。
"""

import aiomysql
from config import settings


async def get_connection():
    """
    创建一个 MySQL 异步连接。

    每次调用都会新建一个连接，用完需要手动 close()。
    后面阶段会优化成连接池（不用每次新建）。
    """
    conn = await aiomysql.connect(
        host=settings.DB_HOST,
        port=settings.DB_PORT,
        user=settings.DB_USER,
        password=settings.DB_PASSWORD,
        db=settings.DB_NAME,
        charset="utf8mb4",
        autocommit=True,
    )
    return conn


async def execute_query(sql: str, params: tuple = None) -> list[dict]:
    """
    执行 SQL 查询，返回结果列表。

    参数：
        sql: SQL 语句
        params: SQL 参数（防注入用）

    返回：
        list[dict]: 每一行是一个字典，key 是列名

    示例：
        result = await execute_query("SELECT * FROM orders WHERE status = %s", (5,))
        # 返回: [{"id": 1, "amount": 56.0, ...}, {"id": 2, ...}]
    """
    conn = await get_connection()
    try:
        # 用 DictCursor，这样返回的结果是字典而不是元组
        async with conn.cursor(aiomysql.DictCursor) as cursor:
            await cursor.execute(sql, params)
            rows = await cursor.fetchall()
            return rows
    finally:
        conn.close()
