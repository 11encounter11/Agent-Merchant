# 苍穹外卖 · 商家智能经营顾问 Agent 服务

> 管理端里的**商家经营顾问**：用自然语言完成 查数 → 诊断 → 建议。服务端口 **8100**。
>
> 本项目基于开源《苍穹外卖》(`sky-take-out`) 课程工程，在其之上**独立新增一层 Python Agent 决策服务**；Java `backend/` 平台只读，不改动其任何一行代码。
>
> 版本号以 `config.py` 的 `APP_VERSION` 为唯一来源（`GET /health` 可见）。
> 架构与设计文档在 `docs/`（图编排 / RAG / 安全 / 模块拆分 / REDESIGN 需求基线），本 README 只做导览。

## 它能做什么

- **查数**：营业额、订单、菜品、成本利润（11 个工具：分析 5 + 经营 4 + 外部 2，直连 MySQL 只读）
- **诊断**：因子分解归因、异常检测、趋势、相关性
- **建议**：菜单优化、促销模拟、备货计划（strategist 生成 + reviewer 校验）
- **知识问答**：退款 / 折扣 / 节假日等平台规定（JSON 知识库 + 关键词/向量混合检索，回答带来源）
- **模型栈**：LLM 走 DeepSeek，Embedding 走智谱 `embedding-3`（两家 Key 分开配置，不可复用）
- **工程保障**：LangGraph 多 Agent 编排、Supervisor 派工、护栏（步数 / Token / 超时 / 幂等·Redis 化）、注入拦截与工具门禁、Bearer 鉴权、限流（IP + 会话防绕过）、输出泄露检测、商家数据隔离（`merchant_id`）、断点续跑 + `/resume`、SSE 类型化事件流、对话日志与点赞/点踩反馈、只读配置后台、Langfuse 观测

## 技术栈

| 层 | 选型 |
|---|---|
| 编排 | LangGraph（状态图 + Checkpointer） |
| 语言 / 框架 | Python 3.11 · FastAPI · Uvicorn |
| 模型 | DeepSeek（LLM）· 智谱 embedding-3（向量）· LangChain-OpenAI 客户端 |
| 数据 | MySQL（业务只读 + 对话日志）· SQLite（checkpoint）· Redis（会话 / 限流，可降级） |
| 检索 | 关键词 + 向量混合（Chroma 持久化），带来源与层级 |
| 观测 | Langfuse（无 Key 自动跳过） |

## 快速开始

```bash
# 1) 配置：复制 .env.example 为 .env，填 LLM_API_KEY / EMBEDDING_API_KEY / DB_PASSWORD 等
cp .env.example .env

# 2) 安装依赖
python -m venv venv && source venv/bin/activate   # Windows: .\venv\Scripts\activate
pip install -r requirements.txt                    # 测试另装 requirements-dev.txt

# 3) 启动
python main.py                                     # http://localhost:8100
```

配置了 `AGENT_API_TOKEN` 时，所有 `/api/*` 请求需带 `Authorization: Bearer <token>`。

**降级说明**：Redis 未启动 → 文件会话 + 本地限流；Embedding Key 无效 → 仅关键词检索；Langfuse 无 Key → 跳过观测。主链路不受影响。

## 接口一览

| 方法 | 路径 | 用途 |
|---|---|---|
| POST | `/api/agent/chat` | 同步对话 |
| POST | `/api/agent/chat/stream` | SSE 流式对话（心跳 + `Last-Event-ID` 断线续播） |
| POST | `/api/agent/chat/resume` | 断点恢复 |
| GET | `/api/agent/sessions` · `/sessions/{id}/logs` | 会话列表 / 历史日志 |
| POST | `/api/agent/feedback` | 点赞 / 点踩反馈 |
| GET | `/api/admin/config` | 只读配置后台（密钥仅回显是否已配置） |
| GET | `/health` | 健康检查（含版本号、Langfuse 状态） |

## 测试与评测

```bash
python -m pytest -q                        # 单元测试（190 passed 基线）
python eval/run_eval.py                    # 离线行为评测（意图 / 门禁 / 注入）
python eval/run_retrieval_eval.py          # 检索质量（Recall@3 / MRR / 负例）
python eval/run_retrieval_eval.py --vector # 含向量腿（需 EMBEDDING_API_KEY）
```

## 架构一图

```
perceive → dispatcher ─┬─ simple (greeting/thanks/knowledge) → call_llm(小模型) → reflect
                       ├─ boundary / security_block ─────────────────────────────→ reflect
                       └─ complex: supervisor ⇄ (analyst→tools | strategist | reviewer)
                                       → call_llm(大模型) → reflect → END
```

- 图与节点：`agent/graph.py`（只连线）+ `agent/workers/`（一节点一文件）
- 能力层：`agent/llm.py`（模型路由）· `security.py`（注入 / 门禁）· `guards.py`（护栏）· `knowledge/`（RAG）· `memory/`（会话 / 限流 / 上下文）
- 接口层：`api/routes.py`；持久层：MySQL（业务 + 日志）/ SQLite（checkpoint）/ Redis（缓存）/ 文件（会话权威）

## 目录结构

```
agent/        编排、节点、护栏、安全、RAG、记忆
api/          HTTP / SSE 接口（对话 + 反馈 + 只读配置）
db/           MySQL 连接池、对话日志、反馈、Redis
schemas/      Pydantic 请求/响应契约
deploy/       Dockerfile / docker-compose / nginx 模板 / 部署 Runbook
eval/         行为评测与检索评测
scripts/      数据校验、流程图导出、迁移 DDL
tests/        单元测试
docs/         架构与设计文档
```

## 部署（Docker Compose）

单机演示部署见 `deploy/RUNBOOK.md`。核心命令（服务器无需装 Python）：

```bash
docker compose -f deploy/docker-compose.yml -f deploy/docker-compose.server.yml \
  --env-file .env up -d --build agent
```

- `docker-compose.server.yml` 额外拉起本机 MySQL 8 + Redis 7，并把 Agent 指向容器网络内的 `mysql` / `redis`。
- 配套的 `web` 服务（`frontend.Dockerfile` + nginx）用于托管工作台前端；其构建依赖 `frontend-ui/` 前端源码（本服务仓库不含该目录），仅后端部署时用 `up -d --build agent` 即可。
- Agent 容器固定 **单 worker**（checkpoint、限流均以单实例为前提）。
- 生产需设 `APP_ENV=prod` 与 `AGENT_API_TOKEN`（prod 下漏配 Token 会 fail-closed，`/api/*` 一律 503）。
- 对外建议只暴露反代端口，`3306 / 6379 / 8100` 只绑 `127.0.0.1`；公网访问再套 HTTPS。

## 数据与合规

- 演示数据为课程库 + 自造流水，**不含任何真实商家或个人数据**。
- 本仓库不包含密钥：`.env`、`.env.*`、`venv/`、`data/`、`logs/` 均在 `.gitignore` 中；`.env.example` 为可提交的模板。
- Java `backend/` 平台只读，不在本仓库内。

## AI 协作入口

改哪、看哪个文件，见根目录 `AGENTS.md`。
