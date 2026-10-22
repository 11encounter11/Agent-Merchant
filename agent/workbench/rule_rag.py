"""平台规则关键词检索（演示语料）。

为什么先不上 embedding：
- 当前只有十几条演示条款，关键词命中足够验证「检索 → 引用 → 回答」链路；
- 向量腿需要额外费用/延迟，且现有知识库的向量集合面向 FAQ，不应把两套来源混在一起；
- 将来导入真实长文规则后，再为 rule_sections 单独建 collection。
"""

from __future__ import annotations

import re

from .rules import load_rules

RULE_TRIGGER = (
    "规则", "条款", "规定", "合规", "处罚", "发票", "食品安全",
    "结算", "投诉", "评价", "活动", "退款规则", "售后",
)


def should_use_rules(query: str) -> bool:
    text = query or ""
    return any(word in text for word in RULE_TRIGGER)


_STOPWORDS = {"平台", "怎么", "规定", "规则", "请问", "什么", "如何", "一下", "可以", "我们"}


def _tokens(query: str) -> list[str]:
    # 中文按 2~4 字片段补充，避免依赖 jieba；规则只有十几条，成本可接受
    chunks = re.findall(r"[\u4e00-\u9fff]{2,}|[A-Za-z0-9_]+", query or "")
    tokens = {chunk for chunk in chunks if chunk not in _STOPWORDS}
    for chunk in chunks:
        for size in (2, 3, 4):
            for index in range(0, max(0, len(chunk) - size + 1)):
                token = chunk[index:index + size]
                if token not in _STOPWORDS:
                    tokens.add(token)
    return list(tokens)


def search_rules(query: str, top_k: int | None = 3, category: str = "") -> list[dict]:
    """规则检索；query 为空时返回目录（供规则中心列表），top_k=None 返回全部。"""
    tokens = _tokens(query) if query else []
    hits = []
    for rule in load_rules():
        if category and rule.get("category") != category:
            continue
        score = 0
        for keyword in rule.get("keywords") or []:
            if keyword and keyword in query:
                score += 3
        for token in tokens:
            if token in rule.get("title", ""):
                score += 2
            elif token in rule.get("content", ""):
                score += 1
        # 至少要有一次实质命中（关键词或标题/正文双命中），避免“退款”泛词把结算规则也带进来
        if query and score < 2:
            continue
        hits.append({
            "rule_id": rule["rule_id"],
            "title": rule["title"],
            "section": rule["section"],
            "effective_date": rule["effective_date"],
            "status": rule["status"],
            "source": rule["source"],
            "category": rule.get("category", ""),
            "demo": rule.get("demo", False),
            "score": float(score),
            "layer": "rule",
            "preview": rule.get("snippet", "")[:160],
            "content": rule.get("content", ""),
        })
    hits.sort(key=lambda item: (-item["score"], item["category"], item["title"]))
    return hits if top_k is None else hits[:top_k]


def get_rule_sections(rule_id: str) -> list[dict]:
    return [rule for rule in load_rules() if rule["rule_id"] == rule_id]


def rule_categories() -> list[dict]:
    counts: dict[str, int] = {}
    for rule in load_rules():
        category = rule.get("category") or "未分类"
        counts[category] = counts.get(category, 0) + 1
    order = ["退款与取消", "食品安全", "财务结算", "营销活动", "履约与商品",
             "评价与申诉", "账号安全", "违规治理"]
    keys = order + sorted(key for key in counts if key not in order)
    return [{"key": key, "label": key, "count": counts.get(key, 0)} for key in keys if counts.get(key)]


def format_rule_context(hits: list[dict]) -> str:
    if not hits:
        return ""
    demo = any(hit.get("demo") for hit in hits)
    header = "[平台规则参考]\n" + (
        "注意：以下为演示语料（DEMO_SYNTHETIC），不是真实平台政策；回答必须标注演示来源。\n"
        if demo else ""
    )
    parts = []
    for hit in hits:
        parts.append(
            f"- {hit['title']} 第 {hit['section']} 条（生效 {hit['effective_date']}，"
            f"来源 {hit['source']}）：{hit['content']}"
        )
    return header + "\n".join(parts) + (
        "\n引用时只能使用以上条款号；没有命中就说“规则库未收录”，不要编造。"
    )
