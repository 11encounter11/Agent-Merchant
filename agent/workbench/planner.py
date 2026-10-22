"""看板编排器：把只读指标编排成 AI 看板计划。"""

from __future__ import annotations

import asyncio
import hashlib
import json
import logging
from datetime import date, datetime, timedelta, timezone
from typing import Any, Optional

from config import settings
from db.database import DBUnavailable

from . import data
from .period import Period, normalize_range
from .preferences import list_preferences, preferred_widgets
from .snapshot import get_snapshot, save_snapshot

logger = logging.getLogger(__name__)

TZ = timezone(timedelta(hours=8))
PLAN_VERSION = "1"
CONTRACT_VERSION = "1"

WIDGETS = {
    "kpi_cards": {
        "title": "经营 KPI",
        "chart_type": "kpi",
        "metric": "revenue",
        "selection_keys": ["metric"],
        "layout": "full",
        "unit": "mixed",
        "grain": "range",
    },
    "sales_trend": {
        "title": "销售额趋势",
        "chart_type": "line",
        "metric": "revenue",
        "selection_keys": ["date"],
        "layout": "wide",
        "unit": "CNY",
        "grain": "day",
    },
    "dish_top10": {
        "title": "菜品 / 套餐 Top10",
        "chart_type": "bar",
        "metric": "dish_sales",
        "selection_keys": ["item_type", "item_id"],
        "layout": "half",
        "unit": "CNY",
        "grain": "range",
    },
    "refund_trend": {
        "title": "退款趋势",
        "chart_type": "line",
        "metric": "refund_amount",
        "selection_keys": ["date"],
        "layout": "half",
        "unit": "CNY",
        "grain": "day",
    },
    "order_heatmap": {
        "title": "时段热力",
        "chart_type": "heatmap",
        "metric": "order_heatmap",
        "selection_keys": ["weekday", "hour"],
        "layout": "half",
        "unit": "order",
        "grain": "weekday_hour",
    },
}

DEFAULT_EXTRA = ["sales_trend", "dish_top10", "refund_trend", "order_heatmap"]

UNAVAILABLE = [
    {"key": "channel_filter", "reason": "NO_DATA_COLUMN", "message": "现有订单表没有渠道字段"},
    {"key": "review_widget", "reason": "NO_DATA_TABLE", "message": "评价与评分数据未接入"},
    {"key": "platform_activity", "reason": "NO_DATA_TABLE", "message": "平台没有活动表/活动 API"},
    {"key": "delivery_area", "reason": "NO_COORDINATES", "message": "地址没有经纬度，无法绘制配送地图"},
    {"key": "cost_margin", "reason": "NO_COST_COLUMN", "message": "菜品/套餐没有成本列，无法计算毛利"},
    {"key": "store_dimension", "reason": "NO_STORE_COLUMN", "message": "订单表无 store_id，当前为商家级看板"},
]


def _change(cur: Optional[float], prev: Optional[float]) -> Optional[float]:
    if cur is None or prev in (None, 0):
        return None
    return round((float(cur) - float(prev)) / float(prev), 4)


def _card(key: str, label: str, value: Any, unit: str, previous: Any, metric: str) -> dict:
    return {
        "key": key,
        "label": label,
        "value": value,
        "unit": unit,
        "previous": previous,
        "change_rate": _change(value, previous),
        "metric": metric,
    }


async def _safe(coro, label: str, errors: list[dict]):
    try:
        return await coro
    except DBUnavailable:
        raise
    except Exception as e:
        logger.warning(f"[Planner] {label} 查询失败: {e}")
        errors.append({"key": label, "message": "查询失败"})
        return None


def _kpi_data(current: Optional[dict], previous: Optional[dict]) -> Optional[dict]:
    if not current:
        return None
    cards = [
        _card("revenue", "营业额", current.get("revenue"), "CNY",
              previous.get("revenue") if previous else None, "completed_net_revenue"),
        _card("orders", "完成订单", current.get("completed_orders"), "order",
              previous.get("completed_orders") if previous else None, "completed_order_count"),
        _card("aov", "客单价", current.get("aov"), "CNY",
              previous.get("aov") if previous else None, "average_order_value"),
        _card("refund_rate", "退款率", current.get("refund_rate"), "ratio",
              previous.get("refund_rate") if previous else None, "refund_rate"),
        _card("new_customers", "新客", current.get("new_customers"), "user",
              previous.get("new_customers") if previous else None, "new_customer_count"),
    ]
    return {"cards": cards}


