"""
反思层（Reflection）

做什么：
- 身份检查：不暴露底层模型名称（通义千问、GPT 等）
- 边界检查：不越界做无关的事（写文案、翻译等）
- 数据合理性检查：建议中的数字是否自洽

不做什么：
- 不做 LLM 调用（纯规则校验，快且可靠）
- 不做内容审核（那是上游 Prompt 的事）
"""

import logging
import re

from agent.constants import BOUNDARY_KW as _BOUNDARY_KW
from config import settings

logger = logging.getLogger(__name__)

# 身份关键词（不允许出现在回复中）
_IDENTITY_KW = [
    "通义千问", "qwen", "deepseek", "gpt", "openai",
    "阿里云", "dashscope", "语言模型",
]

# 身份替代话术
_IDENTITY_REPLACEMENT = "我是苍穹外卖的智能经营顾问"

# B0-A5：提示词/内部信息泄露标记（不区分大小写）
_PROMPT_LEAK_MARKERS = [
    "system_prompt", "system prompt", "systemprompt",
    "提示词内容", "内部指令", "系统规则如下",
]

_LEAK_REPLACEMENT = "这部分内部信息我不能展示。"


def _configured_model_names() -> list[str]:
    """配置中的模型名同样属于不可泄露信息（随 .env 变化，不能写死）。"""
    return [n.strip() for n in (settings.LLM_MODEL, settings.LLM_MODEL_SIMPLE) if n.strip()]

# 边界拒绝信号（LLM 已经在拒绝，无需拦截）
_REJECTION_SIGNALS = [
    "不在我的能力范围", "无法帮您", "不能帮您", "我主要擅长",
    "抱歉", "不好意思", "这超出", "无法完成",
]

# 边界接受信号（LLM 欣然接受越界请求，需拦截）
_ACCEPTANCE_PATTERNS = ["好的", "当然可以", "没问题", "我很乐意"]


def sanitize(response: str, user_input: str = "") -> str:
    """
    统一输出清洗：身份检查 → 边界检查。

    参数：
        response: LLM 原始回复
        user_input: 用户原始输入（可选，用于边界检查）

    返回：
        清洗后的回复
    """
    if not response:
        return response

    response = _check_identity(response)
    response = _check_leak(response)

    if user_input:
        response = _check_boundary(response, user_input)

    return response


def _check_leak(response: str) -> str:
    """B0-A5：模型名 / 提示词标记泄露时按句替换。"""
    lowered = response.lower()
    hits = [m for m in _PROMPT_LEAK_MARKERS if m in lowered]
    hits += [n for n in _configured_model_names() if n.lower() in lowered]
    for hit in hits:
        pattern = r"[^。！？\n]*" + re.escape(hit) + r"[^。！？\n]*[。！？]?"
        response = re.sub(pattern, _LEAK_REPLACEMENT, response, flags=re.IGNORECASE)
        logger.warning(f"[Reflect] 泄露校验触发: '{hit}'")
    return response


def _check_identity(response: str) -> str:
    """检查是否暴露底层模型身份，如有则替换整句。"""
    for keyword in _IDENTITY_KW:
        if keyword.lower() in response.lower():
            # 替换包含关键词的整句
            pattern = r'[^。！？\n]*' + re.escape(keyword) + r'[^。！？\n]*[。！？]?'
            replacement = _IDENTITY_REPLACEMENT + "。"
            response = re.sub(pattern, replacement, response, flags=re.IGNORECASE)
            logger.warning(f"[Reflect] 身份校验触发: 关键词 '{keyword}'")
            break
    return response


def _check_boundary(response: str, user_input: str) -> str:
    """检查 LLM 是否越界接受了不该做的事。"""
    user_lower = user_input.lower()
    response_lower = response.lower()

    # 检查用户输入是否涉及边界
    boundary_kw = None
    for kw in _BOUNDARY_KW:
        if kw in user_lower:
            boundary_kw = kw
            break

    if not boundary_kw:
        return response

    # LLM 已经在拒绝 → 不拦截
    if any(signal in response_lower for signal in _REJECTION_SIGNALS):
        return response

    # LLM 欣然接受 → 拦截
    for pattern in _ACCEPTANCE_PATTERNS:
        if response.strip().startswith(pattern):
            logger.warning(f"[Reflect] 边界校验触发: '{boundary_kw}'，LLM 欣然接受")
            return (
                "这不在我的核心能力范围内。我主要擅长帮您分析经营数据、"
                "诊断经营问题、提供优化建议。有什么经营相关的问题我可以帮您吗？"
            )

    # 检查回复内容是否在帮用户做越界的事
    boundary_content_signals = ["为您撰写", "为您生成", "以下是一篇", "以下文案"]
    for signal in boundary_content_signals:
        if signal in response_lower:
            logger.warning(f"[Reflect] 边界内容触发: 回复包含 '{signal}'")
            return (
                "这不在我的核心能力范围内。我主要擅长帮您分析经营数据、"
                "诊断经营问题、提供优化建议。有什么经营相关的问题我可以帮您吗？"
            )

    return response
