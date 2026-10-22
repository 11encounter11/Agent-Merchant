"""可视化偏好：持久化 + 自然语言意图解析。

用户在对话框说“以后每天给我看退款趋势”，这里做确定性解析并落库；
不依赖 LLM 是否记得调用工具，也不接受用户自定义 SQL/字段。
"""

from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass
from typing import Optional

from config import settings

from . import store

logger = logging.getLogger(__name__)

METRIC_WIDGET = {
    "revenue": "sales_trend",
    "orders": "kpi_cards",
    "aov": "kpi_cards",
    "new_customers": "kpi_cards",
    "refund_rate": "refund_trend",
    "refund_amount": "refund_trend",
    "dish_sales": "dish_top10",
    "order_heatmap": "order_heatmap",
}

METRIC_TITLE = {
    "revenue": "销售额",
    "orders": "订单量",
    "aov": "客单价",
    "new_customers": "新客",
    "refund_rate": "退款率",
    "refund_amount": "退款金额",
    "dish_sales": "菜品销量",
    "order_heatmap": "时段热力",
}

CADENCE_LABEL = {"daily": "每日", "weekly": "每周", "manual": "手动"}
DEFAULT_CHART = {
    "dish_sales": "bar",
    "order_heatmap": "heatmap",
    "orders": "bar",
    "new_customers": "bar",
    "refund_rate": "line",
    "refund_amount": "line",
}

ACTION_WORDS = ("以后", "下次", "每次", "推送", "固定", "自动", "帮我设置", "加一个", "加个", "放进看板", "添加到看板")
REMOVE_WORDS = ("取消", "删除", "去掉", "不要", "移除")
CADENCE_WORDS = {"每周": "weekly", "每星期": "weekly", "每天": "daily", "每日": "daily"}
RANGE_WORDS = (
    ("昨天", "yesterday"), ("昨日", "yesterday"),
    ("近7", "last7"), ("近 7", "last7"), ("一周", "last7"), ("最近7", "last7"),
    ("近30", "last30"), ("近 30", "last30"), ("一个月", "last30"), ("最近30", "last30"),
    ("本周", "this_week"), ("这周", "this_week"), ("本月", "this_month"), ("这个月", "this_month"),
)


@dataclass
class PreferenceIntent:
    action: str  # add|remove|help
    metric: Optional[str] = None
    chart_type: str = "line"
    cadence: str = "daily"
    range_key: str = "yesterday"
    title: str = ""
    reply: str = ""


def _detect_metric(text: str) -> Optional[str]:
    # 先匹配更具体的词，避免“退款金额”被“退款率”抢走
    if "退款金额" in text:
        return "refund_amount"
    if "退款" in text or "退单" in text:
        return "refund_rate"
    if "菜品" in text or "销量" in text or "top" in text.lower():
        return "dish_sales"
    if "时段" in text or "热力" in text or "高峰" in text:
        return "order_heatmap"
    if "客单价" in text:
        return "aov"
    if "新客" in text or "新用户" in text:
        return "new_customers"
    if "订单" in text:
        return "orders"
    if "营业额" in text or "销售额" in text or "营收" in text or "销售" in text:
        return "revenue"
    return None


def _detect_chart(text: str, metric: str) -> str:
    if "折线" in text:
        return "line"
    if "柱" in text or "条形" in text:
        return "bar"
    if "饼" in text:
        return "pie"
    if "热力" in text:
        return "heatmap"
    if "表格" in text:
        return "table"
    if "卡片" in text or "数字" in text:
        return "kpi"
    return DEFAULT_CHART.get(metric, "line")


def _detect_range(text: str) -> str:
    for word, key in RANGE_WORDS:
        if word in text:
            return key
    return "yesterday"


def _detect_cadence(text: str) -> str:
    for word, cadence in CADENCE_WORDS.items():
        if word in text:
            return cadence
    return "daily"


