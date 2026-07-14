"""
反思模块（Reflection Module）

职责：对 LLM 输出做后置校验（对照文章的"规则引擎硬校验"）。

对照文章的 7 大模块：
- 文章方案：规则引擎硬校验 + 轻量模型打分 + 异常触发人工审核
- 我们方案：简化版，只做规则校验（关键词匹配 + 替换）
- 未来可以扩展：模型打分、置信度检查

为什么需要这个模块？
1. 不再完全依赖 Prompt "软约束"，代码层有硬兜底
2. 统一处理输出校验（身份、边界、安全）
3. 方便扩展新的校验规则

类比 Java：
就像 Spring 的 Validator 或 Filter，在响应返回给用户之前做最后的校验。
"""

import logging
import re
from typing import List, Tuple

logger = logging.getLogger(__name__)


class Reflection:
    """
    反思层：对 LLM 输出做后置校验和清洗。
    
    类比 Java：
    就像一个 ResponseAdvice，在 Controller 返回响应之前统一处理。
    """
    
    def __init__(self):
        self.logger = logging.getLogger(self.__class__.__name__)
        
        # 身份关键词（不允许出现在回复中）
        self.identity_keywords = [
            "通义千问", "qwen", "deepseek", "gpt", "openai", 
            "阿里云", "dashscope", "语言模型"
        ]
        
        # 身份替代话术
        self.identity_replacement = "我是苍穹外卖的智能经营助手"
        
        # 边界关键词（如果用户问这些，LLM 不应该欣然接受）
        self.boundary_keywords = [
            "营销文案", "写文章", "写报告", "翻译", "写代码"
        ]
        
        # 边界拒绝话术
        self.boundary_replacement = (
            "这不在我的核心能力范围内。我主要擅长帮您查询经营数据、"
            "处理订单、管理菜品等，有什么经营相关的问题我可以帮您吗？"
        )
    
    def check_identity(self, response: str) -> str:
        """
        检查是否暴露底层模型身份，如有则替换整句。
        
        参数：
            response: LLM 原始回复
        
        返回：
            清洗后的回复
        
        检查规则：
        - 如果回复中包含身份关键词（如"通义千问"、"DeepSeek"），
          用安全的身份描述替换整段话（而不是只替换关键词）
        """
        original = response
        
        # 检查是否包含身份关键词
        for keyword in self.identity_keywords:
            if keyword.lower() in response.lower():
                # 找到包含关键词的句子，替换整句
                # 简单处理：用正则匹配包含关键词的完整句子
                pattern = r'[^。！？\n]*' + re.escape(keyword) + r'[^。！？\n]*[。！？]?'
                replacement = self.identity_replacement + "。"
                response = re.sub(pattern, replacement, response, flags=re.IGNORECASE)
                
                self.logger.warning(
                    f"[Reflection] 身份校验触发: 关键词 '{keyword}' 的句子被替换"
                )
                break  # 只替换一次，避免重复
        
        if original != response:
            self.logger.info(f"[Reflection] 身份清洗完成")
        
        return response
    
    def check_boundary(self, response: str, user_input: str) -> str:
        """
        检查是否越界（如写营销文案），如有则替换为拒绝话术。
        
        参数：
            response: LLM 原始回复
            user_input: 用户原始输入
        
        返回：
            清洗后的回复
        
        检查规则：
        - 如果用户输入包含边界关键词，且 LLM 回复是"欣然接受"（没有拒绝），
          则替换为拒绝话术
        
        注意：
        这个检查比较粗糙（只是关键词匹配），未来可以用 RAG 检索 boundary.json
        来做更精确的判断。
        """
        # 检查用户输入是否涉及边界
        for keyword in self.boundary_keywords:
            if keyword in user_input.lower():
                # 检查 LLM 是否"欣然接受"（简单判断：回复以"好的"、"当然可以"开头）
                acceptance_patterns = ["好的", "当然可以", "没问题", "我很乐意", "当然可以帮您"]
                for pattern in acceptance_patterns:
                    if response.strip().startswith(pattern):
                        self.logger.warning(
                            f"[Reflection] 边界校验触发: 用户请求 '{keyword}'，LLM 欣然接受"
                        )
                        return self.boundary_replacement
        
        return response
    
    def sanitize(self, response: str, user_input: str = "") -> str:
        """
        统一输出清洗：依次执行所有检查。
        
        参数：
            response: LLM 原始回复
            user_input: 用户原始输入（可选，用于边界检查）
        
        返回：
            清洗后的回复
        
        执行顺序：
        1. 身份检查（最重要）
        2. 边界检查
        3. 未来可以加：敏感信息检查、格式校验等
        """
        if not response:
            return response
        
        # 1. 身份检查
        response = self.check_identity(response)
        
        # 2. 边界检查
        if user_input:
            response = self.check_boundary(response, user_input)
        
        return response


# 全局实例
reflection = Reflection()
