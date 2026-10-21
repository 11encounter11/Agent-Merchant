FROM node:22-alpine AS build

WORKDIR /app
COPY frontend-ui/package.json frontend-ui/package-lock.json ./
RUN npm ci --no-audit --no-fund
COPY frontend-ui/ ./
RUN npm run build

FROM nginx:1.27-alpine

# 同源部署：/api 反代到 agent:8100；Token 由 nginx 注入，不打进前端 JS
COPY deploy/nginx.workbench.conf.template /etc/nginx/templates/default.conf.template
COPY --from=build /app/dist /usr/share/nginx/html

EXPOSE 80
