# AGENTS.md · 新对话请先读这份

> 给 Cursor / AI：不要扫全库。按本文继续。细节设计见 `DESIGN.md`；旧叙事（13 查询 Tool、接单主线）以**代码为准**，`README.md` / `CONTEXT.md` 部分过时。

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
| LLM Wiki | **默认不做**（SOP 膨胀、要跨页合成时再考虑） |
| LlamaIndex | **有条件**：有长文语料后再上，并替换手写 chromadb（二选一） |
| MCP | 当前不做 |
| Skill | 后期自研业务 Skill；前期不为 Wiki 预留空壳 |

## 当前代码现实（读代码时别被旧文档带偏）

- 图：`perceive → dispatcher → supervisor ⇄ (analyst/tools|strategist|reviewer) → call_llm → reflect`，见 `agent/graph.py`
- Tool：**11 个**（analysis + business + external），见 `agent/tools/__init__.py`；旧 sales/order 工具已删
- 阶段 A 已修：analyst 真调工具、知识注入、顾问文案
- 面经-1 护栏、面经-2 Supervisor、面经-3 Checkpointer 已落地（见 `docs/INTERVIEW_COVERAGE.md`）
- 启动：`.\venv\Scripts\python.exe main.py`；admin-web 需 OpenSSL legacy（`package.json` 已写）

## 下一步主线（按顺序做）

| 阶段 | 做什么 | 状态 |
|------|--------|------|
| **A** | 修通 analyst 真调工具；注入现有 JSON 知识；改顾问文案 | **已完成** |
| **面经-1** | 护栏：步数 / token 预算 / 工具超时重试 / 入参兜底 | **已完成** |
| **面经-2** | Supervisor 多角色 | **已完成** |
| **面经-3** | Checkpointer + thread_id 断点恢复 | **已完成** |
| **面经-4（当前）** | Redis 会话/限流 + MySQL 对话日志表 | **下一步** |
| B（可选） | 精简 Wiki——默认可跳过 | 后置 |
| C（有条件） | 有长文后上 LlamaIndex，退役 chromadb | 后置 |
| D | 业务 Skill + SSE `agent` 事件（Supervisor 已先做） | 可与面经后续穿插 |
| E | 对话 UI：快捷芯片、专家/工具状态、数据卡 | 可与 D 穿插 |
| F / 面经-5 | 新题集评测、引用脚注、可选 Langfuse | 收尾 |

> **面经工程完整方案**：见 [`docs/INTERVIEW_COVERAGE.md`](docs/INTERVIEW_COVERAGE.md)。  
> 重开对话可说：`按 docs/INTERVIEW_COVERAGE.md 做阶段 4`

验收 A：「为什么营业额下降」能跑出因子分解类工具，且规定类问题能用上 JSON 知识。

## 新对话怎么开（省 token）

第一句直接说其一即可：

- `按 docs/INTERVIEW_COVERAGE.md 做阶段 4`（Redis+日志，当前）
- `按 docs/INTERVIEW_COVERAGE.md 做阶段 3`（Checkpointer，已完成）
- `按 docs/INTERVIEW_COVERAGE.md 做阶段 2`（Supervisor，已完成）
- `按 docs/INTERVIEW_COVERAGE.md 做阶段 1`（护栏，已完成）
- `按 AGENTS.md 讨论阶段 E 的 UI`
- `先读 AGENTS.md，不要全库扫描`

必读文件（按需打开，勿整库）：

1. `AGENTS.md`（本文件）
2. `docs/INTERVIEW_COVERAGE.md`（面经覆盖：写/不写 + 阶段计划）
3. `agent/graph.py` + `agent/nodes.py`
4. `agent/service.py` + `agent/memory/context_builder.py`
5. `agent/tools/__init__.py`
6. 前端：`../admin-web/src/views/agent/index.vue`

## 启动备忘

```powershell
# Agent
cd "e:\苍穹\苍穹外卖\agent-service"
.\venv\Scripts\python.exe main.py

# 管理端
cd "e:\苍穹\苍穹外卖\admin-web"
npm run serve
```
