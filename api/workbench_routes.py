"""AI 工作台 API：看板计划、偏好、规则 feed。"""

from __future__ import annotations

import logging

from fastapi import APIRouter, Depends, HTTPException, Path, Query

from api.routes import require_auth
from db.database import DBUnavailable
from schemas.workbench import (
    PreferenceCreate,
    PreferenceListResponse,
    RuleCategoriesResponse,
    RuleDetailResponse,
    RuleFeedResponse,
    RuleSearchItem,
    RuleSearchResponse,
)
from agent.workbench import planner, preferences, rule_rag, rules

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/workbench", tags=["workbench"])


def _http_error(status: int, detail: str, code: str) -> HTTPException:
    return HTTPException(status_code=status, detail=detail, headers={"X-Error-Code": code})


@router.get("/dashboard")
async def dashboard(
    range_key: str = Query("yesterday", alias="range"),
    refresh: bool = Query(False),
    _auth: None = Depends(require_auth),
):
    try:
        return await planner.build_dashboard(range_key=range_key, refresh=refresh)
    except ValueError as e:
        raise _http_error(400, str(e), "INVALID_ARGUMENT")
    except DBUnavailable as e:
        logger.warning(f"[Workbench] 数据库不可用: {e}")
        raise _http_error(503, "数据库暂不可用，不是没有数据", "DB_UNAVAILABLE")
    except Exception as e:
        logger.exception(f"[Workbench] 看板生成失败: {e}")
        raise _http_error(500, "看板生成失败，请稍后重试", "INTERNAL_ERROR")


@router.get("/preferences", response_model=PreferenceListResponse)
async def list_preferences(_auth: None = Depends(require_auth)):
    try:
        items = await preferences.list_preferences()
        return PreferenceListResponse(preferences=items, total=len(items))
    except DBUnavailable as e:
        raise _http_error(503, f"数据库暂不可用: {e}", "DB_UNAVAILABLE")


@router.post("/preferences")
async def create_preference(payload: PreferenceCreate, _auth: None = Depends(require_auth)):
    try:
        saved = await preferences.save_preference(
            metric=payload.metric,
            chart_type=payload.chart_type,
            cadence=payload.cadence,
            range_key=payload.range_key,
            title=payload.title,
        )
        return {"success": True, "preference": saved}
    except DBUnavailable as e:
        raise _http_error(503, f"数据库暂不可用: {e}", "DB_UNAVAILABLE")


@router.delete("/preferences/{preference_id}")
async def delete_preference(
    preference_id: int = Path(..., ge=1),
    _auth: None = Depends(require_auth),
):
    try:
        deleted = await preferences.delete_preference(preference_id)
        return {"success": deleted}
    except DBUnavailable as e:
        raise _http_error(503, f"数据库暂不可用: {e}", "DB_UNAVAILABLE")


@router.get("/rules", response_model=RuleFeedResponse)
async def rules_feed(_auth: None = Depends(require_auth)):
    return rules.rule_feed()


@router.get("/rules/search", response_model=RuleSearchResponse)
async def search_rules(
    q: str = Query("", max_length=100),
    category: str = Query("", max_length=32),
    page: int = Query(1, ge=1),
    size: int = Query(20, ge=1, le=50),
    _auth: None = Depends(require_auth),
):
    hits = rule_rag.search_rules(q, top_k=None, category=category)
    start = (page - 1) * size
    items = [
        RuleSearchItem(
            rule_id=hit["rule_id"],
            title=hit["title"],
            section=hit["section"],
            category=hit.get("category", ""),
            effective_date=hit["effective_date"],
            status=hit["status"],
            source=hit["source"],
            demo=hit["demo"],
            snippet=hit.get("preview", ""),
            score=hit.get("score", 0),
        )
        for hit in hits[start:start + size]
    ]
    return RuleSearchResponse(items=items, total=len(hits), page=page, size=size)


@router.get("/rules/categories", response_model=RuleCategoriesResponse)
async def rule_categories(_auth: None = Depends(require_auth)):
    return RuleCategoriesResponse(categories=rule_rag.rule_categories())


@router.get("/rules/{rule_id}", response_model=RuleDetailResponse)
async def rule_detail(
    rule_id: str = Path(..., pattern=r"^[a-z0-9-]{1,64}$"),
    section: str = Query("", max_length=16),
    _auth: None = Depends(require_auth),
):
    items = rule_rag.get_rule_sections(rule_id)
    if not items:
        raise _http_error(404, "规则不存在", "RULE_NOT_FOUND")
    item = next((row for row in items if row["section"] == section), items[0]) if section else items[0]
    return RuleDetailResponse(
        rule_id=item["rule_id"],
        title=item["title"],
        section=item["section"],
        category=item.get("category", ""),
        effective_date=item["effective_date"],
        status=item["status"],
        source=item["source"],
        demo=item["demo"],
        snippet=item.get("snippet", ""),
        content=item.get("content", ""),
    )