def _sales_data(period: Period, rows: Optional[list[dict]], prev_rows: Optional[list[dict]],
                prev_kpi: Optional[dict], anomalies: Optional[list[dict]]) -> Optional[dict]:
    if rows is None:
        return None
    days = data.fill_days(rows, period.start, period.end)
    comparison = None
    if prev_rows and prev_kpi and (prev_kpi.get("paid_orders") or 0) > 0:
        prev_days = data.fill_days(prev_rows, period.start - timedelta(days=period.days), period.start)
        comparison = {
            "dates": [row["date"] for row in prev_days],
            "values": [row["revenue"] for row in prev_days],
        }
    return {
        "dates": [row["date"] for row in days],
        "values": [row["revenue"] for row in days],
        "orders": [row["completed_orders"] for row in days],
        "comparison": comparison,
        "anomaly_dates": [item["date"] for item in (anomalies or [])],
    }


def _refund_data(period: Period, rows: Optional[list[dict]]) -> Optional[dict]:
    if rows is None:
        return None
    days = data.fill_refund_days(rows, period.start, period.end)
    return {
        "dates": [row["date"] for row in days],
        "amounts": [row["amount"] for row in days],
        "orders": [row["orders"] for row in days],
        "approximation": True,
        "note": "整单金额近似；日期按取消时间，历史无退款明细表",
    }


def _heatmap_data(rows: Optional[list[dict]]) -> Optional[dict]:
    if rows is None:
        return None
    cells = data.fill_heatmap(rows)
    return {
        "weekday_labels": ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"],
        "cells": cells,
        "max": max((cell["orders"] for cell in cells), default=0),
    }


def _ai_brief(period: Period, kpi: Optional[dict], dish: Optional[list[dict]],
              previous: Optional[dict], anomalies: list[dict]) -> dict:
    lines = []
    if period.fallback_reason == "NO_DATA_IN_REQUESTED_WINDOW":
        lines.append(
            f"请求的「{period.label}」没有支付订单；最近有数据的一天是 "
            f"{period.latest_data_date}，已自动改为展示最近 {period.days} 个完整日。"
        )
    elif period.fallback_reason == "NO_DATA_AT_ALL":
        lines.append("平台目前没有经营数据，暂不做经营结论。")
    elif not kpi:
        lines.append("核心指标查询失败，暂不生成经营结论。")
    elif not kpi.get("paid_orders"):
        lines.append("所选区间没有支付订单，暂不做经营结论。")
    else:
        lines.append(
            f"{period.start} 至 {period.end - timedelta(days=1)}：营业额 "
            f"¥{kpi.get('revenue', 0):,.2f}，完成 {kpi.get('completed_orders', 0)} 单，"
            f"退款率 {((kpi.get('refund_rate') or 0) * 100):.1f}%。"
        )
        if previous and previous.get("paid_orders"):
            change = _change(kpi.get("revenue"), previous.get("revenue"))
            if change is not None:
                direction = "上升" if change >= 0 else "下降"
                lines.append(f"营业额较前一等长区间{direction} {abs(change) * 100:.1f}%。")
        if dish:
            top = dish[0]
            lines.append(f"销售额第一是「{top['name']}」（¥{top['amount']:,.2f}）。")
    if kpi and kpi.get("refund_orders"):
        lines.append("退款数据为整单金额近似，因为平台没有退款明细表。")

    questions = []
    if anomalies:
        questions.append(f"为什么 {anomalies[0]['date']} 销售额下降？哪些菜拖累？")
    if dish:
        questions.append(f"为什么「{dish[0]['name']}」卖得最好？")
    questions.append("退款率正常吗？平台退款规则怎么规定？")
    questions.append("下周应该重点推哪些菜？")
    return {
        "generated_by": "rule",
        "text": " ".join(lines),
        "suggested_questions": questions[:3],
    }


