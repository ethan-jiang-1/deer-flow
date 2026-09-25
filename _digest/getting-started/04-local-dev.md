---
title: "本地开发：make dev"
description: "`make dev` 启动 3 个本地服务（Gateway + Frontend + Nginx），用于个人开发环境。"
topics: [setup, configuration, quickstart]
---

# 本地开发：make dev

`make dev` 先跑 `scripts/check.py` 检查工具，再用 `scripts/serve.sh --dev` 启动 3 个本地服务（外加按需拉起的 AIO sandbox 容器）。

## 进程拓扑

```
make dev
  ├─ Gateway (uvicorn app.gateway.app:app)
  │     --host 0.0.0.0 --port 8001 --reload
  │     Agent runtime（RunManager + StreamBridge）就嵌在这个进程里，
  │     没有独立的 LangGraph Server 进程
  │
  ├─ Frontend (cd frontend && pnpm run dev)
  │     PORT=3000，默认 Webpack（DEER_FLOW_DEV_BUNDLER=turbo 可切 Turbopack）
  │
  ├─ Nginx (docker/nginx/nginx.local.conf)
  │     --port 2026，反向代理 Gateway + Frontend
  │
  └─ (optional) AIO sandbox containers
        Gateway 按需 docker run ... all-in-one-sandbox
```

## 本地开发特点

- **Hot Reload：** Gateway（uvicorn `--reload`，含 `*.yaml` / `.env`）、Frontend（Next.js HMR）——两人热重载
- **Local Sandbox：** 默认使用 `LocalSandboxProvider`——所有 bash/文件操作在 host 上执行，通过虚拟路径映射隔离
- **SQLite：** 单文件数据库，路径 `.deer-flow/data/`
- **Auth：** 认证默认**开启**（首次访问进 setup 页创建管理员，`user_id` 取真实用户）。本地无认证调试才设 `DEER_FLOW_AUTH_DISABLED=1`，此时所有请求以合成 admin 用户 `"default"`（`DEFAULT_USER_ID`，`runtime/user_context.py:98`）运行；该变量在显式生产环境（`DEER_FLOW_ENV`/`ENVIRONMENT` = prod/production）下会被忽略（`app/gateway/auth_disabled.py:11-40`）
- **Memory Stream Bridge：** 单进程内存 pub/sub，无需 Redis

## 前置条件

```bash
# Python 3.12+
uv sync --group dev

# Node.js 22+（🆕 v2.1.0-rc0 起 CI 的 setup-node 从 22 升到 24，#5063；
#              本地门槛与 frontend/Dockerfile 基础镜像仍是 22+）
pnpm install

# config.yaml
make config    # 从 config.example.yaml 生成

# 启动
make dev
```

## 访问地址

| 服务 | URL |
|------|-----|
| Nginx 统一入口 | `http://localhost:2026` |
| Gateway API（直连） | `http://localhost:8001/api/` |
| API Docs | `http://localhost:8001/docs` |
| Frontend | `http://localhost:3000` |
| Health Check | `http://localhost:8001/health` |

nginx 上的 `/api/langgraph/*` 会被 rewrite 到 Gateway 的原生 `/api/*` 路由——没有单独的 LangGraph Server 端口。

## 常见问题

- **config_version mismatch：** 上游更新了配置 schema → 运行 `make config-upgrade` 合并新字段
- **`/api/langgraph/*` 连不上：** Agent runtime 不在独立进程里，直接查 Gateway（`make gateway` / uvicorn，端口 8001）和 `backend/.deer-flow` 下的日志；`backend/langgraph.json` 只是 LangGraph Studio 的 graph 注册，不是本地开发要起的服务
- **Frontend 白屏：** 检查 `NEXT_PUBLIC_LANGGRAPH_BASE_URL`（默认 `/api/langgraph`，通过 nginx 代理到 Gateway 8001）
- **Import 错误：** 运行 `uv sync` 重新安装依赖——harness 包通过 editable install 挂在虚拟环境中
