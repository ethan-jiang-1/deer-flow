---
title: "环境变量全参考"
description: "DeerFlow 读取的全部环境变量：来源、读取点、默认值。真值 = `.env.example` + 代码中的 `os.getenv` + compose 的 `${VAR}`。"
topics: [setup, configuration, quickstart]
---

# 环境变量全参考

DeerFlow 的环境变量有三个来源，文档表格逐条标注了证据路径（相对仓库根）：

1. **配置文件里的 `$VAR` 引用** —— `config.yaml` / `extensions_config.json` 中以 `$` 开头的字符串值由配置加载器解析（`config/app_config.py::resolve_env_variables`、`config/extensions_config.py`）。**AppConfig 缺变量报错，ExtensionsConfig 缺变量存空串**。绝大多数模型/IM key 属于这一类：代码本身不 `os.getenv`，只是把值从环境里取出来。
2. **代码直接读取** —— `os.getenv` / `os.environ.get`。
3. **Docker/构建期** —— `docker/*.yaml` 的 `${VAR}` 插值、`scripts/*.sh`、Makefile。

## 模型 API Keys

| 变量 | 读取方式 | 用途 |
|------|----------|------|
| `OPENAI_API_KEY` | config.yaml `$VAR` | OpenAI 模型 |
| `DEEPSEEK_API_KEY` | config.yaml `$VAR` | DeepSeek 模型 |
| `GEMINI_API_KEY` | config.yaml `$VAR` | Google Gemini |
| `ANTHROPIC_API_KEY` | config.yaml `$VAR` | Anthropic Claude |
| `VOLCENGINE_API_KEY` | config.yaml `$VAR`（`config.example.yaml:156,182`） | 火山引擎（豆包） |
| `NOVITA_API_KEY` | config.yaml `$VAR`（`config.example.yaml:461`） | Novita.ai（OpenAI 兼容） |
| `MINIMAX_API_KEY` | config.yaml `$VAR`（`config.example.yaml:511,546`） | MiniMax（OpenAI 兼容） |
| `VLLM_API_KEY` | config.yaml `$VAR`（`config.example.yaml:695`） | vLLM 自部署（OpenAI 兼容） |
| `STEPFUN_API_KEY` | config.yaml `$VAR`（`config.example.yaml:489`） | 阶跃星辰 StepFun（OpenAI 兼容） |
| `IMAGE_GENERATION_API_KEY` / `_BASE_URL` / `_MODEL` / `_SIZE` / `_PROVIDER` | config.yaml `$VAR`（`config.example.yaml:1552`） | 图像生成 skill 的 OpenAI 兼容图像 API |
| `OPENVIKING_API_KEY` | config.yaml `$VAR`（`config.example.yaml:2061`） | OpenViking memory 后端（`memory.manager_class: openviking`） |

### CLI 订阅作为模型凭证（可选）

`models/credential_loader.py` 是 Gateway 侧的统一读取点，优先级高于目录挂载：

| 变量 | 读取点 | 说明 |
|------|--------|------|
| `CLAUDE_CODE_OAUTH_TOKEN` / `ANTHROPIC_AUTH_TOKEN` | `models/credential_loader.py:197` | Claude 直接 token（首选） |
| `CLAUDE_CODE_OAUTH_TOKEN_FILE_DESCRIPTOR` | `models/credential_loader.py:204` | 从 fd 读 token |
| `CLAUDE_CODE_CREDENTIALS_PATH` | `models/credential_loader.py:139,211` | 指向单个 `.credentials.json`，免挂整个 `~/.claude` |
| `CODEX_AUTH_PATH` | `models/credential_loader.py:228` | 覆盖默认 `~/.codex/auth.json` |
| `ANTHROPIC_BILLING_HEADER` | `models/claude_provider.py:41` | 覆盖 Claude 计费/版本头（OAuth token 访问 Anthropic API 必需） |
| `USE_LOCAL_OAUTH` / `USE_STAGING_OAUTH` / `LOCAL_BRIDGE` | `scripts/export_claude_code_oauth.py:27,29` | OAuth 导出脚本的端点选择（仅脚本） |