def _snapshot_id(period: Period, widget_ids: list[str], preferences: list[dict]) -> str:
    raw = "|".join([
        str(settings.MERCHANT_ID), PLAN_VERSION, period.key, period.start.isoformat(),
        period.end.isoformat(), ",".join(widget_ids),
        ",".join(f"{p['metric']}:{p['chart_type']}:{p['cadence']}" for p in preferences),
    ])
    return "dash_" + hashlib.sha256(raw.encode("utf-8")).hexdigest()[:20]


async def build_dashboard(range_key: str = "yesterday", refresh: bool = False) -> dict:
    normalized = normalize_range(range_key)
    period = await data.resolve_effective_period(normalized)
    prefs = []
    try:
        prefs = await list_preferences()
    except DBUnavailable:
        raise
    except Exception as e:
        logger.warning(f"[Planner] 偏好读取失败，按默认看板: {e}")

    preferred = preferred_widgets(prefs)
    widget_ids = ["kpi_cards"]
    for widget in preferred + DEFAULT_EXTRA:
        if widget not in widget_ids:
            widget_ids.append(widget)

    snapshot_id = _snapshot_id(period, widget_ids, prefs)
    if not refresh:
        cached = await get_snapshot(snapshot_id)
        if cached and cached.get("plan_version") == PLAN_VERSION:
            cached["reused"] = True
            cached["contract_version"] = CONTRACT_VERSION
            logger.info(f"[Planner] 复用快照 snapshot={snapshot_id}")
            return cached

    prev_start, prev_end = data.previous_period(period.start, period.end)
    errors: list[dict] = []
    tasks = {
        "kpi": data.kpi_summary(period.start, period.end),
        "prev_kpi": data.kpi_summary(prev_start, prev_end),
        "sales": data.daily_sales(period.start, period.end),
        "prev_sales": data.daily_sales(prev_start, prev_end),
        "dish": data.dish_top(period.start, period.end),
        "refunds": data.refund_trend(period.start, period.end),
        "heatmap": data.heatmap(period.start, period.end),
        "anomaly": data.anomaly_summary(period),
        "refund_spikes": data.refund_spike_events(period),
    }
    results = await asyncio.gather(
        *(_safe(coro, name, errors) for name, coro in tasks.items()),
        return_exceptions=False,
    )
    result = dict(zip(tasks.keys(), results))
    if all(value is None for value in result.values()):
        raise DBUnavailable("看板全部查询失败")

    kpi = result["kpi"]
    previous = result["prev_kpi"] if (result["prev_kpi"] or {}).get("paid_orders") else None
    anomalies = list(result["anomaly"] or []) + list(result["refund_spikes"] or [])
    anomalies.sort(key=lambda item: 0 if item.get("severity") == "critical" else 1)
    generated_at = datetime.now(TZ).isoformat(timespec="seconds")

    widget_data = {
        "kpi_cards": _kpi_data(kpi, previous),
        "sales_trend": _sales_data(period, result["sales"], result["prev_sales"], previous, anomalies),
        "dish_top10": {"items": result["dish"] or []} if result["dish"] is not None else None,
        "refund_trend": _refund_data(period, result["refunds"]),
        "order_heatmap": _heatmap_data(result["heatmap"]),
    }
    notes = {
        "refund_trend": "整单金额近似，按取消时间归日",
        "order_heatmap": "按完成订单补满 7×24 格",
        "dish_top10": "销售额按 od.amount × number 计算，含套餐",
    }
    widgets = []
    for widget_id in widget_ids:
        definition = WIDGETS[widget_id]
        item = {
            "widget_id": widget_id,
            "title": definition["title"],
            "chart_type": definition["chart_type"],
            "metric": definition["metric"],
            "snapshot_id": snapshot_id,
            "selection_keys": definition["selection_keys"],
            "layout": definition["layout"],
            "data": widget_data.get(widget_id),
            "meta": {
                "unit": definition["unit"],
                "grain": definition["grain"],
                "note": notes.get(widget_id, ""),
            },
        }
        if item["data"] is None:
            item["error"] = "查询失败"
        widgets.append(item)

    data_status = period.to_dict()
    data_status.update({
        "refund_approximation": True,
        "store_dimension": False,
        "data_as_of": generated_at,
        "gap": period.gap or not kpi or not (kpi.get("paid_orders") or 0),
    })
    plan = {
        "snapshot_id": snapshot_id,
        "generated_at": generated_at,
        "plan_version": PLAN_VERSION,
        "contract_version": CONTRACT_VERSION,
        "reused": False,
        "range": {
            "key": period.key,
            "label": period.label,
            "start": period.start.isoformat(),
            "end": period.end.isoformat(),
        },
        "data_status": data_status,
        "ai_brief": _ai_brief(period, kpi, result["dish"], previous, anomalies),
        "widgets": widgets,
        "anomalies": anomalies,
        "preferences_applied": [
            {"metric": p["metric"], "chart_type": p["chart_type"], "cadence": p["cadence"]}
            for p in prefs
        ],
        "unavailable": UNAVAILABLE,
        "partial": bool(errors),
        "errors": errors,
    }
    await save_snapshot(snapshot_id, plan)
    logger.info(
        f"[Planner] dashboard merchant={settings.MERCHANT_ID} range={period.key} "
        f"effective={period.start}..{period.end} fallback={period.fallback_reason or '-'} "
        f"widgets={len(widgets)} partial={bool(errors)}")
    return plan


