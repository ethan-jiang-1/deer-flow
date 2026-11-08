---
title: "Docker Compose 部署"
description: "`docker/docker-compose.yaml` — 5 服务（nginx / frontend / gateway / redis / 可选 provisioner）："
topics: [deployment, docker, kubernetes]
---

# Docker Compose 部署

## 服务拓扑

`docker/docker-compose.yaml`（`make up`）—— 5 个 service，其中 provisioner 只在 K8s sandbox 模式下需要：

```yaml
services:
  redis:                      # 跨 worker SSE stream bridge（run state 仍在 Gateway 进程内存里）
    image: redis:7-alpine
    command: ["redis-server", "--appendonly", "yes"]
    volumes: [redis-data:/data]

  nginx:
    image: nginx:alpine
    ports: ["${BIND_HOST:-127.0.0.1}:${PORT:-2026}:2026"]   # 默认只绑 loopback
    volumes: [./nginx/nginx.conf:/etc/nginx/nginx.conf.template:ro]
    depends_on: [frontend, gateway]        # gateway 要等 healthcheck

  gateway:
    build: { context: ../, dockerfile: backend/Dockerfile }
    command: sh -c "cd backend && PYTHONPATH=. uv run --no-sync uvicorn app.gateway.app:app --host 0.0.0.0 --port 8001 --workers ${GATEWAY_WORKERS:-1}"
    environment:
      - DEER_FLOW_CONFIG_PATH=/app/backend/config.yaml
      - DEER_FLOW_EXTENSIONS_CONFIG_PATH=/app/backend/extensions_config.json
      - DEER_FLOW_STREAM_BRIDGE_REDIS_URL=redis://redis:6379/0
      - DEER_FLOW_CHANNELS_LANGGRAPH_URL=http://gateway:8001/api
      - DEER_FLOW_CHANNELS_GATEWAY_URL=http://gateway:8001
    volumes:
      - ${DEER_FLOW_CONFIG_PATH}:/app/backend/config.yaml:ro                     # 只读
      - ${DEER_FLOW_EXTENSIONS_CONFIG_PATH}:/app/backend/extensions_config.json  # 可写：Gateway 运行时会改
      - ../skills:/app/skills:ro
      - ${DEER_FLOW_HOME}:/app/backend/.deer-flow
    healthcheck: /health/ready (timeout=5，须高于端点 3s deadline)

  frontend:
    build: { context: ../, dockerfile: frontend/Dockerfile, target: prod }
    environment:
      - BETTER_AUTH_SECRET=${BETTER_AUTH_SECRET}
      - DEER_FLOW_INTERNAL_GATEWAY_BASE_URL=http://gateway:8001

  provisioner:                # 可选：K8s/K3s sandbox 模式
    build: { context: ./provisioner, dockerfile: Dockerfile }
    volumes: [~/.kube/config:/root/.kube/config:ro]
    healthcheck: http://localhost:8002/health
```

- **没有 `langgraph` service，也没有 `postgres` service**：agent runtime（RunManager + StreamBridge）内嵌在 Gateway 的 8001 端口；持久化由 `config.yaml` 的 `database.backend` 决定（`memory | sqlite | postgres`，代码默认 `memory`，`config.example.yaml` 模板给的是 `sqlite` + `sqlite_dir: .deer-flow/data`）。要 Postgres 就外接实例，写 `database.backend: postgres` + `postgres_url`。
- **Docker socket 默认不挂**：DooD 是 opt-in，见下。

## 🆕 新增部署组件（同步 #4）

