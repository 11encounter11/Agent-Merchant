"""
经营数据查询工具

提供营业额、订单量、用户统计等查询能力。
每个 Tool 都是一个异步函数，用 @tool 装饰器标记。
"""

from datetime import date, datetime
from langchain_core.tools import tool
from db.database import execute_query


@tool
async def query_turnover(begin_date: str, end_date: str, group_by_day: bool = False) -> str:
    """
    查询指定日期范围内的营业额。

    营业额 = 该时间段内所有“已完成”订单（status=5）的金额总和。

    参数：
        begin_date: 开始日期，格式 “YYYY-MM-DD”，例如 “2026-07-01”
        end_date:   结束日期，格式 “YYYY-MM-DD”，例如 “2026-07-12”
        group_by_day: 是否按天拆分（可选，默认 False）

    使用场景：
        - “今天营业额多少？” → begin_date=今天, end_date=今天
        - “这个月赚了多少？”  → begin_date=本月1号, end_date=今天
        - “上周的营收呢？”    → begin_date=上周一, end_date=上周日
        - “最近30天每天营业额” → begin_date=30天前, end_date=今天, group_by_day=True
    """
    if group_by_day:
        # 按天拆分返回
        sql = """
            SELECT DATE(order_time) AS order_date, COALESCE(SUM(amount), 0) AS turnover
            FROM orders
            WHERE status = 5
              AND DATE(order_time) BETWEEN %s AND %s
            GROUP BY DATE(order_time)
            ORDER BY order_date
        """
        rows = await execute_query(sql, (begin_date, end_date))
        
        if not rows:
            return f"从 {begin_date} 到 {end_date} 没有营业额数据。"
        
        lines = [f"从 {begin_date} 到 {end_date} 每天的营业额："]
        for row in rows:
            date_str = str(row['order_date'])
            turnover = float(row['turnover'])
            lines.append(f"  {date_str}: {turnover:.2f} 元")
        
        return "\n".join(lines)
    else:
        # 返回总和
        sql = """
            SELECT COALESCE(SUM(amount), 0) AS total_turnover
            FROM orders
            WHERE status = 5
              AND DATE(order_time) BETWEEN %s AND %s
        """
        rows = await execute_query(sql, (begin_date, end_date))
        total = float(rows[0]["total_turnover"])

        return f"从 {begin_date} 到 {end_date} 的营业额为：{total:.2f} 元"


@tool
async def query_order_count(begin_date: str, end_date: str) -> str:
    """
    查询指定日期范围内的订单数量统计。

    返回各状态的订单数：待接单、已接单、派送中、已完成、已取消。

    参数：
        begin_date: 开始日期，格式 "YYYY-MM-DD"
        end_date:   结束日期，格式 "YYYY-MM-DD"

    使用场景：
        - "今天有多少单？"
        - "还有几个待处理的订单？"
        - "这个月完成了几单？"
    """
    sql = """
        SELECT
            COUNT(*) AS total,
            SUM(CASE WHEN status = 2 THEN 1 ELSE 0 END) AS waiting,
            SUM(CASE WHEN status = 3 THEN 1 ELSE 0 END) AS confirmed,
            SUM(CASE WHEN status = 4 THEN 1 ELSE 0 END) AS delivering,
            SUM(CASE WHEN status = 5 THEN 1 ELSE 0 END) AS completed,
            SUM(CASE WHEN status = 6 THEN 1 ELSE 0 END) AS cancelled
        FROM orders
        WHERE DATE(order_time) BETWEEN %s AND %s
    """
    rows = await execute_query(sql, (begin_date, end_date))
    r = rows[0]

    return (
        f"从 {begin_date} 到 {end_date} 的订单统计：\n"
        f"  总订单数：{r['total']}\n"
        f"  待接单：{r['waiting']}\n"
        f"  已接单：{r['confirmed']}\n"
        f"  派送中：{r['delivering']}\n"
        f"  已完成：{r['completed']}\n"
        f"  已取消：{r['cancelled']}"
    )


@tool
async def query_user_stats(begin_date: str, end_date: str) -> str:
    """
    查询指定日期范围内的用户统计。

    返回：总用户数、新增用户数（在该时间段内注册的）。

    参数：
        begin_date: 开始日期，格式 "YYYY-MM-DD"
        end_date:   结束日期，格式 "YYYY-MM-DD"

    使用场景：
        - "今天新来了多少顾客？"
        - "目前一共有多少用户？"
        - "这个月新增了多少用户？"
    """
    sql_total = "SELECT COUNT(*) AS total FROM user"
    sql_new = """
        SELECT COUNT(*) AS new_count
        FROM user
        WHERE DATE(create_time) BETWEEN %s AND %s
    """

    rows_total = await execute_query(sql_total)
    rows_new = await execute_query(sql_new, (begin_date, end_date))

    total = rows_total[0]["total"]
    new_count = rows_new[0]["new_count"]

    return (
        f"用户统计（截至 {end_date}）：\n"
        f"  总用户数：{total}\n"
        f"  从 {begin_date} 到 {end_date} 新增用户：{new_count}"
    )