`docker/docker-compose.cli-auth.yaml` 是"挂整目录"的 opt-in 退路；默认 compose **不挂** `~/.claude` / `~/.codex`。

## 搜索 / Web Fetch / 工具 API Keys

| 变量 | 读取点 | 用途 |
|------|--------|------|
| `SERPER_API_KEY` | `.env.example:2` | Google Search (serper.dev) |
| `SERPLY_API_KEY` | `.env.example:5` | Google Search/News/Scholar (serply.io) |
| `SOFYA_API_KEY` | `.env.example:17` | Sofya 搜索/爬取 |
| `TENCENTCLOUD_WSA_APIKEY` | `config.example.yaml:868,876` | 腾讯云 WSA 搜索 |
| `TAVILY_API_KEY` | `.env.example:8` | Tavily 搜索 |
| `JINA_API_KEY` | `.env.example:11` | Jina AI Reader (web fetch) |
| `INFOQUEST_API_KEY` | `.env.example:14` | BytePlus InfoQuest 搜索/爬取 |
| `FIRECRAWL_API_KEY` | `.env.example:32` | Firecrawl 搜索/爬取 |
| `EXA_API_KEY` | config.yaml `$VAR`（`config.example.yaml:887`） | Exa 搜索 |
| `BRAVE_SEARCH_API_KEY` | `community/brave/tools.py:45` | Brave Search（代码直接读；缺失时工具返回 error JSON） |
| `CRW_API_KEY` | `community/fastcrw/tools.py:27` | FastCRW 爬取 |
| `BROWSERLESS_TOKEN` | `community/browserless/tools.py:85` | Browserless（`scripts/doctor.py:516` 也会检查） |
| `GROUNDROUTE_API_KEY` | `community/groundroute/tools.py:52` | GroundRoute（`groundroute` extra 为空包，无需额外依赖） |
| `OPEN_SANDBOX_API_KEY` / `OPEN_SANDBOX_DOMAIN` | `community/opensandbox/provider.py:108-109` | OpenSandbox provider；都为空时 SDK 退回未认证 `localhost:8080` |

## Gateway 配置

| 变量 | 默认值 | 读取点 | 说明 |
|------|--------|--------|------|
| `GATEWAY_HOST` | `0.0.0.0` | `app/gateway/config.py:22` | Gateway 监听地址 |
| `GATEWAY_PORT` | `8001` | `app/gateway/config.py:23` | Gateway 端口 |
| `GATEWAY_ENABLE_DOCS` | `true` | `app/gateway/config.py:24` | 只有小写 `true` 才开启 Swagger/ReDoc（生产设 `false`） |
| `GATEWAY_CORS_ORIGINS` | —（空） | `app/gateway/csrf_middleware.py:115,126` | 逗号分隔的**精确** origin 列表；`CORSMiddleware` 与 `CSRFMiddleware` 共用同一变量，分离部署必须设 |

## 运行时路径 / 配置

