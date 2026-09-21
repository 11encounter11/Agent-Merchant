"""
相关性分析工具（Correlation Analysis）

做什么：
- 计算两个变量之间的 Pearson 相关系数
- 支持：天气 vs 销量、温度 vs 营业额 等场景
- 直接查 MySQL，纯 Python 计算

不做什么：
- 不给建议（那是 strategist 的事）
- 不调 LLM

算法说明：
- Pearson r：衡量线性相关程度，-1 到 1
- |r| > 0.7 强相关，0.3~0.7 中等相关，< 0.3 弱相关
"""

import logging
import math
from datetime import date, timedelta

from langchain_core.tools import tool
from db.database import execute_query
from config import settings

logger = logging.getLogger(__name__)

# 强相关分界（统计学惯例）；中等相关分界走配置 CORRELATION_SIGNIFICANT
_STRONG_R = 0.7


def _pearson_r(x: list[float], y: list[float]) -> float:
    """计算 Pearson 相关系数。"""
    n = len(x)
    if n < 3:
        return 0.0

    mean_x = sum(x) / n
    mean_y = sum(y) / n

    numerator = sum((xi - mean_x) * (yi - mean_y) for xi, yi in zip(x, y))
    denom_x = math.sqrt(sum((xi - mean_x) ** 2 for xi in x))
    denom_y = math.sqrt(sum((yi - mean_y) ** 2 for yi in y))

    if denom_x == 0 or denom_y == 0:
        return 0.0

    return numerator / (denom_x * denom_y)


def _interpret_r(r: float) -> str:
    """解释相关系数。"""
    abs_r = abs(r)
    direction = "正相关" if r > 0 else "负相关" if r < 0 else "无相关"
    if abs_r > _STRONG_R:
        strength = "强"
    elif abs_r > settings.CORRELATION_SIGNIFICANT:
        strength = "中等"
    else:
        strength = "弱"
    return f"{strength}{direction}（r={r:.3f}）"


@tool
async def correlation_analysis(
    variable_a: str = "turnover",
    variable_b: str = "order_count",
    days: int = 30,
) -> str:
    """
    相关性分析：计算两个经营指标之间的 Pearson 相关系数。

    参数：
        variable_a: 变量A，可选：turnover（营业额）、order_count（订单数）、avg_price（客单价）
        variable_b: 变量B，同上
        days: 分析最近多少天的数据（默认 30 天）

    返回：
        相关系数 + 解读 + 每日数据明细

    使用场景：
        - "订单数和营业额有关系吗？"
        - "最近 30 天客单价和订单量的相关性"
    """
    today = date.today()
    start = today - timedelta(days=days - 1)

    # 查询每日数据
    sql = """
        SELECT DATE(order_time) AS order_date,
               COALESCE(SUM(amount), 0) AS turnover,
               COUNT(*) AS order_count,
               COALESCE(AVG(amount), 0) AS avg_price
        FROM orders
        WHERE status IN (3, 4, 5)
          AND DATE(order_time) BETWEEN %s AND %s
        GROUP BY DATE(order_time)
        ORDER BY order_date
    """
    rows = await execute_query(sql, (start.isoformat(), today.isoformat()))

    if len(rows) < 3:
        return f"数据不足（仅 {len(rows)} 天），无法计算相关性。至少需要 3 天数据。"

    # 提取两个变量的数据
    var_map = {"turnover": "turnover", "order_count": "order_count", "avg_price": "avg_price"}
    key_a = var_map.get(variable_a, "turnover")
    key_b = var_map.get(variable_b, "order_count")

    x = [float(r[key_a]) for r in rows]
    y = [float(r[key_b]) for r in rows]

    r = _pearson_r(x, y)
    interpretation = _interpret_r(r)

    lines = [
        f"=== 相关性分析（最近 {days} 天）===",
        f"变量 A：{variable_a}",
        f"变量 B：{variable_b}",
        f"数据天数：{len(rows)} 天",
        "",
        f"【结果】{interpretation}",
        "",
        "【解读】",
    ]

    abs_r = abs(r)
    if abs_r > _STRONG_R:
        lines.append(f"  {variable_a} 和 {variable_b} 高度相关，一个变化时另一个很可能同步变化。")
    elif abs_r > settings.CORRELATION_SIGNIFICANT:
        lines.append(f"  {variable_a} 和 {variable_b} 有一定相关性，但还受其他因素影响。")
    else:
        lines.append(f"  {variable_a} 和 {variable_b} 相关性很弱，基本独立变化。")

    return "\n".join(lines)
