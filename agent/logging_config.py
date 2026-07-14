"""
日志配置模块（Logging Configuration）

职责：统一配置整个 Agent 服务的日志输出。

对照文章的 7 大模块：
- 文章方案：OpenTelemetry 全链路追踪
- 我们方案：Python logging（够用，未来可以升级到 OpenTelemetry）

为什么需要这个模块？
1. 统一日志格式（时间 | 模块 | 级别 | 内容）
2. 同时输出到控制台和文件
3. 方便调试和复盘（看日志就知道 LLM 调了哪些 Tool、传了什么参数）

使用方法：
在 main.py 启动时调用 setup_logging() 一次即可。
"""

import logging
import sys
from pathlib import Path


def setup_logging(log_dir: str = "logs", log_level: int = logging.INFO):
    """
    配置整个应用的日志系统。
    
    参数：
        log_dir: 日志文件目录
        log_level: 日志级别（DEBUG/INFO/WARNING/ERROR）
    
    做了什么：
    1. 创建日志目录（如果不存在）
    2. 配置根日志器（root logger）
    3. 添加两个处理器：
       - 控制台输出（方便开发时看）
       - 文件输出（方便事后复盘）
    
    类比 Java：
    就像 logback.xml 或 log4j.properties 的配置
    """
    # 1. 创建日志目录
    log_path = Path(log_dir)
    log_path.mkdir(exist_ok=True)
    
    # 2. 配置根日志器
    root_logger = logging.getLogger()
    root_logger.setLevel(log_level)
    
    # 清除已有的处理器（避免重复添加）
    root_logger.handlers.clear()
    
    # 3. 定义日志格式
    # 格式：时间 | 模块名 | 级别 | 内容
    formatter = logging.Formatter(
        fmt='%(asctime)s | %(name)-20s | %(levelname)-8s | %(message)s',
        datefmt='%Y-%m-%d %H:%M:%S'
    )
    
    # 4. 控制台处理器（输出到 stdout）
    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setLevel(log_level)
    console_handler.setFormatter(formatter)
    root_logger.addHandler(console_handler)
    
    # 5. 文件处理器（输出到 logs/agent.log）
    file_handler = logging.FileHandler(
        log_path / "agent.log",
        encoding='utf-8',
        mode='a'  # 追加模式
    )
    file_handler.setLevel(log_level)
    file_handler.setFormatter(formatter)
    root_logger.addHandler(file_handler)
    
    # 6. 降低第三方库的日志级别（避免太多噪音）
    logging.getLogger("chromadb").setLevel(logging.WARNING)
    logging.getLogger("httpx").setLevel(logging.WARNING)
    logging.getLogger("openai").setLevel(logging.WARNING)
    logging.getLogger("langchain").setLevel(logging.WARNING)
    
    # 7. 记录启动信息
    root_logger.info("=" * 60)
    root_logger.info("苍穹外卖 Agent 服务启动")
    root_logger.info(f"日志级别: {logging.getLevelName(log_level)}")
    root_logger.info(f"日志文件: {log_path / 'agent.log'}")
    root_logger.info("=" * 60)


# 便捷函数：获取模块专属的 logger
def get_logger(name: str) -> logging.Logger:
    """
    获取模块专属的 logger。
    
    参数：
        name: 模块名称（通常用 __name__）
    
    返回：
        Logger 实例
    
    使用方法：
    logger = get_logger(__name__)
    logger.info("这是一条日志")
    
    类比 Java：
    private static final Logger logger = LoggerFactory.getLogger(Xxx.class);
    """
    return logging.getLogger(name)
