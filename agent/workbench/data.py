"""工作台只读数据层。

硬约束：
- 只读现有 Java 平台表，不写、不建表、不要求 store_id/refund_record；
- 所有业务查询固定 merchant_id=settings.MERCHANT_ID；
- 退款没有 refund_record，只能用 status=6 AND pay_status=2 近似；
- 数据库不可用抛 DBUnavailable，和“查到 0 行”严格区分。
"""

from __future__ import annotations

import logging
from datetime import date, timedelta
from decimal import Decimal
from typing import Any, Iterable, Optional

from config import settings
from db.database import execute_query

from .period import Period, requested_period, with_fallback

logger = logging.getLogger(__name__)

PAID_STATUS_SQL = "status IN (3, 4, 5, 6) AND pay_status IN (1, 2)"
COMPLETED_STATUS_SQL = "status = 5"
REFUND_STATUS_SQL = "status = 6 AND pay_status = 2"


def _money(value: Any) -> float:
    if value is None:
        return 0.0
    if isinstance(value, Decimal):
        return float(value.quantize(Decimal("0.01")))
    return round(float(value), 2)


def _int(value: Any) -> int:
    return int(value or 0)


def _ratio(cur: float, prev: float) -> Optional[float]:
    if prev == 0:
        return None
    return round((cur - prev) / prev, 4)


async def latest_data_date() -> Optional[date]:
    rows = await execute_query(
        "SELECT MAX(DATE(order_time)) AS latest FROM orders WHERE merchant_id = %s",
        (settings.MERCHANT_ID,),
    )
    latest = rows[0].get("latest") if rows else None
    if latest is None:
        return None
    return latest if isinstance(latest, date) else date.fromisoformat(str(latest))


async def has_paid_orders(start: date, end: date) -> bool:
    rows = await execute_query(
        f"""
        SELECT COUNT(*) AS cnt
        FROM orders
        WHERE merchant_id = %s
          AND {PAID_STATUS_SQL}
          AND order_time >= %s AND order_time < %s
        """,
        (settings.MERCHANT_ID, start.isoformat(), end.isoformat()),
    )
    return _int(rows[0]["cnt"]) > 0 if rows else False


async def resolve_effective_period(range_key: str) -> Period:
    requested = requested_period(range_key)
    latest = await latest_data_date()
    has_data = await has_paid_orders(requested.start, requested.end) if latest else False
    return with_fallback(requested, latest, has_data=has_data, fallback_days=7)


async def kpi_summary(start: date, end: date) -> dict:
    rows = await execute_query(
        f"""
        SELECT
            COUNT(*) AS total_orders,
            SUM(CASE WHEN {COMPLETED_STATUS_SQL} THEN 1 ELSE 0 END) AS completed_orders,
            COALESCE(SUM(CASE WHEN {COMPLETED_STATUS_SQL} THEN amount ELSE 0 END), 0) AS revenue,
            SUM(CASE WHEN {PAID_STATUS_SQL} THEN 1 ELSE 0 END) AS paid_orders,
            SUM(CASE WHEN {REFUND_STATUS_SQL} THEN 1 ELSE 0 END) AS refund_orders,
            COALESCE(SUM(CASE WHEN {REFUND_STATUS_SQL} THEN amount ELSE 0 END), 0) AS refund_amount
        FROM orders
        WHERE merchant_id = %s
          AND order_time >= %s AND order_time < %s
        """,
        (settings.MERCHANT_ID, start.isoformat(), end.isoformat()),
    )
    row = rows[0] if rows else {}
    revenue = _money(row.get("revenue"))
    completed = _int(row.get("completed_orders"))
    paid = _int(row.get("paid_orders"))
    refunded = _int(row.get("refund_orders"))
    new_customers = await new_customer_count(start, end)
    return {
        "revenue": revenue,
        "completed_orders": completed,
        "paid_orders": paid,
        "refund_orders": refunded,
        "refund_amount": _money(row.get("refund_amount")),
        "refund_rate": round(refunded / paid, 4) if paid else None,
        "aov": round(revenue / completed, 2) if completed else None,
        "new_customers": new_customers,
    }


async def new_customer_count(start: date, end: date) -> int:
    rows = await execute_query(
        f"""
        SELECT COUNT(*) AS cnt FROM (
            SELECT user_id, MIN(order_time) AS first_paid
            FROM orders
            WHERE merchant_id = %s AND {PAID_STATUS_SQL}
            GROUP BY user_id
            HAVING first_paid >= %s AND first_paid < %s
        ) t
        """,
        (settings.MERCHANT_ID, start.isoformat(), end.isoformat()),
    )
    return _int(rows[0]["cnt"]) if rows else 0


