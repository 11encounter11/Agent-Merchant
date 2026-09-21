# AGENTS.md · 新对话请先读这份

> 给 Cursor / AI：**不要扫全库**。按本文继续。
> 回答只按产品与工程能力描述。
> 旧叙事已归档（`docs/_archive/`）；**权威文档 = `docs/REDESIGN/`**，与代码冲突时以代码为准并回写 REDESIGN。

---

## 移交快照（2026-09-21）

| 项 | 状态 |
|----|------|
| 产品 | 管理端**商家经营顾问**（查数→诊断→建议），端口 **8100** |
| 主链路 | **已完成**（analyst 真调工具 + JSON 知识注入 + 顾问文案） |
| 工程能力 | 护栏 / Supervisor / Checkpointer / Redis+日志 / 路由+安全+评测 / RAG 来源可观测 / Langfuse / **Bearer 鉴权 + CORS 白名单 + 限流防绕过 + 输出泄露检测** |
| **还债进度** | **B0 安全 ✅ B1 测试地基 ✅ B2 单一真值 ✅ B3 健壮性 ✅ B4 清死代码 ✅ B5 文档收口 ✅**（明细 `docs/REDESIGN/04`） |
| **下一个该做** | **B6 功能增强**：merchant_id 商家隔离（已裁决做）、SSE 事件类型化、/resume、配置后台、Skill/UI |
| 测试基线 | `pytest -q` **104 passed**；`eval/run_eval.py` 15/15；测试依赖在 `requirements-dev.txt` |
| Git | 本地 `master` 已提交；**未配置 origin，未 push**（推送需先 `git remote add`） |
| 前端 | `admin-web` 不在本仓库；配置 `AGENT_API_TOKEN` 后前端 `/api/*` 需带 Bearer 头 |

### 最近本地提交（由新到旧）

| Commit | 说明 |
|--------|------|
| （本批） | B5 文档收口：README 重写、过时文档归档加横幅、AGENTS.md 快照更新 |
| `72286bd` | B4 清死代码：删 nodes 转发层/骨架/死配置，阈值接线 |
| `4f917bb` | B3 健壮性：护栏留痕/限流前置/幂等 Redis/懒加载/图单例 R1–R10 |
| `63b41b5` | B2 单一真值：constants/节假日 JSON/成本系数/版本号 |
| `5e7a86e` | B0 安全止血：Bearer/CORS/限流防绕过/泄露检测/移除源码口令 |
| `f9873ef` | B1 测试地基：pytest 配置+冒烟 29 例+monkeypatch 改造 |
| `e6c76e6` | REDESIGN 文档驱动基线（01–05 + BUGFIX_LOG） |
| `31ecd46` | 基线快照：节点拆分 workers + RAG 可观测 + Langfuse |

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
| 还债 B0–B5 | 安全/测试/真值/健壮/清码/文档 | **已完成**（见 `docs/REDESIGN/04` 批次表） |
| Wiki / LlamaIndex | 有长文再考虑 | 默认跳过 |
| B6：merchant_id 隔离、SSE 事件契约、/resume、配置后台、Skill/UI | 功能增强 | **下一批** |

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

新人共同必读（约 30 分钟）：`api/routes.py` → `agent/service.py` → `agent/graph.py`。然后只深读上表自己那一行。

## 新对话必读（按需，勿整库）

0. **`docs/REDESIGN/`（2026-09-20 起权威）**：README 索引 + 01 需求 / 02 架构 / 03 功能 / 04 差距与还债计划 / 05 测试计划 + BUGFIX_LOG。**改代码先对 04 登记，改 bug 必登 BUGFIX_LOG**；与旧文档冲突以 REDESIGN 为准。
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
```

- Agent：http://localhost:8100
- 前端：http://localhost:8888/ （顾问页一般 `/#/agent`）
- Embedding Key 无效时知识库会退回「仅关键词」——正常。
- Redis 未启动时会自动降级文件会话 + 本地限流。
- Langfuse：`.env` 配 `LANGFUSE_PUBLIC_KEY` / `SECRET_KEY` 后，对话会在 Langfuse 控制台成树；不配则跳过，主链路不变。`GET /health` 的 `langfuse` 字段可确认是否启用。

## 已知注意

- **无 git remote**：用户说远程先不推；需要时再 `git remote add` + push。
- 复杂路径较慢（analyst + strategist + reviewer + call_llm 多次 LLM）。
- 近两周订单可能为 0 → 因子分解结果全零，属数据窗口问题。
