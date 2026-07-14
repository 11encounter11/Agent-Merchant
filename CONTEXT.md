# 苍穹外卖 - 商家智能助手 Agent 项目上下文文档

> **用途**：当对话过长导致 AI 出现幻觉时，开一个新对话，把本文件发给 AI，它可以立即了解当前项目状态并继续工作。

---

## 一、项目概述

- **项目名**：苍穹外卖 - 商家智能助手 Agent
- **目标**：为苍穹外卖的管理端（admin-web）新增一个智能客服 Agent，面向**商家（店铺运营者）**，通过对话式交互辅助经营数据查询、订单处理、菜品管理和运营建议
- **管理端用户定位**：商家（外卖店铺运营者），不是平台管理员，也不是消费者

---

## 二、技术栈

| 组件 | 选型 | 说明 |
|------|------|------|
| Agent 框架 | **LangGraph**（图式，1.2.9） | 支持循环和条件分支，适合 Agent |
| Web 框架 | **FastAPI**（0.139.0） | Python 异步 Web 框架 |
| LLM 模型 | **qwen-max**（通义千问） | 通过 DashScope OpenAI 兼容接口调用 |
| 向量数据库 | **chromadb** | RAG 知识库，DashScope text-embedding-v3 |
| 数据库 | **MySQL**（sky_take_out） | 本地已部署，含 800 条测试数据 |
| 前端 | **Vue 2 + Element UI** | 已有项目，对话 UI 已完成 |
| Java 后端 | **Spring Boot 2.7.3** | 已有项目，监听 8080 端口 |
| Agent 服务 | FastAPI | 监听 **8100 端口** |

---

## 三、教学模式

- **模式 C（混合模式）**：简单的我写好让学员理解，核心的带学员一起写，优化迭代教学员方法论
- **学员基础**：
  - Python：基础语法会一些，很多语法不会，学过 LangChain/LangGraph 初步
  - Spring Boot：只了解少量注解含义，很多步骤不清楚
- **教学风格要求**：
  - 每段代码加详细中文注释
  - Java 类比仅限于 FastAPI 接口层（路由、中间件），其他部分不用 Java 类比
  - 核心知识点要先讲原理再写代码
  - Prompt 要带着学员一起迭代，不能一次给最终版
  - 每个阶段开始前，先给出"开发顺序清单"（先写什么文件、再写什么、为什么）

---

## 四、项目目录结构

```
e:/苍穹/苍穹外卖/
├── backend/                          # Java 后端（Spring Boot，已有，不动）
├── admin-web/                        # 管理端前端（Vue 2，已有）
│   └── src/
│       ├── views/agent/index.vue     # 对话页面（已完成）
│       ├── api/agent.ts              # SSE 流式 API 封装
│       └── router.ts                 # 路由（含 /agent 路径）
├── agent-service/                    # Python Agent 服务
│   ├── main.py                       # FastAPI 入口 + 日志初始化
│   ├── config.py                     # 配置管理（Pydantic Settings）
│   ├── .env                          # 环境变量（不提交 Git）
│   ├── requirements.txt              # Python 依赖
│   ├── run_eval.py                   # 50 题单轮评测脚本
│   ├── run_multiturn_eval.py         # 15 组多轮对话评测脚本
│   ├── eval_dataset.json             # 50 题评测集
│   ├── eval_multiturn.json           # 15 组多轮对话评测集
│   ├── test_framework.py             # 7 大模块框架验证脚本
│   ├── CONTEXT.md                    # 本文件
│   ├── agent/
│   │   ├── chat_agent.py             # [规划模块] LangGraph 图 + 对外接口
│   │   ├── prompts.py                # [规划模块] System Prompt v3
│   │   ├── perception.py             # [感知模块] 输入预处理 + 意图分类
│   │   ├── memory.py                 # [记忆模块] 会话记忆 + 知识记忆
│   │   ├── reflection.py             # [反思模块] 输出校验/身份/边界
│   │   ├── logging_config.py         # [日志模块] 统一日志配置
│   │   ├── session.py                # [记忆-工作记忆] JSON 文件持久化
│   │   ├── knowledge/                # [记忆-长期记忆] RAG 知识库
│   │   │   ├── knowledge_base.py     # 混合检索（关键词 + 向量）
│   │   │   └── data/                 # 知识文档（JSON 格式）
│   │   │       ├── holidays.json     # 节假日日期表
│   │   │       ├── dish_aliases.json # 菜品别名映射
│   │   │       ├── boundary.json     # 能力边界规则
│   │   │       ├── identity.json     # 身份声明规则
│   │   │       └── faq.json          # 常见问答模板
│   │   └── tools/                    # [工具模块]
│   │       ├── tool_registry.py      # 统一注册/调用/日志
│   │       ├── sales_tools.py        # 营业额/订单/用户（查 MySQL）
│   │       ├── dish_tools.py         # 菜品列表/搜索（查 MySQL）
│   │       └── order_action_tools.py # 接单/拒单/停售/起售（调 Java API）
│   ├── db/
│   │   └── database.py               # MySQL 异步连接（aiomysql）
│   ├── schemas/
│   │   └── chat.py                   # ChatRequest / ChatResponse 模型
│   ├── docs/
│   │   └── PROJECT_RETROSPECTIVE.md  # 项目问题回顾文档
│   ├── eval_results/                 # 评测结果目录
│   ├── logs/                         # 日志目录
│   └── data/sessions/                # 会话持久化目录
└── database/
    └── sky.sql                       # 数据库建表 SQL
```

