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

## 🆕 同步 #6（v2.1.0-rc0）Docker 部署变更

| 组件 | 位置 | 变更 |
|------|------|------|
| **sandbox-network-proxy 镜像** | `docker/sandbox-network-proxy/Dockerfile` 🆕 | 新的独立 Docker 镜像，配套 workflow `.github/workflows/sandbox-network-proxy-image.yaml` 构建发布 |
| **Compose healthcheck** | `docker/docker-compose.yaml` | gateway 健康检查 `/health`(timeout=3) → `/health/ready`(timeout=5)；`/health/ready` 在 3s 端点 deadline 内并发跑两个探针，客户端 timeout 必须高于它 |

### `docker/provisioner/app.py` 大改（+379 行）主题

- **skills 容器路径可配置**：`CreateSandboxRequest` 新增 `skills_container_path`（默认 `/mnt/skills`，老 Gateway 不传保持兼容）。`_normalize_skills_container_path()` 校验绝对路径、非 root、无冗余分隔符，且不得与保留挂载（`/mnt/user-data`、`/mnt/acp-workspace`、`/mnt/integrations/lark-cli`）重叠。
- **受管 skill 分类挂载**：`<skills-root>/{public,custom,legacy,integrations}` 由 provisioner 自动派生并加入 extra mount 白名单（替代旧的硬编码 `/mnt/skills/custom` / `/mnt/skills/integrations`），并支持 skill override mount 的归并判断。
- **`max_shell_sessions`**：新 Gateway 按 process-wide subagent capacity 传入，provisioner 写入 sandbox 响应（`None` 保持旧调用方兼容，默认上限 10）。

### `scripts/deploy.sh` Windows 修复

`aio` 模式下 Docker socket 检查改为从 `.env` 读取 `DEER_FLOW_DOCKER_SOCKET`；Windows（Git Bash/MSYS）上 Docker Desktop 即使宿主无 socket 文件也会把默认 `/var/run/docker.sock` 挂进容器，且导出该路径会被 MSYS 转换成 `C:\Program Files\Git\var\run\docker.sock` 导致 compose mkdir 报错——此时跳过 socket 文件检查并 unset 该变量，让 Compose 用自身默认 fallback。

### 本地启停命令（同步 #6）

- **`make start SKIP_FRONTEND_BUILD=1`**（#5053，`scripts/serve.sh --skip-frontend-build`）：生产模式复用上一次前端构建，跳过 `next build`；`start-daemon` 同样支持。
- **`make dev` Windows 修复**：Makefile 统一 `RUN_SHELL_SCRIPT`——Windows 仍走 Git Bash 包装，POSIX 改为显式 `$(BASH)` 调用，修复丢失可执行位的 checkout（zip 下载、`core.fileMode=false`）。
- **`scripts/pnpm.py` 解析顺序变化**（#5305）：Windows 先试 `pnpm.cmd` 再 `pnpm`（Corepack 同理 `corepack.cmd` 优先），POSIX 顺序不变。
- **`scripts/doctor.py` / `scripts/detect_uv_extras.py`**：`models[].use == langchain_ollama:*` 会自动探测 `ollama` uv extra（`_PROVIDER_EXTRAS` 映射）；doctor 各检查对 `models`/`tools` 为 `None` 或非 dict 项更健壮，并补 serply/sofya/tencent_wsa 等 API key 提示。
- **`make extension-upgrade SOURCE=...`**：新根 make 目标，替换已装扩展并保留其配置。

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
