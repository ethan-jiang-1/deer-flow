---
title: "Docker Compose 部署"
description: "`docker/docker-compose.yml` — 4 服务 + PostgreSQL："
topics: [deployment, docker, kubernetes]
---

# Docker Compose 部署

## 服务拓扑

`docker/docker-compose.yml` — 4 服务 + PostgreSQL：

```yaml
services:
  nginx:
    image: nginx:alpine
    ports: ["2026:2026"]
    volumes: [./nginx.conf:/etc/nginx/nginx.conf]
    depends_on: [gateway, frontend]

  gateway:
    build: backend/
    command: uvicorn app.gateway:app --host 0.0.0.0 --port 8000
    environment:
      - DEER_FLOW_CONFIG_PATH=/app/config.yaml
      - DATABASE_BACKEND=postgres  # 覆盖 config.yaml
    depends_on: [postgres, langgraph]

  langgraph:
    build:
      context: backend/
      dockerfile: langgraph.Dockerfile
    command: langgraph up --port 8123
    environment:
      - LANGGRAPH_STORE_POSTGRES_URI=postgresql://...

  frontend:
    build: frontend/
    environment:
      - NEXT_PUBLIC_LANGGRAPH_BASE_URL=/api/langgraph

  postgres:
    image: postgres:16-alpine
    volumes: [pgdata:/var/lib/postgresql/data]

  sandbox:  # 可选：仅在使用 AIO sandbox 时需要
    image: all-in-one-sandbox:latest
    volumes:
      - /var/run/docker.sock:/var/run/docker.sock  # DooD
```

## 🆕 新增部署组件（同步 #4）

| 组件 | 位置 | 用途 |
|------|------|------|
| **Lark CLI broker** | `docker/lark-cli-broker/` | Pattern B 凭据 broker sidecar（`serve` 模式跑在 loopback `:8788`；`install-shim` 模式写 shim 到 emptyDir）。设 `LARK_CLI_BROKER_IMAGE` 启用 |
| **Lark CLI init** | `docker/lark-cli-init/` | Pattern A init-container（`build-runtime.sh` 准备 Linux amd64/arm64 二进制写入共享 emptyDir）。设 `LARK_CLI_INIT_IMAGE` 启用 |
| **OpenViking compose** | `docker-compose.openviking.yaml` | OpenViking memory 后端（HTTP）部署模板 |
| **Dev compose** | `docker-compose-dev.yaml` | 开发环境 compose（与 prod 分开） |

> 这两个镜像配合 provisioner 使用：`docker/provisioner/app.py` 提供 `/api/capabilities` 探针，让 Gateway 判断 `lark-cli` 在 chat 时是否真的可用（`sandbox_runtime_mode: none | gateway-download | init-container | broker`）。

## 网络配置

所有服务在一个 Docker network 内通信：

```
nginx (:2026) → gateway (:8000) → langgraph (:8123)
                              → postgres (:5432)
              → frontend (:3000)
gateway                        → sandbox (Docker API, DooD 模式)
```

## DooD（Docker-outside-of-Docker）

Gateway 容器通过挂载 `/var/run/docker.sock` 来管理 AIO sandbox 容器：

```
Gateway container
  └─ docker.sock → host Docker daemon
        └─ docker run ... all-in-one-sandbox (sibling container, 非嵌套)
```

不是 Docker-in-Docker（dind）——创建的 sandbox 容器是 host Docker daemon 的 sibling container，与 Gateway 在同一层级。这种模式的性能更好、复杂性更低，但需要 Gateway 容器有访问 Docker socket 的权限。

## 环境变量

| 变量 | 用途 |
|------|------|
| `DATABASE_BACKEND` | 覆盖 config.yaml → `postgres` |
| `POSTGRES_URI` | PostgreSQL 连接串 |
| `DEER_FLOW_SANDBOX_HOST` | AIO 容器 hostname（DooD 模式通常设为 `host.docker.internal`） |
| `DEER_FLOW_INTERNAL_AUTH_TOKEN` | 多 worker 必须手动设置相同值 |

## 数据卷

- **PostgreSQL：** `pgdata` named volume — 持久化 thread/run/memory 数据
- **User data：** bind mount `./data/users:/app/data/users` — thread workspace 文件
- **Skills：** bind mount `./skills:/app/skills` — public + custom skills

## 生产 Checklist

- [ ] 设置 `DEER_FLOW_AUTH_ENABLED=true` + 配置 JWT secret
- [ ] 手动设置 `DEER_FLOW_INTERNAL_AUTH_TOKEN`（多 worker 环境）
- [ ] 评估是否需要 `seccomp=unconfined`（见 `security/02-sandbox-isolation.md`）
- [ ] 配置 PostgreSQL 备份
- [ ] Nginx 层配置 rate limiting
- [ ] 设置 `GATEWAY_CORS_ORIGINS` 为确切的前端域名（非 `*`）
- [ ] 日志收集（Docker 默认 log driver 或 fluentd/loki sidecar）