---

## 五、已完成的阶段（全部 7 个阶段）

### 阶段 1-5：核心功能 ✅
- FastAPI 骨架 + CORS + 健康检查
- LLM 接入（qwen-max）+ SSE 流式输出
- MySQL 异步连接 + 9 个业务 Tool
- Java API 对接（JWT token 认证）
- 多轮对话 + 会话管理

### 阶段 6：前端对话 UI ✅
- Vue 2 对话页面（`views/agent/index.vue`）
- SSE 流式渲染 + Markdown 渲染 + 打字机效果
- Tool 调用状态展示（🔧 正在查询营业额...）

### 阶段 7：测试 + 优化 ✅
- 50 题评测集 + 自动评测脚本
- 评测通过率：**96%**（48/50，2 题为启动瞬态问题）
- 3 个模型对比测试（deepseek-chat / deepseek-v4-pro / qwen-max）

### 架构升级：7 大正交模块 ✅
参照生产级 Agent 架构，拆分为 7 个独立模块：
1. **通信模块**（main.py）：FastAPI + SSE 流式协议
2. **感知模块**（perception.py）：输入清洗 + 意图预分类
3. **记忆模块**（memory.py + session.py + knowledge/）：三层记忆
4. **规划模块**（chat_agent.py + prompts.py）：LangGraph ReAct 循环
5. **工具模块**（tools/ + tool_registry.py）：9 个工具 + 统一注册
6. **反思模块**（reflection.py）：身份检查 + 边界拦截
7. **日志模块**（logging_config.py）：控制台 + 文件双输出

### 近期改进 ✅
- **RAG 混合检索**：关键词匹配层 + DashScope 中文 embedding（text-embedding-v3）
- **会话持久化**：session.py 从内存 dict 改为 JSON 文件存储
- **多轮对话评测**：15 组多轮对话测试用例
- **Tool 调用状态展示**：SSE 新增 tool_call / tool_result 事件
- **Bug 修复**：5 个 Bug（E10 身份替换、A10 按天拆分、C04/D04 停售查询、E03 边界拒绝、A09 端午节日期）
- **RAG 知识库填充**：24 条知识（5 个 JSON 文件）

---

## 六、当前状态 & 下一步

### 当前状态
- 7 个阶段全部完成
- 7 大模块架构已搭建
- RAG 知识库已填充（混合检索）
- 评测通过率 96%
- 项目回顾文档已创建

### 下一步可选方向

**中期改进**：
1. 中文 embedding 优化（修复 A01/A10 启动瞬态 500 错误）
2. 会话管理 UI（前端增加历史会话列表/切换）
3. Token 消耗监控（记录每次 LLM 调用的 token 数）

**远期改进**：
1. 意图预分类（轻量模型做快速意图识别，减少 LLM 调用）
2. 主动推送（Agent 主动提醒商家）
3. 经营报告生成（定时生成日/周/月经营分析）
4. 多 Agent 协作（拆分为数据查询 Agent + 运营建议 Agent）

---

## 七、7 大模块架构详解

### 数据流

```
用户输入 → [通信模块] → [感知模块:清洗] → [记忆模块:组装上下文] → [规划模块:LLM] → 要不要调Tool?
                                                                                    ↓ 要           ↓ 不要
                                                                              [工具模块]      [反思模块:校验] → [通信模块] → 用户
                                                                                ↓
                                                                          回到 [规划模块]
```

### 各模块职责

| 模块 | 文件 | 职责 |
|------|------|------|
| 通信 | main.py | FastAPI 服务，定义 API 接口（/api/agent/chat, /api/agent/chat/stream） |
| 感知 | perception.py | 输入清洗（去空格/控制字符），预留意图分类接口 |
| 记忆 | memory.py + session.py + knowledge/ | 工作记忆（对话历史 JSON 文件）+ 长期记忆（RAG 向量检索） |
| 规划 | chat_agent.py + prompts.py | LangGraph 有向图编排，ReAct 循环（思考→行动→观察） |
| 工具 | tools/ + tool_registry.py | 9 个业务工具，统一注册/调用/日志/错误处理 |
| 反思 | reflection.py | 输出校验（身份关键词替换、边界拦截） |
| 日志 | logging_config.py | 统一日志配置（控制台 + logs/agent.log） |

