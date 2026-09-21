"""
备货计划工具（Prep Plan）

做什么：
- 基于历史销量预测明日各菜品备货量
- 考虑星期几的影响（工作日 vs 周末销量不同）
- 直接查 MySQL，纯 Python 计算

不做什么：
- 不做最终备货决策（那是 strategist + LLM 的事）
- 不查天气（天气数据由 external/weather.py 提供，strategist 节点综合判断）
"""

import logging
from datetime import date, timedelta

from langchain_core.tools import tool
from db.database import execute_query
from config import settings

logger = logging.getLogger(__name__)


@tool
async def prep_plan(days: int = 14) -> str:
    """
    备货计划：基于历史销量预测明日各菜品建议备货量。

    参数：
        days: 参考最近多少天的数据（默认 14 天）

    返回：
        各菜品的历史日均销量 + 建议备货量 + 星期几调整

    使用场景：
        - "明天要备多少货？"
        - "帮我算一下备货量"
    """
    today = date.today()
    start = today - timedelta(days=days - 1)
    tomorrow = today + timedelta(days=1)
    tomorrow_weekday = tomorrow.weekday()  # 0=周一, 6=周日
    weekday_names = ["周一", "周二", "周三", "周四", "周五", "周六", "周日"]

    # 1. 查询各菜品总销量
    sql_total = """
        SELECT d.name AS dish_name,
               c.name AS category_name,
               SUM(od.number) AS total_sold,
               AVG(od.number) AS avg_per_order
        FROM order_detail od
        JOIN dish d ON od.dish_id = d.id
        JOIN category c ON d.category_id = c.id
        JOIN orders o ON od.order_id = o.id
        WHERE o.status IN (3, 4, 5)
          AND o.merchant_id = %s
          AND DATE(o.order_time) BETWEEN %s AND %s
        GROUP BY d.id, d.name, c.name
        ORDER BY total_sold DESC
    """
    rows = await execute_query(sql_total, (settings.MERCHANT_ID, start.isoformat(), today.isoformat()))

    if not rows:
        return f"最近 {days} 天没有销售数据，无法生成备货计划。"

    # 2. 查询明天是星期几的历史数据（用于调整）
    sql_weekday = """
        SELECT DATE(o.order_time) AS order_date,
               DAYOFWEEK(o.order_time) AS day_of_week
        FROM orders o
        WHERE o.status IN (3, 4, 5)
          AND o.merchant_id = %s
          AND DATE(o.order_time) BETWEEN %s AND %s
          AND DAYOFWEEK(o.order_time) = %s
        GROUP BY DATE(o.order_time)
    """
    # MySQL DAYOFWEEK: 1=Sunday, 2=Monday, ..., 7=Saturday
    mysql_dow = (tomorrow_weekday + 2) % 7 + 1  # Python 0=Mon → MySQL 2=Mon
    weekday_dates = await execute_query(sql_weekday, (settings.MERCHANT_ID, start.isoformat(), today.isoformat(), mysql_dow))
    weekday_count = len(weekday_dates)

    # 3. 查询明天同星期的菜品销量
    weekday_dishes = {}
    if weekday_count > 0:
        sql_weekday_dish = """
            SELECT d.name AS dish_name,
                   SUM(od.number) AS total_sold
            FROM order_detail od
            JOIN dish d ON od.dish_id = d.id
            JOIN orders o ON od.order_id = o.id
            WHERE o.status IN (3, 4, 5)
              AND o.merchant_id = %s
              AND DATE(o.order_time) BETWEEN %s AND %s
              AND DAYOFWEEK(o.order_time) = %s
            GROUP BY d.id, d.name
        """
        wd_rows = await execute_query(sql_weekday_dish, (settings.MERCHANT_ID, start.isoformat(), today.isoformat(), mysql_dow))
        weekday_dishes = {r["dish_name"]: int(r["total_sold"]) for r in wd_rows}

    # 4. 计算备货量
    lines = [
        f"=== 备货计划建议（明天 {tomorrow} {weekday_names[tomorrow_weekday]}）===",
        f"参考数据：最近 {days} 天",
        "",
    ]

    total_items = 0
    for r in rows:
        name = r["dish_name"]
        category = r["category_name"]
        total_sold = int(r["total_sold"])
        daily_avg = total_sold / days

        # 如果有同星期数据，用同星期均值调整
        if name in weekday_dishes and weekday_count > 0:
            weekday_avg = weekday_dishes[name] / weekday_count
            # 加权平均：70% 同星期 + 30% 总平均
            recommended = weekday_avg * 0.7 + daily_avg * 0.3
        else:
            recommended = daily_avg

        # 加 10% 安全余量，向上取整
        recommended = int(recommended * 1.1) + 1
        total_items += recommended

        lines.append(
            f"  {name}（{category}）：\n"
            f"    日均 {daily_avg:.1f} 份 → 建议备货 {recommended} 份"
        )

    lines.insert(3, f"预计总备货量：{total_items} 份")

    return "\n".join(lines)
