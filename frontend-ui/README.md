# frontend-ui · AI 经营工作台

独立于 Java `admin-web` 的新工作台 UI，直连 Python `agent-service`。

```bash
cd frontend-ui
npm install
npm run dev       # http://localhost:5173
npm run build
```

- 开发期 Vite 把 `/api` 代理到 `http://127.0.0.1:8100`。
- 后端未启动时自动使用 `src/mock/dashboard.ts`，页面明确标“演示数据”。
- 鉴权：新建 `.env.local` 填 `VITE_AGENT_TOKEN`（仅本地生效，已被 `.gitignore` 忽略）；不要把生产 Token 打进构建。
- 交互：点 KPI/某天/菜品/热力格 → 右侧 AI 上下文 chip；在对话框说“以后每天给我看退款趋势”→ 后端保存偏好并重排看板。
- 数据事实：实库最新订单 `2026-07-28`；请求“昨日”会回退到最近 7 个完整日；退款为整单近似。