---

## 八、RAG 知识库

### 混合检索策略

检索分三层，合并去重后返回 top_k 条结果：

1. **关键词规则匹配**（KEYWORD_RULES）：确定性最高，只要用户输入包含关键词就返回
2. **文档关键词匹配**（data/ 中 JSON 的 keywords 字段）
3. **向量语义检索**（chromadb + DashScope text-embedding-v3）：处理模糊表达

### 知识文档

| 文件 | 内容 | 条数 |
|------|------|------|
| holidays.json | 节假日日期表（端午/中秋/国庆等） | 7 条 |
| dish_aliases.json | 菜品别名映射（素菜=新鲜时蔬） | 7 条 |
| boundary.json | 能力边界规则（营销文案拒绝话术） | 3 条 |
| identity.json | 身份声明规则（不暴露模型名） | 3 条 |
| faq.json | 常见问答模板（打招呼/退款/打折） | 4 条 |

---

## 九、9 个 Tool 清单

| Tool | 功能 | 参数 | 实现方式 |
|------|------|------|---------|
| query_turnover | 查询营业额 | begin_date, end_date, **group_by_day** | 查 MySQL |
| query_order_count | 查询订单统计 | begin_date, end_date | 查 MySQL |
| query_user_stats | 查询用户统计 | begin_date, end_date | 查 MySQL |
| query_dish_list | 查询菜品列表 | category_name, **status** | 查 MySQL |
| query_dish_by_name | 按名搜索菜品 | dish_name | 查 MySQL |
| accept_order | 接单 | order_id | 调 Java API |
| reject_order | 拒单 | order_id, reason | 调 Java API |
| stop_dish | 停售菜品 | dish_id | 调 Java API |
| start_dish | 起售菜品 | dish_id | 调 Java API |

加粗参数为最近新增的参数。

---

## 十、评测结果

### 单轮评测（50 题）
- 评测脚本：`run_eval.py`
- 评测集：`eval_dataset.json`（5 大类 × 10 题）
- 最新通过率：**96%**（48/50）
- 失败项：A01/A10 为启动瞬态 500 错误（DashScope embedding 初始化延迟）

### 多轮对话评测（15 组）
- 评测脚本：`run_multiturn_eval.py`
- 评测集：`eval_multiturn.json`（15 组多轮对话）
- 覆盖场景：上下文指代、条件修改、否定修正、批量操作、经营建议追问

---

## 十一、关键配置信息

| 配置项 | 值 |
|--------|-----|
| Agent 服务端口 | 8100 |
| Java 后端端口 | 8080 |
| 前端开发服务器端口 | 8888 |
| MySQL 数据库名 | sky_take_out |
| MySQL 密码 | 123456 |
| Redis 密码 | 123456 |
| LLM 模型 | qwen-max（通义千问，阿里云 DashScope） |
| LLM API Base URL | https://dashscope.aliyuncs.com/compatible-mode/v1 |
| Embedding 模型 | text-embedding-v3（DashScope） |
| LLM API Key 变量名 | LLM_API_KEY（在 .env 中配置） |
| Python 版本 | 3.12.4 |
| Node 版本 | 24.18.0（通过 nvm 管理） |
| Java 后端登录 | POST /admin/employee/login，admin / 123456 |
| Java API Token Header | `token: <jwt_token>` |

---

## 十二、启动方式

```powershell
# 1. 启动 Agent 服务（必须用 venv 的 Python）
cd "e:\苍穹\苍穹外卖\agent-service"
.\venv\Scripts\python.exe main.py

# 2. 确保 Java 后端在跑（IDEA 运行 SkyApplication）

# 3. 启动前端（阶段 6 需要）
cd "e:\苍穹\苍穹外卖\admin-web"
$env:NODE_OPTIONS = "--openssl-legacy-provider"
npm run serve

# 4. 跑评测
.\venv\Scripts\python.exe run_eval.py              # 50 题单轮评测
.\venv\Scripts\python.exe run_multiturn_eval.py     # 15 组多轮评测
.\venv\Scripts\python.exe test_framework.py         # 框架验证
```

---

## 十三、Git commit 记录

