---
title: "快速启动"
description: "- Python 3.12+"
topics: [setup, configuration, quickstart]
---

# 快速启动

## 前提条件

- Python 3.12+
- Node.js 22+（CI 的 `setup-node` 用 24；`frontend/AGENTS.md`、README、CONTRIBUTING 与 `frontend/Dockerfile` 的基础镜像都是 22+）
- pnpm
- uv (Python 包管理器)
- Docker (可选，沙箱隔离)

## 两种方式

### 方式一：本地开发（推荐研究用）

```bash
# 1. 检查环境
make check

# 2. 安装所有依赖
make install

# 3. 生成配置文件（scripts/configure.py）
make config          # 复制 config.example.yaml → config.yaml（已存在则中止）
                     # 同时复制 .env.example → .env、frontend/.env.example → frontend/.env
                     # 注意：不会生成 extensions_config.json（该文件可选；Docker 启动时由 scripts/docker.sh 补建）

# 4. 编辑 config.yaml，至少配置一个模型（如 DeepSeek 或 OpenAI）
#    models:
#      - name: deepseek
#        display_name: DeepSeek
#        use: deerflow.models.patched_deepseek:PatchedChatDeepSeek
#        model: deepseek-chat
#        api_key: $DEEPSEEK_API_KEY
#        ...

# 5. 启动（hot-reload）
make dev

# 访问 http://localhost:2026
```

`make dev` 实际执行 `python scripts/check.py` 做工具检查，再执行 `scripts/serve.sh --dev`，会启动：
- Gateway API (FastAPI, port 8001, hot-reload)
- Frontend (Next.js dev, port 3000, hot-reload；默认 Webpack，`DEER_FLOW_DEV_BUNDLER=turbo` 切 Turbopack)
- Nginx (port 2026, 反向代理，配置 `docker/nginx/nginx.local.conf`)

（外加按需拉起的 AIO sandbox 容器。）

### 方式二：Docker 开发

```bash
# 1. 拉沙箱镜像
make docker-init

# 2. 配置 .env 中的模型 API Key
#    DEEPSEEK_API_KEY=sk-xxx

# 3. 启动
make docker-start

# 访问 http://localhost:2026
```

`make docker-start` 使用 `docker/docker-compose-dev.yaml`，服务结构同生产但带 hot-reload 和源码挂载。

## Make 常用命令

| 命令 | 作用 |
|------|------|
| `make dev` | 本地开发启动（前台，Ctrl+C 停止；先跑 `scripts/check.py`） |
| `make dev-daemon` | 本地开发后台启动 |
| `make start` | 本地生产模式启动（`SKIP_FRONTEND_BUILD=1` 复用上次前端构建） |
| `make start-daemon` | 本地生产模式后台启动 |
| `make stop` | 停止所有服务 |
| `make clean` | 停止 + 清理临时文件 |
| `make config` | 生成 config.yaml / .env / frontend/.env（已有 config.yaml 则中止） |
| `make config-upgrade` | 用 `scripts/config-upgrade.sh` 合并新字段到已有 config.yaml |
| `make doctor` | 检查配置和系统需求 |
| `make setup` | 交互式安装向导（`scripts/setup_wizard.py`） |
| `make support-bundle` | 生成脱敏排障摘要 + issue 草稿（`scripts/support_bundle.py --include-doctor`） |
| `make up` | Docker 生产部署（`scripts/deploy.sh`） |
| `make down` | 停止 Docker 生产容器（`scripts/deploy.sh down`） |
| `make docker-init` | 拉沙箱镜像（`scripts/docker.sh init`） |
| `make setup-sandbox` | 同上，等价推荐入口（`scripts/setup-sandbox.sh`） |
| `make docker-start` | Docker 开发模式（`scripts/docker.sh start` → `docker/docker-compose-dev.yaml`） |
| `make docker-stop` | 停止 Docker 开发 |
| `make docker-logs` | 查看 Docker 开发日志（`--frontend` / `--gateway` / `--redis` 变体） |

### 后端专用命令 (cd backend)

| 命令 | 作用 |
|------|------|
| `make gateway` | 只启动 Gateway API (port 8001，无 reload) |
| `make dev` | Gateway API hot-reload（`--reload`，含 `*.yaml` / `.env`） |
| `make test` | 默认离线套件：`-m "not live" --ignore=tests/blocking_io`（**不含** live 与 blocking-io） |
| `make test-live` | live 测试（需 `DEER_FLOW_RUN_LIVE_TESTS=1` 与真实凭证） |
| `make test-blocking-io` | `tests/blocking_io` 严格 blocking-I/O 套件 |
| `make lint` | `ruff check .` + `ruff format --check .` |
| `make format` | `ruff check . --fix && ruff format .` |
| `make migrate-rev MSG="..."` | 生成新的 Alembic 迁移 |

### 前端专用命令 (cd frontend)

| 命令 | 作用 |
|------|------|
| `make dev` | `pnpm dev` |
| `make build` | `pnpm build` |
| `make test` | 单元测试（`pnpm test` → rstest） |
| `make test-e2e` | E2E (Playwright)（`pnpm test:e2e`） |
| `pnpm typecheck` | TypeScript 检查（`frontend/Makefile` 没有这个 target） |

## 启动后验证

```bash
# 1. Gateway 健康检查
curl http://localhost:8001/health
# -> {"status": "healthy", "service": "deer-flow-gateway"}

# 2. 模型列表
curl http://localhost:8001/api/models
# -> {"models": [...]}

# 3. Swagger 文档
open http://localhost:8001/docs

# 4. 前端
open http://localhost:2026
```

## 目录结构（运行时产生）

```
backend/.deer-flow/                  # DEER_FLOW_HOME 默认值（backend/Makefile 设为 $(CURDIR)/.deer-flow）
├── data/
│   └── deerflow.db                 # SQLite：checkpointer 与应用数据共用同一个库
│                                   # （config.example.yaml: database.sqlite_dir: .deer-flow/data）
├── users/
│   └── {user_id}/
│       ├── memory.json             # 用户记忆
│       ├── agents/
│       │   └── {agent_name}/       # 自定义 Agent (SOUL.md + config.yaml)
│       └── threads/
│           └── {thread_id}/
│               └── user-data/
│                   ├── workspace/  # Agent 工作区
│                   ├── uploads/    # 用户上传文件
│                   └── outputs/    # Agent 产出文件
└── ...                             # run_events 默认 backend: memory（不落库）
```

> 只有显式配置 legacy `checkpointer:` 段（例如 `connection_string: checkpoints.db`）时才会出现独立的 `checkpoints.db`；默认的统一 `database:` 段不产生该文件。

## 第一个对话

1. 打开 `http://localhost:2026`
2. 如果第一次使用，会进 setup 页面创建管理员账号
3. 创建一个新对话
4. 在输入框输入任意问题，Agent 会调用配置的工具（如 web_search、bash）来回答

## 常见问题

**Q: 启动时提示 config.yaml 不存在？**
```bash
make config    # 从 config.example.yaml 生成
```

**Q: 模型报 API key 错误？**
检查 `config.yaml` 中的 `api_key: $XXX` 对应的环境变量是否设置。

**Q: 前端连不上 Gateway？**
确认 `frontend/.env` 中 `DEER_FLOW_INTERNAL_GATEWAY_BASE_URL` 指向 Gateway（默认 `http://127.0.0.1:8001`，见 `frontend/src/core/auth/gateway-config.ts:15-20`）。
