"""平台规则/日历 feed。

只有 `agent/knowledge/rules/*.json` 中的真实条款才作为规则展示；
没有文件就返回空态，不生成条款号。活动没有数据源，固定 unavailable。
"""

from __future__ import annotations

import json
import logging
from datetime import date
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

AGENT_DIR = Path(__file__).resolve().parents[1]
RULES_DIR = AGENT_DIR / "knowledge" / "rules"
ACTIVITIES_DIR = AGENT_DIR / "knowledge" / "activities"
HOLIDAYS_PATH = AGENT_DIR / "knowledge" / "data" / "holidays.json"

REQUIRED_RULE_FIELDS = ("rule_key", "title", "section", "effective_date", "content")


def _snippet(text: str, limit: int = 160) -> str:
    clean = " ".join(str(text or "").split())
    return clean[:limit]


def load_rules() -> list[dict]:
    if not RULES_DIR.exists():
        return []
    items: list[dict] = []
    for path in sorted(RULES_DIR.glob("*.json")):
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except Exception as e:
            logger.warning(f"[Rules] 读取失败 {path.name}: {e}")
            continue
        rows = payload if isinstance(payload, list) else payload.get("rules", [])
        for row in rows:
            if not isinstance(row, dict):
                continue
            missing = [key for key in REQUIRED_RULE_FIELDS if not str(row.get(key) or "").strip()]
            if missing:
                logger.warning(f"[Rules] 跳过缺字段 {path.name}: {missing}")
                continue
            if str(row.get("status", "active")).lower() != "active":
                continue
            items.append({
                "rule_id": str(row["rule_key"]),
                "title": str(row["title"]),
                "section": str(row["section"]),
                "effective_date": str(row["effective_date"]),
                "status": "active",
                "source": str(row.get("source") or path.stem),
                "category": str(row.get("category") or "未分类"),
                "demo": bool(row.get("demo")),
                "keywords": [str(word) for word in (row.get("keywords") or [])],
                "content": str(row["content"]),
                "snippet": _snippet(row.get("content")),
            })
    return items


def _parse_month_day(value: str) -> tuple[int, int] | None:
    try:
        month, day = str(value).split("-")[-2:]
        return int(month), int(day)
    except Exception:
        return None


def load_calendar(limit: int = 5) -> list[dict]:
    if not HOLIDAYS_PATH.exists():
        return []
    try:
        payload = json.loads(HOLIDAYS_PATH.read_text(encoding="utf-8"))
    except Exception as e:
        logger.warning(f"[Rules] 日历读取失败: {e}")
        return []
    today = date.today()
    items = []
    for row in payload if isinstance(payload, list) else []:
        parsed = _parse_month_day(str(row.get("date") or ""))
        if not parsed:
            continue
        month, day = parsed
        try:
            when = date(today.year, month, day)
            if when < today:
                when = date(today.year + 1, month, day)
        except ValueError:
            continue
        items.append({
            "name": str(row.get("name") or ""),
            "date": when.isoformat(),
            "type": str(row.get("type") or ""),
            "impact": str(row.get("impact") or ""),
            "text": str(row.get("text") or ""),
        })
    items.sort(key=lambda item: item["date"])
    return items[:limit]


def load_activities() -> list[dict]:
    """平台活动：目录文件存在即自动展示；没有文件就是空态，不造假。"""
    if not ACTIVITIES_DIR.exists():
        return []
    today = date.today()
    items: list[dict] = []
    for path in sorted(ACTIVITIES_DIR.glob("*.json")):
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except Exception as e:
            logger.warning(f"[Activities] 读取失败 {path.name}: {e}")
            continue
        rows = payload if isinstance(payload, list) else [payload]
        for row in rows:
            if not isinstance(row, dict):
                continue
            if not all(str(row.get(key) or "").strip() for key in ("activity_key", "title", "start_date", "end_date")):
                logger.warning(f"[Activities] 跳过缺字段 {path.name}")
                continue
            if str(row.get("status", "active")).lower() != "active":
                continue
            try:
                end = date.fromisoformat(str(row["end_date"]))
            except ValueError:
                continue
            if end < today:
                continue
            items.append({
                "activity_key": str(row["activity_key"]),
                "title": str(row["title"]),
                "start_date": str(row["start_date"]),
                "end_date": str(row["end_date"]),
                "status": "active",
                "description": _snippet(row.get("description"), 200),
                "source": str(row.get("source") or path.stem),
            })
    return items


def rule_feed() -> dict:
    rules = load_rules()
    activities = load_activities()
    calendar = load_calendar()
    unavailable = []
    if not activities:
        unavailable.append({
            "key": "platform_activity",
            "reason": "NO_ACTIVITY_FEED",
            "message": "活动目录为空；平台导出活动 JSON 后会自动展示",
        })
    if not rules:
        unavailable.append({
            "key": "formal_rule_corpus",
            "reason": "RULE_CORPUS_MISSING",
            "message": "规则库未收录；请导入含 rule_key/section/effective_date 的真实条款",
        })
    return {
        "status": "ok" if rules else "empty",
        "reason": "" if rules else "RULE_CORPUS_MISSING",
        "rules": rules,
        "activities": activities,
        "activity_status": "ok" if activities else "empty",
        "calendar": calendar,
        "unavailable": unavailable,
    }