```
f8345bd fix: 修复5个Bug + 填充RAG知识库 + 回归测试98% + 项目回顾文档
463b6ae feat: 7大模块架构搭建(感知/记忆/RAG知识库/工具管理/反思/日志)
b2ef00f feat: 阶段7 - 切换qwen-max模型(100%通过率) + Bug分析
92fd6ad docs: deepseek-chat vs deepseek-v4-pro 对比评测分析
9b891ef docs: 第一轮评测Bug记录(6个问题) + 企业测试方法论
ee17f8e feat: 阶段7 - 添加评测集(50题)和自动测试脚本
0c40b0c feat: 阶段6 Prompt迭代 - 日期注入改用V2模板
3cd93c2 fix: Prompt动态注入当前日期
0a92dc0 docs: 更新CONTEXT.md交接文档(阶段1-5全部完成)
3771abe fix: 菜品停售/起售恢复走Java API
aed07a1 fix: 菜品停售/起售改为直接DB操作
c39b3b8 fix: 修复流程图生成代码
abe84bf feat: 阶段3-5整合提交
9e8f34c feat: 阶段5 - 多轮对话会话管理
be5af20 feat: 阶段4 - 菜品查询Tool+订单操作Tool+Prompt v3
a53bf83 feat: 阶段3 - 数据库连接+经营数据查询Tool+Prompt v2
210c703 feat: 阶段2 - 接入DeepSeek+LangGraph Agent+SSE流式输出
cbc08e5 docs: 添加项目上下文交接文档
8053f2f feat: 阶段1 - 项目初始化
```

---

## 十四、给新对话的指令

当用户把本文件发给你时，你应该：
1. 阅读本文件，了解项目全貌和当前进度
2. 确认当前状态（第六节）
3. 按教学模式（第三节）的风格继续教学
4. 每个任务开始前，先给出"开发顺序清单"（先写什么文件、再写什么、为什么）
5. 先确认用户是否已理解相关代码，再继续新内容
# 苍穹外卖 - 商家智能助手 Agent 项目上下文文档

> **用途**：当对话过长导致 AI 出现幻觉时，开一个新对话，把本文件发给 AI，它可以立即了解当前项目状态并继续工作。

---

## 一、项目概述

- **项目名**：苍穹外卖 - 商家智能助手 Agent
- **目标**：为苍穹外卖的管理端（admin-web）新增一个智能客服 Agent，面向**商家（店铺运营者）**，通过对话式交互辅助经营数据查询、订单处理、菜品管理和运营建议
- **管理端用户定位**：商家（外卖店铺运营者），不是平台管理员，也不是消费者

---

## 二、技术栈

| 组件 | 选型 | 说明 |
|------|------|------|
| Agent 框架 | **LangGraph**（图式，1.2.9） | 支持循环和条件分支，适合 Agent |
| Web 框架 | **FastAPI**（0.139.0） | Python 异步 Web 框架 |
| LLM 模型 | **DeepSeek** API | 兼容 OpenAI 协议，用 langchain-openai 调用 |
| 数据库 | **MySQL**（sky_take_out） | 本地已部署，含800条测试数据 |
| 前端 | **Vue 2 + Element UI** | 已有项目，需新增对话组件 |
| Java 后端 | **Spring Boot 2.7.3** | 已有项目，监听 8080 端口 |
| 前端开发服务器 | Vue CLI | 监听 8888 端口 |
| Agent 服务 | FastAPI | 监听 **8100 端口** |
| 版本管理 | Git | 本地仓库已初始化 |

---

## 三、教学模式

- **模式 C（混合模式）**：简单的我写好让学员理解，核心的带学员一起写，优化迭代教学员方法论
- **学员基础**：
  - Python：基础语法会一些，很多语法不会，学过 LangChain/LangGraph 初步
  - Spring Boot：只了解少量注解含义，很多步骤不清楚
  - **重要**：类比 Spring Boot 时需要讲解更细致，不能假设学员理解完整的 Spring Boot 流程
- **教学风格要求**：
  - 每段代码加详细中文注释
  - Java 类比仅限于 FastAPI 接口层（路由、中间件），其他部分不用 Java 类比
  - 核心知识点要先讲原理再写代码
  - Prompt 要带着学员一起迭代，不能一次给最终版
  - 每个阶段开始前，先给出"开发顺序清单"（先写什么文件、再写什么、为什么）

---

## 四、项目目录结构

