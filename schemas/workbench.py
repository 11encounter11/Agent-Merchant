"""工作台 API 契约（Python 侧）。"""

from __future__ import annotations

from typing import Any, Literal, Optional

from pydantic import BaseModel, Field

RangeKey = Literal["yesterday", "last7", "last30", "this_week", "this_month"]
WidgetId = Literal[
    "kpi_cards",
    "sales_trend",
    "dish_top10",
    "refund_trend",
    "order_heatmap",
]
MetricKey = Literal[
    "revenue",
    "orders",
    "aov",
    "refund_rate",
    "refund_amount",
    "new_customers",
    "dish_sales",
    "order_heatmap",
]
ChartType = Literal["line", "bar", "pie", "heatmap", "table", "kpi"]
Cadence = Literal["daily", "weekly", "manual"]


class WidgetContext(BaseModel):
    """前端只允许提交选中键，不允许提交图表数值。"""

    widget_id: str = Field(..., max_length=32)
    snapshot_id: Optional[str] = Field(default=None, max_length=64)
    selection: dict[str, Any] = Field(default_factory=dict)
    range_key: Optional[str] = Field(default=None, max_length=16)
    title: Optional[str] = Field(default=None, max_length=64)


class PreferenceCreate(BaseModel):
    metric: MetricKey
    chart_type: ChartType = "line"
    cadence: Cadence = "daily"
    range_key: RangeKey = "yesterday"
    title: Optional[str] = Field(default=None, max_length=64)


class PreferenceItem(BaseModel):
    id: int
    metric: str
    chart_type: str
    cadence: str
    range_key: str
    title: str
    active: bool = True
    created_at: str = ""
    updated_at: str = ""


class PreferenceListResponse(BaseModel):
    preferences: list[PreferenceItem]
    total: int


class RuleFeedItem(BaseModel):
    rule_id: str
    title: str
    section: str = ""
    category: str = ""
    effective_date: str = ""
    status: str = "active"
    source: str = ""
    demo: bool = False
    snippet: str = ""


class RuleSearchItem(RuleFeedItem):
    score: float = 0


class RuleSearchResponse(BaseModel):
    items: list[RuleSearchItem] = Field(default_factory=list)
    total: int = 0
    page: int = 1
    size: int = 20


class RuleDetailResponse(RuleFeedItem):
    content: str = ""


class RuleCategoryItem(BaseModel):
    key: str
    label: str
    count: int = 0


class RuleCategoriesResponse(BaseModel):
    categories: list[RuleCategoryItem] = Field(default_factory=list)


class CalendarItem(BaseModel):
    name: str
    date: str
    type: str = ""
    impact: str = ""
    text: str = ""


class ActivityItem(BaseModel):
    activity_key: str
    title: str
    start_date: str
    end_date: str
    status: str = "active"
    description: str = ""
    source: str = ""


class RuleFeedResponse(BaseModel):
    status: Literal["ok", "empty"]
    reason: str = ""
    rules: list[RuleFeedItem] = Field(default_factory=list)
    activities: list[ActivityItem] = Field(default_factory=list)
    activity_status: Literal["ok", "empty"] = "empty"
    calendar: list[CalendarItem] = Field(default_factory=list)
    unavailable: list[dict] = Field(default_factory=list)
