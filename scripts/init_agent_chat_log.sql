-- Agent 对话日志表
-- 可手动执行：mysql -u root -p sky_take_out < scripts/init_agent_chat_log.sql
-- 服务启动时也会 ensure_chat_log_table() 自动建表

CREATE TABLE IF NOT EXISTS agent_chat_log (
    id            BIGINT PRIMARY KEY AUTO_INCREMENT,
    session_id    VARCHAR(64)  NOT NULL,
    thread_id     VARCHAR(64)  NULL,
    role          VARCHAR(16)  NOT NULL COMMENT 'human|ai',
    content       MEDIUMTEXT   NOT NULL,
    token_total   INT          NOT NULL DEFAULT 0,
    created_at    DATETIME     NOT NULL DEFAULT CURRENT_TIMESTAMP,
    -- 适合：按会话拉历史
    INDEX idx_session_created (session_id, created_at),
    -- 适合：按时间清理 / 统计
    INDEX idx_created (created_at)
    -- 不适合：对 content 建普通 BTree 整列索引（大文本、写入成本高）
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
COMMENT='Agent 对话日志';
