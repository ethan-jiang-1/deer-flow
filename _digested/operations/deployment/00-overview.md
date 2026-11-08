---
title: "部署架构全景"
description: "DeerFlow 支持 4 种部署模式，从个人开发到生产多租户。"
topics: [deployment, docker, kubernetes]
---

# 部署架构全景

DeerFlow 支持 4 种部署模式，从个人开发到生产多租户。

## 部署模式矩阵

| 模式 | 进程拓扑 | 沙箱 | 持久化 | 适用场景 |
|------|---------|------|--------|---------|
| **本地开发** | `make dev` — 3 服务（Gateway + Frontend + Nginx） | Local | SQLite | 个人开发 |
| **Docker Compose** | 4 容器（nginx / frontend / gateway / redis）+ 可选 provisioner | Docker (AIO) | SQLite / 外部 Postgres | 团队测试 |
| **Nginx + Docker** | Nginx 反向代理 + Gateway（内含 agent runtime）+ Sandbox | Docker 或 Local | Postgres | 生产单租户 |
| **K3s Provisioner** | Gateway（内含 agent runtime）+ K3s Pods | K3s Pod (per-thread) | Postgres | 生产多租户 |

## 本地开发（make dev）

`make dev` = `scripts/check.py` + `scripts/serve.sh --dev`，起 3 个服务：

```
make dev
  ├─ Gateway  uvicorn app.gateway.app:app --reload (port 8001)
  ├─ Frontend pnpm run dev (port 3000，默认 Webpack)
  ├─ Nginx    nginx.local.conf (port 2026，统一入口)
  └─ (可选) AIO sandbox containers（由 Gateway 按需拉起）
```

- **Gateway** — FastAPI + uvicorn hot reload；agent runtime（RunManager + StreamBridge）就在这个进程里，**没有独立的 LangGraph Server**
- **Frontend** — Next.js dev server，HMR (Hot Module Replacement)
- **Nginx** — 统一入口，`/api/langgraph/*` rewrite 到 Gateway 原生 `/api/*`
- **Sandbox** — 可选，仅在使用 AIO 沙箱时需要 Docker

> 🆕 同步 #6：`make start` 支持 `SKIP_FRONTEND_BUILD=1` 复用上次前端构建（#5053）；生产启动用镜像内预装 Python 环境（`uv run --no-sync`）+ 真实 `/health` 探针，`make up` 等 probe 通过才打成功横幅。详见 `01-docker.md`。

## Docker Compose

`docker/docker-compose.yaml`（生产栈，`make up`）：

```
┌────────────┐      ┌────────────────┐      ┌────────────┐
│  nginx      │─────▶│  gateway       │      │  frontend  │
│  (:2026)   │      │  (:8001)       │      │  (:3000)   │
│  反向代理   │      │ FastAPI +      │      │ Next.js    │
└────────────┘      │ agent runtime  │      └────────────┘
                    └───────┬────────┘
                            ├─ redis (:6379)        # 跨 worker SSE stream bridge
                            ├─ provisioner (:8002)  # 可选，K8s sandbox 模式
                            └─ sandbox 容器         # 仅 DooD overlay 挂 docker.sock
```

Docker Compose 的 nginx 配置路由：
- `/api/langgraph/*` → Gateway（rewrite 成 Gateway 原生 `/api/*`）
- `/api/*`（其他）→ Gateway
- `/`（非 API）→ Frontend

数据库不是 compose 里的一个服务：`database.backend` 取 `memory | sqlite | postgres`（`backend/packages/harness/deerflow/config/database_config.py`，代码默认 `memory`；`config.example.yaml` 模板给的是 `sqlite` + `sqlite_dir: .deer-flow/data`，落在 `DEER_FLOW_HOME` 卷）。要 Postgres 就外接实例，把 `database.backend` 设为 `postgres` 并配 `postgres_url`。

## Nginx 路由规则

生产部署的典型 Nginx 配置：

```nginx
server {
    listen 2026;

    # Gateway API
    location /api/ {
        proxy_pass http://gateway:8001;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
    }

    # LangGraph 兼容入口（SSE streaming）— rewrite 到 Gateway 原生 /api/*
    location /api/langgraph/ {
        rewrite ^/api/langgraph/(.*) /api/$1 break;
        proxy_pass http://gateway:8001;
        proxy_buffering off;          # SSE 需要禁用缓冲
        proxy_read_timeout 600s;      # Agent 执行可能很长
    }

    # Frontend static files
    location / {
        proxy_pass http://frontend:3000;
    }
}
```

关键配置：
- **`proxy_buffering off`** — SSE 流式响应必须禁用 Nginx 缓冲，否则前端收不到增量更新
- **`proxy_read_timeout 600s`** — Agent 执行可能超过默认的 60s 超时
- **Rate limiting** — 未在 DeerFlow 内建，需在 Nginx 层配置 `limit_req_zone`

## K3s Provisioner 模式

当 `config.yaml` 设置 `sandbox.provisioner_url` 时，每个 Agent thread 获得独立的 K3s Pod：

```
Gateway（内含 agent runtime）→ SandboxMiddleware.ensure_sandbox_initialized()
  → AioSandboxProvider
    → RemoteSandboxBackend → POST provisioner:8002/api/sandboxes
      → 创建 Pod: sandbox-{sandbox_id} (namespace: deer-flow)
        ├─ image: all-in-one-sandbox
        ├─ CPU: 100m-1000m, Mem: 256Mi-1Gi
        ├─ /mnt/user-data/* 挂载 (hostPath/PVC subPath)
        └─ /mnt/skills read-only
      → 创建 Service: sandbox-{sandbox_id}-svc (NodePort)
      → 返回 sandbox_url → Gateway 通过 Pod IP:NodePort 通信
```

Provisioner 位于 `docker/provisioner/app.py` — FastAPI 服务，管理 K3s Pod 生命周期。

### K3s 资源限制

| 资源 | Request | Limit |
|------|---------|-------|
| CPU | 100m | 1000m |
| Memory | 256Mi | 1Gi |
| Ephemeral Storage | — | 500Mi |

### 安全配置

| 设置 | 值 |
|------|-----|
| privileged | `false` |
| allowPrivilegeEscalation | `true` |
| Readiness probe | `/v1/sandbox`, 5s interval, 5s initial delay |
| Liveness probe | `/v1/sandbox`, 10s interval, 10s initial delay |

**注意：** `allowPrivilegeEscalation: true` 允许容器内的 setuid 程序。对于高安全需求的部署，建议评估是否需要设为 `false`。

## 配置环境

关键环境变量：

| 变量 | 用途 | 默认值 |
|------|------|--------|
| `DEER_FLOW_CONFIG_PATH` | config.yaml 路径 | `./config.yaml` |
| `DEER_FLOW_AUTH_DISABLED` | **关闭**认证（仅本地/E2E；生产环境变量为 prod 时被忽略） | 未设（= 认证开启） |
| `GATEWAY_CORS_ORIGINS` | CORS 白名单 | same-origin |
| `DEER_FLOW_SANDBOX_HOST` | AIO 容器 hostname | `localhost` |
| `LANGFUSE_TRACING` | 启用 Langfuse | `false` |
| `LANGSMITH_TRACING` | 启用 LangSmith | `false` |
| `NEXT_PUBLIC_LANGGRAPH_BASE_URL` | 前端 LangGraph URL | `/api/langgraph` |
