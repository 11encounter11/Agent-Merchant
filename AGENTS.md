# AGENTS.md · 新对话请先读这份

> 给 Cursor / AI：**不要扫全库**。按本文继续。
> 回答只按产品与工程能力描述。
> **权威文档 = `docs/AI_WORKBENCH/`**（产品 / 架构 / 执行 / UI 规格 / API 契约）。
> 裁决顺序：`docs/AI_WORKBENCH/` > 本文 > 代码。Java `backend/` 只读，一行都不能改。

---

## 移交快照（2026-10-20 更新）

| 项 | 状态 |
|----|------|
| 产品 | 管理端**商家经营顾问**（查数→诊断→建议），端口 **8100** |
| **模型栈（2026-10-20 切换）** | LLM=**DeepSeek `deepseek-flash`**（`https://api.deepseek.com`，tool calling 实测可用）；Embedding=**智谱 `embedding-3`**（付费，2048 维）。**两家 Key 不通用**，`_resolve_embedding_key()` 已禁止跨供应商复用 |
| 主链路 | **已完成**（analyst 真调工具 + JSON 知识注入 + 顾问文案） |
| 工程能力 | 护栏 / Supervisor / Checkpointer / Redis+日志 / 路由+安全+评测 / RAG 来源可观测 / Langfuse / **Bearer 鉴权 + CORS 白名单 + 限流防绕过 + 输出泄露检测** / **输入白名单（会话 ID 防路径穿越）+ SSE 心跳与反代防缓冲 + 落盘收尾（失败/中断也留痕）+ DB 不可用语义区分 + 向量索引持久化 + 检索评测（Recall@3/MRR）** / **SSE 断线续播（id:+retry+Last-Event-ID 回放）+ 历史日志端点** |
| **工作台进度** | 看板 5 Widget + 快照复用 + 偏好 + 12 条演示规则 RAG + 规则中心分类/搜索/详情 + 活动空态 + 图表上下文对话已可用；`docs/AI_WORKBENCH/03` 记录批次与证据 |
| **下一个该做** | 后端：身份桥接（单商家暂不做）、正式规则语料（待提供）；p95 已测（1 并发 37ms / 5 并发 92ms）；部署：单商家 compose 已验收（8081）；前端窗口按契约联调 |
| 测试基线 | `pytest -q` **190 passed**；`bench_workbench.py` last30 p95 37ms(c1)/92ms(c5)（2026-10-20 工作台 + 错误契约 + 快照复用/退款异常后实跑）；`frontend-ui` 的 `npm run build` 通过；`eval/run_eval.py` 15/15；`eval/run_retrieval_eval.py` **26 例**：仅关键词 Recall@3 86.4% / **加 `--vector` Recall@3 100%、MRR 1.0、负例 4/4、语义改写 4/4**（阈值 `RAG_VECTOR_MIN_SCORE=0.52`，实测校准，勿随意改）；**L4 活服务评测实际不可用**（`scripts/run_test.py` 不发 `Authorization` 头，配 Token 即全 401）；B7 各项另经活服务 + 双实例（DB 断开）实机验证 |
| Git | 本地 `master` 已提交；**未配置 origin，未 push**（推送需先 `git remote add`） |
| 前端 | 新工作台在 `frontend-ui/`（Vue 3 + Vite）；配置 `AGENT_API_TOKEN` 后 `/api/*` 需带 Bearer 头。旧 `admin-web` 是 Java 平台自带前端，不属于本次改造。 |

### 最近本地提交（由新到旧）

| Commit | 说明 |
|--------|------|
| （本批·未提交） | B8+A7 功能补齐：历史日志端点 / SSE 断线续播（id:+retry+Last-Event-ID 回放）+ 10 新测试 |
| `b5151eb` | B7 复审修复：路径穿越 / SSE 心跳+落盘收尾+usage / DBUnavailable / 向量索引持久化+metadata / 检索评测 27 例 |
| `cff0d11` | 收尾：requirements 锁上界、删坏脚本、.env.example 补缺、文档终检 |
| `88958c1` | B6c+B6d：配置后台 1/2 级 + 对话反馈闭环（agent_feedback） |
| `af2fbff` | B6b：SSE 事件类型化 + /resume 断点恢复端点 |
| `f46869d` | B6a：merchant_id 商家隔离（迁移已执行、活库验证） |
| `4871a02` | B5 文档收口：归档/横幅/README 重写/快照更新 |
| `72286bd` | B4 清死代码：删 nodes 转发层/骨架/死配置，阈值接线 |
| `4f917bb` | B3 健壮性：护栏留痕/限流前置/幂等 Redis/懒加载/图单例 R1–R10 |
| `63b41b5` | B2 单一真值：constants/节假日 JSON/成本系数/版本号 |
| `5e7a86e` | B0 安全止血：Bearer/CORS/限流防绕过/泄露检测/移除源码口令 |

---

## 产品定位（已锁定）

- **是什么**：管理端里的**商家经营顾问**（查数 → 诊断 → 建议），端口 **8100**。
- **不是什么**：C 端客服、接单/拒单「语音遥控器」。
- **前端**：`admin-web` → `/agent`（SSE：`/api/agent/chat/stream`）。
- **目标**：作品集向——技术要能讲清「为什么用」；**不堆名词**。