def detect_preference_intent(text: str) -> Optional[PreferenceIntent]:
    """只拦截“设置/取消未来推送”的话术，普通问数不拦截。"""
    raw = (text or "").strip()
    if not raw:
        return None

    has_action = any(word in raw for word in ACTION_WORDS)
    is_remove = any(word in raw for word in REMOVE_WORDS)
    # “取消订单怎么处理”“以后退款规则”不是偏好设置，必须同时出现看板/推送语境
    pref_context = any(word in raw for word in (
        "看板", "推送", "偏好", "图", "每天", "每日", "每周", "下次", "每次",
        "固定", "自动", "加一个", "加个", "放进", "帮我设置",
    ))
    if (not has_action and not is_remove) or not pref_context:
        return None

    metric = _detect_metric(raw)
    if metric is None:
        if "看板" in raw or "推送" in raw or "图" in raw:
            return PreferenceIntent(
                action="help",
                reply=(
                    "可以。请告诉我固定哪个指标（销售额/订单量/客单价/退款率/菜品销量/时段热力），"
                    "以及图型（折线/柱状/饼图/热力/表格）。例如：以后每天给我看退款趋势，用折线图。"
                ),
            )
        return None

    cadence = _detect_cadence(raw)
    if is_remove:
        title = f"{METRIC_TITLE[metric]}（{cadence}）"
        return PreferenceIntent(
            action="remove",
            metric=metric,
            cadence=cadence,
            title=title,
            reply=f"已取消「{title}」的自动看板偏好。",
        )

    chart_type = _detect_chart(raw, metric)
    range_key = _detect_range(raw)
    title = f"{METRIC_TITLE[metric]}·{cadence == 'weekly' and '每周' or '每日'}"
    return PreferenceIntent(
        action="add",
        metric=metric,
        chart_type=chart_type,
        cadence=cadence,
        range_key=range_key,
        title=title,
        reply=(
            f"已记住：{title}（{range_key}，{chart_type}）。"
            "下次打开工作台会自动按这个偏好编排看板。"
        ),
    )


async def list_preferences() -> list[dict]:
    return await asyncio.to_thread(store.load_preferences, settings.MERCHANT_ID)


async def save_preference(
    metric: str,
    chart_type: str = "line",
    cadence: str = "daily",
    range_key: str = "yesterday",
    title: Optional[str] = None,
) -> dict:
    title = (title or f"{METRIC_TITLE.get(metric, metric)}·{CADENCE_LABEL.get(cadence, cadence)}")[:64]
    item = {
        "metric": metric,
        "chart_type": chart_type,
        "cadence": cadence,
        "range_key": range_key,
        "title": title,
    }
    return await asyncio.to_thread(
        store.upsert_preference, settings.MERCHANT_ID, item
    )


async def delete_preference(preference_id: int) -> bool:
    return await asyncio.to_thread(
        store.delete_preference, settings.MERCHANT_ID, int(preference_id)
    )


async def delete_by_metric(metric: str, cadence: str = "daily") -> int:
    return await asyncio.to_thread(
        store.delete_by_metric, settings.MERCHANT_ID, metric, cadence
    )


async def apply_preference_intent(intent: PreferenceIntent) -> tuple[str, Optional[dict]]:
    """执行解析结果；DB 失败不影响对话主链路，只返回可读提示。"""
    if intent.action == "help" or not intent.metric:
        return intent.reply, None
    try:
        if intent.action == "remove":
            await delete_by_metric(intent.metric, intent.cadence)
            return intent.reply, None
        saved = await save_preference(
            metric=intent.metric,
            chart_type=intent.chart_type,
            cadence=intent.cadence,
            range_key=intent.range_key,
            title=intent.title,
        )
        return intent.reply, saved
    except Exception as e:
        logger.warning(f"[Preference] 保存/删除失败: {e}")
        return "偏好暂未保存（数据库不可用），请稍后重试。", None


def preferred_widgets(preferences: list[dict]) -> list[str]:
    widgets = []
    for pref in preferences:
        widget = METRIC_WIDGET.get(pref.get("metric"))
        if widget and widget not in widgets:
            widgets.append(widget)
    return widgets
