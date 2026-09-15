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
    LLM_TEMPERATURE: float = 0.7
    LLM_MODEL_ALIAS: str = "智谱 GLM-4.7-Flash"

    # ================================================================
    # Embedding 配置（用于 RAG 知识库向量化）
    # ================================================================
    EMBEDDING_API_KEY: str = ""
    EMBEDDING_BASE_URL: str = "https://dashscope.aliyuncs.com/compatible-mode/v1"
    EMBEDDING_MODEL: str = "text-embedding-v3"

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
    # 工程护栏（面经阶段 1：防死循环 / 预算 / 工具稳健性）
    # ================================================================
    MAX_TOOL_STEPS: int = 4
    TOKEN_BUDGET: int = 12000
    TOOL_TIMEOUT_SEC: float = 20.0
    TOOL_MAX_RETRIES: int = 2
    IDEMPOTENCY_TTL_SEC: int = 600

    # ================================================================
    # Supervisor（面经阶段 2）
    # ================================================================
    MAX_SUPERVISOR_ROUNDS: int = 6

    class Config:
        env_file = ".env"
        env_file_encoding = "utf-8"


settings = Settings()
