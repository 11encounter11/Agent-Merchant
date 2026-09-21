"""
天气查询工具（Weather Tool）

做什么：
- 查询实时天气和未来 3 天预报（温度、天气状况、降雨量）
- 使用和风天气 API（需要在 .env 配置 WEATHER_API_KEY）
- 通过 httpx 异步调用

不做什么：
- 不做天气分析决策（那是 strategist 的事）
"""

import logging

import httpx
from langchain_core.tools import tool

from config import settings

logger = logging.getLogger(__name__)


@tool
async def query_weather(city: str = "") -> str:
    """
    查询天气信息（实时 + 未来 3 天预报）。

    参数：
        city: 城市 ID（和风天气 Location ID），默认使用配置中的 WEATHER_DEFAULT_CITY
              例如：101040100 = 重庆，101010100 = 北京

    返回：
        当前天气 + 未来 3 天预报（温度、天气状况、降雨概率）

    使用场景：
        - "今天天气怎么样？"
        - "明天会下雨吗？"
        - 备货时参考天气（高温→冰饮需求增加，下雨→外卖订单可能增加）
    """
    if not settings.WEATHER_API_KEY:
        return "天气 API 未配置（缺少 WEATHER_API_KEY），无法查询天气。"

    location = city or settings.WEATHER_DEFAULT_CITY

    try:
        async with httpx.AsyncClient(timeout=settings.WEATHER_TIMEOUT_SEC) as client:
            # 1. 实时天气
            now_resp = await client.get(
                f"{settings.WEATHER_API_URL}/weather/now",
                params={"location": location, "key": settings.WEATHER_API_KEY},
            )
            now_data = now_resp.json()

            # 2. 3 天预报
            forecast_resp = await client.get(
                f"{settings.WEATHER_API_URL}/weather/3d",
                params={"location": location, "key": settings.WEATHER_API_KEY},
            )
            forecast_data = forecast_resp.json()

        lines = ["=== 天气信息 ===", ""]

        # 解析实时天气
        if now_data.get("code") == "200" and now_data.get("now"):
            now = now_data["now"]
            lines.extend([
                f"【当前天气】",
                f"  温度：{now.get('temp', '?')}°C（体感 {now.get('feelsLike', '?')}°C）",
                f"  天气：{now.get('text', '?')}",
                f"  湿度：{now.get('humidity', '?')}%",
                f"  风力：{now.get('windDir', '?')} {now.get('windScale', '?')}级",
            ])
        else:
            lines.append("【当前天气】查询失败")

        # 解析预报
        if forecast_data.get("code") == "200" and forecast_data.get("daily"):
            lines.append("")
            lines.append("【未来 3 天预报】")
            for day in forecast_data["daily"]:
                date_str = day.get("fxDate", "?")
                temp_min = day.get("tempMin", "?")
                temp_max = day.get("tempMax", "?")
                text_day = day.get("textDay", "?")
                text_night = day.get("textNight", "?")
                humidity = day.get("humidity", "?")
                lines.append(
                    f"  {date_str}：{temp_min}~{temp_max}°C，"
                    f"白天{text_day}/夜间{text_night}，湿度{humidity}%"
                )
        else:
            lines.append("【未来 3 天预报】查询失败")

        return "\n".join(lines)

    except httpx.TimeoutException:
        return "天气查询超时，请稍后再试。"
    except Exception as e:
        logger.error(f"[Weather] 查询失败: {e}")
        return f"天气查询失败：{str(e)[:100]}"
