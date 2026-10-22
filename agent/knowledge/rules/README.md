# 平台规则语料（真实条款）

只有真实、可追溯的平台规则才放在这里。`agent/workbench/rules.py` 会扫描 `*.json` 并在
`GET /api/workbench/rules` 中返回；没有文件时 UI 显示“规则库未收录”，不会编造条款。

每个文件可以是数组或 `{"rules": [...]}`，每条必须包含：

```json
{
  "rule_key": "refund-handling",
  "title": "商家退款处理规则",
  "section": "3.2",
  "effective_date": "2026-01-01",
  "status": "active",
  "source": "平台规则中心",
  "content": "条款原文……"
}
```

缺字段、`status != active` 的条目会被跳过。不要放示例/占位条款。
