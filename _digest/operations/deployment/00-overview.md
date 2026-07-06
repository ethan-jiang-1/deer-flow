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
| **本地开发** | `make dev` — 4 进程 | Local | SQLite | 个人开发 |
| **Docker Compose** | 4 容器 | Docker (AIO) | SQLite / Postgres | 团队测试 |
| **Nginx + Docker** | Nginx 反向代理 + Gateway + LangGraph + Sandbox | Docker 或 Local | Postgres | 生产单租户 |
| **K3s Provisioner** | Gateway + LangGraph + K3s Pods | K3s Pod (per-thread) | Postgres | 生产多租户 |

## 本地开发（make dev）

```
make dev
  ├─ uvicorn backend.gateway:app --reload (port 2026)
  ├─ langgraph dev (port 8123)
  ├─ pnpm dev (Turbopack, port 3000)
  └─ (可选) AIO sandbox containers
```

4 个独立进程通过 `make dev` 中的 Procfile 管理：
- **Gateway** — FastAPI + uvicorn hot reload, `/api/*` 端点
- **LangGraph Server** — `langgraph dev` 命令，Graph execution + streaming
- **Frontend** — Next.js Turbopack，HMR (Hot Module Replacement)
- **Sandbox** — 可选，仅在使用 AIO 沙箱时需要 Docker

## Docker Compose

`docker/docker-compose.yml`：

```
┌────────────┐  ┌─────────────┐  ┌──────────┐  ┌───────────────┐
│  nginx      │  │  gateway    │  │ langgraph│  │  sandbox      │
│  (:2026)   │→│  (:8000)    │→│  (:8123) │→│  (Docker API) │
│  反向代理   │  │  FastAPI    │  │  Pregel  │  │  per-thread   │
└────────────┘  └─────────────┘  └──────────┘  └───────────────┘
                                             ↓
                                    ┌──────────────┐
                                    │  postgres    │
                                    │  (:5432)    │
                                    └──────────────┘
```

Docker Compose 的 nginx 配置路由：
- `/api/*` → Gateway
- `/api/langgraph/*` → LangGraph Server

## Nginx 路由规则

生产部署的典型 Nginx 配置：

```nginx
server {
    listen 2026;

    # Gateway API
    location /api/ {
        proxy_pass http://gateway:8000;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
    }

    # LangGraph runtime (SSE streaming)
    location /api/langgraph/ {
        proxy_pass http://langgraph:8123;
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
Gateway → LangGraph Server → SandboxMiddleware.ensure_sandbox_initialized()
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
| `DEER_FLOW_AUTH_ENABLED` | 启用认证 | `false` |
| `GATEWAY_CORS_ORIGINS` | CORS 白名单 | same-origin |
| `DEER_FLOW_SANDBOX_HOST` | AIO 容器 hostname | `localhost` |
| `LANGFUSE_TRACING` | 启用 Langfuse | `false` |
| `LANGSMITH_TRACING` | 启用 LangSmith | `false` |
| `NEXT_PUBLIC_LANGGRAPH_BASE_URL` | 前端 LangGraph URL | `/api/langgraph` |