| 变量 | 说明 |
|------|------|
| `DEER_FLOW_PROJECT_ROOT` | 项目根目录：设了必须是存在的目录，否则回落到 `cwd`（`config/runtime_paths.py:7-16`） |
| `DEER_FLOW_HOME` | 可写数据目录，默认 `{project_root}/.deer-flow`（`config/runtime_paths.py:19-23`） |
| `DEER_FLOW_CONFIG_PATH` | config.yaml 的完整路径（优先级第 2 档） |
| `DEER_FLOW_EXTENSIONS_CONFIG_PATH` | extensions_config.json 的完整路径（`config/extensions_config.py:424`；显式设置后文件缺失会报错，不再回落搜索） |
| `DEER_FLOW_SKILLS_PATH` | Skills 目录（覆盖 config.yaml 的 `skills.path`；`config/skills_config.py:47`） |
| `DEER_FLOW_DOCKER_SOCKET` | Docker socket 路径；默认 `/var/run/docker.sock`，**只在 opt-in 的 `docker-compose.dood.yaml:26` 里挂载** |
| `DEER_FLOW_REPO_ROOT` | 仓库根目录（DooD 下计算 Skills host path；`scripts/deploy.sh:125`） |
| `DEER_FLOW_DATE_TIMEZONE` | 注入 agent 的会话日期所用 IANA 时区（如 `Asia/Shanghai`）。非 config schema 字段，date-context 中间件运行时读（`agents/middlewares/dynamic_context_middleware.py:97`） |
| `TZ` | 平台时区回退：`DEER_FLOW_DATE_TIMEZONE` 未设或非法时用它（`dynamic_context_middleware.py:132`） |
| `DEER_FLOW_FILE_IO_WORKERS` | ContextVar-preserving 文件 IO 线程池大小（`utils/file_io.py:19`） |
| `DEER_FLOW_ASSEMBLY_WORKERS` | 上下文装配线程池大小（`utils/assembly_io.py:19`） |
| `DEERMEM_DATA_DIR` | DeerMem 数据根；未设则 `~/.deermem/`（`agents/memory/backends/deermem/deermem/core/paths.py:65`） |

## 认证与安全（v2.1.0）

| 变量 | 说明 |
|------|------|
| `DEER_FLOW_AUTH_DISABLED` | **只认字面值 `1`**（`app/gateway/auth_disabled.py:30-31`）= 关闭认证，所有请求以合成 admin 用户 `"default"` 运行（email `default@test.local`，`auth_disabled.py:11-13,49-58`）。认证**默认开启**。显式生产环境下**被忽略**：`DEER_FLOW_ENV` 或 `ENVIRONMENT` 去空白转小写后 ∈ {`prod`, `production`} 即否决（`auth_disabled.py:20-27,34-35`） |
| `AUTH_JWT_SECRET` | JWT 签名密钥。显式设置优先；未设时在 `DEER_FLOW_HOME` 下生成并持久化（`app/gateway/auth/config.py:25,48,57,68`） |
| `AUTH_TRUSTED_PROXIES` | 逗号分隔的受信代理网段，用于解析真实客户端 IP（`app/gateway/routers/auth.py:211-229`，非法项只告警） |

## 内部通信

| 变量 | 说明 |
|------|------|
| `DEER_FLOW_INTERNAL_AUTH_TOKEN` | 多 worker / IM 频道之间的共享内部认证 token（`app/gateway/internal_auth.py:15`）；`make up` 会自动生成并持久化 |
| `DEER_FLOW_INTERNAL_GATEWAY_BASE_URL` | Frontend SSR 连 Gateway 的 URL，**默认 `http://127.0.0.1:8001`**（`frontend/src/core/auth/gateway-config.ts:15-20`） |
| `DEER_FLOW_TRUSTED_ORIGINS` | Frontend 信任的 origin 列表，默认 `["http://localhost:3000"]`（`gateway-config.ts:22-28`） |
| `DEER_FLOW_CHANNELS_LANGGRAPH_URL` | IM 频道连 LangGraph API 的 URL（compose 默认 `http://gateway:8001/api`） |
| `DEER_FLOW_CHANNELS_GATEWAY_URL` | IM 频道连 Gateway API 的 URL（compose 默认 `http://gateway:8001`） |
| `DEER_FLOW_STREAM_BRIDGE_REDIS_URL` | Redis stream bridge 地址；未设时依次回落 `REDIS_URL` → `redis://localhost:6379/0`（`runtime/stream_bridge/async_provider.py:28,45`） |
| `REDIS_URL` | 通用 Redis 回落地址，被 stream bridge、checkpoint cache、sandbox ownership 共享（`runtime/checkpoint_cache/provider.py:22`、`community/aio_sandbox/ownership/factory.py:68`） |
| `DEER_FLOW_SANDBOX_OWNERSHIP_REDIS_URL` | sandbox ownership 专用 Redis；未设时按 ownership → stream bridge → `REDIS_URL` 顺序回落（`community/aio_sandbox/ownership/factory.py:23,68`） |

