---
title: "Docker 部署"
description: "生产部署（`docker/docker-compose.yaml`）4 个服务，通过 `deer-flow` bridge 网络互联："
topics: [integration, sdk, docker-deploy]
---

# Docker 部署

## 架构

生产部署（`docker/docker-compose.yaml`）4 个服务，通过 `deer-flow` bridge 网络互联：

```
                    Port 2026
                        │
                   ┌────┴────┐
                   │  nginx   │  (alpine, 反向代理)
                   └────┬────┘
                        │
          ┌─────────────┼─────────────┐
          │             │             │
    ┌─────┴─────┐ ┌────┴────┐ ┌─────┴──────┐
    │ frontend  │ │ gateway │ │provisioner │ (可选)
    │ Next.js   │ │ FastAPI │ │  K3s sandbox│
    │  :3000    │ │  :8001  │ │   :8002    │
    └───────────┘ └────────┘ └────────────┘
```

## 开发环境 (docker-compose-dev.yaml)

```bash
# 首次
make docker-init      # 拉 sandbox 镜像

# 启动
make docker-start     # hot-reload 模式，源码挂载
make docker-stop
make docker-logs
make docker-logs-frontend
make docker-logs-gateway

# 访问
open http://localhost:2026
```

开发环境特性：
- 源码挂载（backend + frontend）
- uvicorn `--reload` hot-reload
- Next.js dev server + `WATCHPACK_POLLING=true`
- `.env` 中配置 API key

## 生产环境 (docker-compose.yaml)

```bash
# 构建 + 启动
make up               # 等效 docker compose -f docker/docker-compose.yaml up -d --build

# 停止
make down             # docker compose -f docker/docker-compose.yaml down

# 访问
open http://localhost:${PORT:-2026}    # PORT 默认 2026
```

### nginx 服务

```yaml
nginx:
  image: nginx:alpine
  ports: ["${PORT:-2026}:2026"]
  volumes: ["./nginx/nginx.conf:/etc/nginx/nginx.conf.template:ro"]
```

最简的反向代理。所有请求经此路由。

### frontend 服务

```yaml
frontend:
  build:
    dockerfile: frontend/Dockerfile
    target: prod
  environment:
    - BETTER_AUTH_SECRET=${BETTER_AUTH_SECRET}       # 必须设置
    - DEER_FLOW_INTERNAL_GATEWAY_BASE_URL=http://gateway:8001
```

Next.js 生产构建。需 `BETTER_AUTH_SECRET`（auth/session 加密密钥）。

### gateway 服务

```yaml
gateway:
  build:
    dockerfile: backend/Dockerfile
    args:
      UV_EXTRAS: ${UV_EXTRAS:-}   # 如 postgres
  command: uvicorn app.gateway.app:app --host 0.0.0.0 --port 8001 --workers 4
  volumes:
    - config.yaml:/app/backend/config.yaml:ro
    - extensions_config.json:/app/backend/extensions_config.json:ro
    - ../skills:/app/skills:ro
    - .deer-flow:/app/backend/.deer-flow          # 数据持久化
    - /var/run/docker.sock:/var/run/docker.sock    # Docker-out-of-Docker (沙箱)
    - ~/.claude:/root/.claude:ro                   # Claude Code CLI auth
    - ~/.codex:/root/.codex:ro                     # Codex CLI auth
  environment:
    - DEER_FLOW_CONFIG_PATH=/app/backend/config.yaml
    - DEER_FLOW_HOME=/app/backend/.deer-flow
    - DEER_FLOW_SANDBOX_HOST=host.docker.internal
    - DEER_FLOW_INTERNAL_AUTH_TOKEN=${DEER_FLOW_INTERNAL_AUTH_TOKEN}
  extra_hosts: ["host.docker.internal:host-gateway"]
```

关键点：
- **4 workers**（可通过 `GATEWAY_WORKERS` 调整）
- **DooD**（Docker-out-of-Docker）：需要 `/var/run/docker.sock` 来在宿主机上启动沙箱容器
- **数据持久化**：`.deer-flow/` 挂载为 volume，存 SQLite、checkpoints、用户数据
- **IM channels 内部通信**：`DEER_FLOW_CHANNELS_LANGGRAPH_URL=http://gateway:8001/api`
- **SQLite postgres 切换**：build 参数 `UV_EXTRAS=postgres`

### provisioner 服务（可选，K3s 模式）

沙箱启用 `provisioner_url` 时启动。挂载 `~/.kube/config`。

## 后端 Dockerfile

`backend/Dockerfile` 是多阶段构建：

1. **builder** — 安装 Python 3.12 + Node.js 22 + uv
2. **dev** — 保留编译工具链
3. **runtime** — 精简镜像（~200 MiB 更小）

build args: `APT_MIRROR`, `UV_IMAGE`, `UV_INDEX_URL`, `UV_EXTRAS`

## 环境变量清单（Docker 必需）

| 变量 | 必需 | 说明 |
|------|------|------|
| `BETTER_AUTH_SECRET` | 生产是 | 前端 session 加密 |
| `DEER_FLOW_CONFIG_PATH` | 否 | config.yaml 路径 |
| `DEER_FLOW_HOME` | 否 | 数据目录 |
| `DEER_FLOW_INTERNAL_AUTH_TOKEN` | 多worker是 | 内部通信认证 |
| `DEER_FLOW_SKILLS_PATH` | 否 | Skills 目录 |
| `PORT` | 否 | Nginx 端口，默认 2026 |
| `GATEWAY_WORKERS` | 否 | uvicorn workers，默认 4 |
| `UV_EXTRAS` | 否 | postgres 等 extra |
| `LANGSMITH_TRACING` | 否 | 默认 false |

## Nginx 路由

```
/api/langgraph/*   → gateway:8001/api/*     (LangGraph compatible)
/api/*             → gateway:8001/api/*     (REST APIs)
/docs|/redoc|...   → gateway:8001
/*                 → frontend:3000          (SPA)
```

## 沙箱 Docker 集成

Gateway 容器通过 DooD 模式在宿主机上启动沙箱容器：
- `/var/run/docker.sock` 挂载
- `host.docker.internal` host-gateway（解决容器网络和宿主机网络之间的地址问题）
- 沙箱容器用 `AioSandboxProvider` 管理，LRU 淘汰（默认 3 个并发）
- Skills 目录通过 volume 传入沙箱容器，路径保持 `/mnt/skills`

## 常见问题

**Q: Gateway 容器中 `localhost:8001` 连不上？**
Gateway 和 frontend 通过 Docker 网络内的 service name 通信：`http://gateway:8001`。

**Q: SQLite 文件跑在哪里？**
在挂载的 volume 中：`backend/.deer-flow/data/deerflow.db`。

**Q: 如何切到 PostgreSQL？**
1. 设置 `.env`：`DATABASE_URL=postgresql://...` 和 `UV_EXTRAS=postgres`
2. 修改 `config.yaml`：`database.backend: postgres`
3. `make up` 重建
