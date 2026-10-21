# 单商家演示部署 Runbook

> 目标：Java/MySQL/Redis 保持原样，只部署 Python Agent 与 `frontend-ui`。
> 当前**单商家**：`MERCHANT_ID=1`，不做 Java JWT/租户桥接；上多商家前必须另做身份方案。

## 1. 端口与边界

| 服务 | 地址 | 说明 |
|---|---|---|
| Java 管理端/nginx | `8080` | 现有平台，**不改** |
| Agent（容器内） | `agent:8100` | 只绑定宿主机 `127.0.0.1:8100` |
| 新工作台 | `http://<host>:8081` | nginx 静态页 + `/api` 反代；与 Java 隔离 |
| MySQL / Redis | 宿主机 | 通过 `host.docker.internal` 访问 |

不改 `E:/苍穹/苍穹外卖/deploy/nginx.conf`、不改 Java 代码、不新增 MySQL 表。

## 2. 准备

1. 宿主机已有 Java 平台、MySQL、Redis，且允许 Docker 访问。
2. 在 `agent-service/` 下准备 `.env`（从 `.env.example` 复制）：
   - `LLM_API_KEY` / `LLM_BASE_URL` / `LLM_MODEL`
   - `EMBEDDING_API_KEY`（若启用向量；演示规则不依赖）
   - `DB_PASSWORD`，以及 `AGENT_API_TOKEN`（生产必须设置）
   - `APP_ENV=prod`（Token 未配时 fail-closed）
3. 不要把 `.env` 提交；`.dockerignore` 已排除。
4. 前端**不要**设置 `VITE_AGENT_TOKEN`：生产由 nginx 注入 `Authorization`，避免 Token 进入 JS bundle。

## 3. 启动

```bash
cd "E:/苍穹/苍穹外卖/agent-service"

# 用同一个 .env 做 compose 变量替换（web 需要 AGENT_API_TOKEN）
docker compose --env-file .env -f deploy/docker-compose.yml up -d --build
```

- Agent 容器：`--workers 1`，**不要扩容多 worker**（checkpoint、偏好文件、限流都是单实例前提）。
- `data/` 以 bind mount 持久化到宿主机 `agent-service/data/`；备份这个目录即可保住会话/偏好/快照。
- MySQL/Redis 若不在宿主机，改 compose 里的 `DB_HOST` / `REDIS_URL`；Redis 有密码时写成 `redis://:密码@host:6379/0`。

## 4. 验收

```bash
# 通过 nginx（Token 由 nginx 注入）
curl -s http://127.0.0.1:8081/health
curl -s "http://127.0.0.1:8081/api/workbench/dashboard?range=yesterday"
curl -s "http://127.0.0.1:8081/api/workbench/rules/search?q=退款"
```

浏览器打开 `http://<host>:8081`：

1. 默认显示“昨日”；实库最新数据较旧时会回退最近 7 个完整日并提示。
2. 点 KPI/某天/菜品 → 右侧上下文 chip → 提问 → 先出现「数据事实（服务端快照）」再出现解释。
3. 规则卡片搜索/分类/详情可打开；演示规则显示 `DEMO_SYNTHETIC`。
4. “以后每天…”→ 偏好保存、看板重排。

## 5. 观测与故障

| 现象 | 排查 |
|---|---|
| `/api` 401 | `.env` 的 `AGENT_API_TOKEN` 与 nginx 注入值不一致；重启 web |
| 503 `DB_UNAVAILABLE` | 容器内 `DB_HOST` 不通；检查 MySQL 绑定地址/防火墙 |
| 页面是 Mock 数据 | `/api` 不通；看浏览器 Network 与 `docker compose logs web agent` |
| SSE 一卡一卡/最后才出字 | nginx 必须保留 `proxy_buffering off` 与 `X-Accel-Buffering: no` |
| 规则为空 | `agent/knowledge/rules/` 无文件；演示语料应已随镜像带入 |
| 容器 OOM | Chroma/LLM 依赖；4C8G 单机按单 worker 运行，先扩内存再谈并发 |

## 6. 升级/回滚

```bash
docker compose --env-file .env -f deploy/docker-compose.yml up -d --build
docker compose --env-file .env -f deploy/docker-compose.yml down
```

- 回滚：保留上一次镜像 tag 或 `git` 版本；schema 是加法/无新增表，回滚只影响应用。
- Agent 本地 `data/` 与新版本格式兼容；如字段不兼容，先备份再迁移。
- 现有 Java nginx/8080 不受影响；不要把 8081 和 8080 配到同一个 upstream。

## 7. 当前明确未做

- 多商家身份桥接（Java JWT → merchant/store）。
- 真实平台规则原文（当前 12 条演示语料）。
- 活动实时数据源（目录为空时只显示空态）。
- HTTPS/域名/ICP 备案与公网访问策略：需在宿主机反代层另配；不要把 8081 直接裸露公网。
