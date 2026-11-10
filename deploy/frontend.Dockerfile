FROM node:22-alpine AS build

# 出网受限的机器可用 --build-arg NPM_REGISTRY=<镜像源> 覆盖；
# 实测首尔演示机反而直连 npmjs 更快，故默认仍用官方源
ARG NPM_REGISTRY=https://registry.npmjs.org

WORKDIR /app
COPY frontend-ui/package.json frontend-ui/package-lock.json ./
RUN npm ci --no-audit --no-fund --registry=$NPM_REGISTRY \
      --fetch-retries=5 --fetch-timeout=180000
COPY frontend-ui/ ./
RUN npm run build

FROM nginx:1.27-alpine

# 同源部署：/api 反代到 agent:8100；Token 由 nginx 注入，不打进前端 JS
COPY deploy/nginx.workbench.conf.template /etc/nginx/templates/default.conf.template
COPY --from=build /app/dist /usr/share/nginx/html

EXPOSE 80
