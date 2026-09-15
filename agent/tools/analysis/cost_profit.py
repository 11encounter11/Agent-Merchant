"""
成本利润分析工具（Cost & Profit Analysis）

做什么：
- 分析菜品/分类的毛利率、收入贡献
- 成本数据优先从数据库 dish_cost 字段读取，没有则用模拟成本率
- 直接查 MySQL，纯 Python 计算

不做什么：
- 不给建议（那是 strategist 的事）
- 不调 LLM
"""

import logging
from datetime import date, timedelta

from langchain_core.tools import tool
from db.database import execute_query

logger = logging.getLogger(__name__)

# 默认成本率（当数据库没有成本数据时的估算值）
_DEFAULT_COST_RATIO = 0.35


@tool
async def cost_profit_analysis(
    category_name: str = "",
    days: int = 30,
) -> str:
    """
    成本利润分析：计算菜品/分类的毛利率和收入贡献。

    参数：
        category_name: 分类名称（可选，为空则分析全部分类）
        days: 分析最近多少天（默认 30 天）

    返回：
        各分类/菜品的收入、成本估算、毛利率、利润贡献占比

    使用场景：
        - "哪个分类最赚钱？"
        - "菜品的毛利率怎么样？"
        - "利润贡献最高的菜是哪些？"
    """
    today = date.today()
    start = today - timedelta(days=days - 1)

    # 查询各分类的销售数据
    sql_category = """
        SELECT c.name AS category_name,
               SUM(od.number) AS total_sold,
               SUM(od.amount) AS total_revenue
        FROM order_detail od
        JOIN dish d ON od.dish_id = d.id
        JOIN category c ON d.category_id = c.id
        JOIN orders o ON od.order_id = o.id
        WHERE o.status IN (3, 4, 5)
          AND DATE(o.order_time) BETWEEN %s AND %s
        GROUP BY c.id, c.name
        ORDER BY total_revenue DESC
    """

    params = (start.isoformat(), today.isoformat())
    if category_name:
        sql_category += " HAVING c.name = %s"
        params = (start.isoformat(), today.isoformat(), category_name)

    categories = await execute_query(sql_category, params)

    if not categories:
        return f"最近 {days} 天没有销售数据。"

    # 查询各菜品明细（含成本字段，如果有的话）
    sql_dish = """
        SELECT d.name AS dish_name,
               c.name AS category_name,
               d.price,
               COALESCE(d.cost, d.price * %s) AS unit_cost,
               SUM(od.number) AS total_sold,
               SUM(od.amount) AS total_revenue
        FROM order_detail od
        JOIN dish d ON od.dish_id = d.id
        JOIN category c ON d.category_id = c.id
        JOIN orders o ON od.order_id = o.id
        WHERE o.status IN (3, 4, 5)
          AND DATE(o.order_time) BETWEEN %s AND %s
    """
    dish_params = (_DEFAULT_COST_RATIO, start.isoformat(), today.isoformat())
    if category_name:
        sql_dish += " AND c.name = %s"
        dish_params = (_DEFAULT_COST_RATIO, start.isoformat(), today.isoformat(), category_name)

    sql_dish += " GROUP BY d.id, d.name, c.name, d.price, d.cost ORDER BY total_revenue DESC LIMIT 20"
    dishes = await execute_query(sql_dish, dish_params)

    # 组装分类分析
    total_revenue = sum(float(c["total_revenue"]) for c in categories)

    lines = [
        f"=== 成本利润分析（最近 {days} 天{'，' + category_name if category_name else ''}）===",
        "",
        f"【分类利润概览】（总营收：{total_revenue:.0f} 元）",
    ]

    for c in categories:
        revenue = float(c["total_revenue"])
        cost_est = revenue * _DEFAULT_COST_RATIO
        profit = revenue - cost_est
        margin = (profit / revenue * 100) if revenue > 0 else 0
        contribution = (revenue / total_revenue * 100) if total_revenue > 0 else 0

        lines.append(
            f"  {c['category_name']}：营收 {revenue:.0f} 元 | "
            f"成本估算 {cost_est:.0f} 元 | "
            f"毛利 {profit:.0f} 元（毛利率 {margin:.0f}%）| "
            f"贡献占比 {contribution:.1f}%"
        )

    # 菜品明细
    if dishes:
        lines.append("")
        lines.append(f"【菜品利润 TOP{min(20, len(dishes))}】")
        lines.append(f"  （注：成本数据为估算值，成本率={_DEFAULT_COST_RATIO*100:.0f}%）")
        lines.append("")

        for d in dishes:
            revenue = float(d["total_revenue"])
            unit_cost = float(d["unit_cost"])
            price = float(d["price"])
            sold = int(d["total_sold"])
            unit_profit = price - unit_cost
            total_profit = unit_profit * sold
            margin = (unit_profit / price * 100) if price > 0 else 0

            lines.append(
                f"  {d['dish_name']}（{d['category_name']}）：\n"
                f"    售价 {price:.0f} 元 | 成本 {unit_cost:.0f} 元 | "
                f"单份利润 {unit_profit:.0f} 元 | 毛利率 {margin:.0f}%\n"
                f"    销量 {sold} 份 | 总利润 {total_profit:.0f} 元"
            )

    return "\n".join(lines)
