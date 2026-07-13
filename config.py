"""
============================================================
苍穹外卖 - 商家智能助手 Agent 配置文件
============================================================

【教学说明】这个文件是干什么的？
类比 Java 的 application.yml —— 把所有"会变的值"集中管理。
比如数据库密码、API Key、端口号，这些值换个环境就要改，
所以我们不把它们写死在代码里，而是放在配置文件中。

【教学说明】Pydantic Settings 是什么？
它是一个"配置读取器"。它会按以下优先级读取配置：
1. 环境变量（最高优先级）
2. .env 文件
3. 代码里写的默认值（最低优先级）

类比 Java 的 @ConfigurationProperties，
你在 yml 里写 server.port=8080，Spring 自动注入到代码里。
Pydantic Settings 也一样，在 .env 里写 DB_HOST=localhost，它自动读到代码里。
"""

from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    """
    所有配置项都写在这里。

    【教学说明】每个字段后面的 "= xxx" 是默认值。
    如果你在 .env 文件里写了同名的变量，就会覆盖默认值。
    """

    # ===================== 服务配置 =====================
    APP_NAME: str = "苍穹外卖-商家智能助手"   # 服务名称
    APP_HOST: str = "0.0.0.0"                # 监听地址，0.0.0.0 表示允许外部访问
    APP_PORT: int = 8100                      # 服务端口（8080被Java后端占了，8888被前端占了）

    # ===================== LLM 配置（通义千问 Qwen） =====================
    # 阿里云 DashScope API 兼容 OpenAI 格式，所以我们用 langchain-openai 来调用
    # 申请 API Key：https://dashscope.console.aliyun.com/apiKey
    LLM_API_KEY: str = ""                    # 你的 DashScope API Key（从 .env 读取）
    LLM_BASE_URL: str = "https://dashscope.aliyuncs.com/compatible-mode/v1"  # DashScope API 地址
    LLM_MODEL: str = "qwen-max"              # 模型名称（可选：qwen-max / qwen-plus / qwen-turbo）

    # ===================== MySQL 数据库配置 =====================
    # Agent 需要直接查数据库来获取经营数据
    DB_HOST: str = "localhost"               # 数据库地址
    DB_PORT: int = 3306                      # 数据库端口
    DB_USER: str = "root"                    # 数据库用户名
    DB_PASSWORD: str = "123456"              # 数据库密码（从 .env 读取）
    DB_NAME: str = "sky_take_out"            # 数据库名称

    # ===================== Java 后端 API 配置 =====================
    # Agent 需要调用 Java 后端的写操作接口（如接单、停售菜品）
    JAVA_BACKEND_URL: str = "http://localhost:8080"  # Java 后端地址

    class Config:
        """Pydantic Settings 的配置"""
        env_file = ".env"           # 指定 .env 文件路径
        env_file_encoding = "utf-8"


# 创建全局配置实例（类比 Spring 的 @Bean，整个应用共享一个配置对象）
settings = Settings()