## IM 频道

| 变量 | 平台 |
|------|------|
| `FEISHU_APP_ID` / `FEISHU_APP_SECRET` | 飞书 |
| `SLACK_BOT_TOKEN` (`xoxb-…`) / `SLACK_APP_TOKEN` (`xapp-…`, Socket Mode) | Slack |
| `TELEGRAM_BOT_TOKEN` | Telegram |
| `DISCORD_BOT_TOKEN` | Discord |
| `DINGTALK_CLIENT_ID` / `DINGTALK_CLIENT_SECRET` | 钉钉（`config.example.yaml:2725`） |
| `WECOM_BOT_ID` / `WECOM_BOT_SECRET` | 企业微信（`config.example.yaml:2715`） |
| `WECHAT_BOT_TOKEN` / `WECHAT_ILINK_BOT_ID` | 微信（`config.example.yaml:2665-2666`） |
| `BUZZ_PRIVATE_KEY` | Buzz（hex 或 `nsec1…`；`config.example.yaml:2745`） |

> 这些变量由用户在 `config.yaml -> channels.<platform>` 里以 `$VAR` 形式引用（不是代码直接 `os.getenv`），由配置加载器解析。

## 可观测性

| 变量 | 读取点 | 说明 |
|------|--------|------|
| `LANGSMITH_TRACING` | `config/tracing_config.py:153` | 启用 LangSmith；别名 `LANGCHAIN_TRACING_V2` → `LANGCHAIN_TRACING`（首个"存在且非空"的生效） |
| `LANGSMITH_API_KEY` | `tracing_config.py:154` | 别名 `LANGCHAIN_API_KEY`；开启但缺失时启动报 `ValueError`（`tracing_config.py:22-23`） |
| `LANGSMITH_PROJECT` | `tracing_config.py:155` | 别名 `LANGCHAIN_PROJECT`；默认 `deer-flow` |
| `LANGSMITH_ENDPOINT` | `tracing_config.py:156` | 别名 `LANGCHAIN_ENDPOINT`；默认 `https://api.smith.langchain.com` |
| `LANGFUSE_TRACING` | `tracing_config.py:159` | 启用 Langfuse |
| `LANGFUSE_PUBLIC_KEY` / `LANGFUSE_SECRET_KEY` | `tracing_config.py:160-161` | 开启但缺失时启动报 `ValueError`（`tracing_config.py:41-47`） |
| `LANGFUSE_BASE_URL` | `tracing_config.py:162` | Langfuse 服务地址；**默认 `https://cloud.langfuse.com`**。注意：DeerFlow 只读 `LANGFUSE_BASE_URL`，不读旧名 `LANGFUSE_HOST`（后者仅出现在测试里） |
| `MONOCLE_TRACING` | `tracing_config.py:165` | 启用 Monocle OTel；只由 Gateway lifespan 自动初始化，内嵌/TUI 调用方需自己调 `deerflow.tracing.setup_monocle_tracing_if_enabled()` |
| `MONOCLE_EXPORTERS` | `tracing_config.py:166` | 逗号分隔，默认 `file`；合法值仅 `file`/`console`/`okahu`/`s3`/`blob`/`gcs`，未知值启动报错（`tracing_config.py:53,78-80`） |
| `OKAHU_API_KEY` | `tracing_config.py:167` | 选 `okahu` exporter 时必填（`tracing_config.py:81-82`） |
| `DEER_FLOW_ENV` / `ENVIRONMENT` | `app/gateway/auth_disabled.py:20-27` | 环境标签（`production`/`staging`），用于 trace metadata；同时是 `DEER_FLOW_AUTH_DISABLED` 的生产环境否决条件 |

