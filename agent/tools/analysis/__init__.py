"""
数据分析工具包（analysis tools）

做什么：
- 纯 Python 计算 + MySQL 查询，不经过 LLM
- 提供因子分解、相关性、异常检测、趋势分析、成本利润等分析能力
- 每个工具是一个 @tool 装饰的异步函数，可被 LangGraph ToolNode 调用

不做什么：
- 不做策略生成（那是 business/ 的事）
- 不调 LLM（快、准、可测试）
"""

from agent.tools.analysis.factor_decomposition import factor_decomposition
from agent.tools.analysis.correlation import correlation_analysis
from agent.tools.analysis.anomaly_detection import anomaly_detection
from agent.tools.analysis.time_series import trend_analysis
from agent.tools.analysis.cost_profit import cost_profit_analysis

ANALYSIS_TOOLS = [
    factor_decomposition,
    correlation_analysis,
    anomaly_detection,
    trend_analysis,
    cost_profit_analysis,
]

__all__ = ["ANALYSIS_TOOLS"]
