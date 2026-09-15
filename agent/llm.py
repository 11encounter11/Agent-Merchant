"""
LLM 工厂（集中管理模型实例）

做什么：
- 集中创建和管理所有 LLM 实例
- 提供 get_llm()（基础 LLM）和 get_llm_with_tools(tools)（绑定工具的 LLM）
- 未来换模型、A/B 测试只改这一个文件

不做什么：
- 不在这里调用 LLM（调用在 nodes.py 的 call_llm / strategist / reviewer 节点）
- 不在这里管理 Prompt（Prompt 在 prompts.py）
"""

import logging

from langchain_openai import ChatOpenAI

from config import settings

logger = logging.getLogger(__name__)

# 缓存的 LLM 实例（避免重复创建）
_base_llm: ChatOpenAI | None = None
_tool_llm: ChatOpenAI | None = None


def get_llm() -> ChatOpenAI:
    """
    获取基础 LLM 实例（不绑定工具）。
    用于 strategist、reviewer 等需要纯文本推理的节点。
    """
    global _base_llm
    if _base_llm is None:
        _base_llm = ChatOpenAI(
            api_key=settings.LLM_API_KEY,
            base_url=settings.LLM_BASE_URL,
            model=settings.LLM_MODEL,
            temperature=settings.LLM_TEMPERATURE,
        )
        logger.info(f"[LLM] 基础 LLM 已创建: {settings.LLM_MODEL}")
    return _base_llm


def get_llm_with_tools(tools: list) -> ChatOpenAI:
    """
    获取绑定了工具的 LLM 实例。
    用于 analyst 节点（需要调用数据分析工具）。

    参数：
        tools: LangChain @tool 装饰的函数列表
    """
    global _tool_llm
    if _tool_llm is None:
        _tool_llm = ChatOpenAI(
            api_key=settings.LLM_API_KEY,
            base_url=settings.LLM_BASE_URL,
            model=settings.LLM_MODEL,
            temperature=settings.LLM_TEMPERATURE,
        ).bind_tools(tools)
        logger.info(f"[LLM] 工具 LLM 已创建: {settings.LLM_MODEL}, 绑定 {len(tools)} 个工具")
    return _tool_llm
