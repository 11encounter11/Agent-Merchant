"""common：各工人共用的 LLM 调用包装。不要在这里写业务节点。"""

import logging

from agent.llm import invoke_routed, is_llm_connect_error

logger = logging.getLogger(__name__)


def try_invoke_routed(*args, **kwargs):
    """LLM 网络失败返回 None，避免节点抛错把 checkpoint 卡在 next。"""
    try:
        return invoke_routed(*args, **kwargs)
    except Exception as e:
        if is_llm_connect_error(e):
            logger.warning(f"[LLM] 连接失败，本节点跳过: {e}")
            return None
        raise