async def daily_sales(start: date, end: date) -> list[dict]:
    rows = await execute_query(
        f"""
        SELECT DATE(order_time) AS day,
               COALESCE(SUM(CASE WHEN {COMPLETED_STATUS_SQL} THEN amount ELSE 0 END), 0) AS revenue,
               SUM(CASE WHEN {COMPLETED_STATUS_SQL} THEN 1 ELSE 0 END) AS completed_orders,
               SUM(CASE WHEN {PAID_STATUS_SQL} THEN 1 ELSE 0 END) AS paid_orders
        FROM orders
        WHERE merchant_id = %s
          AND order_time >= %s AND order_time < %s
        GROUP BY DATE(order_time)
        ORDER BY day
        """,
        (settings.MERCHANT_ID, start.isoformat(), end.isoformat()),
    )
    return [
        {
            "date": str(row["day"]),
            "revenue": _money(row.get("revenue")),
            "completed_orders": _int(row.get("completed_orders")),
            "paid_orders": _int(row.get("paid_orders")),
        }
        for row in rows
    ]


async def dish_top(start: date, end: date, limit: int = 10) -> list[dict]:
    rows = await execute_query(
        f"""
        SELECT CASE WHEN od.dish_id IS NULL THEN 'setmeal' ELSE 'dish' END AS item_type,
               COALESCE(od.dish_id, od.setmeal_id) AS item_id,
               od.name,
               SUM(od.number) AS qty,
               SUM(od.amount * od.number) AS amount
        FROM order_detail od
        JOIN orders o ON o.id = od.order_id
        WHERE o.merchant_id = %s
          AND o.status = 5
          AND o.order_time >= %s AND o.order_time < %s
          AND COALESCE(od.dish_id, od.setmeal_id) IS NOT NULL
        GROUP BY item_type, item_id, od.name
        ORDER BY amount DESC
        LIMIT %s
        """,
        (settings.MERCHANT_ID, start.isoformat(), end.isoformat(), int(limit)),
    )
    return [
        {
            "item_type": row["item_type"],
            "item_id": str(row["item_id"]),
            "name": row["name"],
            "qty": _int(row.get("qty")),
            "amount": _money(row.get("amount")),
        }
        for row in rows
    ]


async def refund_trend(start: date, end: date) -> list[dict]:
    """退款近似：整单金额 + COALESCE(cancel_time, order_time)。"""
    rows = await execute_query(
        f"""
        SELECT DATE(COALESCE(cancel_time, order_time)) AS day,
               COALESCE(SUM(amount), 0) AS amount,
               COUNT(*) AS orders
        FROM orders
        WHERE merchant_id = %s
          AND {REFUND_STATUS_SQL}
          AND COALESCE(cancel_time, order_time) >= %s
          AND COALESCE(cancel_time, order_time) < %s
        GROUP BY day
        ORDER BY day
        """,
        (settings.MERCHANT_ID, start.isoformat(), end.isoformat()),
    )
    return [
        {
            "date": str(row["day"]),
            "amount": _money(row.get("amount")),
            "orders": _int(row.get("orders")),
        }
        for row in rows
    ]


async def heatmap(start: date, end: date) -> list[dict]:
    rows = await execute_query(
        f"""
        SELECT WEEKDAY(order_time) + 1 AS weekday,
               HOUR(order_time) AS hour,
               COUNT(*) AS orders
        FROM orders
        WHERE merchant_id = %s
          AND {COMPLETED_STATUS_SQL}
          AND order_time >= %s AND order_time < %s
        GROUP BY weekday, hour
        """,
        (settings.MERCHANT_ID, start.isoformat(), end.isoformat()),
    )
    return [
        {"weekday": _int(row["weekday"]), "hour": _int(row["hour"]), "orders": _int(row["orders"])}
        for row in rows
    ]


def fill_days(rows: Iterable[dict], start: date, end: date) -> list[dict]:
    by_day = {row["date"]: row for row in rows}
    out = []
    day = start
    while day < end:
        key = day.isoformat()
        row = by_day.get(key)
        out.append({
            "date": key,
            "revenue": row["revenue"] if row else 0.0,
            "completed_orders": row["completed_orders"] if row else 0,
            "paid_orders": row["paid_orders"] if row else 0,
        })
        day += timedelta(days=1)
    return out