ALLOWED_SELECTION = {
    "kpi_cards": {"metric"},
    "sales_trend": {"date"},
    "dish_top10": {"item_type", "item_id"},
    "refund_trend": {"date"},
    "order_heatmap": {"weekday", "hour"},
}


def _sanitize_selection(widget_id: str, selection: dict) -> dict:
    allowed = ALLOWED_SELECTION.get(widget_id, set())
    clean = {}
    for key, value in (selection or {}).items():
        if key not in allowed:
            continue
        text = str(value).strip()[:48]
        if not text:
            continue
        if key == "date":
            try:
                date.fromisoformat(text)
            except ValueError:
                continue
        elif key == "item_type":
            if text not in {"dish", "setmeal"}:
                continue
        elif key == "item_id":
            if not text.isdigit():
                continue
        elif key == "weekday":
            if not text.isdigit() or not 1 <= int(text) <= 7:
                continue
        elif key == "hour":
            if not text.isdigit() or not 0 <= int(text) <= 23:
                continue
        clean[key] = text
    return clean


def _money_text(value: Any) -> str:
    try:
        return f"¥{float(value):,.2f}"
    except (TypeError, ValueError):
        return "—"


def _revenue_attribution(cards: list[dict]) -> Optional[dict]:
    """营业额变化 = 订单数效应 + 客单价效应 + 交叉效应（服务端确定性计算）。"""
    by_key = {card.get("key"): card for card in cards}
    revenue, orders, aov = by_key.get("revenue"), by_key.get("orders"), by_key.get("aov")
    if not (revenue and orders and aov):
        return None
    try:
        r0, r1 = float(revenue.get("previous")), float(revenue.get("value"))
        n0, n1 = float(orders.get("previous")), float(orders.get("value"))
    except (TypeError, ValueError):
        return None
    if n0 <= 0 or n1 <= 0:
        return None
    a0, a1 = r0 / n0, r1 / n1
    order_effect = (n1 - n0) * a0
    aov_effect = (a1 - a0) * n0
    cross_effect = (n1 - n0) * (a1 - a0)
    total = order_effect + aov_effect + cross_effect
    if total == 0:
        return None
    parts = [
        ("订单数效应", order_effect),
        ("客单价效应", aov_effect),
        ("交叉效应", cross_effect),
    ]
    return {
        "parts": parts,
        "total": total,
        "shares": [(name, value / total) for name, value in parts],
        "top": max(parts, key=lambda item: abs(item[1]))[0],
    }


