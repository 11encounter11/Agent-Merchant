"""
消息工具函数

负责 LLM 消息列表的清洗与流式内容过滤，
避免 tool / AI 配对错误或把占位符推给前端。
"""

import logging

from langchain_core.messages import AIMessage, ToolMessage

logger = logging.getLogger(__name__)


def sanitize_tool_pairing(messages: list) -> list:
    """
    保证发给 LLM 的消息满足：
    role=tool 必须跟在带 tool_calls 的 AIMessage 之后（可连续多条 ToolMessage）。
    """
    final = []
    i = 0
    while i < len(messages):
        msg = messages[i]
        if isinstance(msg, AIMessage) and getattr(msg, "tool_calls", None):
            j = i + 1
            tool_msgs = []
            while j < len(messages) and isinstance(messages[j], ToolMessage):
                tool_msgs.append(messages[j])
                j += 1
            if tool_msgs:
                final.append(msg)
                final.extend(tool_msgs)
            else:
                logger.warning("[Messages] 丢弃无 Tool 结果的 AI tool_calls 声明")
            i = j
            continue
        if isinstance(msg, ToolMessage):
            logger.warning(
                "[Messages] 丢弃孤立 ToolMessage（缺少前置 tool_calls）: %s",
                (msg.content or "")[:80],
            )
            i += 1
            continue
        final.append(msg)
        i += 1
    return final


def is_placeholder_content(text: str) -> bool:
    """
    模型在决定调工具前，常先吐出「。」「嗯」等占位碎片。
    stream_mode=messages 会把这些当成 content 推给前端，造成界面上单独一个句号。
    """
    t = (text or "").strip()
    if not t:
        return True
    if len(t) <= 3 and all(
        ch in "。.?？!！…,~～、，,；;：:、·—-\n\r\t 嗯啊呃 "
        for ch in t
    ):
        return True
    return False