| 组件 | 位置 | 用途 |
|------|------|------|
| **Lark CLI broker** | `docker/lark-cli-broker/` | Pattern B 凭据 broker sidecar（`serve` 模式跑在 loopback `:8788`；`install-shim` 模式写 shim 到 emptyDir）。设 `LARK_CLI_BROKER_IMAGE` 启用 |
| **Lark CLI init** | `docker/lark-cli-init/` | Pattern A init-container（`build-runtime.sh` 准备 Linux amd64/arm64 二进制写入共享 emptyDir）。设 `LARK_CLI_INIT_IMAGE` 启用 |
| **OpenViking compose** | `docker/docker-compose.openviking.yaml` | OpenViking memory 后端（HTTP）部署模板 |
| **Dev compose** | `docker/docker-compose-dev.yaml` | 开发环境 compose（`make docker-start`，`scripts/docker.sh -p deer-flow-dev`）：服务同 prod——`redis` / `nginx` / `frontend` / `gateway` / `provisioner`，额外带 hot-reload 与源码挂载 |

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

所有服务在同一个 `deer-flow` Docker network 内，只有 nginx 的 2026 发布到宿主（默认绑 `127.0.0.1`）：

```
nginx (:2026) ──▶ gateway (:8001) ──▶ redis (:6379)     # stream bridge
              └─▶ frontend (:3000)
gateway ──▶ provisioner (:8002, 可选，K8s 模式)
gateway ──▶ sandbox 容器（仅 DooD overlay：挂 docker.sock）
```

## DooD（Docker-outside-of-Docker）

`docker/docker-compose.yaml` **默认不挂** `/var/run/docker.sock`。只有 `aio`（纯 DooD）sandbox 模式才由 `scripts/deploy.sh` 追加 opt-in overlay `docker/docker-compose.dood.yaml`，把宿主 docker.sock 挂进 Gateway：

```
Gateway container
  └─ docker.sock → host Docker daemon
        └─ docker run ... all-in-one-sandbox (sibling container, 非嵌套)
```

不是 Docker-in-Docker（dind）——创建的 sandbox 容器是 host Docker daemon 的 sibling container，与 Gateway 在同一层级。这种模式的性能更好、复杂性更低，但要求 Gateway 容器能访问 Docker socket，只应在受信宿主上开启。

## 环境变量

| 变量 | 用途 |
|------|------|
| `DATABASE_URL` | PostgreSQL 连接串，在 `config.yaml` 里被 `database.postgres_url: $DATABASE_URL` 引用 |
| `DEER_FLOW_STREAM_BRIDGE_REDIS_URL` | 跨 worker SSE 的 Redis Streams 地址（compose 默认 `redis://redis:6379/0`） |
| `DEER_FLOW_SANDBOX_HOST` | AIO 容器 hostname（compose 设为 `host.docker.internal`） |
| `DEER_FLOW_INTERNAL_AUTH_TOKEN` | 多 worker / IM channel 的内部认证共享 token |
| `BETTER_AUTH_SECRET` | 前端 auth/session 加密密钥，必填 |
| `GATEWAY_WORKERS` | Gateway worker 数，默认 1（>1 需要 Redis stream bridge） |

## 数据卷

- **Redis：** `redis-data` named volume — stream bridge 的 appendonly 数据
- **Gateway 运行数据：** bind mount `${DEER_FLOW_HOME}:/app/backend/.deer-flow` — SQLite、threads workspace、memory、checkpoints
- **Skills：** bind mount `../skills:/app/skills:ro` — public + custom skills（只读）
- **config.yaml：** `${DEER_FLOW_CONFIG_PATH}:/app/backend/config.yaml:ro`（只读）；`extensions_config.json` 同一个文件但**可写**，因为 Gateway 运行时会改写它（MCP 开关、skill 更新）

## 生产 Checklist

- [ ] 确认认证**保持开启**（默认即开启，不存在"启用认证"变量；不要设置 `DEER_FLOW_AUTH_DISABLED=1`）+ 配置 JWT secret
- [ ] 手动设置 `DEER_FLOW_INTERNAL_AUTH_TOKEN`（多 worker 环境）
- [ ] 评估是否需要 `seccomp=unconfined`（见 `security/02-sandbox-isolation.md`）
- [ ] 配置 PostgreSQL 备份
- [ ] Nginx 层配置 rate limiting
- [ ] 设置 `GATEWAY_CORS_ORIGINS` 为确切的前端域名（非 `*`）
- [ ] 日志收集（Docker 默认 log driver 或 fluentd/loki sidecar）
