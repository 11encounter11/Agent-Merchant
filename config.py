"""
配置管理（Pydantic Settings）

优先级：环境变量 > .env > 默认值
所有可配置的参数集中在这里，不要在代码里硬编码任何密钥、URL 或阈值。
"""

from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    # ================================================================
    # 应用配置
    # ================================================================
    APP_NAME: str = "苍穹外卖-商家智能经营顾问"
    APP_HOST: str = "0.0.0.0"
    APP_PORT: int = 8100
    # dev | prod。prod 下「鉴权配置缺失」= 拒绝服务，而不是放行（fail-closed）
    APP_ENV: str = "dev"
    # S5 单一真值：/health、FastAPI 元信息、README 都以此为准
    APP_VERSION: str = "0.4.0"

    # ================================================================
    # LLM 配置（支持多模型切换）
    # ================================================================
    LLM_API_KEY: str = ""
    LLM_BASE_URL: str = "https://api.deepseek.com"
    LLM_MODEL: str = "deepseek-flash"
    # 简单意图（greeting/thanks/知识）用的小模型；空则与 LLM_MODEL 相同
    LLM_MODEL_SIMPLE: str = ""
    LLM_TEMPERATURE: float = 0.7
    # 路由不准（置信度低于阈值）时回退大模型
    LLM_ROUTE_FALLBACK_TO_LARGE: bool = True
    LLM_ROUTE_CONFIDENCE_MIN: float = 0.5
    # False：LLM HTTP 不走系统/环境代理（智谱等国内接口被 Clash 劫持时会 SSL EOF）
    # 若模型必须走代理才能访问，设为 true
    LLM_HTTP_TRUST_ENV: bool = False
    # R9 单一真值：LLM HTTP 超时（总/连接）
    LLM_TIMEOUT_SEC: float = 60.0
    LLM_CONNECT_TIMEOUT_SEC: float = 20.0

    # ================================================================
    # Embedding 配置（用于 RAG 知识库向量化；与 LLM 分属不同供应商）
    # ================================================================
    EMBEDDING_API_KEY: str = ""
    EMBEDDING_BASE_URL: str = "https://open.bigmodel.cn/api/paas/v4"
    # 智谱付费嵌入模型：默认 2048 维（可选 256/512/1024/2048），单请求上限 3072 token / 64 条
    EMBEDDING_MODEL: str = "embedding-3"
    # 短 JSON 不切；超过该字数才切片
    RAG_CHUNK_SIZE: int = 500
    RAG_CHUNK_OVERLAP: int = 50
    RAG_TOP_K: int = 3
    # 关键词命中不足时的向量补齐（数据类意图不补，避免知识命中污染分析上下文）
    RAG_VECTOR_BACKFILL: bool = True
    # 向量命中相似度下限（1/(1+距离)）；低于此值视为不相关，不注入 Prompt。
    # 0.52 为实测校准值（智谱 embedding-3 + 27 条语料）：向量腿正例 top1 ≥0.544，
    # 最强负例 0.4952 → 取窗口中点。降到 0.45 会让负例污染，升到 0.55 开始丢召回。
    RAG_VECTOR_MIN_SCORE: float = 0.52
    # 持久化向量库目录（chromadb PersistentClient）：避免每次重启重新 embedding
    RAG_VECTOR_INDEX_PATH: str = "data/chroma"
    # 启动预热：把「加载知识 + 建索引」从首个用户请求挪到服务启动
    RAG_VECTOR_PRELOAD: bool = True

    # ================================================================
    # MySQL 数据库（苍穹外卖 sky_take_out）
    # ================================================================
    # 口令不得写入源码：必须在 .env / 环境变量提供，未配置时启动告警、查数工具不可用
    DB_HOST: str = "localhost"
    DB_PORT: int = 3306
    DB_USER: str = "root"
    DB_PASSWORD: str = ""
    DB_NAME: str = "sky_take_out"
    # B6a 数据隔离：所有经营数据查询强制过滤该商家 ID（需先执行 scripts/migrate_add_merchant_id.sql）
    MERCHANT_ID: int = 1

    # ================================================================
    # 天气 API（和风天气 https://dev.qweather.com）
    # ================================================================
    WEATHER_API_KEY: str = ""
    WEATHER_API_URL: str = "https://devapi.qweather.com/v7"
    WEATHER_DEFAULT_CITY: str = "101040100"
    WEATHER_TIMEOUT_SEC: float = 10.0

    # ================================================================
    # 会话与记忆
    # ================================================================
    MAX_HISTORY: int = 20

    # ================================================================
    # 分析阈值（R9：算法阈值以配置为准，工具不再硬编码）
    # ================================================================
    # 异常检测 Z-score 阈值（|Z| 超过即视为异常突变点）
    ANOMALY_THRESHOLD: float = 2.0
    # 相关性 |r| 中等相关/弱相关分界（>0.7 恒为强相关）
    CORRELATION_SIGNIFICANT: float = 0.5
    # S4 单一真值：数据库无成本字段时的估算成本率（cost_profit/menu/promotion 共用）
    COST_RATIO_DEFAULT: float = 0.35

    # ================================================================
    # 工程护栏（防死循环 / 预算 / 工具稳健性）
    # ================================================================
    MAX_TOOL_STEPS: int = 4
    TOKEN_BUDGET: int = 12000
    TOOL_TIMEOUT_SEC: float = 20.0
    TOOL_MAX_RETRIES: int = 2
    IDEMPOTENCY_TTL_SEC: int = 600

    # ================================================================
    # Supervisor
    # ================================================================
    MAX_SUPERVISOR_ROUNDS: int = 6

    # ================================================================
    # Checkpointer
    # backend: memory | sqlite
    # ================================================================
    CHECKPOINT_BACKEND: str = "sqlite"
    CHECKPOINT_SQLITE_PATH: str = "data/checkpoints.sqlite"
    # 演示断点：设为 tools 时，工具执行后暂停，可用同 thread_id 续跑
    CHECKPOINT_INTERRUPT_AFTER: str = ""
    # R9：续跑/跳过卡住节点的防御性循环上限
    CHECKPOINT_MAX_SKIP: int = 20

    # ================================================================
    # Redis / 限流 / 对话日志
    # ================================================================
    REDIS_ENABLED: bool = True
    REDIS_URL: str = "redis://localhost:6379/0"
    REDIS_SESSION_TTL_SEC: int = 86400
    RATE_LIMIT_ENABLED: bool = True
    RATE_LIMIT_PER_MINUTE: int = 30
    CHAT_LOG_ENABLED: bool = True

    # ================================================================
    # SSE
    # ================================================================
    # 心跳间隔（秒）：工具阶段没有字节下发时发 `: ping` 注释帧，
    # 防止反向代理/网关按「连接空闲」掐断长连接
    SSE_HEARTBEAT_SEC: float = 15.0

    # ================================================================
    # 安全（注入拦截 / 工具门禁 / API 鉴权 / CORS）
    # ================================================================
    SECURITY_INJECTION_ENABLED: bool = True
    # 非空时 /api/* 必须带 Authorization: Bearer <token>；空=开发模式（启动告警）
    AGENT_API_TOKEN: str = ""
    # CORS 白名单（逗号分隔）；禁止使用 *
    CORS_ORIGINS: str = "http://localhost:8888,http://127.0.0.1:8888"
    # 仅当部署在可信反向代理后才置 true：允许采信 x-forwarded-for 取客户端 IP
    TRUST_PROXY_HEADERS: bool = False

    # ================================================================
    # Langfuse（观测：Callback 挂到图运行配置，不改节点）
    # ================================================================
    LANGFUSE_ENABLED: bool = True
    LANGFUSE_PUBLIC_KEY: str = ""
    LANGFUSE_SECRET_KEY: str = ""
    LANGFUSE_BASE_URL: str = "https://cloud.langfuse.com"

    class Config:
        env_file = ".env"
        env_file_encoding = "utf-8"
        # .env 遗留的已删除配置项（如 JAVA_*）忽略而非报错，保证配置演进不炸启动
        extra = "ignore"


settings = Settings()
