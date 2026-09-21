"""共享常量（B2 单一真值）：同一事实只允许在这里定义一次。"""

# 边界关键词：perception（输入分类）与 reflection（输出校验）共用同一份
BOUNDARY_KW = [
    "写文案", "写文章", "写报告", "翻译", "写代码", "写诗",
    "营销文案", "朋友圈", "小红书",
]

# 小模型意图集：llm（模型路由）与 security（工具门禁）共用同一份
SIMPLE_INTENTS = frozenset({"greeting", "thanks", "knowledge"})
