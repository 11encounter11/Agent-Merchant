"""数据充分性闸门：把工具输出分成「取不到 / 取到了但没有 / 有数据」，供提示层加硬约束。

判定为什么不交给模型：工具返回的缺数文案是确定性字符串，而模型面对全零窗口会把
「查不到」讲成「生意下滑」（SPEC/03 G10）。把分类放在代码里，约束才可测、可复现。
"""

from agent.prompts import DATA_INSUFFICIENCY_RULE

# 故障：连数都没取到，必须与「取到了但没有」分开表述
UNAVAILABLE_MARKERS = (
    "暂时取不到经营数据",
    "经营数据库暂时不可用",
    "执行失败",
)

# 取到了但窗口内没有可用记录
EMPTY_MARKERS = (
    "数据不足",
    "没有数据",
    "没有销售数据",
    "没有找到",
    "近期没有节假日",
    "暂无",
    "无有效订单记录",
)

LEVEL_UNAVAILABLE = "unavailable"
LEVEL_EMPTY = "empty"
LEVEL_PARTIAL = "partial"
LEVEL_SUFFICIENT = "sufficient"

_DETAIL = {
    LEVEL_UNAVAILABLE: "有工具取数失败（数据库或服务不可用）：{names}",
    LEVEL_EMPTY: "取到的结果里没有可用记录（窗口内为空或全零）：{names}",
    LEVEL_PARTIAL: "部分工具没取到可用数据：取数失败 {unavailable}；窗口内无记录 {empty}。",
}


def classify(analysis: dict) -> dict:
    """按工具输出文案判定本轮数据充分性。

    level：unavailable / empty（两者都没有任何有效数据）→ 不能下经营结论；
    partial → 只用有数据的部分下结论；sufficient → 正常。
    """
    unavailable: list[str] = []
    empty: list[str] = []
    has_data = False

    for name, content in (analysis or {}).items():
        text = str(content or "")
        if any(m in text for m in UNAVAILABLE_MARKERS):
            unavailable.append(name)
        elif any(m in text for m in EMPTY_MARKERS):
            empty.append(name)
        else:
            has_data = True

    if unavailable and not has_data:
        level = LEVEL_UNAVAILABLE
    elif empty and not has_data:
        level = LEVEL_EMPTY
    elif unavailable or empty:
        level = LEVEL_PARTIAL
    else:
        level = LEVEL_SUFFICIENT

    return {
        "level": level,
        "unavailable": unavailable,
        "empty": empty,
        "has_data": has_data,
    }


def insufficiency_note(verdict: dict) -> str:
    """把判定结果转成注入 Prompt 的硬约束；数据充分时返回空串。"""
    level = verdict.get("level") or LEVEL_SUFFICIENT
    if level == LEVEL_SUFFICIENT:
        return ""
    detail = _DETAIL[level].format(
        names="、".join(verdict.get("unavailable") or verdict.get("empty") or []),
        unavailable="、".join(verdict.get("unavailable") or []) or "无",
        empty="、".join(verdict.get("empty") or []) or "无",
    )
    return DATA_INSUFFICIENCY_RULE.format(detail=detail)
