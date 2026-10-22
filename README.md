# 苍穹外卖 · 商家智能经营顾问（Agent + AI 经营工作台）

> 面向管理端的**商家经营顾问**：用自然语言完成 查数 → 诊断 → 建议，并配一套可视化的 **AI 经营工作台**（看板 + 规则中心 + 对话）。
>
> 本项目基于开源《苍穹外卖》(`sky-take-out`) 课程工程，在其之上**独立新增 Python Agent 决策服务 + Vue 3 工作台前端**；Java `backend/` 平台只读，不改动其任何一行代码。
>
> - Agent 服务端口 **8100**；工作台前端开发端口 **5173**（`/api` 反代到 8100）。
> - 版本号以 `config.py` 的 `APP_VERSION` 为唯一来源（`GET /health` 可见）。

## 它能做什么

**Agent 对话（查数 → 诊断 → 建议）**
- **查数**：营业额、订单、菜品、成本利润（11 个工具：分析 5 + 经营 4 + 外部 2，直连 MySQL 只读）
- **诊断**：因子分解归因、异常检测、趋势、相关性
- **建议**：菜单优化、促销模拟、备货计划（strategist 生成 + reviewer 校验）
- **知识问答**：退款 / 折扣 / 节假日等平台规定（JSON 知识库 + 关键词/向量混合检索，回答带来源）

**AI 经营工作台（可视化 + 个性化）**
- **看板 5 Widget**：KPI 网格、趋势图、退款图、菜品排行、热力格 + AI 摘要条 + 异常带
- **图表上下文对话**：点 KPI / 某天 / 某菜品 / 热力格 → 生成上下文 chip，带着它继续追问
- **偏好**：自然语言设定（"以后每天给我看退款趋势"）→ 后端保存并重排看板
- **规则中心**：平台规定分类 / 搜索 / 详情（演示 12 条关键词 RAG）
- **对话日志与反馈**：点赞 / 点踩闭环，落库 `agent_chat_log` / `agent_feedback`

## 技术栈

| 层 | 选型 |
|---|---|
| 编排 | LangGraph（状态图 + Checkpointer） |
| Agent 语言 / 框架 | Python 3.11 · FastAPI · Uvicorn |
| 模型 | DeepSeek（LLM）· 智谱 embedding-3（向量）· LangChain-OpenAI 客户端 |
| 数据 | MySQL（业务只读 + 对话日志）· SQLite（checkpoint）· Redis（会话 / 限流，可降级） |
| 检索 | 关键词 + 向量混合（Chroma 持久化），带来源与层级 |
| 观测 | Langfuse（无 Key 自动跳过） |
| **前端工作台** | **Vue 3.5 + Vite 5 + TypeScript · ECharts 5 · markdown-it**（无重型框架，构建产物纯静态） |

## 快速开始

### 1) Agent 服务（后端）

```bash
cp .env.example .env          # 填 LLM_API_KEY / EMBEDDING_API_KEY / DB_PASSWORD 等
python -m venv venv && source venv/bin/activate   # Windows: .\venv\Scripts\activate
pip install -r requirements.txt                     # 测试另装 requirements-dev.txt
python main.py                                      # http://localhost:8100
```

### 2) 工作台前端

```bash
cd frontend-ui
cp .env.example .env.local    # 本地填 VITE_AGENT_TOKEN（生产 Token 勿打进构建）
npm install
npm run dev                   # http://localhost:5173，/api 反代到 8100
npm run build                 # 产出 dist/（纯静态，可交任意静态服务器/反代托管）
```

配置了 `AGENT_API_TOKEN` 时，所有 `/api/*` 请求需带 `Authorization: Bearer <token>`。

**降级说明**：Redis 未启动 → 文件会话 + 本地限流；Embedding Key 无效 → 仅关键词检索；Langfuse 无 Key → 跳过观测；后端未启动 → 前端自动用 `src/mock/dashboard.ts` 演示数据并明确标注。主链路不受影响。

## 接口一览

| 方法 | 路径 | 用途 |
|---|---|---|
| POST | `/api/agent/chat` · `/chat/stream` · `/chat/resume` | 同步 / SSE 流式（心跳 + `Last-Event-ID` 续播）/ 断点恢复 |
| GET | `/api/agent/sessions` · `/sessions/{id}/logs` | 会话列表 / 历史日志 |
| POST | `/api/agent/feedback` | 点赞 / 点踩反馈 |
| GET | `/api/workbench/dashboard` | 看板数据（快照复用） |
| GET/POST | `/api/workbench/preferences` | 读 / 存个性化偏好 |
| GET | `/api/workbench/rules` · `/rules/search` · `/rules/categories` · `/rules/{id}` | 规则中心：列表 / 搜索 / 分类 / 详情 |
| GET | `/api/admin/config` | 只读配置后台（密钥仅回显是否已配置） |
| GET | `/health` | 健康检查（含版本号、Langfuse 状态） |

