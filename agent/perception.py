"""
感知模块（Perception Module）

职责：预处理用户输入，为后续流程做准备。

对照文章的 7 大模块：
- 文章方案：轻量分类模型 + LLM 兜底
- 我们方案：直接用 LLM 的 bind_tools 做意图识别（已经够用）
- 这个模块主要做：输入清洗、日志记录、预留扩展点

为什么需要这个模块？
1. 统一处理用户输入的预处理逻辑
2. 记录原始输入用于调试和日志
3. 未来如果要接本地轻量模型做意图分类，可以在这里扩展
"""

import logging
import re

logger = logging.getLogger(__name__)


class Perception:
    """
    感知层：负责接收和预处理用户输入。
    
    类比 Java：
    就像 Spring Boot 的 Filter 或 Interceptor，
    在请求到达 Controller 之前先做一些预处理。
    """
    
    def __init__(self):
        self.logger = logging.getLogger(self.__class__.__name__)
    
    def preprocess(self, user_input: str) -> str:
        """
        清洗用户输入。
        
        参数：
            user_input: 用户原始输入
        
        返回：
            清洗后的输入字符串
        
        做了什么：
        1. 去除首尾空白
        2. 去除特殊控制字符
        3. 规范化空白（多个空格变一个）
        """
        if not user_input:
            return ""
        
        # 1. 去除首尾空白
        cleaned = user_input.strip()
        
        # 2. 去除控制字符（ASCII 0-31，除了换行和制表符）
        cleaned = re.sub(r'[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]', '', cleaned)
        
        # 3. 规范化空白（多个连续空格变一个）
        cleaned = re.sub(r'\s+', ' ', cleaned)
        
        # 4. 记录日志
        self.logger.info(f"[Perception] 原始输入: '{user_input}' → 清洗后: '{cleaned}'")
        
        return cleaned
    
    def classify_intent(self, user_input: str) -> dict:
        """
        意图分类（预留扩展点）。
        
        参数：
            user_input: 清洗后的用户输入
        
        返回：
            意图字典：{"intent": "xxx", "confidence": 0.0-1.0}
        
        当前实现：
        - 直接返回 unknown，因为意图识别由 LLM 的 bind_tools 处理
        - 未来可以接本地轻量模型（如 BERT）做快速分类
        
        未来扩展场景：
        - 如果用户量很大，可以用本地模型先分类，过滤掉 90% 的简单问题
        - 只有置信度低的才调用 LLM，节省 Token 成本
        """
        # 当前由 LLM 处理，这里只返回占位
        return {
            "intent": "unknown",
            "confidence": 0.0,
            "method": "llm_fallback"
        }


# 全局实例（整个应用共享一个）
perception = Perception()