```
e:/苍穹/苍穹外卖/
├── backend/                          # Java 后端（Spring Boot，已有，不动）
├── admin-web/                        # 管理端前端（Vue 2，已有）
├── agent-service/                    # 【新建】Python Agent 服务
│   ├── main.py                       # FastAPI 入口
│   ├── config.py                     # 配置管理（Pydantic Settings）
│   ├── .env                          # 环境变量（不提交 Git）
│   ├── .gitignore
│   ├── requirements.txt              # Python 依赖
│   ├── LEARNING_PROGRESS.md          # 学习进度文档
│   ├── CONTEXT.md                    # 本文件
│   ├── venv/                         # Python 虚拟环境（不提交 Git）
│   ├── agent/
│   │   ├── chat_agent.py             # Agent 核心（LangGraph 图 + 接口函数）
│   │   ├── prompts.py                # System Prompt（当前 v3）
│   │   ├── session.py                # 会话管理（多轮对话历史存储）
│   │   └── tools/
│   │       ├── sales_tools.py        # 营业额/订单/用户统计（查 MySQL）
│   │       ├── dish_tools.py         # 菜品列表/搜索（查 MySQL）
│   │       └── order_action_tools.py # 接单/拒单/停售/起售（调 Java API）
│   ├── db/
│   │   └── database.py               # MySQL 异步连接（aiomysql）
│   ├── schemas/
│   │   └── chat.py                   # ChatRequest / ChatResponse 模型
│   ├── generate_test_data.py         # 测试数据生成脚本
│   ├── test_multiturn.py             # 多轮对话测试脚本
│   └── graph学习/                     # 学员自学 LangGraph 的练习文件
└── database/
    └── sky.sql                       # 数据库建表 SQL
```

---

## 五、已完成的阶段（1-5）

### 阶段 1：项目初始化 + 环境搭建 ✅
- FastAPI 骨架、CORS、健康检查
- Pydantic Settings 配置管理
- Python 虚拟环境 + 依赖安装
- Git 初始化

### 阶段 2：接入 DeepSeek + 对话接口 ✅
- `agent/prompts.py`：System Prompt v1（角色定义 + 能力边界）
- `schemas/chat.py`：ChatRequest / ChatResponse 数据模型
- `agent/chat_agent.py`：LangGraph 图（State → call_llm 节点 → END）
- `main.py`：`/api/agent/chat`（非流式）和 `/api/agent/chat/stream`（SSE 流式）
- Prompt v1 → v2 迭代

### 阶段 3：数据库连接 + 查询 Tool ✅
- `db/database.py`：aiomysql 异步连接 + `execute_query()` 通用查询
- `agent/tools/sales_tools.py`：3 个 Tool（query_turnover、query_order_count、query_user_stats）
- LangGraph 图升级：加入 ToolNode + 条件边（should_continue）
- Prompt v2（告诉 LLM 有哪些工具 + 日期格式要求）
- `generate_test_data.py`：生成 800 条订单 + 50 个用户 + 6 个套餐的测试数据

### 阶段 4：扩展 Tool + Java API 对接 ✅
- `agent/tools/dish_tools.py`：2 个 Tool（query_dish_list、query_dish_by_name）
- `agent/tools/order_action_tools.py`：4 个 Tool（accept_order、reject_order、stop_dish、start_dish）
  - 接单/拒单：通过 httpx 调用 Java 后端 REST API（JWT token 认证）
  - 停售/起售：通过 httpx 调用 Java 后端 REST API
- Token 管理机制：登录获取 token → 缓存 → 自动续期
- Prompt v3（加入操作类工具说明 + 安全规则）

### 阶段 5：多轮对话 + 会话管理 ✅
- `agent/session.py`：会话存储模块（get_history / save_history / clear_history）
- `chat_agent.py` 改造：加载历史 → 拼新消息 → 跑图 → 存回历史
- MAX_HISTORY = 20（防止上下文过长）
- 多轮对话测试通过（"那2024年呢"能正确理解上下文）

---

## 六、当前阶段 & 下一步

### 当前：阶段 7 - 全面测试 + Prompt 深度优化（进行中）

**已完成**：
- 构建 50 题评测集（`eval_dataset.json`，5 大类 × 10 题）
- 编写自动测试脚本（`run_eval.py`，支持按类别/ID 过滤）
- 完成 3 个模型对比测试：
  - deepseek-chat：自动 98%，人工发现 6 个 Bug（4个日期错误）
  - deepseek-v4-pro：自动 94%，人工发现 2 个 Bug（0个日期错误，但慢 2.5 倍）
  - **qwen-max（当前使用）**：自动 100%，人工发现 3 个 Bug
- 建立 Bug 跟踪机制（`eval_results/BUG_qwen-max.md`）
- 学习企业级测试方法论（`docs/AGENT_TESTING_GUIDE.md`）

**qwen-max 当前 Bug（待修复）**：
1. BUG-001: 端午节日期推算错误（A09）→ Prompt 补充节假日参考
2. BUG-002: 营销文案没有拒绝（E03）→ Prompt 加强能力边界
3. BUG-003: 暴露了底层模型身份（E10）→ Prompt 加强身份约束

**工具层 Bug（两个模型都有，需改代码）**：
- 营业额无法按天拆分（A10）→ 新增 Tool 或扩展 query_turnover
- 无法查询已停售菜品（C04, D04）→ query_dish_list 加 status 参数

