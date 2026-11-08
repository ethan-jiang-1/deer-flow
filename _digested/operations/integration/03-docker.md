---
title: "Docker 部署"
description: "生产部署（`docker/docker-compose.yaml`）5 个服务（redis/nginx/frontend/gateway + 可选 provisioner），通过 `deer-flow` bridge 网络互联："
topics: [integration, sdk, docker-deploy]
---

# Docker 部署

> 本文从**集成视角**看 Docker 部署。compose 字段级权威说明见 [operations/deployment/01-docker.md](../deployment/01-docker.md)。本文的通道/凭据相关行已按 v2.2.0 重核。

## 架构

生产部署（`docker/docker-compose.yaml`）5 个服务，通过 `deer-flow` bridge 网络互联：

```
                    ${BIND_HOST:-127.0.0.1}:${PORT:-2026}
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
    └───────────┘ └────┬────┘ └────────────┘
                       │ depends_on (healthy)
                 ┌─────┴─────┐
                 │   redis   │  (stream bridge)
                 │   :6379   │
                 └───────────┘
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
# 构建 + 启动（走 scripts/deploy.sh：自动生成/持久化 DEER_FLOW_INTERNAL_AUTH_TOKEN、
# 按沙箱模式追加 opt-in overlay、等 /health/ready 探针就绪）
make up

# 停止
make down             # scripts/deploy.sh down

# 访问
open http://localhost:${PORT:-2026}    # PORT 默认 2026
```

### nginx 服务

```yaml
nginx:
  image: nginx:1.31.2-alpine        # 🆕 v2.2.0 由 nginx:alpine 改为钉版
  # 默认只绑 loopback；BIND_HOST 需显式设为 0.0.0.0 才对外暴露
  ports: ["${BIND_HOST:-127.0.0.1}:${PORT:-2026}:2026"]
  volumes: ["./nginx/nginx.conf:/etc/nginx/nginx.conf.template:ro"]
```

最简的反向代理。所有请求经此路由。

🆕 **为什么钉 `1.31.2-alpine`**（`docker/docker-compose.yaml` 注释）：1.31.3 起的 alpine 构建带 musl 1.2.6，其 `pwrite()` 会发 `pwritev2(RWF_NOAPPEND)`；老 Docker / EOL 内核上的 seccomp 配置拒绝该 syscall，master 进程反复重启并报 `pwrite() "/run/nginx.pid" failed (1: Operation not permitted)`（#7615）。1.31.2 是最后一个用 musl 1.2.5（`pwrite64`）的 alpine 构建。

🆕 **启动脚本兼容无 IPv6 主机**：`nginx.conf` 同时 listen `[::]:2026`，在内核禁用 IPv6 的主机上 nginx 会 `socket() ... 97: Address family not supported` 直接退出、容器反复重启，`make up` 永远等不到健康。compose 的 command 因此先 `test -e /proc/net/if_inet6`，缺了就 `sed` 删掉那条 IPv6 listen，再 `exec nginx`（让 nginx 成为 PID 1 以正确接收信号）。

