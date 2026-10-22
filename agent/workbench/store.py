"""工作台本地存储：偏好与快照。

为什么不用 MySQL：Java 平台只读。本模块只写 agent-service 自己的 data/ 目录，
不建表、不改现有 schema；单实例部署足够，后续需要多实例再换 Redis/自有库。
"""

from __future__ import annotations

import json
import logging
import os
import tempfile
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)

# Windows 的 Python 常缺 tzdata；看板时区固定 +08:00，避免启动期依赖
TZ = timezone(timedelta(hours=8))
DATA_DIR = Path(__file__).resolve().parents[2] / "data" / "workbench"
PREFS_FILE = DATA_DIR / "preferences.json"
SNAP_DIR = DATA_DIR / "snapshots"
SNAPSHOT_TTL_MINUTES = 30
SNAPSHOT_KEEP_HOURS = 24


def _ensure_dirs() -> None:
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    SNAP_DIR.mkdir(parents=True, exist_ok=True)


def _read_json(path: Path, default):
    if not path.exists():
        return default
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception as e:
        logger.warning(f"[Store] 读取失败 {path.name}: {e}")
        return default


def _atomic_write(path: Path, payload) -> None:
    _ensure_dirs()
    fd, tmp = tempfile.mkstemp(prefix=path.name, suffix=".tmp", dir=str(path.parent))
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            json.dump(payload, handle, ensure_ascii=False, indent=2, default=str)
        os.replace(tmp, path)
    finally:
        if os.path.exists(tmp):
            os.remove(tmp)


def load_preferences(merchant_id: int) -> list[dict]:
    payload = _read_json(PREFS_FILE, {"version": 1, "items": []})
    items = payload.get("items", []) if isinstance(payload, dict) else []
    return [
        item for item in items
        if int(item.get("merchant_id", 0)) == int(merchant_id) and item.get("active", True)
    ]


def upsert_preference(merchant_id: int, item: dict) -> dict:
    payload = _read_json(PREFS_FILE, {"version": 1, "items": []})
    items = payload.get("items", []) if isinstance(payload, dict) else []
    now = datetime.now(TZ).isoformat(timespec="seconds")
    existing = next(
        (row for row in items
         if int(row.get("merchant_id", 0)) == int(merchant_id)
         and row.get("metric") == item["metric"]
         and row.get("cadence") == item["cadence"]),
        None,
    )
    if existing:
        existing.update({
            "chart_type": item["chart_type"],
            "range_key": item["range_key"],
            "title": item["title"],
            "active": True,
            "updated_at": now,
        })
        saved = existing
    else:
        next_id = max((int(row.get("id", 0)) for row in items), default=0) + 1
        saved = {
            "id": next_id,
            "merchant_id": int(merchant_id),
            "metric": item["metric"],
            "chart_type": item["chart_type"],
            "cadence": item["cadence"],
            "range_key": item["range_key"],
            "title": item["title"],
            "active": True,
            "created_at": now,
            "updated_at": now,
        }
        items.append(saved)
    _atomic_write(PREFS_FILE, {"version": 1, "items": items})
    return saved


def delete_preference(merchant_id: int, preference_id: int) -> bool:
    payload = _read_json(PREFS_FILE, {"version": 1, "items": []})
    items = payload.get("items", []) if isinstance(payload, dict) else []
    kept = [
        row for row in items
        if not (int(row.get("merchant_id", 0)) == int(merchant_id)
                and int(row.get("id", 0)) == int(preference_id))
    ]
    if len(kept) == len(items):
        return False
    _atomic_write(PREFS_FILE, {"version": 1, "items": kept})
    return True


def delete_by_metric(merchant_id: int, metric: str, cadence: str) -> int:
    payload = _read_json(PREFS_FILE, {"version": 1, "items": []})
    items = payload.get("items", []) if isinstance(payload, dict) else []
    kept = [
        row for row in items
        if not (int(row.get("merchant_id", 0)) == int(merchant_id)
                and row.get("metric") == metric and row.get("cadence") == cadence)
    ]
    removed = len(items) - len(kept)
    if removed:
        _atomic_write(PREFS_FILE, {"version": 1, "items": kept})
    return removed


def save_snapshot(snapshot_id: str, merchant_id: int, plan: dict) -> bool:
    _ensure_dirs()
    now = datetime.now(TZ)
    payload = {
        "snapshot_id": snapshot_id,
        "merchant_id": int(merchant_id),
        "created_at": now.isoformat(timespec="seconds"),
        "expires_at": (now + timedelta(minutes=SNAPSHOT_TTL_MINUTES)).isoformat(timespec="seconds"),
        "plan": plan,
    }
    try:
        _atomic_write(SNAP_DIR / f"{snapshot_id}.json", payload)
    except Exception as e:
        logger.warning(f"[Store] 快照写入失败 {snapshot_id}: {e}")
        return False
    _prune_snapshots(now)
    return True


def load_snapshot(snapshot_id: str, merchant_id: int) -> Optional[dict]:
    if not snapshot_id:
        return None
    path = SNAP_DIR / f"{snapshot_id}.json"
    payload = _read_json(path, None)
    if not isinstance(payload, dict):
        return None
    if int(payload.get("merchant_id", 0)) != int(merchant_id):
        return None
    try:
        expires = datetime.fromisoformat(str(payload.get("expires_at")))
    except ValueError:
        return None
    if expires <= datetime.now(TZ):
        try:
            path.unlink(missing_ok=True)
        except OSError:
            pass
        return None
    return payload.get("plan")


def _prune_snapshots(now: datetime) -> None:
    if not SNAP_DIR.exists():
        return
    cutoff = now - timedelta(hours=SNAPSHOT_KEEP_HOURS)
    for path in SNAP_DIR.glob("dash_*.json"):
        try:
            if datetime.fromtimestamp(path.stat().st_mtime, TZ) < cutoff:
                path.unlink(missing_ok=True)
        except OSError:
            continue