## 技术选型结论（已讨论）

| 项 | 结论 |
|----|------|
| 编排 | **只留 LangGraph**（不要 Dify / CrewAI 第二套） |
| 经营数据 | **SQL Tools 必做**（不进向量库） |
| 规定类知识 | 现有 `agent/knowledge/data/*.json` **先真正注入对话** |
| LLM Wiki | **默认不做** |
| LlamaIndex | **有条件**（有长文再上，替换手写 chromadb） |
| MCP | **当前不做** |
| Skill | 后期；不为 Wiki 预留空壳 |

## 当前架构（代码为准）

```
perceive → dispatcher
  → simple (greeting/thanks/knowledge): call_llm(小模型) → reflect
  → boundary / security_block: reflect
  → complex: supervisor ⇄ (analyst → tools? | strategist | reviewer) → call_llm(大模型) → reflect
```

| 模块 | 路径 | 备注 |
|------|------|------|
| 图 | `agent/graph.py` | 只连线；Checkpointer 编译；`get_agent_graph()` |
| 调度 | `agent/supervisor.py` | 规则 Supervisor–Worker |
| 节点 | `agent/workers/` | 一节点一文件（nodes.py 转发层已删） |
| 共享常量 | `agent/constants.py` | 单一真值（边界词/简单意图集） |
| 护栏 | `agent/guards.py` | 步数/token/超时重试/幂等 |
| LLM 路由 | `agent/llm.py` | 小/大模型；`inspect_turn` |
| 安全 | `agent/security.py` | 注入拦截/降权 + 工具门禁；`reflection.py` 输出泄露检测；`routes.py` Bearer 鉴权 |
| Checkpoint | `agent/checkpointing.py` + `main.py` lifespan | Sqlite 默认 |
| 会话 | `agent/memory/session_memory.py` | 文件权威 + Redis 热缓存 |
| 限流 | `agent/memory/rate_limit.py` | Redis 或本地窗口 |
| RAG | `agent/knowledge/knowledge_base.py` | 关键词+向量；命中带来源/层级 |
| 对话日志 | `db/chat_log.py` | 表 `agent_chat_log` |
| 观测 | `agent/observability.py` | Langfuse Callback；无 Key 跳过 |
| 服务 | `agent/service.py` | chat / chat_stream |

Tool：**11 个**（analysis + business + external），见 `agent/tools/__init__.py`。

## 下一步主线

| 项 | 做什么 | 状态 |
|----|--------|------|
| 经营顾问主链路 | 查数 → 诊断 → 建议 | **已完成** |
| Langfuse | Callback 挂到图运行配置 | **已完成**（无 Key 跳过） |
| 历史 Agent 工程化 B0–B8 | 安全/测试/真值/健壮/清码/文档 | **已完成**；旧明细已从工作区移除，不再作为当前计划 |
| Wiki / LlamaIndex | 有长文再考虑 | 默认跳过 |
| B6：merchant_id 隔离、SSE 事件契约、/resume、配置后台、Skill/UI | 功能增强 | **已完成** |
| B7：复审修复（路径穿越/流式留痕/DB 语义/SSE 心跳/向量腿与持久化/检索验收） | 复审后修复 | **已完成** |

## 出问题改哪个文件

