"""
节假日查询工具（Calendar Tool）

做什么：
- 查询中国节假日和特殊日期
- 数据来自本地 JSON 文件（knowledge/data/holidays.json）
- 用于辅助经营决策（节假日促销、备货量调整）

不做什么：
- 不做节假日决策（那是 strategist 的事）
"""

import json
import logging
from datetime import date
from pathlib import Path

from langchain_core.tools import tool

logger = logging.getLogger(__name__)

# B2-S3 单一真值：节假日数据只存 knowledge/data/holidays.json（RAG 与工具共用），
# 原内置 _HOLIDAYS 硬编码已删除（其 2026 端午/中秋日期与真实历法不符）。
_DATA_FILE = Path(__file__).resolve().parents[2] / "knowledge" / "data" / "holidays.json"


def _load_holidays() -> dict:
    try:
        entries = json.loads(_DATA_FILE.read_text(encoding="utf-8"))
        return {
            e["name"]: {"date": e["date"], "type": e["type"], "impact": e["impact"]}
            for e in entries
            if e.get("name") and e.get("date")
        }
    except Exception as e:
        logger.error(f"[Holiday] 读取 holidays.json 失败: {e}")
        return {}


_HOLIDAYS = _load_holidays()


@tool
async def query_holiday(query: str = "") -> str:
    """
    查询节假日信息。

    参数：
        query: 查询内容，可以是节日名称或日期。为空则返回即将到来的节假日。

    返回：
        节假日列表 + 对经营的影响程度

    使用场景：
        - "最近有什么节日？"
        - "春节对营业有什么影响？"
        - "下周有节假日吗？"
    """
    today = date.today()
    current_year = today.year

    if query:
        # 按名称搜索
        matches = []
        query_lower = query.lower()
        for name, info in _HOLIDAYS.items():
            if query_lower in name.lower() or name.lower() in query_lower:
                matches.append((name, info))

        if not matches:
            return f"没有找到与 '{query}' 相关的节假日信息。"

        lines = [f"=== 节假日查询：{query} ===", ""]
        for name, info in matches:
            lines.append(
                f"  {name}：{info['date']}（{info['type']}）\n"
                f"    对经营影响：{info['impact']}"
            )
        return "\n".join(lines)

    else:
        # 返回即将到来的节假日
        upcoming = []
        for name, info in _HOLIDAYS.items():
            month, day = info["date"].split("-")
            holiday_date = date(current_year, int(month), int(day))
            if holiday_date >= today:
                days_until = (holiday_date - today).days
                upcoming.append((name, info, days_until, holiday_date))

        # 也检查明年的元旦
        if not upcoming or upcoming[-1][2] > 30:
            next_new_year = date(current_year + 1, 1, 1)
            days_until = (next_new_year - today).days
            upcoming.append(("元旦", _HOLIDAYS["元旦"], days_until, next_new_year))

        upcoming.sort(key=lambda x: x[2])

        if not upcoming:
            return "近期没有节假日。"

        lines = ["=== 即将到来的节假日 ===", ""]
        for name, info, days_until, holiday_date in upcoming[:5]:
            lines.append(
                f"  {name}：{holiday_date}（{info['type']}）\n"
                f"    距今 {days_until} 天 | 经营影响：{info['impact']}"
            )
        return "\n".join(lines)