追踪配置是**进程内单次读取 + 缓存**（`tracing_config.py:143-170`）：改 env 要重启。

## 数据库

| 变量 | 说明 |
|------|------|
| `DATABASE_URL` | PostgreSQL 连接字符串（`postgresql://...`），仅 `database.backend: postgres` 需要；在 config.yaml 里以 `postgres_url: $DATABASE_URL` 引用（`config/database_config.py:25`） |
| `DEER_FLOW_STREAM_BRIDGE_REDIS_URL` / `REDIS_URL` | 见"内部通信"；`backend: redis` 的 stream bridge 与 checkpoint cache 也走这里 |
| `MIGRATIONS_PATH` | Alembic 迁移目录覆盖（仅脚本/运维路径使用） |

## Docker / 构建（compose `${VAR}` 插值）

| 变量 | 默认值 | 来源 | 说明 |
|------|--------|------|------|
| `PORT` | `2026` | `docker/docker-compose.yaml:54` | Nginx 对外端口 |
| `BIND_HOST` | `127.0.0.1` | `docker-compose.yaml:54` | Docker 入口发布地址（loopback 默认；`0.0.0.0` 才对外暴露） |
| `GATEWAY_WORKERS` | `1` | `docker-compose.yaml:107` | uvicorn worker 数。run state 是 per-worker 内存，只有启用 Redis stream bridge 且接受 cancel/dedup/IM 局限时才调高 |
| `UV_EXTRAS` | — | `docker-compose.yaml:97`；`scripts/detect_uv_extras.py` | 如 `postgres`；脚本会从环境自动探测 |
| `UV_IMAGE` | `ghcr.io/astral-sh/uv:0.11.1` | `docker-compose.yaml:95` | 构建用 UV 镜像 |
| `UV_INDEX_URL` | `https://pypi.org/simple` | `docker-compose.yaml:96` | PyPI 索引 |
| `UV_CACHE_DIR` | — | `scripts/tool-error-degradation-detection.sh:18` | uv 缓存目录 |
| `NPM_REGISTRY` | 空 | `docker-compose.yaml:77,98` | pnpm/npm registry 覆盖（frontend build 与 gateway build 共用） |
| `PNPM_STORE_PATH` | `/root/.local/share/pnpm/store` | `docker-compose.yaml:76` | pnpm store 路径 |
| `APT_MIRROR` | 空 | `docker-compose.yaml:94`；`docker/provisioner` | APT 镜像源 |
| `PIP_INDEX_URL` | 空 | `docker-compose.yaml:171` | provisioner 镜像的 pip 索引 |
| `LARK_CLI_NPM_VERSION` | `1.0.65` | `docker-compose.yaml:99` | 打包进镜像的 lark-cli 版本 |
| `LARK_CLI_INIT_IMAGE` | 空 | `docker-compose.yaml:181` | Pattern A：用 init container 下发 sandbox lark-cli runtime |
| `LARK_CLI_BROKER_IMAGE` | 空 | `docker-compose.yaml:186` | Pattern B：broker sidecar 持有凭证（同时设置时**覆盖** Pattern A） |
| `LARK_CLI_VERSION` / `LARK_CLI_RUNTIME_DEST` | — | `integrations/lark_cli.py:96`（fallback `v1.0.65`）、`integrations/lark_broker.py:443-444` | broker runtime 安装版本与目标路径 |
| `OPENVIKING_IMAGE` | `ghcr.io/volcengine/openviking:latest` | `docker/docker-compose.openviking.yaml:14` | openviking overlay 镜像 |
| `OPENVIKING_PORT` | `1933` | `docker-compose.openviking.yaml:18` | openviking overlay 端口 |
| `BETTER_AUTH_SECRET` | — | `docker-compose.yaml:80` | Frontend session 加密密钥（生产必须） |
| `DEER_FLOW_INTERNAL_AUTH_TOKEN` | — | `docker-compose.yaml:137` | 见"内部通信" |
| `DEER_FLOW_INTERNAL_GATEWAY_BASE_URL` | compose 固定 `http://gateway:8001` | `docker-compose.yaml:81` | 容器内 SSR 走服务别名 |
| `DEER_FLOW_DEV_ALLOWED_ORIGINS` | `127.0.0.1,::1` | `docker/docker-compose-dev.yaml:170`；`frontend/.env.example` | **仅开发**：允许加载 Next dev 资源/HMR 的额外 host；生产忽略 |
| `DEER_FLOW_ROOT` | 当前 checkout | `scripts/docker.sh:122-128` | Compose 主机侧路径解析 |
| `GITHUB_WEBHOOK_SECRET` | — | `app/gateway/routers/github_webhooks.py:43` | GitHub webhook HMAC 密钥；未设则 `/api/webhooks/github` fail-closed 不挂载（返回 404） |
| `DEER_FLOW_ALLOW_UNVERIFIED_GITHUB_WEBHOOKS` | — | `routers/github_webhooks.py:44`；`app/gateway/app.py:971-979` | `1` = 开发环境免密钥挂载 webhook 路由 |
| `NO_PROXY` / `no_proxy` | compose 追加内部主机名 | `docker-compose.yaml:143-144` | 在 `../.env` 继承值后追加 `localhost,127.0.0.1,::1,gateway,frontend,nginx,provisioner,openviking,host.docker.internal`；`HTTP_PROXY`/`HTTPS_PROXY`/`ALL_PROXY` 通过 `env_file` 继承 |

