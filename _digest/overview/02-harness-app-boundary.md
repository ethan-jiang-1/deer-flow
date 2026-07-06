---
title: "Harness / App 两层分层"
description: "DeerFlow 后端最核心的架构决策：严格的两层拆分。"
topics: [architecture, system-overview]
---

# Harness / App 两层分层

DeerFlow 后端最核心的架构决策：严格的两层拆分。

## 边界定义

```
┌─────────────────────────────────────────┐
│              app.*                      │
│  ┌─────────────┐  ┌──────────────────┐  │
│  │ gateway/    │  │ channels/        │  │
│  │ (FastAPI)   │  │ (IM integrations)│  │
│  └──────┬──────┘  └────────┬─────────┘  │
│         │                  │            │
│         └──────┬───────────┘            │
│                │                        │
│         ─ ─ ─ ─│─ ─ ─ ─ ─ ─ ─ ─ ─ ─  │
│                │    依赖方向 →           │
│                ▼                        │
│  ┌──────────────────────────────────┐   │
│  │         deerflow.*               │   │
│  │  (harness 可独立发布为 pip 包)      │   │
│  └──────────────────────────────────┘   │
└─────────────────────────────────────────┘
```

### Harness 层 (`deerflow.*`)

- 包名：`deerflow-harness`（`backend/packages/harness/`）
- **可独立发布**为 pip 包
- 包含 Agent 框架的所有核心逻辑
- **绝不导入 `app.*`**

### App 层 (`app.*`)

- 不发布，仅用于本项目的 Gateway 和 IM 集成
- 导入 `deerflow.*`（允许）
- 包含 FastAPI 路由、认证、IM 频道

## CI 强制执行

`tests/test_harness_boundary.py` 检查 harness 包中的任何文件不得 `import app` 或 `from app`。

```python
# 通过 AST 分析或 import hook 检测违规
# 如果 harness 层导入了 app 层的模块，CI 失败
```

## 为什么这样拆分

| 原因 | 说明 |
|------|------|
| **可测试性** | Harness 可以不依赖 FastAPI/HTTP 层独立测试 |
| **可发布性** | `deerflow-harness` 可以作为 pip 包发布，第三方可以不依赖 Gateway 使用 |
| **关注点分离** | Agent 逻辑不关心 HTTP 细节；HTTP 层不污染 Agent 逻辑 |
| **嵌入式使用** | `DeerFlowClient` 复用整层 harness，无需启动 HTTP 服务 |

## 各层职责

### Harness 层

| 子系统 | 源码路径 |
|--------|----------|
| Lead Agent + Middlewares + Memory | `agents/` |
| Runtime (RunManager, checkpointer, stream bridge) | `runtime/` |
| Sandbox (abstract + local + tools) | `sandbox/` |
| Subagents (executor, registry, builtins) | `subagents/` |
| Tools (assembly, builtins) | `tools/` |
| Models (factory, vllm provider) | `models/` |
| MCP (tools, cache, client) | `mcp/` |
| Skills (loading, storage, parsing) | `skills/` |
| Config (29 files for all config types) | `config/` |
| Community integrations | `community/` |
| Persistence (ORM, engine, models, migrations) | `persistence/` |
| Guardrails (provider protocol, builtins) | `guardrails/` |
| Tracing (LangSmith + Langfuse callbacks) | `tracing/` |
| Reflection (dynamic module/class loading) | `reflection/` |
| DeerFlowClient (embedded SDK) | `client.py` |

### App 层

| 子系统 | 源码路径 |
|--------|----------|
| Gateway App + lifespan | `gateway/app.py` |
| 15 Route Modules | `gateway/routers/` |
| Auth (local, OAuth, JWT) | `gateway/auth/` |
| Auth Middleware | `gateway/auth_middleware.py` |
| CSRF Middleware | `gateway/csrf_middleware.py` |
| Internal Auth (service-to-service) | `gateway/internal_auth.py` |
| LangGraph Auth Compat | `gateway/langgraph_auth.py` |
| Feishu Integration | `channels/feishu.py` (~33KB) |
| Slack Integration | `channels/slack.py` |
| Telegram Integration | `channels/telegram.py` |
| WeChat Integration | `channels/wechat.py` (~53KB) |
| WeCom Integration | `channels/wecom.py` |
| DingTalk Integration | `channels/dingtalk.py` (~31KB) |
| Discord Integration | `channels/discord.py` (~25KB) |
| Channel Manager | `channels/manager.py` (~40KB) |
| Message Bus | `channels/message_bus.py` |
| Channel Store | `channels/store.py` |

## 导入规则总结

```python
# ✓ Harness 内部
from deerflow.agents import make_lead_agent
from deerflow.models import create_chat_model

# ✓ App 内部
from app.gateway.app import app

# ✓ App → Harness（唯一允许的跨层方向）
from deerflow.config import get_app_config
from deerflow.runtime.runs import RunManager

# ✗ Harness → App（被 test_harness_boundary.py 阻止）
# from app.gateway.routers.uploads import ...  # CI 失败
```

## DeerFlowClient 的特殊地位

`DeerFlowClient` 虽然属于 harness 层，但它是"App 的等价替代品"——它复用了 Gateway 的所有底层逻辑（相同的 `make_lead_agent`、`get_app_config`、`get_available_tools` 等），但不需要 HTTP 服务。

这体现了分层的最大价值：harness 可以在两个完全不同的消费者中工作：
1. Gateway API（HTTP 消费者）
2. DeerFlowClient（嵌入式消费者）

而且两者的返回格式通过 `TestGatewayConformance` 测试保证一致。