### 下一步
1. 修复 qwen-max 的 3 个 Prompt Bug
2. 修复工具层 Bug（按天营业额、停售菜品查询）
3. 修复后跑回归测试，对比准确率
4. 补充多轮对话测试（当前评测集是无记忆独立会话）

---

## 七、9 个 Tool 清单

| Tool | 功能 | 实现方式 | 所在文件 |
|------|------|---------|---------|
| query_turnover | 查询营业额 | 查 MySQL | sales_tools.py |
| query_order_count | 查询订单统计 | 查 MySQL | sales_tools.py |
| query_user_stats | 查询用户统计 | 查 MySQL | sales_tools.py |
| query_dish_list | 查询菜品列表 | 查 MySQL | dish_tools.py |
| query_dish_by_name | 按名搜索菜品 | 查 MySQL | dish_tools.py |
| accept_order | 接单 | 调 Java API | order_action_tools.py |
| reject_order | 拒单 | 调 Java API | order_action_tools.py |
| stop_dish | 停售菜品 | 调 Java API | order_action_tools.py |
| start_dish | 起售菜品 | 调 Java API | order_action_tools.py |

---

## 八、Prompt 版本记录

| 版本 | 改动 | 测试结果 |
|------|------|---------|
| v1 | 基础角色定义 + 能力边界 | 闲聊正常，问数据说"还在学习中" |
| v2 | 加入工具说明 + 日期格式要求 | 能正确调用 3 个查询 Tool |
| v3 | 加入操作类工具 + 安全规则 | 9 个 Tool 全部可用 |

---

## 九、关键配置信息

| 配置项 | 值 |
|--------|-----|
| Agent 服务端口 | 8100 |
| Java 后端端口 | 8080 |
| 前端开发服务器端口 | 8888 |
| MySQL 数据库名 | sky_take_out |
| MySQL 密码 | 123456 |
| Redis 密码 | 123456 |
| LLM 模型 | qwen-max（通义千问，阿里云 DashScope） |
| LLM API Base URL | https://dashscope.aliyuncs.com/compatible-mode/v1 |
| LLM API Key 变量名 | LLM_API_KEY（在 .env 中配置） |
| Python 版本 | 3.12.4 |
| Node 版本 | 24.18.0（通过 nvm 管理） |
| Java 后端登录 | POST /admin/employee/login，admin / 123456 |
| Java API Token Header | `token: <jwt_token>` |

---

## 十、数据库关键表

| 表名 | 说明 | 数据量 |
|------|------|--------|
| orders | 订单表（状态 1-7） | 800 条（2024-2026） |
| order_detail | 订单明细 | 1931 条 |
| dish | 菜品表 | 24 道 |
| setmeal | 套餐表 | 6 个 |
| category | 分类表 | 10 个 |
| employee | 员工表 | 6 人 |
| user | 用户表 | 52 人 |

**订单状态码**：1=待付款, 2=待接单, 3=已接单, 4=派送中, 5=已完成, 6=已取消, 7=退款

---

## 十一、Git commit 记录

```
3771abe fix: 菜品停售/起售恢复走Java API(Redis密码问题已修复)
aed07a1 fix: 菜品停售/起售改为直接DB操作(Java后端菜品接口500错误)
c39b3b8 fix: 修复流程图生成代码(get_graph调用对象错误)
abe84bf feat: 阶段3-5整合提交
9e8f34c feat: 阶段5 - 多轮对话会话管理
be5af20 feat: 阶段4 - 菜品查询Tool+订单操作Tool+Prompt v3
a53bf83 feat: 阶段3 - 数据库连接+经营数据查询Tool+Prompt v2
210c703 feat: 阶段2 - 接入DeepSeek+LangGraph Agent+SSE流式输出
cbc08e5 docs: 添加项目上下文交接文档
8053f2f feat: 阶段1 - 项目初始化
```

---

## 十二、启动方式

```powershell
# 1. 启动 Agent 服务
cd "e:\苍穹\苍穹外卖\agent-service"
.\venv\Scripts\python.exe main.py

# 2. 确保 Java 后端在跑（IDEA 运行 SkyApplication）

# 3. 阶段 6 时需要启动前端
cd "e:\苍穹\苍穹外卖\admin-web"
$env:NODE_OPTIONS = "--openssl-legacy-provider"
npm run serve
```

---

## 十三、给新对话的指令

当用户把本文件发给你时，你应该：
1. 阅读本文件，了解项目全貌和当前进度
2. 确认当前阶段（第六节"当前阶段"部分）
3. 按教学模式（第三节）的风格继续教学
4. 每个阶段开始前，先给出"开发顺序清单"（先写什么、再写什么、为什么）
5. 先确认用户是否已阅读上一阶段的代码，再继续新内容
# 苍穹外卖 - 商家智能助手 Agent 项目上下文文档

