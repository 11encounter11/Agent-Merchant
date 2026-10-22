# 平台活动语料（真实活动）

平台侧把活动导出为 `*.json` 放在这里，`agent/workbench/rules.py` 每次请求会扫描并展示；
没有文件时 UI 显示“暂无活动数据源”，不造假。

支持单条或数组：

```json
{
  "activity_key": "summer-2026",
  "title": "夏日满减",
  "start_date": "2026-07-01",
  "end_date": "2026-07-31",
  "status": "active",
  "description": "满 30 减 5，平台补贴",
  "source": "平台活动中心"
}
```

必填 `activity_key/title/start_date/end_date`；`status != active` 或已结束的活动不返回。