## 测试与评测

```bash
python -m pytest -q                        # 单元测试（工作台 + Agent 全链路）
python eval/run_eval.py                    # 离线行为评测（意图 / 门禁 / 注入）
python eval/run_retrieval_eval.py          # 检索质量（Recall@3 / MRR / 负例）
python eval/run_retrieval_eval.py --vector # 含向量腿（需 EMBEDDING_API_KEY）
python scripts/bench_workbench.py          # 工作台看板 p95 压测
```

## 架构一图

```
perceive → dispatcher ─┬─ simple (greeting/thanks/knowledge) → call_llm(小模型) → reflect
                       ├─ boundary / security_block ─────────────────────────────→ reflect
                       └─ complex: supervisor ⇄ (analyst→tools | strategist | reviewer)
                                       → call_llm(大模型) → reflect → END

工作台前端 (Vue3)  ──/api──▶  FastAPI ─┬─ api/routes.py           （对话 / 反馈 / 配置）
                                        └─ api/workbench_routes.py （看板 / 偏好 / 规则）→ agent/workbench/
```

- 图与节点：`agent/graph.py`（只连线）+ `agent/workers/`（一节点一文件）
- 能力层：`agent/llm.py`（模型路由）· `security.py`（注入 / 门禁）· `guards.py`（护栏）· `knowledge/`（RAG）· `memory/`（会话 / 限流 / 上下文）
- 工作台层：`agent/workbench/`（planner / preferences / rules / rule_rag / snapshot / store / period / data）
- 接口层：`api/routes.py` + `api/workbench_routes.py`；持久层：MySQL（业务 + 日志）/ SQLite（checkpoint）/ Redis（缓存）/ 文件（会话权威）

## 目录结构

```
agent/            编排、节点、护栏、安全、RAG、记忆、工作台逻辑（workbench/）
api/              HTTP / SSE 接口（routes.py 对话 + workbench_routes.py 工作台）
db/               MySQL 连接池、对话日志、反馈、Redis
schemas/          Pydantic 请求/响应契约（chat / workbench）
frontend-ui/      Vue 3 + Vite 工作台（components/ 看板 5 Widget + 对话 Dock）
deploy/           Dockerfile / docker-compose / nginx 模板 / 部署 Runbook
eval/             行为评测与检索评测
scripts/          数据校验、流程图导出、压测、迁移 DDL
tests/            单元测试（Agent + 工作台 + 错误契约）
```

## 部署（Docker Compose）

单机演示部署见 `deploy/RUNBOOK.md`。核心命令（服务器无需装 Python；前端构好在容器内完成）：

```bash
docker compose -f deploy/docker-compose.yml -f deploy/docker-compose.server.yml \
  --env-file .env up -d --build
```

- `docker-compose.yml`：`agent`（后端，端口绑 `127.0.0.1:8100`）+ `web`（`frontend-ui/` 构建产物 + nginx 反代 `/api`，注入 Token）。
- `docker-compose.server.yml`：额外拉起本机 MySQL 8 + Redis 7，并把 Agent 指向容器网络内的 `mysql` / `redis`。
- Agent 容器固定 **单 worker**（checkpoint、偏好、限流均以单实例为前提）。
- 生产需设 `APP_ENV=prod` 与 `AGENT_API_TOKEN`（prod 下漏配 Token 会 fail-closed，`/api/*` 一律 503）。
- 对外建议只暴露反代端口，`3306 / 6379 / 8100` 只绑 `127.0.0.1`；公网访问再套 HTTPS。

## 数据与合规

- 演示数据为课程库 + 自造流水，**不含任何真实商家或个人数据**。
- 本仓库不包含密钥：`.env`、`.env.*`、`venv/`、`node_modules/`、`dist/`、`data/`、`logs/` 均在 `.gitignore` 中；`.env.example` 为可提交的模板。
- Java `backend/` 平台只读，不在本仓库内。

## AI 协作入口

改哪、看哪个文件，见根目录 `AGENTS.md`。