def _selection_facts(widget: dict, selection: dict) -> list[str]:
    """只保留本次选中项的关键事实，由系统置顶，禁止模型转写。"""
    data = widget.get("data") or {}
    widget_id = widget.get("widget_id")
    if widget_id == "kpi_cards":
        selected = str(selection.get("metric") or "")
        for card in (data.get("cards") or []):
            if card.get("key") != selected:
                continue
            unit = card.get("unit")
            value = card.get("value")
            previous = card.get("previous")
            if unit == "ratio":
                current_text = f"{float(value) * 100:.2f}%" if value is not None else "—"
                previous_text = f"{float(previous) * 100:.2f}%" if previous is not None else "—"
            elif unit == "CNY":
                current_text = _money_text(value)
                previous_text = _money_text(previous)
            else:
                current_text = "—" if value is None else str(value)
                previous_text = "—" if previous is None else str(previous)
            change = card.get("change_rate")
            change_text = f"{float(change) * 100:+.1f}%" if change is not None else "无对比"
            facts = [f"{card.get('label')}：本期 {current_text}；上期 {previous_text}；环比 {change_text}"]
            if selected == "revenue":
                attribution = _revenue_attribution(data.get("cards") or [])
                if attribution:
                    parts = "；".join(
                        f"{name} {_money_text(value)}（{share * 100:.0f}%）"
                        for (name, value), (_, share) in zip(attribution["parts"], attribution["shares"])
                    )
                    facts.append(f"营业额归因：{parts}")
            return facts
    if widget_id == "sales_trend":
        dates = data.get("dates") or []
        selected = selection.get("date")
        if selected in dates:
            index = dates.index(selected)
            orders = data.get("orders") or []
            return [f"{selected} 销售额 {_money_text((data.get('values') or [])[index])}；完成订单 {orders[index] if index < len(orders) else '—'} 单"]
    if widget_id == "refund_trend":
        dates = data.get("dates") or []
        selected = selection.get("date")
        if selected in dates:
            index = dates.index(selected)
            orders = data.get("orders") or []
            return [f"{selected} 退款 {_money_text((data.get('amounts') or [])[index])}；退款单 {orders[index] if index < len(orders) else '—'} 笔（整单近似）"]
    if widget_id == "dish_top10":
        for item in (data.get("items") or []):
            if str(item.get("item_id")) == str(selection.get("item_id")) and item.get("item_type") == selection.get("item_type"):
                return [f"{item.get('name')}：销售额 {_money_text(item.get('amount'))}；售出 {item.get('qty')} 份"]
    if widget_id == "order_heatmap":
        weekday = selection.get("weekday")
        hour = selection.get("hour")
        if weekday and hour is not None:
            for cell in (data.get("cells") or []):
                if str(cell.get("weekday")) == str(weekday) and str(cell.get("hour")) == str(hour):
                    return [f"weekday={weekday}，hour={hour}：完成订单 {cell.get('orders')} 单"]
    return []


def _widget_summary(widget: dict, selection: dict) -> list[str]:
    """从服务端快照提取少量权威数值，避免模型改用“今天”查数。"""
    data = widget.get("data") or {}
    widget_id = widget.get("widget_id")
    lines: list[str] = []
    if widget_id == "kpi_cards":
        def shown_value(value: Any, unit: str) -> str:
            if value is None:
                return "—"
            if unit == "ratio":
                return f"{float(value) * 100:.2f}%"
            if unit == "CNY":
                return _money_text(value)
            return str(value)

        for card in (data.get("cards") or []):
            unit = card.get("unit")
            value_text = shown_value(card.get("value"), unit)
            previous_text = shown_value(card.get("previous"), unit)
            change = card.get("change_rate")
            change_text = f"{float(change) * 100:+.1f}%" if change is not None else "无对比"
            lines.append(
                f"{card.get('label')}：本期 {value_text}；上期 {previous_text}；环比 {change_text}"
            )
    elif widget_id == "sales_trend":
        dates = data.get("dates") or []
        values = data.get("values") or []
        selected = selection.get("date")
        if selected in dates:
            index = dates.index(selected)
            lines.append(f"{selected} 销售额={_money_text(values[index])}，完成订单={data.get('orders', [])[index] if index < len(data.get('orders') or []) else '—'}")
        lines.append(f"区间总销售额={_money_text(sum(values))}，日均={_money_text(sum(values) / len(values)) if values else '—'}")
    elif widget_id == "refund_trend":
        dates = data.get("dates") or []
        amounts = data.get("amounts") or []
        selected = selection.get("date")
        if selected in dates:
            index = dates.index(selected)
            lines.append(f"{selected} 退款={_money_text(amounts[index])}，退款单={data.get('orders', [])[index] if index < len(data.get('orders') or []) else '—'}")
        lines.append(f"区间退款合计={_money_text(sum(amounts))}（整单近似）")
    elif widget_id == "dish_top10":
        for item in (data.get("items") or [])[:5]:
            marker = ""
            if str(item.get("item_id")) == str(selection.get("item_id")) and item.get("item_type") == selection.get("item_type"):
                marker = "（选中）"
            lines.append(f"{item.get('name')}{marker}：销售额 {_money_text(item.get('amount'))}，售出 {item.get('qty')} 份")
    elif widget_id == "order_heatmap":
        selected = selection
        cells = data.get("cells") or []
        if selected.get("weekday") and selected.get("hour") is not None:
            for cell in cells:
                if str(cell.get("weekday")) == str(selected["weekday"]) and str(cell.get("hour")) == str(selected["hour"]):
                    lines.append(f"选中时段（weekday={selected['weekday']}, hour={selected['hour']}）完成订单={cell.get('orders')} 单")
                    break
        lines.append(f"区间完成订单合计={sum(int(cell.get('orders') or 0) for cell in cells)} 单")
    return lines


