"""
异常检测工具（Anomaly Detection）

做什么：
- 检测经营指标的异常突变（退单率、评分、销量等）
- 使用 Z-score 方法：偏离均值超过 2 个标准差视为异常
- 直接查 MySQL，纯 Python 计算

不做什么：
- 不给建议（那是 strategist 的事）
- 不调 LLM

算法说明：
- Z-score = (x - mean) / std
- |Z| > 2 视为异常点（约 95% 置信区间外）
"""

import logging
import math
from datetime import date, timedelta

from langchain_core.tools import tool
from db.database import execute_query
from config import settings

logger = logging.getLogger(__name__)


def _z_scores(values: list[float]) -> list[float]:
    """计算每个值的 Z-score。"""
    n = len(values)
    if n < 2:
        return [0.0] * n

    mean = sum(values) / n
    variance = sum((x - mean) ** 2 for x in values) / (n - 1)
    std = math.sqrt(variance) if variance > 0 else 0

    if std == 0:
        return [0.0] * n

    return [(x - mean) / std for x in values]


@tool
async def anomaly_detection(
    metric: str = "turnover",
    days: int = 30,
    threshold: float = -1.0,
) -> str:
    """
    异常检测：找出经营指标中的异常突变点。

    参数：
        metric: 检测指标，可选：
                turnover（营业额）、order_count（订单数）、
                cancel_rate（退单率）、avg_price（客单价）
        days: 分析最近多少天（默认 30 天）
        threshold: Z-score 阈值；不传（-1）则用系统配置 ANOMALY_THRESHOLD（默认 2.0，越大越不敏感）

    返回：
        异常点列表 + 每日指标值 + 统计摘要

    使用场景：
        - "最近有什么异常吗？"
        - "营业额有没有突然下降的日子？"
        - "退单率有没有异常？"
    """
    if threshold <= 0:
        threshold = settings.ANOMALY_THRESHOLD
    today = date.today()
    start = today - timedelta(days=days - 1)

    # 根据指标选择 SQL
    if metric == "cancel_rate":
        sql = """
            SELECT DATE(order_time) AS order_date,
                   COUNT(*) AS total_orders,
                   SUM(CASE WHEN status = 6 THEN 1 ELSE 0 END) AS cancelled
            FROM orders
            WHERE merchant_id = %s
              AND DATE(order_time) BETWEEN %s AND %s
            GROUP BY DATE(order_time)
            ORDER BY order_date
        """
        rows = await execute_query(sql, (settings.MERCHANT_ID, start.isoformat(), today.isoformat()))
        if not rows:
            return f"最近 {days} 天没有数据。"

        values = [float(r["cancelled"]) / float(r["total_orders"]) * 100 if r["total_orders"] > 0 else 0 for r in rows]
        dates = [str(r["order_date"]) for r in rows]
        metric_label = "退单率(%)"

    elif metric == "order_count":
        sql = """
            SELECT DATE(order_time) AS order_date, COUNT(*) AS cnt
            FROM orders
            WHERE status IN (3, 4, 5)
              AND merchant_id = %s
              AND DATE(order_time) BETWEEN %s AND %s
            GROUP BY DATE(order_time)
            ORDER BY order_date
        """
        rows = await execute_query(sql, (settings.MERCHANT_ID, start.isoformat(), today.isoformat()))
        if not rows:
            return f"最近 {days} 天没有数据。"

        values = [float(r["cnt"]) for r in rows]
        dates = [str(r["order_date"]) for r in rows]
        metric_label = "订单数"

    elif metric == "avg_price":
        sql = """
            SELECT DATE(order_time) AS order_date,
                   COALESCE(AVG(amount), 0) AS avg_amount
            FROM orders
            WHERE status IN (3, 4, 5)
              AND merchant_id = %s
              AND DATE(order_time) BETWEEN %s AND %s
            GROUP BY DATE(order_time)
            ORDER BY order_date
        """
        rows = await execute_query(sql, (settings.MERCHANT_ID, start.isoformat(), today.isoformat()))
        if not rows:
            return f"最近 {days} 天没有数据。"

        values = [float(r["avg_amount"]) for r in rows]
        dates = [str(r["order_date"]) for r in rows]
        metric_label = "客单价(元)"

    else:  # turnover
        sql = """
            SELECT DATE(order_time) AS order_date,
                   COALESCE(SUM(amount), 0) AS total
            FROM orders
            WHERE status IN (3, 4, 5)
              AND merchant_id = %s
              AND DATE(order_time) BETWEEN %s AND %s
            GROUP BY DATE(order_time)
            ORDER BY order_date
        """
        rows = await execute_query(sql, (settings.MERCHANT_ID, start.isoformat(), today.isoformat()))
        if not rows:
            return f"最近 {days} 天没有数据。"

        values = [float(r["total"]) for r in rows]
        dates = [str(r["order_date"]) for r in rows]
        metric_label = "营业额(元)"

    # Z-score 检测
    z_scores = _z_scores(values)
    mean_val = sum(values) / len(values) if values else 0
    std_val = math.sqrt(sum((x - mean_val) ** 2 for x in values) / (len(values) - 1)) if len(values) > 1 else 0

    anomalies = []
    for i, (d, v, z) in enumerate(zip(dates, values, z_scores)):
        if abs(z) >= threshold:
            direction = "偏高" if z > 0 else "偏低"
            anomalies.append((d, v, z, direction))

    # 组装结果
    lines = [
        f"=== 异常检测（{metric_label}，最近 {days} 天，阈值 Z={threshold}）===",
        "",
        f"【统计摘要】",
        f"  均值：{mean_val:.1f}",
        f"  标准差：{std_val:.1f}",
        f"  数据天数：{len(values)}",
        "",
    ]

    if anomalies:
        lines.append(f"【发现 {len(anomalies)} 个异常点】")
        for d, v, z, direction in anomalies:
            lines.append(f"  {d}：{v:.1f}（Z={z:+.2f}，{direction}）")
    else:
        lines.append("【未发现异常】所有数据点均在正常范围内。")

    return "\n".join(lines)
