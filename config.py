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

    # ================================================================
    # LLM 配置（支持多模型切换）
    # ================================================================
    LLM_API_KEY: str = ""
    LLM_BASE_URL: str = "https://open.bigmodel.cn/api/paas/v4/"
    LLM_MODEL: str = "GLM-4.7-Flash"
    # 简单意图（greeting/thanks/知识）用的小模型；空则与 LLM_MODEL 相同
    LLM_MODEL_SIMPLE: str = ""
    LLM_TEMPERATURE: float = 0.7
    LLM_MODEL_ALIAS: str = "智谱 GLM-4.7-Flash"
    # 路由不准（置信度低于阈值）时回退大模型
    LLM_ROUTE_FALLBACK_TO_LARGE: bool = True
    LLM_ROUTE_CONFIDENCE_MIN: float = 0.5
    # False：LLM HTTP 不走系统/环境代理（智谱等国内接口被 Clash 劫持时会 SSL EOF）
    # 若模型必须走代理才能访问，设为 true
    LLM_HTTP_TRUST_ENV: bool = False

    # ================================================================
    # Embedding 配置（用于 RAG 知识库向量化）
    # ================================================================
    EMBEDDING_API_KEY: str = ""
    EMBEDDING_BASE_URL: str = "https://dashscope.aliyuncs.com/compatible-mode/v1"
    EMBEDDING_MODEL: str = "text-embedding-v3"
    # 短 JSON 不切；超过该字数才切片
    RAG_CHUNK_SIZE: int = 500
    RAG_CHUNK_OVERLAP: int = 50
    RAG_TOP_K: int = 3

    # ================================================================
    # MySQL 数据库（苍穹外卖 sky_take_out）
    # ================================================================
    DB_HOST: str = "localhost"
    DB_PORT: int = 3306
    DB_USER: str = "root"
    DB_PASSWORD: str = "123456"
    DB_NAME: str = "sky_take_out"

    # ================================================================
    # Java 后端（苍穹外卖 Spring Boot）
    # ================================================================
    JAVA_BACKEND_URL: str = "http://localhost:8080"
    JAVA_ADMIN_USER: str = "admin"
    JAVA_ADMIN_PASSWORD: str = "123456"

    # ================================================================
    # 天气 API（和风天气 https://dev.qweather.com）
    # ================================================================
    WEATHER_API_KEY: str = ""
    WEATHER_API_URL: str = "https://devapi.qweather.com/v7"
    WEATHER_DEFAULT_CITY: str = "101040100"

    # ================================================================
    # 会话与记忆
    # ================================================================
    MAX_HISTORY: int = 20
    ENABLE_LLM_CACHE: bool = False

    # ================================================================
    # 分析阈值
    # ================================================================
    ANOMALY_THRESHOLD: float = 0.2
    CORRELATION_SIGNIFICANT: float = 0.5
    FORECAST_CONFIDENCE: float = 0.8

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
    # 安全（注入拦截 / 工具门禁）
    # ================================================================
    SECURITY_INJECTION_ENABLED: bool = True

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


settings = Settings()
