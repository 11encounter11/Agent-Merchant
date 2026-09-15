# AGENTS.md · 新对话请先读这份

> 给 Cursor / AI：**不要扫全库**。按本文 + `docs/INTERVIEW_COVERAGE.md` 继续。  
> 旧叙事（13 查询 Tool、接单主线）以**代码为准**；`README.md` / `CONTEXT.md` 部分过时。

---

## 移交快照（2026-09-15）

| 项 | 状态 |
|----|------|
| 产品 | 管理端**商家经营顾问**（查数→诊断→建议），端口 **8100** |
| 产品阶段 A | **已完成**（analyst 真调工具 + JSON 知识注入 + 顾问文案） |
| 面经 1–5 | **已完成**（护栏 / Supervisor / Checkpointer / Redis+日志 / 路由+安全+评测） |
| **下一个该做** | **面经阶段 6**（有条件）：RAG 命中来源可观测 |
| Git | 本地 `master` 已提交；**未配置 origin，未 push** |
| 前端欢迎语 | `admin-web` **不一定在本仓库**；顾问文案改过 `index.vue`，若另仓需自行提交 |

### 新对话第一句（复制即可）

```text
按 docs/INTERVIEW_COVERAGE.md 做阶段 6
```

### 最近本地提交（由新到旧）

| Commit | 说明 |
|--------|------|
| （待提交） | feat(interview-5): 模型路由 + 注入/门禁 + 最小评测 |
| `a2828d5` | feat(interview-4): Redis 会话/限流 + MySQL agent_chat_log |
| `1ed28d8` | feat(interview-3): Checkpointer + thread_id |
| `f830868` | feat(interview-2): Supervisor–Worker |
| `33a2a30` | feat(interview-1): 工程护栏 |
| `cc6e43a` | feat(phase-A): LangGraph 经营顾问闭环 + 面经方案落盘 |

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
| MCP | **当前不做**（口述「为何暂缓」即可） |
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
| 图 | `agent/graph.py` | Checkpointer 编译；`get_agent_graph()` |
| 调度 | `agent/supervisor.py` | 规则 Supervisor–Worker |
| 节点 | `agent/nodes.py` | 含护栏接入 |
| 护栏 | `agent/guards.py` | 步数/token/超时重试/幂等 |
| LLM 路由 | `agent/llm.py` | 小/大模型；`inspect_turn` |
| 安全 | `agent/security.py` | 注入拦截/降权 + 工具门禁 |
| Checkpoint | `agent/checkpointing.py` + `main.py` lifespan | Sqlite 默认 |
| 会话 | `agent/memory/session_memory.py` | 文件权威 + Redis 热缓存 |
| 限流 | `agent/memory/rate_limit.py` | Redis 或本地窗口 |
| 对话日志 | `db/chat_log.py` | 表 `agent_chat_log` |
| 服务 | `agent/service.py` | chat / chat_stream |
| 面经总表 | `docs/INTERVIEW_COVERAGE.md` | 写/不写标注 + 阶段验收 |

Tool：**11 个**（analysis + business + external），见 `agent/tools/__init__.py`。

## 下一步主线

| 阶段 | 做什么 | 状态 |
|------|--------|------|
| A / 面经 1–5 | 见上 | **已完成** |
| **面经-6（有条件）** | RAG 命中来源可观测 | **下一步** |
| B/C | Wiki / LlamaIndex | 默认跳过或有条件 |
| D/E/F | Skill、SSE agent 事件、UI、Langfuse | 可穿插 |

阶段 5 已完成；阶段 6 验收细节见 `docs/INTERVIEW_COVERAGE.md`。

## 新对话必读（按需，勿整库）

1. `AGENTS.md`（本文件）
2. `docs/INTERVIEW_COVERAGE.md`
3. `agent/graph.py` + `agent/supervisor.py` + `agent/nodes.py`
4. `agent/llm.py` + `agent/security.py` + `agent/service.py`
5. `agent/reflection.py`
6. `eval/interview5_cases.json` + `eval/run_eval.py`（阶段 5 最小评测）

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
- Embedding Key 无效时知识库会退回「仅关键词」——正常，勿当阶段失败。  
- Redis 未启动时会自动降级文件会话 + 本地限流。

## 已知注意

- **无 git remote**：用户说远程先不推；需要时再 `git remote add` + push。  
- 复杂路径较慢（analyst + strategist + reviewer + call_llm 多次 LLM）。  
- 近两周订单可能为 0 → 因子分解结果全零，属数据窗口问题。
