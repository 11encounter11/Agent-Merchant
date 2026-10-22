"""看板快照：图表与对话之间的权威桥。"""

from __future__ import annotations

import logging
from typing import Optional

from config import settings

from . import store

logger = logging.getLogger(__name__)

TTL_MINUTES = store.SNAPSHOT_TTL_MINUTES
MAX_BYTES = 256 * 1024


async def save_snapshot(snapshot_id: str, plan: dict) -> bool:
    import asyncio
    import json

    payload = json.dumps(plan, ensure_ascii=False, default=str)
    if len(payload.encode("utf-8")) > MAX_BYTES:
        logger.warning(f"[Snapshot] 跳过写入：超过 {MAX_BYTES} bytes snapshot={snapshot_id}")
        return False
    return await asyncio.to_thread(
        store.save_snapshot, snapshot_id, settings.MERCHANT_ID, plan
    )


async def get_snapshot(snapshot_id: str) -> Optional[dict]:
    import asyncio

    return await asyncio.to_thread(
        store.load_snapshot, snapshot_id, settings.MERCHANT_ID
    )
