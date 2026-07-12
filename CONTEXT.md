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
| DeepSeek 模型 | deepseek-chat |
| DeepSeek API Base URL | https://api.deepseek.com |
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
