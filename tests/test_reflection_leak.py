"""B0-A5：输出泄露检测（配置模型名 / 提示词标记）。"""

from agent.reflection import sanitize
from config import settings


def test_configured_model_name_is_masked():
    raw = f"我是 {settings.LLM_MODEL} 模型，很高兴为您服务。"
    out = sanitize(raw)
    assert settings.LLM_MODEL.lower() not in out.lower()
    assert out != raw
    # 命中「身份」还是「泄露」分支取决于 _IDENTITY_KW 是否含当前供应商名，
    # 换供应商会翻边——断言行为（被安全话术替换），不断言具体分支
    assert ("智能经营顾问" in out) or ("内部信息" in out)


def test_prompt_marker_is_masked():
    out = sanitize("您的 SYSTEM_PROMPT 要求只回答经营问题。")
    assert "SYSTEM_PROMPT" not in out


def test_normal_reply_untouched():
    text = "本周营业额上升 12%，主要来自订单数增长。"
    assert sanitize(text) == text