### provisioner 容器内部（compose 固定值，非用户配置）

`docker/docker-compose.yaml:176-191` 直接写死：`K8S_NAMESPACE=deer-flow`、`SANDBOX_IMAGE`、`THREADS_HOST_PATH=${DEER_FLOW_HOME}/threads`、`KUBECONFIG_PATH`、`NODE_HOST=host.docker.internal`、`K8S_API_SERVER`、`DEER_FLOW_HOST_BASE_DIR=${DEER_FLOW_HOME}`；`DEER_FLOW_SANDBOX_HOST=host.docker.internal` 则由 compose 传给 Gateway（`docker-compose.yaml:140`）。改这些要改 compose，不是 `.env`。

## 沙箱 provider 凭证

| 变量 | 说明 |
|------|------|
| `E2B_API_KEY` | E2B 云沙箱（仅 `E2BSandboxProvider`，需 `e2b-code-interpreter` 依赖；`.env.example:51`） |
| `PROVISIONER_API_KEY` | provisioner/K8s 沙箱认证（需与 `sandbox.provisioner_api_key` 一致；`.env.example:88`） |

## 沙箱网络（AIO 进阶，一般无需手工设置）

这些由 AIO sandbox provider 在启动侧车时**自行注入**到容器，用户通常不必设置；只有自建/调试侧车时才有意义：

| 变量 | 读取点 | 说明 |
|------|--------|------|
| `DEER_FLOW_SANDBOX_HOST` | `community/aio_sandbox/local_backend.py:368` | 沙箱可达 host，默认 `localhost` |
| `DEER_FLOW_SANDBOX_BIND_HOST` | `local_backend.py:348` | 显式 bind 地址（必须是 IP 字面量或可解析） |
| `DEER_FLOW_SANDBOX_NETWORK` | `local_backend.py:1776` | 复用/校验的目标 Docker 网络 |
| `DEERFLOW_NETWORK_MODE` | `community/aio_sandbox/network_proxy.py:114` | 出网模式，默认 `isolated` |
| `DEERFLOW_ALLOW_DOMAINS_JSON` | `network_proxy.py:107` | allowlist 模式的域名 JSON 数组 |
| `DEERFLOW_RECORD_DENIALS` | `network_proxy.py:525` | `1` = 记录被拒请求 |
| `DEERFLOW_SANDBOX_TARGET` | `network_proxy.py:604` | 侧车转发目标 `host:port` |
| `DEERFLOW_ALLOW_SYNTHETIC_DNS` | `network_proxy.py:218` | `1` = 允许合成 DNS |
| `DEERFLOW_POLICY_DB` | `network_proxy.py:25` | 网络策略 SQLite 路径，默认 `/tmp/deerflow-network-policy.sqlite3` |
| `DEER_FLOW_SANDBOX_CONTAINER_USER` / `DEER_FLOW_SANDBOX_SECCOMP_PROFILE` | `local_backend.py:1765` / `:1740` | 容器用户与 seccomp profile 覆盖 |