> **用途**：当对话过长导致 AI 出现幻觉时，开一个新对话，把本文件发给 AI，它可以立即了解当前项目状态并继续工作。

---

## 一、项目概述

- **项目名**：苍穹外卖 - 商家智能助手 Agent
- **目标**：为苍穹外卖的管理端（admin-web）新增一个智能客服 Agent，面向**商家（店铺运营者）**，通过对话式交互辅助经营数据查询、订单处理、菜品管理和运营建议
- **管理端用户定位**：商家（外卖店铺运营者），不是平台管理员，也不是消费者

---

## 二、技术栈

| 组件 | 选型 | 说明 |
|------|------|------|
| Agent 框架 | **LangGraph**（图式，1.2.9） | 支持循环和条件分支，适合 Agent |
| Web 框架 | **FastAPI**（0.139.0） | Python 异步 Web 框架，类比 Spring Boot |
| LLM 模型 | **DeepSeek** API | 兼容 OpenAI 协议，用 langchain-openai 调用 |
| 数据库 | **MySQL**（sky_take_out） | 本地已部署，已有数据 |
| 前端 | **Vue 2 + Element UI** | 已有项目，需新增对话组件 |
| Java 后端 | **Spring Boot 2.7.3** | 已有项目，监听 8080 端口 |
| 前端开发服务器 | Vue CLI | 监听 8888 端口 |
| Agent 服务 | FastAPI | 监听 **8100 端口** |
| 版本管理 | Git | 本地仓库已初始化 |

---

## 三、教学模式

- **模式 C（混合模式）**：简单的我写好让学员理解，核心的带学员一起写，优化迭代教学员方法论
- **学员基础**：
  - Python：基础语法会一些，很多语法不会，学过 LangChain/LangGraph 初步
  - Spring Boot：只了解少量注解含义，很多步骤不清楚
  - **重要**：类比 Spring Boot 时需要讲解更细致，不能假设学员理解完整的 Spring Boot 流程
- **教学风格要求**：
  - 每段代码加详细中文注释
  - 用 Java 类比帮助理解，但要解释清楚 Java 端在做什么
  - 核心知识点要先讲原理再写代码
  - Prompt 要带着学员一起迭代，不能一次给最终版

---

## 四、项目目录结构

```
e:/苍穹/苍穹外卖/
├── backend/                          # Java 后端（Spring Boot，已有，不动）
│   ├── sky-common/
│   ├── sky-pojo/
│   └── sky-server/                   # 主服务，监听 8080 端口
├── admin-web/                        # 管理端前端（Vue 2，已有）
│   └── src/
│       ├── views/                    # 页面组件
│       ├── api/                      # API 封装
│       └── router.ts                 # 路由配置
├── agent-service/                    # 【新建】Python Agent 服务
│   ├── main.py                       # FastAPI 入口（已写好）
│   ├── config.py                     # 配置管理（已写好）
│   ├── .env                          # 环境变量（已配置，含 API Key 和 DB 密码）
│   ├── .gitignore                    # Git 忽略规则（已配好）
│   ├── requirements.txt              # Python 依赖（已安装）
│   ├── LEARNING_PROGRESS.md          # 学习进度文档
│   ├── CONTEXT.md                    # 本文件 - 上下文交接文档
│   ├── venv/                         # Python 虚拟环境（不提交 Git）
│   ├── agent/
│   │   ├── __init__.py
│   │   ├── chat_agent.py             # 【阶段2】Agent 核心逻辑
│   │   ├── prompts.py                # 【阶段2】System Prompt
│   │   └── tools/
│   │       ├── __init__.py
│   │       ├── sales_tools.py        # 【阶段3】营业额查询
│   │       ├── order_tools.py        # 【阶段3-4】订单查询/操作
│   │       ├── dish_tools.py         # 【阶段4】菜品管理
│   │       └── report_tools.py       # 【阶段3】报表分析
│   ├── db/
│   │   ├── __init__.py
│   │   └── database.py               # 【阶段3】MySQL 连接
│   └── schemas/
│       ├── __init__.py
│       └── chat.py                   # 【阶段2】请求/响应模型
└── database/
    └── sky.sql                       # 数据库建表 SQL（已有）
```

---

## 五、已完成的阶段

### 阶段 1：项目初始化 + 环境搭建 ✅

**完成内容**：
- 创建了 `agent-service/` 完整目录结构
- 创建了 Python 虚拟环境（venv），安装了所有依赖
- 编写了 `main.py`（FastAPI Hello World，含 CORS、健康检查接口）
- 编写了 `config.py`（Pydantic Settings 配置管理）
- 配置了 `.env`（DeepSeek API Key、MySQL 连接信息、Java 后端地址）
- Git 初始化 + 首次 commit（commit ID: 8053f2f）
- 启动服务验证：`http://localhost:8100/health` 返回正常

