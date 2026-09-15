"""
策略生成工具包（business tools）

做什么：
- 结合 analysis/ 的分析结果，生成可执行的经营建议
- 每个工具内部调用分析工具，组合结果后由 LLM 生成策略

不做什么：
- 不做纯数据计算（那是 analysis/ 的事）
"""

from agent.tools.business.business_report import business_report
from agent.tools.business.menu_optimization import menu_optimization
from agent.tools.business.promotion_planner import promotion_planner
from agent.tools.business.prep_plan import prep_plan

BUSINESS_TOOLS = [
    business_report,
    menu_optimization,
    promotion_planner,
    prep_plan,
]

__all__ = ["BUSINESS_TOOLS"]
