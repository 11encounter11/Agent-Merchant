"""看板区间：完整日、半开区间、最近数据回退。"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, timedelta
from typing import Optional

RANGE_LABELS = {
    "yesterday": "昨日",
    "last7": "近 7 日",
    "last30": "近 30 日",
    "this_week": "本周",
    "this_month": "本月",
}

VALID_RANGES = frozenset(RANGE_LABELS)


@dataclass(frozen=True)
class Period:
    key: str
    label: str
    start: date
    end: date  # exclusive
    requested_start: date
    requested_end: date
    latest_data_date: Optional[date] = None
    fallback_reason: str = ""

    @property
    def days(self) -> int:
        return (self.end - self.start).days

    @property
    def gap(self) -> bool:
        """请求窗口是否有数据；回退时仍以 requested 判断。"""
        return self.fallback_reason == "NO_DATA_IN_REQUESTED_WINDOW"

    def to_dict(self) -> dict:
        return {
            "key": self.key,
            "label": self.label,
            "start": self.start.isoformat(),
            "end": self.end.isoformat(),
            "effective_start": self.start.isoformat(),
            "effective_end": self.end.isoformat(),
            "requested_start": self.requested_start.isoformat(),
            "requested_end": self.requested_end.isoformat(),
            "latest_data_date": self.latest_data_date.isoformat() if self.latest_data_date else None,
            "fallback_reason": self.fallback_reason or None,
            "gap": self.gap,
        }


def normalize_range(range_key: Optional[str]) -> str:
    key = (range_key or "yesterday").strip()
    if key not in VALID_RANGES:
        raise ValueError(f"不支持的区间: {key}；可选 {sorted(VALID_RANGES)}")
    return key


def requested_period(range_key: str, today: Optional[date] = None) -> Period:
    """返回请求区间；end 为开区间，所有区间只包含完整日/本周至今。"""
    key = normalize_range(range_key)
    today = today or date.today()

    if key == "yesterday":
        start, end = today - timedelta(days=1), today
    elif key == "last7":
        start, end = today - timedelta(days=7), today
    elif key == "last30":
        start, end = today - timedelta(days=30), today
    elif key == "this_week":
        start, end = today - timedelta(days=today.weekday()), today + timedelta(days=1)
    else:  # this_month
        start, end = today.replace(day=1), today + timedelta(days=1)

    return Period(
        key=key,
        label=RANGE_LABELS[key],
        start=start,
        end=end,
        requested_start=start,
        requested_end=end,
    )


def with_fallback(
    requested: Period,
    latest_data_date: Optional[date],
    *,
    has_data: bool,
    fallback_days: int = 7,
) -> Period:
    """请求窗口无支付订单时，回退到最近 N 个完整日；不伪造数据。"""
    if has_data or latest_data_date is None:
        return Period(
            key=requested.key,
            label=requested.label,
            start=requested.start,
            end=requested.end,
            requested_start=requested.requested_start,
            requested_end=requested.requested_end,
            latest_data_date=latest_data_date,
            fallback_reason="" if latest_data_date else "NO_DATA_AT_ALL",
        )

    end = latest_data_date + timedelta(days=1)
    start = end - timedelta(days=fallback_days)
    return Period(
        key=requested.key,
        label=requested.label,
        start=start,
        end=end,
        requested_start=requested.requested_start,
        requested_end=requested.requested_end,
        latest_data_date=latest_data_date,
        fallback_reason="NO_DATA_IN_REQUESTED_WINDOW",
    )
