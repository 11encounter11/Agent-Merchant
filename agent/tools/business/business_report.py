"""
经营报告工具（Business Report）

做什么：
- 生成经营日报/周报：汇总营业额、订单数、趋势、异常
- 内部调用 analysis/ 的多个工具，组合成一份完整报告
- 直接查 MySQL，纯 Python 计算

不做什么：
- 不做深度策略建议（那是 strategist 节点 + LLM 的事）
"""

import logging
from datetime import date, timedelta

from langchain_core.tools import tool
from db.database import execute_query

logger = logging.getLogger(__name__)


@tool
async def business_report(report_type: str = "daily") -> str:
    """
    生成经营报告（日报/周报）。

    参数：
        report_type: 报告类型，"daily"（日报，对比昨天）或 "weekly"（周报，对比上周）

    返回：
        完整的经营报告：营业额、订单数、趋势、异常点、分类排名

    使用场景：
        - "给我看看今天的经营情况" → daily
        - "这周的经营报告" → weekly
    """
    today = date.today()

    if report_type == "weekly":
        period_end = today
        period_start = today - timedelta(days=6)
        compare_end = today - timedelta(days=7)
        compare_start = today - timedelta(days=13)
        title = f"周报（{period_start} ~ {period_end}）"
    else:
        period_end = today
        period_start = today
        compare_end = today - timedelta(days=1)
        compare_start = today - timedelta(days=1)
        title = f"日报（{today}）"

    # 1. 汇总数据
    sql_summary = """
        SELECT
            COUNT(*) AS order_count,
            COALESCE(SUM(amount), 0) AS total_amount,
            COALESCE(AVG(amount), 0) AS avg_amount,
            SUM(CASE WHEN status = 6 THEN 1 ELSE 0 END) AS cancelled
        FROM orders
        WHERE DATE(order_time) BETWEEN %s AND %s
    """
    current = await execute_query(sql_summary, (period_start.isoformat(), period_end.isoformat()))
    previous = await execute_query(sql_summary, (compare_start.isoformat(), compare_end.isoformat()))

    if not current:
        return f"{'本' if report_type == 'weekly' else '今'}日没有经营数据。"

    cur = current[0]
    prev = previous[0] if previous else {"order_count": 0, "total_amount": 0, "avg_amount": 0, "cancelled": 0}

    cur_turnover = float(cur["total_amount"])
    prev_turnover = float(prev["total_amount"])
    cur_orders = cur["order_count"] or 0
    prev_orders = prev["order_count"] or 0
    cur_cancelled = cur["cancelled"] or 0

    turnover_change = ((cur_turnover - prev_turnover) / prev_turnover * 100) if prev_turnover else 0
    orders_change = ((cur_orders - prev_orders) / prev_orders * 100) if prev_orders else 0

    # 2. 分类排名
    sql_category = """
        SELECT c.name AS category_name,
               SUM(od.amount) AS total_revenue,
               SUM(od.number) AS total_sold
        FROM order_detail od
        JOIN dish d ON od.dish_id = d.id
        JOIN category c ON d.category_id = c.id
        JOIN orders o ON od.order_id = o.id
        WHERE o.status IN (3, 4, 5)
          AND DATE(o.order_time) BETWEEN %s AND %s
        GROUP BY c.id, c.name
        ORDER BY total_revenue DESC
        LIMIT 5
    """
    categories = await execute_query(sql_category, (period_start.isoformat(), period_end.isoformat()))

    # 3. 组装报告
    lines = [
        f"=== {title} ===",
        "",
        "【核心指标】",
        f"  营业额：{cur_turnover:.0f} 元（环比 {turnover_change:+.1f}%）",
        f"  订单数：{cur_orders}（环比 {orders_change:+.1f}%）",
        f"  客单价：{float(cur['avg_amount']):.1f} 元",
        f"  退单数：{cur_cancelled}",
    ]

    # 趋势判断
    if turnover_change > 5:
        lines.append(f"  趋势：营业额上升 {turnover_change:.1f}%")
    elif turnover_change < -5:
        lines.append(f"  趋势：营业额下降 {abs(turnover_change):.1f}%，需关注")
    else:
        lines.append(f"  趋势：营业额基本平稳")

    if categories:
        lines.append("")
        lines.append("【分类排名 TOP5】")
        for i, c in enumerate(categories, 1):
            lines.append(f"  {i}. {c['category_name']}：{float(c['total_revenue']):.0f} 元（{int(c['total_sold'])} 份）")

    return "\n".join(lines)