🆕 **Compose ≥ 2.24 要求**：`env_file` 改成 long-form（`path:` + `required: false`），使**全新 checkout 缺少 `../.env` / `../frontend/.env` 时不会直接 abort**；旧客户端会报 `services.<name>.env_file.0 must be a string`。

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
    context: ../
    dockerfile: backend/Dockerfile
    args:
      UV_EXTRAS: ${UV_EXTRAS:-}   # 如 postgres
  # 默认单 worker：run 状态在本进程内存里；仅在 Postgres + Redis stream bridge 下才允许调高
  command: sh -c "cd backend && PYTHONPATH=. exec uv run --no-sync uvicorn app.gateway.app:app --host 0.0.0.0 --port 8001 --workers ${GATEWAY_WORKERS:-1} --timeout-graceful-shutdown 10"
  stop_grace_period: 90s
  init: true
  volumes:
    - ${DEER_FLOW_CONFIG_PATH}:/app/backend/config.yaml:ro
    # 故意可写：Gateway 运行时会改写它（MCP 开关 / PUT,PATCH /api/mcp/config / skill 更新）
    - ${DEER_FLOW_EXTENSIONS_CONFIG_PATH}:/app/backend/extensions_config.json
    - ../skills:/app/skills:ro
    - ${DEER_FLOW_HOME}:/app/backend/.deer-flow          # 数据持久化
    # 注意：docker.sock（DooD）与 ~/.claude、~/.codex 默认都不挂载，
    # 它们在 opt-in overlay 里：docker-compose.dood.yaml / docker-compose.cli-auth.yaml
  environment:
    - DEER_FLOW_PROJECT_ROOT=/app
    - DEER_FLOW_CONFIG_PATH=/app/backend/config.yaml
    - DEER_FLOW_EXTENSIONS_CONFIG_PATH=/app/backend/extensions_config.json
    - DEER_FLOW_HOME=/app/backend/.deer-flow
    - DEER_FLOW_STREAM_BRIDGE_REDIS_URL=${DEER_FLOW_STREAM_BRIDGE_REDIS_URL:-redis://redis:6379/0}
    - DEER_FLOW_CHANNELS_LANGGRAPH_URL=${DEER_FLOW_CHANNELS_LANGGRAPH_URL:-http://gateway:8001/api}
    - DEER_FLOW_CHANNELS_GATEWAY_URL=${DEER_FLOW_CHANNELS_GATEWAY_URL:-http://gateway:8001}
    - DEER_FLOW_SANDBOX_HOST=host.docker.internal
    - DEER_FLOW_INTERNAL_AUTH_TOKEN=${DEER_FLOW_INTERNAL_AUTH_TOKEN}
    - DEER_FLOW_CREDENTIALS_KEY=${DEER_FLOW_CREDENTIALS_KEY:-}   # 🆕 静态凭据加密密钥
  extra_hosts: ["host.docker.internal:host-gateway"]
```

关键点：
- **默认 1 个 worker，且多 worker 有硬条件**（v2.2.0 起由 Gateway 自己把关）：`GATEWAY_WORKERS > 1` 只在 **Postgres**（`database.backend: postgres`、`run_events.backend: db`、`run_ownership.heartbeat_enabled: true`）**加** Redis stream bridge 时才被支持，否则 Gateway 拒绝启动。**IM 通道、WeChat QR 登录、browser 工具仍是 worker-local**——启用它们时保持单 worker。
- 🆕 **`init: true` + `exec` + `--timeout-graceful-shutdown 10`**：`sh -c` 里若 fork 出服务器，`sh` 会占据 PID 1 且没有 SIGTERM handler，内核丢弃信号、lifespan shutdown 从不执行，每次停止都耗满 `stop_grace_period` 再被 SIGKILL（#6835）。现在 command 用 `exec`、Compose 用 `init: true`（tini 作 PID 1，转发信号并回收孙进程）。
- 🆕 **`stop_grace_period: 90s`**：默认 10s 会 SIGKILL 掉 30s 的 memory 队列 flush（`memory.shutdown_flush_timeout_seconds`）。90s 覆盖 `--timeout-graceful-shutdown 10` + lifespan 最坏情况（7 个各限 5s 的 hook + 1s 检索预热 + 5s run drain + 30s memory flush ≈ 71s）+ 余量，算术由 `backend/tests/_gateway_shutdown_budget.py` 钉住。
- 🆕 **`DEER_FLOW_CREDENTIALS_KEY`**：静态凭据（连接凭据、Web UI 录入的通道凭据、MCP OAuth refresh token）的 Fernet 密钥。`scripts/deploy.sh` 负责解析/生成：`--env` 文件提供了就用；否则若 `$DEER_FLOW_HOME/.credentials_key` 不存在，用 python3/python/openssl 之一生成 32 字节 urlsafe-base64 并以 `umask 077` + `noclobber` 写入（**要备份**）；三者都没有则报错要求手工设置。compose 里留空则回落到挂载卷中的 `.credentials_key`。多副本必须显式设置（无法共享自动生成的文件）。
- **DooD**（Docker-out-of-Docker）：基础 compose **不挂** `/var/run/docker.sock`，只有 aio 沙箱模式才通过 opt-in overlay `docker/docker-compose.dood.yaml` 追加（`scripts/deploy.sh` 按 `detect_sandbox_mode()=="aio"` 决定）
- **数据持久化**：`${DEER_FLOW_HOME}` 挂载为 volume，存 SQLite、checkpoints、用户数据
- **IM channels 内部通信**：`DEER_FLOW_CHANNELS_LANGGRAPH_URL=http://gateway:8001/api`
- **SQLite postgres 切换**：build 参数 `UV_EXTRAS=postgres`
- **CLI auth 目录**（`~/.claude`/`~/.codex`）默认不挂：opt-in overlay `docker/docker-compose.cli-auth.yaml`；优先用 `CLAUDE_CODE_OAUTH_TOKEN` 等 env token

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
| `BIND_HOST` | 否 | 入口发布地址，默认 127.0.0.1（loopback） |
| `GATEWAY_WORKERS` | 否 | uvicorn workers，默认 1 |
| `UV_EXTRAS` | 否 | postgres 等 extra |
| `LANGSMITH_TRACING` | 否 | 默认 false |
| `DEER_FLOW_CREDENTIALS_KEY` 🆕 | 存储凭据时是 | 静态凭据加密密钥；多副本必填，单机可由 `deploy.sh` 生成到 `$DEER_FLOW_HOME/.credentials_key` |
| `DEER_FLOW_MULTI_INSTANCE` 🆕 | 多副本是 | 声明多实例拓扑（`deployment_config.py:26`；`deployment.multi_instance: true` 是等价写法，环境变量优先，见 `multi_instance_declaration()` `:93`）。开启后 `leader_lease: auto` 解析为生效，且 WeChat 扫码登录端点返回 503（进程内单会话不支持多 worker） |

## Nginx 路由

```
/api/langgraph/*   → gateway:8001/api/*     (LangGraph compatible)
/api/*             → gateway:8001/api/*     (REST APIs)
/docs|/redoc|...   → gateway:8001
/*                 → frontend:3000          (SPA)
```

## 沙箱 Docker 集成

aio（纯 DooD）沙箱模式通过 **opt-in overlay** `docker/docker-compose.dood.yaml` 追加 socket 挂载：
- `/var/run/docker.sock` 挂载（仅该 overlay）
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
