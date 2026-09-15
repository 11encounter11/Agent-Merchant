"""
工具包：统一导出 ALL_TOOLS

做什么：
- 汇总所有工具（analysis + business + external）
- 供图构建（execute_tools）和 LLM bind_tools 使用

不做什么：
- 不注册工具（直接 import 列表即可，不需要 ToolRegistry 过度设计）
"""

from agent.tools.analysis import ANALYSIS_TOOLS
from agent.tools.business import BUSINESS_TOOLS
from agent.tools.external import EXTERNAL_TOOLS

# 所有工具汇总
ALL_TOOLS = ANALYSIS_TOOLS + BUSINESS_TOOLS + EXTERNAL_TOOLS

__all__ = ["ALL_TOOLS"]
