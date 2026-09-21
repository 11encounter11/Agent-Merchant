-- B6a 商家数据隔离迁移（04 §2 A7；执行前请先备份）
-- 幂等性：MySQL 不支持 ADD COLUMN IF NOT EXISTS（8.0 亦不支持），重复执行会报 Duplicate column，
-- 属预期——报 Duplicate 即表示已迁移过，可忽略。

-- 1) 经营数据根表：orders（11 个工具的所有查询都以 orders 为锚点，过滤此表即全覆盖）
ALTER TABLE orders
    ADD COLUMN merchant_id BIGINT NOT NULL DEFAULT 1 COMMENT '商家ID（Agent 数据隔离）';

-- 存量行由 DEFAULT 1 自动回填；为查询加复合索引
ALTER TABLE orders
    ADD INDEX idx_merchant_time (merchant_id, order_time);

-- 2) Agent 对话日志：补商家维度
ALTER TABLE agent_chat_log
    ADD COLUMN merchant_id BIGINT NOT NULL DEFAULT 1 COMMENT '商家ID';

-- 验证：
--   SHOW COLUMNS FROM orders LIKE 'merchant_id';
--   SELECT merchant_id, COUNT(*) FROM orders GROUP BY merchant_id;
