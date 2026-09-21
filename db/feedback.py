"""
对话反馈表 agent_feedback（B6d 反馈闭环）

点赞/点踩 + 纠错评论落库；写失败静默降级（与 chat_log 同策略），不影响主链路。
后续可导出差评样本进入 eval 回归集（03 加分项 1 的闭环目标）。
"""

from __future__ import annotations

import logging

from config import settings
from db.database import execute_write

logger = logging.getLogger(__name__)

CREATE_SQL = """
CREATE TABLE IF NOT EXISTS agent_feedback (
    id          BIGINT PRIMARY KEY AUTO_INCREMENT,
    merchant_id BIGINT       NOT NULL DEFAULT 1 COMMENT '商家ID',
    session_id  VARCHAR(64)  NOT NULL,
    thread_id   VARCHAR(64)  NULL,
    rating      VARCHAR(8)   NOT NULL COMMENT 'up|down',
    comment     VARCHAR(500) NULL,
    created_at  DATETIME     NOT NULL DEFAULT CURRENT_TIMESTAMP,
    INDEX idx_session_created (session_id, created_at),
    INDEX idx_rating_created (rating, created_at)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
COMMENT='Agent 对话反馈';
"""


async def ensure_feedback_table() -> bool:
    if not settings.CHAT_LOG_ENABLED:
        return False
    try:
        await execute_write(CREATE_SQL)
        logger.info("[Feedback] agent_feedback 表已就绪")
        return True
    except Exception as e:
        logger.warning(f"[Feedback] 建表失败，反馈功能降级: {e}")
        return False


async def append_feedback(
    *,
    session_id: str,
    rating: str,
    thread_id: str = "",
    comment: str = "",
) -> bool:
    if not settings.CHAT_LOG_ENABLED:
        return False
    sql = """
        INSERT INTO agent_feedback (merchant_id, session_id, thread_id, rating, comment)
        VALUES (%s, %s, %s, %s, %s)
    """
    try:
        await execute_write(
            sql,
            (
                settings.MERCHANT_ID,
                session_id,
                thread_id or None,
                rating,
                (comment or "")[:500] or None,
            ),
        )
        return True
    except Exception as e:
        logger.warning(f"[Feedback] 写入失败（已忽略）: {e}")
        return False
