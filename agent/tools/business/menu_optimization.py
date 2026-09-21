"""
菜品优化工具（Menu Optimization）

做什么：
- ABC 分析：按销量 × 利润率矩阵对菜品分类
- A 类（高销量高利润）= 明星菜品，B 类 = 潜力菜品，C 类 = 考虑调整
- 直接查 MySQL，纯 Python 计算

不做什么：
- 不做最终上下架决策（那是 strategist + LLM 的事）
"""

import logging
from datetime import date, timedelta

from langchain_core.tools import tool
from db.database import execute_query
from config import settings

logger = logging.getLogger(__name__)


@tool
async def menu_optimization(days: int = 30) -> str:
    """
    菜品优化分析：ABC 分类 + 上下架建议。

    参数：
        days: 分析最近多少天（默认 30 天）

    返回：
        各菜品的销量、毛利率、ABC 分类、优化建议

    使用场景：
        - "哪些菜该下架？"
        - "菜品结构合不合理？"
        - "帮我做一下菜品分析"
    """
    today = date.today()
    start = today - timedelta(days=days - 1)

    sql = """
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
        GROUP BY d.id, d.name, c.name, d.price, d.cost
        ORDER BY total_revenue DESC
    """
    rows = await execute_query(sql, (settings.COST_RATIO_DEFAULT, start.isoformat(), today.isoformat()))

    if not rows:
        return f"最近 {days} 天没有销售数据。"

    # 计算总销量和总营收，用于 ABC 分类
    total_sold = sum(int(r["total_sold"]) for r in rows)
    total_revenue = sum(float(r["total_revenue"]) for r in rows)

    # ABC 分类（按营收贡献累计占比）
    cumulative_revenue = 0
    classified = []
    for r in rows:
        revenue = float(r["total_revenue"])
        cumulative_revenue += revenue
        cum_pct = (cumulative_revenue / total_revenue * 100) if total_revenue > 0 else 0

        price = float(r["price"])
        cost = float(r["unit_cost"])
        margin = ((price - cost) / price * 100) if price > 0 else 0
        sold = int(r["total_sold"])
        sold_pct = (sold / total_sold * 100) if total_sold > 0 else 0

        # ABC 分类
        if cum_pct <= 70:
            abc = "A"
        elif cum_pct <= 90:
            abc = "B"
        else:
            abc = "C"

        classified.append({
            "name": r["dish_name"],
            "category": r["category_name"],
            "sold": sold,
            "sold_pct": sold_pct,
            "revenue": revenue,
            "margin": margin,
            "abc": abc,
            "cum_pct": cum_pct,
        })

    # 组装结果
    lines = [
        f"=== 菜品优化分析（最近 {days} 天，共 {len(classified)} 个菜品）===",
        "",
        f"【帕累托分析】",
        f"  A 类（贡献 70% 营收）：{sum(1 for c in classified if c['abc'] == 'A')} 个菜品",
        f"  B 类（贡献 70%-90%）：{sum(1 for c in classified if c['abc'] == 'B')} 个菜品",
        f"  C 类（贡献 90%-100%）：{sum(1 for c in classified if c['abc'] == 'C')} 个菜品",
    ]

    # 按分类展示
    for abc_type in ["A", "B", "C"]:
        items = [c for c in classified if c["abc"] == abc_type]
        if not items:
            continue

        label = {"A": "明星菜品（重点维护）", "B": "潜力菜品（可优化提升）", "C": "长尾菜品（考虑调整）"}
        lines.append("")
        lines.append(f"【{abc_type} 类 — {label[abc_type]}】")

        for c in items[:10]:  # 每类最多展示 10 个
            lines.append(
                f"  {c['name']}（{c['category']}）：\n"
                f"    销量 {c['sold']} 份（{c['sold_pct']:.1f}%）| "
                f"营收 {c['revenue']:.0f} 元 | "
                f"毛利率 {c['margin']:.0f}%"
            )

    return "\n".join(lines)
