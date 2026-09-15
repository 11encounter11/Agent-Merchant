"""
因子分解工具（Factor Decomposition）

做什么：
- 把营业额分解为 订单数 × 客单价，逐层下钻找根因
- 支持乘法分解（营业额 = 订单数 × 客单价）和加法分解（按菜品/分类拆分）
- 直接查 MySQL，纯 Python 计算

不做什么：
- 不给建议（那是 strategist 的事）
- 不调 LLM

算法说明：
- 乘法分解：营业额 = 订单数 × 客单价，分别计算两个因子的变化率
- 加法分解：按分类/菜品拆分营业额，找出贡献最大/下降最多的项
"""

import logging
from datetime import date, timedelta

from langchain_core.tools import tool
from db.database import execute_query

logger = logging.getLogger(__name__)


@tool
async def factor_decomposition(
    begin_date: str = "",
    end_date: str = "",
    compare_begin_date: str = "",
    compare_end_date: str = "",
) -> str:
    """
    因子分解：把营业额拆成 订单数 × 客单价，找出变化根因。

    参数：
        begin_date: 分析期开始日期（YYYY-MM-DD），默认最近 7 天
        end_date: 分析期结束日期（YYYY-MM-DD），默认今天
        compare_begin_date: 对比期开始日期（默认上一个 7 天）
        compare_end_date: 对比期结束日期

    返回：
        营业额分解结果：订单数变化贡献 + 客单价变化贡献 + 分类维度拆解

    使用场景：
        - "营业额为什么下降了？" → 自动对比上周 vs 本周
        - "分析最近 7 天的营业额变化原因"
    """
    # 默认日期：最近 7 天 vs 上一个 7 天
    today = date.today()
    if not end_date:
        end_date = today.isoformat()
    if not begin_date:
        begin_date = (today - timedelta(days=6)).isoformat()
    if not compare_end_date:
        compare_end_date = (today - timedelta(days=7)).isoformat()
    if not compare_begin_date:
        compare_begin_date = (today - timedelta(days=13)).isoformat()

    # 1. 查询两个周期的汇总数据
    sql = """
        SELECT
            COUNT(*) AS order_count,
            COALESCE(SUM(amount), 0) AS total_amount,
            COALESCE(AVG(amount), 0) AS avg_amount
        FROM orders
        WHERE status IN (3, 4, 5)
          AND DATE(order_time) BETWEEN %s AND %s
    """
    current = await execute_query(sql, (begin_date, end_date))
    previous = await execute_query(sql, (compare_begin_date, compare_end_date))

    if not current or not previous:
        return "数据不足，无法进行因子分解。"

    cur = current[0]
    prev = previous[0]

    cur_orders = cur["order_count"] or 0
    cur_turnover = float(cur["total_amount"])
    cur_avg = float(cur["avg_amount"]) if cur["order_count"] else 0

    prev_orders = prev["order_count"] or 0
    prev_turnover = float(prev["total_amount"])
    prev_avg = float(prev["avg_amount"]) if prev["order_count"] else 0

    # 2. 计算变化率
    turnover_change = cur_turnover - prev_turnover
    turnover_change_pct = (turnover_change / prev_turnover * 100) if prev_turnover else 0

    orders_change = cur_orders - prev_orders
    orders_change_pct = (orders_change / prev_orders * 100) if prev_orders else 0

    avg_change = cur_avg - prev_avg
    avg_change_pct = (avg_change / prev_avg * 100) if prev_avg else 0

    # 3. 按分类拆解（加法分解）
    sql_category = """
        SELECT c.name AS category_name,
               COALESCE(SUM(od.amount), 0) AS category_amount
        FROM order_detail od
        JOIN dish d ON od.dish_id = d.id
        JOIN category c ON d.category_id = c.id
        JOIN orders o ON od.order_id = o.id
        WHERE o.status IN (3, 4, 5)
          AND DATE(o.order_time) BETWEEN %s AND %s
        GROUP BY c.id, c.name
        ORDER BY category_amount DESC
    """
    cur_categories = await execute_query(sql_category, (begin_date, end_date))
    prev_categories = await execute_query(sql_category, (compare_begin_date, compare_end_date))

    # 构建分类对比
    prev_cat_map = {r["category_name"]: float(r["category_amount"]) for r in prev_categories} if prev_categories else {}
    category_comparison = []
    for r in cur_categories:
        name = r["category_name"]
        cur_amt = float(r["category_amount"])
        prev_amt = prev_cat_map.get(name, 0)
        change = cur_amt - prev_amt
        category_comparison.append((name, cur_amt, prev_amt, change))

    # 4. 组装结果
    lines = [
        f"=== 因子分解（{begin_date} ~ {end_date} vs {compare_begin_date} ~ {compare_end_date}）===",
        "",
        f"【营业额】{cur_turnover:.0f} 元 → 环比变化 {turnover_change:+.0f} 元（{turnover_change_pct:+.1f}%）",
        f"  ├── 订单数：{prev_orders} → {cur_orders}（{orders_change:+d}，{orders_change_pct:+.1f}%）",
        f"  └── 客单价：{prev_avg:.1f} → {cur_avg:.1f} 元（{avg_change:+.1f}，{avg_change_pct:+.1f}%）",
        "",
        "【根因判断】",
    ]

    # 判断主因
    if abs(orders_change_pct) > abs(avg_change_pct):
        lines.append(f"  主因：订单数变化（{orders_change_pct:+.1f}%）影响大于客单价（{avg_change_pct:+.1f}%）")
    else:
        lines.append(f"  主因：客单价变化（{avg_change_pct:+.1f}%）影响大于订单数（{orders_change_pct:+.1f}%）")

    if category_comparison:
        lines.append("")
        lines.append("【分类拆解】")
        for name, cur_amt, prev_amt, change in category_comparison:
            lines.append(f"  {name}：{prev_amt:.0f} → {cur_amt:.0f} 元（{change:+.0f}）")

    return "\n".join(lines)