## 其他

| 变量 | 读取点 | 说明 |
|------|--------|------|
| `GITHUB_TOKEN` | `.env.example:67` | GitHub API Token（MCP GitHub server、GitHub 事件触发 agent 等） |
| `SKIP_FRONTEND_BUILD` | `Makefile:150-164` | `make start` / `make start-daemon` 传 `--skip-frontend-build`，复用上次前端构建 |
| `DEERFLOW_LARK_BROKER_URL` / `_HOST` / `_PORT` / `_TIMEOUT` / `_CLI` / `_PYTHON` / `_DENY_SUBCOMMANDS` | `integrations/lark_broker.py:41,86,137,432` | broker 侧车连接与 shim 参数（由 provisioner 注入；`_PYTHON` 在 PATH 为空时固定 python3 路径） |
| `LANGSERVE_GRAPHS` / `LANGSMITH_LANGGRAPH_API_VARIANT` | `app/gateway` | LangGraph 兼容 runtime/Studio 集成相关 |

## 前端（`frontend/.env`）

| 变量 | 默认 | 说明 |
|------|------|------|
| `NEXT_PUBLIC_BACKEND_BASE_URL` | 空（走 nginx） | 直连 Gateway 的浏览器侧 URL（`frontend/src/env.js` schema） |
| `NEXT_PUBLIC_LANGGRAPH_BASE_URL` | `/api/langgraph`（走 nginx） | LangGraph 兼容入口 |
| `NEXT_PUBLIC_STATIC_WEBSITE_ONLY` | 空 | 只构建静态文档站、不连后端的开关 |
| `GITHUB_OAUTH_TOKEN` | — | 文档站/GitHub 集成用的服务端 token（`frontend/src/env.js`） |
| `SKIP_ENV_VALIDATION` / `NODE_ENV` | — | 构建期：跳过 t3-env 校验 / Next 运行模式 |
| `DEER_FLOW_INTERNAL_GATEWAY_BASE_URL` | `http://127.0.0.1:8001` | SSR 用（见上） |
| `DEER_FLOW_TRUSTED_ORIGINS` | `http://localhost:3000` | SSR 信任 origin |
| `DEER_FLOW_DEV_ALLOWED_ORIGINS` | — | 仅 dev server 的额外 host |
| `BETTER_AUTH_SECRET` | — | 生产必须（compose 注入） |

## 配置优先级总结

```
1. 代码显式传参 config_path
2. 环境变量 DEER_FLOW_CONFIG_PATH / DEER_FLOW_EXTENSIONS_CONFIG_PATH（设了但文件不存在 → 报错）
3. project_root()/config.yaml
     project_root() = DEER_FLOW_PROJECT_ROOT（须为存在的目录）否则 cwd   # config/runtime_paths.py:7-16
4. legacy 候选：backend/config.yaml → repo_root/config.yaml               # config/app_config.py:156-160
   （extensions 侧：extensions_config.json → mcp_config.json；都没有则返回 None，extensions 可选）
```

config.yaml 中 `$VAR` 语法引用环境变量，如 `api_key: $OPENAI_API_KEY`；AppConfig 里缺变量**报错**，ExtensionsConfig 里缺变量**存空串**。
