---
title: "环境变量全参考"
description: "所有环境变量来自 `.env.example` 和代码中的 `config.py`。"
topics: [setup, configuration, quickstart]
---

# 环境变量全参考

所有环境变量来自 `.env.example` 和代码中的 `config.py`。

## 模型 API Keys

| 变量 | 用途 |
|------|------|
| `OPENAI_API_KEY` | OpenAI 模型 |
| `DEEPSEEK_API_KEY` | DeepSeek 模型 |
| `GEMINI_API_KEY` | Google Gemini |
| `ANTHROPIC_API_KEY` | Anthropic Claude |
| `VOLCENGINE_API_KEY` | 火山引擎（豆包） |
| `NOVITA_API_KEY` | Novita.ai（OpenAI 兼容） |
| `MINIMAX_API_KEY` | MiniMax（OpenAI 兼容） |
| `VLLM_API_KEY` | vLLM 自部署（OpenAI 兼容） |
| `STEPFUN_API_KEY` | 阶跃星辰 StepFun（OpenAI 兼容） |
| `IMAGE_GENERATION_API_KEY` / `_BASE_URL` / `_MODEL` / `_SIZE` / `_PROVIDER` | 图像生成 skill 的 OpenAI 兼容图像 API |
| `OPENVIKING_API_KEY` | OpenViking memory 后端（`memory.manager_class: openviking`） |

## 搜索/Web Fetch API Keys

| 变量 | 用途 |
|------|------|
| `SERPER_API_KEY` | Google Search (serper.dev) |
| `SERPLY_API_KEY` | 🆕 Google Search/News/Scholar (serply.io) |
| `SOFYA_API_KEY` | 🆕 Sofya 搜索/爬取 |
| `TENCENTCLOUD_WSA_APIKEY` | 🆕 腾讯云 WSA 搜索 |
| `TAVILY_API_KEY` | Tavily 搜索 |
| `JINA_API_KEY` | Jina AI Reader (web fetch) |
| `INFOQUEST_API_KEY` | BytePlus InfoQuest 搜索/爬取 |
| `FIRECRAWL_API_KEY` | Firecrawl 搜索/爬取 |
| `EXA_API_KEY` | Exa 搜索 |

## Gateway 配置

| 变量 | 默认值 | 说明 |
|------|--------|------|
| `GATEWAY_HOST` | `0.0.0.0` | Gateway 监听地址 |
| `GATEWAY_PORT` | `8001` | Gateway 端口 |
| `GATEWAY_ENABLE_DOCS` | `true` | Swagger/ReDoc 开关（生产设为 `false`） |
| `GATEWAY_CORS_ORIGINS` | — | 逗号分隔的 origin 列表（分离部署时设置） |

## 运行时路径/配置

| 变量 | 说明 |
|------|------|
| `DEER_FLOW_PROJECT_ROOT` | 项目根目录（用于计算相对路径） |
| `DEER_FLOW_HOME` | 可写数据目录，默认 `.deer-flow` |
| `DEER_FLOW_CONFIG_PATH` | config.yaml 的完整路径 |
| `DEER_FLOW_EXTENSIONS_CONFIG_PATH` | extensions_config.json 的完整路径 |
| `DEER_FLOW_SKILLS_PATH` | Skills 目录（覆盖 config.yaml 中的 skills.path） |
| `DEER_FLOW_DOCKER_SOCKET` | Docker socket 路径（Docker 部署时） |
| `DEER_FLOW_REPO_ROOT` | 仓库根目录（Docker DooD 中用于 Skills host path） |
| `DEER_FLOW_DATE_TIMEZONE` | 🆕 注入 agent 的会话日期所用 IANA 时区（如 `Asia/Shanghai`；非 config schema 字段，date-context 中间件运行时读取） |

## 认证（🆕 v2.1.0）

| 变量 | 说明 |
|------|------|
| `DEER_FLOW_AUTH_DISABLED` | `1` = 关闭认证（认证**默认开启**），所有请求以合成 admin 用户 `"default"` 运行；在 `DEER_FLOW_ENV`/`ENVIRONMENT` = `prod`/`production` 时被忽略（`app/gateway/auth_disabled.py:11-40`） |

## 内部通信

| 变量 | 说明 |
|------|------|
| `DEER_FLOW_INTERNAL_AUTH_TOKEN` | 多 worker/IM 频道之间的共享认证 token |
| `DEER_FLOW_INTERNAL_GATEWAY_BASE_URL` | Frontend SSR 连 Gateway 的 URL，默认 `http://localhost:8001` |
| `DEER_FLOW_TRUSTED_ORIGINS` | CSRF 信任的 origin 列表 |
| `DEER_FLOW_CHANNELS_LANGGRAPH_URL` | IM 频道连 LangGraph API 的 URL |
| `DEER_FLOW_CHANNELS_GATEWAY_URL` | IM 频道连 Gateway API 的 URL |

