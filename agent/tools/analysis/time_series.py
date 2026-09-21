"""
趋势分析工具（Time Series Analysis）

做什么：
- 分析经营指标的趋势方向和周期性
- 使用移动平均（MA）平滑数据 + 线性回归判断趋势
- 直接查 MySQL，纯 Python 计算

不做什么：
- 不给建议（那是 strategist 的事）
- 不调 LLM

算法说明：
- 移动平均（MA-3）：平滑短期波动，看清趋势
- 线性回归：y = a*x + b，斜率 a > 0 上升，a < 0 下降
- 周期性：对比相邻周期的数据，看是否有规律性波动
"""

import logging
from datetime import date, timedelta

from langchain_core.tools import tool
from db.database import execute_query
from config import settings

logger = logging.getLogger(__name__)


def _linear_regression(values: list[float]) -> tuple[float, float, str]:
    """
    简单线性回归，返回 (斜率, 截距, 趋势描述)。
    """
    n = len(values)
    if n < 2:
        return 0.0, 0.0, "数据不足"

    x_mean = (n - 1) / 2.0
    y_mean = sum(values) / n

    numerator = sum((i - x_mean) * (v - y_mean) for i, v in enumerate(values))
    denominator = sum((i - x_mean) ** 2 for i in range(n))

    if denominator == 0:
        return 0.0, y_mean, "平稳"

    slope = numerator / denominator
    # 用斜率占均值的比例判断趋势
    change_rate = (slope / y_mean * 100) if y_mean != 0 else 0

    if change_rate > 1:
        trend = "上升"
    elif change_rate < -1:
        trend = "下降"
    else:
        trend = "平稳"

    return slope, y_mean, trend


def _moving_average(values: list[float], window: int = 3) -> list[float]:
    """计算移动平均。"""
    if len(values) < window:
        return values[:]
    result = []
    for i in range(len(values) - window + 1):
        avg = sum(values[i:i + window]) / window
        result.append(avg)
    return result


@tool
async def trend_analysis(
    metric: str = "turnover",
    days: int = 14,
) -> str:
    """
    趋势分析：查看经营指标的趋势方向和周期性。

    参数：
        metric: 分析指标，可选：turnover（营业额）、order_count（订单数）、avg_price（客单价）
        days: 分析最近多少天（默认 14 天）

    返回：
        趋势方向 + 移动平均 + 统计摘要 + 每日数据

    使用场景：
        - "最近一周经营趋势怎么样？"
        - "营业额是在涨还是在跌？"
        - "最近 30 天的业绩分析"
    """
    today = date.today()
    start = today - timedelta(days=days - 1)

    # 查询每日数据
    if metric == "order_count":
        sql = """
            SELECT DATE(order_time) AS order_date, COUNT(*) AS value
            FROM orders
            WHERE status IN (3, 4, 5)
              AND merchant_id = %s
              AND DATE(order_time) BETWEEN %s AND %s
            GROUP BY DATE(order_time)
            ORDER BY order_date
        """
        metric_label = "订单数"
    elif metric == "avg_price":
        sql = """
            SELECT DATE(order_time) AS order_date,
                   COALESCE(AVG(amount), 0) AS value
            FROM orders
            WHERE status IN (3, 4, 5)
              AND merchant_id = %s
              AND DATE(order_time) BETWEEN %s AND %s
            GROUP BY DATE(order_time)
            ORDER BY order_date
        """
        metric_label = "客单价(元)"
    else:  # turnover
        sql = """
            SELECT DATE(order_time) AS order_date,
                   COALESCE(SUM(amount), 0) AS value
            FROM orders
            WHERE status IN (3, 4, 5)
              AND merchant_id = %s
              AND DATE(order_time) BETWEEN %s AND %s
            GROUP BY DATE(order_time)
            ORDER BY order_date
        """
        metric_label = "营业额(元)"

    rows = await execute_query(sql, (settings.MERCHANT_ID, start.isoformat(), today.isoformat()))

    if not rows:
        return f"最近 {days} 天没有{metric_label}数据。"

    dates = [str(r["order_date"]) for r in rows]
    values = [float(r["value"]) for r in rows]

    # 线性回归
    slope, y_mean, trend = _linear_regression(values)

    # 移动平均
    ma_values = _moving_average(values, window=3)

    # 统计摘要
    total = sum(values)
    avg_val = total / len(values) if values else 0
    max_val = max(values) if values else 0
    min_val = min(values) if values else 0
    max_date = dates[values.index(max_val)] if values else ""
    min_date = dates[values.index(min_val)] if values else ""

    # 组装结果
    lines = [
        f"=== 趋势分析（{metric_label}，最近 {days} 天）===",
        "",
        f"【统计摘要】",
        f"  总计：{total:.0f}",
        f"  日均：{avg_val:.1f}",
        f"  最高：{max_val:.1f}（{max_date}）",
        f"  最低：{min_val:.1f}（{min_date}）",
        "",
        f"【趋势判断】{trend}",
        f"  线性斜率：{slope:+.2f}/天",
    ]

    if trend == "上升":
        lines.append(f"  解读：{metric_label}整体呈上升趋势，日均增长约 {slope:.1f}")
    elif trend == "下降":
        lines.append(f"  解读：{metric_label}整体呈下降趋势，日均减少约 {abs(slope):.1f}")
    else:
        lines.append(f"  解读：{metric_label}基本平稳，无明显趋势")

    # 移动平均（最近 5 个）
    if ma_values:
        lines.append("")
        lines.append(f"【移动平均 MA-3】（最近 {min(5, len(ma_values))} 个）")
        ma_dates = dates[2:]  # MA-3 从第 3 天开始
        for i in range(max(0, len(ma_values) - 5), len(ma_values)):
            lines.append(f"  {ma_dates[i]}：{ma_values[i]:.1f}")

    return "\n".join(lines)