| 出问题 | 改哪个文件 |
|--------|------------|
| HTTP / SSE | `api/routes.py`, `schemas/chat.py` |
| 限流 | `agent/memory/rate_limit.py` |
| 进图前上下文 / RAG | `memory/context_builder.py`, `knowledge/` |
| 意图分错 | `perception.py`（规则）+ `workers/perceive.py`（接入） |
| 问候走错路 | `workers/dispatcher.py` |
| 复杂问题派错工人 | `supervisor.py` + `workers/supervisor_node.py` |
| 选错工具 | `workers/analyst.py`, `security.py` 门禁 |
| 查数结果不对 | `workers/execute_tools.py` + `tools/analysis/` 对应工具 |
| 建议文案不对 | `workers/strategist.py`, `prompts.py` 的 STRATEGIST |
| 最终回复不对 | `workers/call_llm.py`, `prompts.py` 的 SYSTEM_PROMPT |
| 越界没拦住 / 模型名漏出 | `workers/reflect.py`, `reflection.py` |
| 死循环 / 超时 | `guards.py`（以及 analyst/execute_tools 里的调用点） |
| 断点续跑 | `checkpointing.py`, `main.py` lifespan |
| 会话 ID 被拒 / 400-422（穿越、超长） | `schemas/chat.py` 的 `SESSION_ID_PATTERN`（请求体）+ `api/routes.py` 的 `Path(pattern=)`（路径参数） |
| 流式没数据 / 前端断流 / 没有 usage | `api/routes.py` 的 SSE 生产者-消费者与心跳；`agent/service.py:chat_stream` |
| 落盘缺行（失败或中断的轮次） | `agent/service.py:_persist_turn`（四条路径统一收尾） |
| 模型把「查不到」说成「没数据」 | `db/database.py:DBUnavailable` + `agent/guards.py` 的不重试分支 |
| 知识召回不准 / 想调 keywords | `agent/knowledge/knowledge_base.py`（`_vector_allowed`、`RAG_VECTOR_MIN_SCORE`、data/*.json）+ 先跑 `eval/run_retrieval_eval.py` |
| 历史日志查不到 / 端点 404 | `db/chat_log.py:list_session_logs` + `api/routes.py` 的 `/sessions/{id}/logs` |
| SSE 续播没回放 / id 不对 | `api/routes.py` 的 `_sse_buffers` + `_sse(event, data, event_id)`（**注意：无缓冲时会静默重跑整轮图，见 SPEC/03 G2**） |
| 多轮越问越贵 / 上下文里同句重复 | `agent/service.py:_initial_state` + `agent/memory/context_builder.py`（**checkpoint `messages` 通道累加不裁剪，见 SPEC/03 G1**） |

新人共同必读（约 30 分钟）：`api/routes.py` → `agent/service.py` → `agent/graph.py`。然后只深读上表自己那一行。

## 新对话必读（按需，勿整库）

0. **`docs/AI_WORKBENCH/`（唯一现行文档集）**：README → 01 产品 / 02 架构（Python 只读查库、AI 看板编排、偏好、规则 feed、SSE 上下文）/ 03 执行 / 04 UI 规格 / 05 API 契约（前后端并行唯一依据 + `contracts/*.example.json`）。**Java `backend/` 只读，一行都不能改**。前端在 `frontend-ui/`（Vue 3 + Vite + ECharts），后端在 `agent/workbench/` + `api/workbench_routes.py`。**数据事实**：`status=7` 不存在（退款=`status=6 AND pay_status=2`，无 refund_record，金额整单近似）、`order_detail.amount` 是单价（须 `amount*number`）、最新订单 2026-07-28（“昨日”默认回退最近 7 个完整日）、无 store_id/活动表/正式规则语料。
1. `AGENTS.md`（本文件）
2. `agent/graph.py` + `agent/supervisor.py` + `agent/workers/`
3. `agent/llm.py` + `agent/security.py` + `agent/service.py`
4. `agent/knowledge/knowledge_base.py` + `agent/knowledge/chunking.py`
5. `eval/cases.json` + `eval/run_eval.py`

## 启动备忘

```powershell
# Agent
cd "e:\苍穹\苍穹外卖\agent-service"
.\venv\Scripts\python.exe main.py

# 管理端（OpenSSL legacy 已在 package.json）
cd "e:\苍穹\苍穹外卖\admin-web"
npm run serve

# 新工作台 UI（独立于 admin-web）
cd "e:\苍穹\苍穹外卖\agent-service\frontend-ui"
npm install
npm run dev   # http://localhost:5173，/api 代理到 8100
```

- Agent：http://localhost:8100
- 前端：http://localhost:8888/ （顾问页一般 `/#/agent`）
- Embedding Key 无效时知识库会退回「仅关键词」——正常。**但 LLM 与 Embedding 现在分属两家（DeepSeek / 智谱），`EMBEDDING_API_KEY` 必须单独配**；缺 Key 时会在日志里留一行明确警告，不再静默拿 LLM 的 Key 去撞智谱（SPEC/03 N5.2b）。
- 向量阈值 `RAG_VECTOR_MIN_SCORE=0.52` 是**实测校准值**（正例 top1 ≥0.544、最强负例 0.495，带宽只有 ~0.05）。改它必须重跑 `eval/run_retrieval_eval.py --vector` 并核对负例干净度，0.45 会让无关知识直接注入 Prompt。
- Redis 未启动时会自动降级文件会话 + 本地限流。**注意：降级是粘滞的**——`redis_client._redis_failed` 一旦置位，本次进程内不再重连，须重启进程（SPEC/03 G6）。
- Langfuse：`.env` 配 `LANGFUSE_PUBLIC_KEY` / `SECRET_KEY` 后，对话会在 Langfuse 控制台成树；不配则跳过，主链路不变。`GET /health` 的 `langfuse` 字段可确认是否启用。

## 已知注意

- **无 git remote**：用户说远程先不推；需要时再 `git remote add` + push。
- 复杂路径较慢（analyst + strategist + reviewer + call_llm 多次 LLM），且工具是**顺序执行**（`execute_tools.py:44-66` 无 gather）。
- 近两周订单可能为 0 → 因子分解结果全零。**这不是"数据窗口问题"就完事**：当前 4 个 prompt 都没有"数据不足/全零时如何作答"的约束，模型会把全零当成真实结论输出（SPEC/03 G10，N4 批处理）。
- **两档模型路由当前未生效**：`.env` 未设 `LLM_MODEL_SIMPLE` → 小模型档回落到同一个模型，`LLM_ROUTE_CONFIDENCE_MIN` 与"小→大回退"分支都无法产生行为差异（SPEC/03 G5）。
- 全仓 `agent/ api/ db/ schemas/` 内 **0 处** TODO/FIXME/NotImplementedError；`nodes.py`、`LongTermMemory` 已物理删除，勿按旧文档查找。
