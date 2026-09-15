"""
外部数据工具包（external tools）

做什么：
- 提供外部数据接入能力（天气、节假日等）
- 这些数据用于辅助经营决策（如高温天促销冰饮）
"""

from agent.tools.external.weather import query_weather
from agent.tools.external.calendar_tool import query_holiday

EXTERNAL_TOOLS = [
    query_weather,
    query_holiday,
]

__all__ = ["EXTERNAL_TOOLS"]
