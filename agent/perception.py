"""
感知层（Perception）

做什么：
- 输入清洗：去空白、控制字符
- 意图分类：关键词规则快速分类（greeting / query_analysis / query_report / boundary / unknown）
- 情境注入：自动获取当前日期、星期、时间，写入 state.context
- greeting 短路直接回复，boundary 直接拒绝，不走 LLM

不做什么：
- 不做 LLM 调用（意图分类用关键词规则，够用且快）
- 不做数据分析（那是 analyst 节点的事）

意图分类结果会被 dispatcher 节点用来决定路由。
"""

import logging
import re
from datetime import datetime

logger = logging.getLogger(__name__)


# ============================================================
# 意图分类关键词规则
# ============================================================

_GREETING_KW = ["你好", "在吗", "hi", "hello", "早上好", "下午好", "晚上好", "help", "帮助"]
_THANKS_KW = ["谢谢", "感谢", "谢了", "多谢"]

# 分析类意图（需要走复杂路径：analyst → strategist → reviewer）
_ANALYSIS_KW = [
    "为什么", "原因", "分析", "诊断", "趋势", "预测", "备货",
    "下降", "上升", "异常", "波动", "对比", "比较",
    "促销", "优化", "建议", "怎么办", "怎么改",
    "毛利", "利润", "成本", "ABC",
]

# 报告类意图（需要调 business_report 工具）
_REPORT_KW = [
    "日报", "周报", "报告", "汇报", "经营情况", "经营状况",
    "今天怎么样", "这周怎么样", "最近怎么样",
]

# 边界类（直接拒绝）
_BOUNDARY_KW = [
    "写文案", "写文章", "写报告", "翻译", "写代码", "写诗",
    "营销文案", "朋友圈", "小红书",
]


def preprocess(user_input: str) -> str:
    """
    输入清洗：去空白、控制字符、规范化。
    """
    if not user_input:
        return ""

    cleaned = user_input.strip()
    # 去除控制字符（ASCII 0-31，除了换行和制表符）
    cleaned = re.sub(r'[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]', '', cleaned)
    # 规范化空白
    cleaned = re.sub(r'\s+', ' ', cleaned)

    return cleaned


def classify_intent(user_input: str) -> dict:
    """
    意图分类：用关键词规则快速分类。

    返回：
        {"intent": "greeting|thanks|query_analysis|query_report|boundary|unknown",
         "confidence": 0.0~1.0}

    分类优先级：boundary > analysis > report > greeting > thanks > unknown
    """
    cleaned = user_input.strip().lower()

    # 1. 边界检查（最高优先级）
    for kw in _BOUNDARY_KW:
        if kw in cleaned:
            return {"intent": "boundary", "confidence": 0.9, "keyword": kw}

    # 2. 分析类意图
    for kw in _ANALYSIS_KW:
        if kw in cleaned:
            return {"intent": "query_analysis", "confidence": 0.8, "keyword": kw}

    # 3. 报告类意图
    for kw in _REPORT_KW:
        if kw in cleaned:
            return {"intent": "query_report", "confidence": 0.8, "keyword": kw}

    # 4. 打招呼
    if any(kw in cleaned for kw in _GREETING_KW):
        return {"intent": "greeting", "confidence": 0.8}

    # 5. 感谢
    if any(kw in cleaned for kw in _THANKS_KW):
        return {"intent": "thanks", "confidence": 0.9}

    # 6. 兜底：交给 LLM 处理
    return {"intent": "unknown", "confidence": 0.0}


def inject_context() -> dict:
    """
    注入情境信息：当前日期、星期、时间。

    返回：
        {"current_date": "2026-07-25", "weekday": "星期六", "hour": 14, "time_str": "14:30"}
    """
    now = datetime.now()
    weekdays = ["星期一", "星期二", "星期三", "星期四", "星期五", "星期六", "星期日"]

    return {
        "current_date": now.strftime("%Y-%m-%d"),
        "weekday": weekdays[now.weekday()],
        "hour": now.hour,
        "time_str": now.strftime("%H:%M"),
    }