def fill_refund_days(rows: Iterable[dict], start: date, end: date) -> list[dict]:
    by_day = {row["date"]: row for row in rows}
    out = []
    day = start
    while day < end:
        key = day.isoformat()
        row = by_day.get(key)
        out.append({
            "date": key,
            "amount": row["amount"] if row else 0.0,
            "orders": row["orders"] if row else 0,
        })
        day += timedelta(days=1)
    return out


def fill_heatmap(rows: Iterable[dict]) -> list[dict]:
    by_cell = {(row["weekday"], row["hour"]): row["orders"] for row in rows}
    cells = []
    for weekday in range(1, 8):
        for hour in range(24):
            cells.append({
                "weekday": weekday,
                "hour": hour,
                "orders": by_cell.get((weekday, hour), 0),
            })
    return cells


def previous_period(start: date, end: date) -> tuple[date, date]:
    length = (end - start).days
    return start - timedelta(days=length), start


def sales_drops(days: list[dict], min_paid: int = 10, min_rate: float = -0.15,
                min_amount: float = 500) -> list[dict]:
    drafts = []
    for prev, cur in zip(days, days[1:]):
        if cur["paid_orders"] < min_paid or prev["revenue"] <= 0:
            continue
        diff = cur["revenue"] - prev["revenue"]
        rate = diff / prev["revenue"]
        if diff > -min_amount or rate > min_rate:
            continue
        drafts.append({
            "type": "sales_drop",
            "severity": "critical" if rate <= -0.30 else "warning",
            "date": cur["date"],
            "title": f"{cur['date'][5:]} 销售额环比 {rate * 100:.1f}%",
            "detail": f"当日完成订单 {cur['completed_orders']} 笔，营业额较前一日减少 ¥{abs(diff):.2f}",
            "selection": {"date": cur["date"]},
        })
    return drafts


def refund_spikes(days: list[dict], refunds: list[dict]) -> list[dict]:
    """近 8 日中，退款率达到 8% 或达到前 7 日中位数 2 倍的日期。"""
    refund_by_day = {row["date"]: row for row in refunds}
    rates: list[Optional[float]] = []
    for row in days:
        paid = int(row.get("paid_orders") or 0)
        refunded = int((refund_by_day.get(row["date"]) or {}).get("orders") or 0)
        rates.append(round(refunded / paid, 4) if paid else None)

    events = []
    for index in range(7, len(days)):
        current = rates[index]
        if current is None:
            continue
        prior = [rate for rate in rates[index - 7:index] if rate is not None]
        mid = median(prior)
        over_fixed = current >= 0.08
        over_median = mid is not None and mid > 0 and current >= mid * 2
        if not over_fixed and not over_median:
            continue
        day = days[index]["date"]
        refund = refund_by_day.get(day) or {}
        events.append({
            "type": "refund_spike",
            "severity": "warning",
            "date": day,
            "title": (
                f"{day[5:]} 退款率 {current * 100:.1f}%，超过 8%"
                if over_fixed else
                f"{day[5:]} 退款率是近 7 日中位数的 {current / mid:.1f} 倍"
            ),
            "detail": (
                f"退款金额 ¥{float(refund.get('amount') or 0):.2f}，"
                f"退款订单 {int(refund.get('orders') or 0)} 笔；历史退款原因未记录"
            ),
            "selection": {"date": day},
        })
    return events[-2:]


async def refund_spike_events(period: Period) -> list[dict]:
    today = date.today()
    end = min(period.end, today)
    start = end - timedelta(days=15)
    if start >= end:
        return []
    days = fill_days(await daily_sales(start, end), start, end)
    refunds = fill_refund_days(await refund_trend(start, end), start, end)
    return refund_spikes(days, refunds)


def median(values: list[float]) -> Optional[float]:
    if not values:
        return None
    ordered = sorted(values)
    middle = len(ordered) // 2
    if len(ordered) % 2:
        return ordered[middle]
    return (ordered[middle - 1] + ordered[middle]) / 2


async def anomaly_summary(period: Period) -> list[dict]:
    """只分析完整日：窗口截止到 min(period.end, today)。"""
    today = date.today()
    end = min(period.end, today)
    start = end - timedelta(days=8)
    if start >= end:
        return []
    days = fill_days(await daily_sales(start, end), start, end)
    return sales_drops(days)
