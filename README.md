# 苍穹外卖 · 商家智能经营顾问 Agent 服务

> 管理端里的**商家经营顾问**：自然语言 查数 → 诊断 → 建议。端口 **8100**。
> 版本号以 `config.py` 的 `APP_VERSION` 为唯一来源（`GET /health` 可见）。
> **文档权威入口：`docs/REDESIGN/`**（需求/架构/功能/差距计划/测试计划）。本 README 只是导览。

## 它能做什么

- **查数**：营业额、订单、菜品、成本利润（11 个工具：分析 5 + 经营 4 + 外部 2，实时查 MySQL）
- **诊断**：因子分解归因、异常检测、趋势、相关性
- **建议**：菜单优化、促销模拟、备货计划（strategist 生成 + reviewer 校验）
- **知识问答**：退款/折扣/节假日等平台规定（JSON 知识库 + 关键词/向量混合检索，回答带来源）
- **工程保障**：LangGraph 多 Agent 编排、Supervisor 派工、护栏（步数/Token/超时/幂等·Redis 化）、
  注入拦截与工具门禁、Bearer 鉴权、限流（IP+会话防绕过）、输出泄露检测、商家数据隔离（merchant_id）、
  断点续跑 + `/resume`、SSE 类型化事件流、对话日志与反馈（点赞/点踩）、只读配置后台、Langfuse 观测

## 快速开始

```powershell
# 1) 配置：复制 .env.example 为 .env，填 LLM_API_KEY、DB_PASSWORD 等
# 2) 安装：pip install -r requirements.txt  （测试另装 requirements-dev.txt）
.\venv\Scripts\python.exe main.py            # http://localhost:8100

# 测试与评测
.\venv\Scripts\python.exe -m pytest -q       # 单元测试
.\venv\Scripts\python.exe eval\run_eval.py   # 离线行为评测（意图/门禁/注入）
```

前端在 `admin-web` 仓库：`npm run serve` → `http://localhost:8888/#/agent`。
配置了 `AGENT_API_TOKEN` 时，前端所有 `/api/*` 请求需带 `Authorization: Bearer <token>`。

降级说明：Redis 未启动 → 文件会话 + 本地限流；Embedding Key 无效 → 仅关键词检索；Langfuse 无 Key → 跳过观测。主链路不受影响。

## 架构一图

```
perceive → dispatcher ─┬─ simple (greeting/thanks/knowledge) → call_llm(小模型) → reflect
                       ├─ boundary / security_block ─────────────────────────────→ reflect
                       └─ complex: supervisor ⇄ (analyst→tools | strategist | reviewer)
                                       → call_llm(大模型) → reflect → END
```

- 图与节点：`agent/graph.py`（只连线）+ `agent/workers/`（一节点一文件）
- 能力层：`agent/llm.py`（模型路由）`security.py`（注入/门禁）`guards.py`（护栏）`knowledge/`（RAG）`memory/`（会话/限流/上下文）
- 接口层：`api/routes.py`；持久层：MySQL（业务+日志）/ SQLite（checkpoint）/ Redis（缓存）/ 文件（会话权威）

## 文档地图

| 你要找 | 看哪里 |
|--------|--------|
| 项目是什么/边界 | `docs/REDESIGN/01_REQUIREMENTS.md` |
| 架构与技术选型理由 | `docs/REDESIGN/02_ARCHITECTURE.md` |
| 功能点与接口契约 | `docs/REDESIGN/03_FEATURES.md` |
| 还债计划与当前差距 | `docs/REDESIGN/04_GAP_AND_PLAN.md` |
| 测试矩阵与 bug 审计 | `docs/REDESIGN/05_TEST_PLAN.md` + `BUGFIX_LOG.md` |
| AI 协作入口（改哪看哪） | `AGENTS.md` |
| 历史设计/复盘（考古） | `docs/`（已加状态横幅）与 `docs/_archive/` |