async def validate_widget_context(context: Optional[dict]) -> dict:
    """把前端上下文变成可注入 Prompt 的安全摘要；不信任前端数值。"""
    if not context:
        return {"text": "", "verified": False}
    widget_id = str(context.get("widget_id") or "")
    if widget_id not in WIDGETS:
        return {"text": "", "verified": False}
    snapshot_id = str(context.get("snapshot_id") or "")
    selection = _sanitize_selection(widget_id, context.get("selection") or {})
    plan = await get_snapshot(snapshot_id) if snapshot_id else None
    verified = False
    period_start = period_end = ""
    facts: list[str] = []
    hint = ""
    if plan:
        match = next((w for w in plan.get("widgets", []) if w.get("widget_id") == widget_id), None)
        if match:
            verified = True
            status = plan.get("data_status") or {}
            period_start = str(status.get("effective_start") or "")
            period_end = str(status.get("effective_end") or "")
            facts = _selection_facts(match, selection)
            if widget_id == "kpi_cards" and selection.get("metric") == "revenue":
                attribution = _revenue_attribution((match.get("data") or {}).get("cards") or [])
                if attribution:
                    top = attribution["top"]
                    second = sorted(attribution["parts"], key=lambda item: abs(item[1]), reverse=True)[1][0]
                    hint = f"系统归因提示：{top}最大，{second}次之；不要把它说反。"
            hint = (hint + " 快照没有提供时段/菜品/天气等原因，不要编造；需要时说明“需进一步查数”。").strip()
    selection_text = "，".join(f"{k}={v}" for k, v in selection.items()) or "无"
    period_text = f"快照有效区间：{period_start} 至 {period_end}（开区间）；" if period_start else ""
    tool_rule = (
        f"如需调用数据工具，begin_date/end_date 必须使用 {period_start} 至 {period_end}，"
        "不要使用今天或模型自行猜测的日期。"
        if period_start else "快照不可用；如调用工具，请重新确认数据区间。"
    )
    text = (
        "[图表上下文]\n"
        f"用户从看板选择了「{WIDGETS[widget_id]['title']}」（{widget_id}）。"
        f"{period_text}选中：{selection_text}。"
        f"快照校验：{'通过' if verified else '未通过（快照不存在/已过期）'}。\n"
        "具体金额/百分比由服务端在开头置顶，正文不要再重复数字，只解释原因、影响和建议。\n"
        f"{hint}\n{tool_rule}\n"
        "请围绕该选择回答；不要假设或复述整张表。"
    )
    return {
        "text": text,
        "verified": verified,
        "widget_id": widget_id,
        "selection": selection,
        "snapshot_id": snapshot_id,
        "facts": "；".join(facts),
    }