**启动方式**：
```powershell
cd "e:\苍穹\苍穹外卖\agent-service"
.\venv\Scripts\python.exe main.py
```

**Git commit 记录**：
```
8053f2f feat: 阶段1 - 项目初始化，搭建FastAPI服务骨架
```

---

## 六、当前阶段 & 下一步

### 当前：准备进入阶段 2 - 接入 DeepSeek + 第一个对话接口

**阶段 2 需要做的事**：
1. 创建 `agent/prompts.py` - 编写第一版 System Prompt（v1）
2. 创建 `schemas/chat.py` - 定义请求/响应数据模型
3. 创建 `agent/chat_agent.py` - 用 LangGraph 构建最简 Agent（无 Tool，只有 LLM）
4. 在 `main.py` 添加 `/api/agent/chat` 接口
5. 先实现非流式输出，跑通后改为 SSE 流式输出
6. 测试 Agent 是否能正常回复

**阶段 2 教学重点**：
- LLM API 调用原理（DeepSeek 怎么用 HTTP 协议对话）
- System Prompt 的"三板斧"写法（角色定义、能力边界、输出格式）
- SSE 流式输出原理（打字机效果怎么实现的）
- LangGraph 基础：节点（Node）、边（Edge）、状态（State）是什么

---

## 七、关键配置信息

| 配置项 | 值 |
|--------|-----|
| Agent 服务端口 | 8100 |
| Java 后端端口 | 8080 |
| 前端开发服务器端口 | 8888 |
| MySQL 数据库名 | sky_take_out |
| LLM 模型 | qwen-max（通义千问，阿里云 DashScope） |
| LLM API Base URL | https://dashscope.aliyuncs.com/compatible-mode/v1 |
| LLM API Key 变量名 | LLM_API_KEY（在 .env 中配置） |
| Python 版本 | 3.12.4 |
| Python 虚拟环境路径 | e:/苍穹/苍穹外卖/agent-service/venv |

---

## 八、数据库关键表

| 表名 | 说明 | Agent 用途 |
|------|------|-----------|
| orders | 订单表（状态 1-7） | 查营业额、订单量、订单操作 |
| order_detail | 订单明细 | 查菜品销量 |
| dish | 菜品表 | 菜品查询、停售管理 |
| setmeal | 套餐表 | 套餐查询 |
| category | 分类表（type: 1=菜品分类, 2=套餐分类） | 分类查询 |
| employee | 员工表 | 员工管理 |
| user | 用户表（微信用户/顾客） | 新老客统计 |
| address_book | 地址簿 | - |
| dish_flavor | 菜品口味 | - |
| setmeal_dish | 套餐菜品关系 | - |

**订单状态码**：1=待付款, 2=待接单, 3=已接单, 4=派送中, 5=已完成, 6=已取消, 7=退款

---

## 九、7 阶段开发计划总览

| 阶段 | 内容 | 状态 |
|------|------|------|
| 1 | 项目初始化 + 环境搭建 | ✅ 完成 |
| 2 | 接入 DeepSeek + 第一个对话接口 | ⏳ 待开始 |
| 3 | 数据库连接 + 第一批 Tool（经营数据查询） | 待开始 |
| 4 | 扩展 Tool + Java 后端 API 对接 | 待开始 |
| 5 | 多轮对话 + 会话管理 | 待开始 |
| 6 | 前端对接（对话 UI） | 待开始 |
| 7 | 全面测试 + Prompt 深度优化 | 待开始 |

---

## 十、8 大技能学习地图

| # | 技能块 | 状态 |
|---|--------|------|
| 1 | Prompt 工程（角色设定/Few-shot/输出约束/迭代优化） | 待学习 |
| 2 | Tool 设计与编写（按商家问题反推工具，docstring 写法） | 待学习 |
| 3 | Agent 思考链路/调试（LangGraph 图执行流程、日志分析） | 待学习 |
| 4 | SQL 数据库查询（SUM/COUNT/GROUP BY/JOIN） | 待学习 |
| 5 | API 对接（GET/PUT/POST、请求头 token、httpx） | 待学习 |
| 6 | 会话管理（session_id、上下文截断、对话回溯） | 待学习 |
| 7 | 前端对接（SSE 原理、EventSource、Markdown 渲染） | 待学习 |
| 8 | 测试与迭代方法论（评测集构建、回归测试、准确率追踪） | 待学习 |

---

## 十一、给新对话的指令

当用户把本文件发给你时，你应该：
1. 阅读本文件，了解项目全貌和当前进度
2. 确认当前阶段（第六节"当前阶段"部分）
3. 按教学模式（第三节）的风格继续教学
4. 从当前阶段的下一步开始执行
5. 先确认用户是否已阅读上一阶段的代码，再继续新内容
