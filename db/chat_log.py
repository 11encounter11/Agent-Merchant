"""
对话日志表 agent_chat_log

索引设计：
- 适合：INDEX(session_id, created_at) —— 按会话拉历史
- 适合：INDEX(created_at) —— 按时间清理/统计
- 不适合：对 content（MEDIUMTEXT）建整列索引 —— 体积大、区分度用途弱、写入成本高
  若要做全文检索，用 FULLTEXT 或外部搜索，而不是普通 BTree 索引整段正文
"""

from __future__ import annotations

import logging

from config import settings
from db.database import execute_write

logger = logging.getLogger(__name__)

CREATE_SQL = """
CREATE TABLE IF NOT EXISTS agent_chat_log (
    id            BIGINT PRIMARY KEY AUTO_INCREMENT,
    merchant_id   BIGINT       NOT NULL DEFAULT 1 COMMENT '商家ID（数据隔离）',
    session_id    VARCHAR(64)  NOT NULL,
    thread_id     VARCHAR(64)  NULL,
    role          VARCHAR(16)  NOT NULL COMMENT 'human|ai',
    content       MEDIUMTEXT   NOT NULL,
    token_total   INT          NOT NULL DEFAULT 0,
    created_at    DATETIME     NOT NULL DEFAULT CURRENT_TIMESTAMP,
    INDEX idx_session_created (session_id, created_at),
    INDEX idx_merchant_created (merchant_id, created_at),
    INDEX idx_created (created_at)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
COMMENT='Agent 对话日志';
"""


async def ensure_chat_log_table() -> bool:
    """启动时建表；失败则关闭本功能（不影响主流程）。"""
    if not settings.CHAT_LOG_ENABLED:
        return False
    try:
        await execute_write(CREATE_SQL)
        logger.info("[ChatLog] agent_chat_log 表已就绪")
        return True
    except Exception as e:
        logger.warning(f"[ChatLog] 建表失败，将跳过落库: {e}")
        return False


async def append_chat_log(
    *,
    session_id: str,
    role: str,
    content: str,
    thread_id: str = "",
    token_total: int = 0,
) -> None:
    if not settings.CHAT_LOG_ENABLED:
        return
    if not content or not str(content).strip():
        return
    sql = """
        INSERT INTO agent_chat_log (merchant_id, session_id, thread_id, role, content, token_total)
        VALUES (%s, %s, %s, %s, %s, %s)
    """
    try:
        await execute_write(
            sql,
            (
                settings.MERCHANT_ID,
                session_id,
                thread_id or None,
                role,
                str(content),
                int(token_total or 0),
            ),
        )
    except Exception as e:
        logger.warning(f"[ChatLog] 写入失败（已忽略）: {e}")
