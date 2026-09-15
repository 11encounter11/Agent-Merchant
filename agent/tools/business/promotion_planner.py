"""
促销方案工具（Promotion Planner）

做什么：
- 基于销售数据生成促销方案建议的数据支撑
- 分析哪些菜品适合做促销（高销量低利润 or 低销量高利润）
- 简单的盈亏模拟：降价 X 元 → 预计多卖 Y 份 → 净增收多少
- 直接查 MySQL，纯 Python 计算

不做什么：
- 不做最终促销决策（那是 strategist + LLM 的事）
"""

import logging
from datetime import date, timedelta

from langchain_core.tools import tool
from db.database import execute_query

logger = logging.getLogger(__name__)

_DEFAULT_COST_RATIO = 0.35


@tool
async def promotion_planner(
    category_name: str = "",
    days: int = 30,
) -> str:
    """
    促销方案数据支撑：找出适合促销的菜品 + 盈亏模拟。

    参数：
        category_name: 分类名称（可选，为空则分析全部）
        days: 分析最近多少天（默认 30 天）

    返回：
        适合促销的菜品列表 + 降价盈亏模拟

    使用场景：
        - "有什么促销建议？"
        - "哪些菜适合做活动？"
        - "降价 2 元能多赚多少？"
    """
    today = date.today()
    start = today - timedelta(days=days - 1)

    # 查询菜品销售数据
    sql = """
        SELECT d.name AS dish_name,
               c.name AS category_name,
               d.price,
               COALESCE(d.cost, d.price * %s) AS unit_cost,
               SUM(od.number) AS total_sold,
               SUM(od.amount) AS total_revenue,
               COUNT(DISTINCT o.id) AS order_count
        FROM order_detail od
        JOIN dish d ON od.dish_id = d.id
        JOIN category c ON d.category_id = c.id
        JOIN orders o ON od.order_id = o.id
        WHERE o.status IN (3, 4, 5)
          AND DATE(o.order_time) BETWEEN %s AND %s
    """
    params = [_DEFAULT_COST_RATIO, start.isoformat(), today.isoformat()]
    if category_name:
        sql += " AND c.name = %s"
        params.append(category_name)

    sql += " GROUP BY d.id, d.name, c.name, d.price, d.cost ORDER BY total_sold DESC"
    rows = await execute_query(sql, tuple(params))

    if not rows:
        return f"最近 {days} 天没有销售数据。"

    # 分析每个菜品
    candidates = []
    for r in rows:
        price = float(r["price"])
        cost = float(r["unit_cost"])
        sold = int(r["total_sold"])
        revenue = float(r["total_revenue"])
        margin = ((price - cost) / price * 100) if price > 0 else 0
        unit_profit = price - cost

        # 日均销量
        daily_avg = sold / days

        # 盈亏模拟：降价 2 元
        discount = min(2, price * 0.1)  # 最多降 10%
        new_price = price - discount
        new_unit_profit = new_price - cost

        if new_unit_profit > 0 and daily_avg > 0:
            # 假设价格弹性：降价 10% → 销量增加 15%（简化假设）
            elasticity = 1.5
            sales_increase_pct = (discount / price) * 100 * elasticity
            new_daily = daily_avg * (1 + sales_increase_pct / 100)
            new_daily_profit = new_unit_profit * new_daily
            current_daily_profit = unit_profit * daily_avg
            profit_change = new_daily_profit - current_daily_profit

            candidates.append({
                "name": r["dish_name"],
                "category": r["category_name"],
                "price": price,
                "cost": cost,
                "margin": margin,
                "daily_avg": daily_avg,
                "discount": discount,
                "profit_change": profit_change,
                "new_daily_profit": new_daily_profit,
            })

    # 按利润变化排序（最有价值的促销方案排前面）
    candidates.sort(key=lambda x: x["profit_change"], reverse=True)

    # 组装结果
    lines = [
        f"=== 促销方案数据支撑（最近 {days} 天{'，' + category_name if category_name else ''}）===",
        "",
    ]

    if not candidates:
        lines.append("没有找到适合促销的菜品。")
        return "\n".join(lines)

    lines.append(f"【推荐促销菜品 TOP{min(5, len(candidates))}】（按预计净增收排序）")
    lines.append(f"  （假设：价格弹性 1.5，即降价 10% → 销量增加 15%）")
    lines.append("")

    for i, c in enumerate(candidates[:5], 1):
        lines.append(
            f"  {i}. {c['name']}（{c['category']}）\n"
            f"     现价 {c['price']:.0f} 元 | 成本 {c['cost']:.0f} 元 | 毛利率 {c['margin']:.0f}%\n"
            f"     日均销量 {c['daily_avg']:.1f} 份\n"
            f"     建议降价 {c['discount']:.1f} 元 → 预计日均净增收 {c['profit_change']:+.0f} 元"
        )

    # 汇总
    total_potential = sum(c["profit_change"] for c in candidates[:5])
    lines.append("")
    lines.append(f"【汇总】如果以上 5 个菜品全部促销，预计日均净增收 {total_potential:+.0f} 元")

    return "\n".join(lines)
