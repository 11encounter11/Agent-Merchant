"""B0-A5：输出泄露检测（配置模型名 / 提示词标记）。"""

from agent.reflection import sanitize
from config import settings


def test_configured_model_name_is_masked():
    out = sanitize(f"我是 {settings.LLM_MODEL} 模型，很高兴为您服务。")
    assert settings.LLM_MODEL not in out
    assert "内部信息" in out


def test_prompt_marker_is_masked():
    out = sanitize("您的 SYSTEM_PROMPT 要求只回答经营问题。")
    assert "SYSTEM_PROMPT" not in out


def test_normal_reply_untouched():
    text = "本周营业额上升 12%，主要来自订单数增长。"
    assert sanitize(text) == text