## IM 频道

| 变量 | 平台 |
|------|------|
| `FEISHU_APP_ID` | 飞书 |
| `FEISHU_APP_SECRET` | 飞书 |
| `SLACK_BOT_TOKEN` | Slack (`xoxb-...`) |
| `SLACK_APP_TOKEN` | Slack (`xapp-...`, Socket Mode) |
| `TELEGRAM_BOT_TOKEN` | Telegram |
| `DISCORD_BOT_TOKEN` | Discord |
| `DINGTALK_CLIENT_ID` | 钉钉 |
| `DINGTALK_CLIENT_SECRET` | 钉钉 |
| `WECOM_BOT_ID` | 企业微信 |
| `WECOM_BOT_SECRET` | 企业微信 |
| `WECHAT_BOT_TOKEN` | 微信（WeChat） |
| `WECHAT_ILINK_BOT_ID` | 微信（WeChat） |
| `BUZZ_PRIVATE_KEY` | Buzz（hex 或 `nsec1…`） |

> 这些变量由用户在 `config.yaml -> channels.<platform>` 里以 `$VAR` 形式引用（不是代码直接 `os.getenv`），由配置加载器解析。

## 可观测性

| 变量 | 说明 |
|------|------|
| `LANGSMITH_TRACING` | 启用 LangSmith 追踪（`true` / `false`） |
| `LANGSMITH_ENDPOINT` | LangSmith API 端点 |
| `LANGSMITH_API_KEY` | LangSmith API Key |
| `LANGSMITH_PROJECT` | LangSmith 项目名 |
| `LANGFUSE_TRACING` | 启用 Langfuse 追踪（`true` / `false`） |
| `LANGFUSE_PUBLIC_KEY` | Langfuse Public Key |
| `LANGFUSE_SECRET_KEY` | Langfuse Secret Key |
| `LANGFUSE_BASE_URL` | Langfuse 服务地址（代码读取点；默认 `https://cloud.langfuse.com`） |
| `MONOCLE_TRACING` / `MONOCLE_EXPORTERS` / `OKAHU_API_KEY` | Monocle OTel 观测（`file`/`console`/`okahu`/`s3`/`blob`/`gcs`） |
| `DEER_FLOW_ENV` / `ENVIRONMENT` | 环境标签（`production` / `staging`），用于 trace metadata；同时是 `DEER_FLOW_AUTH_DISABLED` 的生产环境否决条件 |

## 数据库

| 变量 | 说明 |
|------|------|
| `DATABASE_URL` | PostgreSQL 连接字符串（`postgresql://...`），仅 postgres 后端需要 |

## Docker 专用

| 变量 | 默认值 | 说明 |
|------|--------|------|
| `PORT` | `2026` | Nginx 对外端口 |
| `BIND_HOST` | `127.0.0.1` | Docker 入口发布地址（loopback 默认；`0.0.0.0` 才对外暴露） |
| `GATEWAY_WORKERS` | `1` | uvicorn worker 数（compose 默认单 worker；仅 Redis stream bridge 下才建议调高） |
| `UV_EXTRAS` | — | 如 `postgres` |
| `BETTER_AUTH_SECRET` | — | Frontend session 加密密钥（生产必须） |
| `PNPM_STORE_PATH` | — | pnpm store 路径 |
| `APT_MIRROR` | — | APT 镜像源 |
| `UV_IMAGE` | `ghcr.io/astral-sh/uv:0.11.1` | 构建用 UV 镜像 |
| `UV_INDEX_URL` | `https://pypi.org/simple` | PyPI 索引 |
| `PROVISIONER_API_KEY` | — | provisioner/K8s 沙箱认证（需与 `sandbox.provisioner_api_key` 一致） |
| `E2B_API_KEY` | — | E2B 云沙箱 API Key（仅 `E2BSandboxProvider` 需要） |
| `GITHUB_WEBHOOK_SECRET` | — | GitHub webhook HMAC 校验密钥；未设则 `/api/webhooks/github` 不挂载 |
| `DEER_FLOW_ALLOW_UNVERIFIED_GITHUB_WEBHOOKS` | — | `1` = 开发环境免密钥挂载 GitHub webhook 路由 |

## 其他

| 变量 | 说明 |
|------|------|
| `GITHUB_TOKEN` | GitHub API Token（MCP GitHub server 等使用） |

## 配置优先级总结

```
1. 代码显式传参
2. 环境变量 (如 DEER_FLOW_CONFIG_PATH)
3. 当前目录 config.yaml
4. 父目录 config.yaml (项目根，推荐)
```

config.yaml 中 `$VAR` 语法引用环境变量，如 `api_key: $OPENAI_API_KEY`。
