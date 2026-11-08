---
title: "API 端点详解"
description: "Gateway 是 FastAPI 应用，默认 `http://localhost:8001`。Nginx 统一入口为 `http://localhost:2026`。"
topics: [integration, sdk, docker-deploy]
---

# API 端点详解

Gateway 是 FastAPI 应用，默认 `http://localhost:8001`。Nginx 统一入口为 `http://localhost:2026`。

> **权威划分**：完整的端点清单与请求模型以 [operations/app-layer/01-api-reference.md](../app-layer/01-api-reference.md) 为准（本文只保留集成视角常用的端点摘要 + SSE 协议 + nginx 路由）。两份文档如有出入，以 app-layer 那份为准。

## 端点全景

| 前缀 | 文件 | 关键端点 |
|------|------|----------|
| `/health` | `app.py` | `GET /health` |
| `/api/models` | `models.py` | `GET /` 列表；`GET /{name}` 详情 |
| `/api/mcp` | `mcp.py` | `GET /config`；`PUT /config` |
| `/api/skills` | `skills.py` | `GET /`；`GET /{name}`；`PUT /{name}` enable；`POST /install` |
| `/api/memory` | `memory.py` | `GET /` 数据；`POST /reload`；`DELETE /` 清空；CRUD facts；`GET /export`；`POST /import`；`GET /config`；`GET /status` |
| `/api/threads/{id}/runs` | `thread_runs.py` | `POST /` 创建后台运行；`POST /stream` 创建+SSE；`POST /wait` 创建+阻塞；`GET /` 列表；`GET /{rid}` 详情；`POST /{rid}/cancel` 取消；`GET /{rid}/join` 加入SSE；`GET /{rid}/stream` 获取SSE；`GET /{rid}/messages` 分页消息；`GET /{rid}/events` 事件流 |
| `/api/threads/{id}` | `threads.py` | `DELETE /` 删除线程+本地数据；`POST ""` 创建；`POST /search` 搜索；`GET /{id}` 获取；`PATCH /{id}` 合并metadata；`GET /{id}/state` 状态快照；`POST /{id}/state` 更新状态；`POST /{id}/history` checkpoint历史 |
| `/api/threads/{id}/token-usage` | `thread_runs.py` | `GET /` 聚合token用量 |
| `/api/threads/{id}/messages` | `thread_runs.py` | `GET /` 含feedback的展示消息 |
| `/api/threads/{id}/suggestions` | `suggestions.py` | `POST /` 生成后续问题建议 |
| `/api/threads/{id}/artifacts` | `artifacts.py` | `GET /{path}` 文件下载；`PUT /{path}` 写入 |
| `/api/threads/{id}/uploads` | `uploads.py` | `POST /` 上传文件；`GET /list` 列表；`GET /limits` 限额；`DELETE /{filename}` 删除 |
| `/api/agents` | `agents.py` | `GET /` 自定义Agent列表；`GET /check` 名称检查；`GET/{name}` 获取；`POST /` 创建；`PUT /{name}` 更新；`DELETE /{name}` 删除 |
| `/api/user-profile` | `agents.py` | `GET /` 读取 / `PUT /` 覆盖全局 `USER.md`（顶层路径，**不是** `/api/agents/user-profile`） |
| `/api/v1/auth` | `auth.py` | `POST /login/local`；`POST /register`；`POST /logout`；`POST /change-password`；`GET /me`；`GET /setup-status`；`POST /initialize`；`GET /oauth/{provider}`；`GET /callback/{provider}` |
| `/api/runs` | `runs.py` | `POST /stream` 无状态SSE运行；`POST /wait` 无状态阻塞运行；`GET /{rid}/messages`；`GET /{rid}/feedback` |
| `/api/threads/{id}/runs/{rid}/feedback` | `feedback.py` | Thread/Run feedback CRUD（`feedback.py:20` 的 prefix 是 `/api/threads`，不存在独立 `/api/feedback` 挂载） |
| `/api/channels` | `channels.py` | IM频道管理 |
| `/api/assistants` | `assistants_compat.py` | OpenAI Assistants兼容层 |

---

## 集成视角：异常 → HTTP 摘要

> 这里**不穷举**。全量「领域异常 → HTTP 映射」表在 [operations/app-layer/01-api-reference.md](../app-layer/01-api-reference.md) 的「领域异常 → HTTP 映射」小节；本文只列**集成特有**的几条，出现分歧以 app-layer 那份为准。

### Lark/Feishu 托管集成（`app/gateway/routers/integrations.py`）

| 情况 | 状态码 | 依据 |
|------|--------|------|
| 非管理员调 `POST /api/integrations/lark/install` | 403 `Admin privileges required to install integrations.` | `integrations.py:38,271`（`require_admin_user` → `deps.py:894-902`） |
| `lark-cli` 不存在（`FileNotFoundError`） | 404 | `integrations.py:276-277,296-297,321-322,346-347,369-370,394-395` |
| 参数/流程异常（`ValueError`） | 400 | 同上各端点的 `except ValueError` |
| 流程代际过期（`LarkFlowSupersededError`） | 409 | `integrations.py:323-324,371-372,396-397`（异常定义 `deerflow/integrations/lark_cli.py:266-267`） |
| 轮询/流程超时（`TimeoutError`） | 504 | `integrations.py:300-301,327-328,350-351,375-376,400-401` |
| 其它未预期异常 | 500（泛化 detail） | `integrations.py:264-266,282-284,302-304,329-331,352-354,377-379,402-404` |
| 非管理员读 status/complete | 200，但 `cli.path`/`install_path` 被脱敏为空 | `integrations.py:41-51,182-207,263,320,345,393` |

### GitHub webhook（`app/gateway/routers/github_webhooks.py`）

| 情况 | 状态码 | 依据 |
|------|--------|------|
| 未配置 secret 且未开 `DEER_FLOW_ALLOW_UNVERIFIED_GITHUB_WEBHOOKS=1`，运行期拒绝投递 | 503 | `github_webhooks.py:223-241` |
| `X-Hub-Signature-256` 校验失败/缺失 | 401 | `:249-252` |
| 缺 `X-GitHub-Event` 头 | 400 | `:254-255` |
| body 非合法 JSON（先验签后解析） | 400 | `:257-267` |
| 已识别事件的 fan-out 运行期失败（可人工重投） | 503 | `:363-368` |
| 未识别事件 / 频道未启用 / 载荷格式错误 / 频道服务不可用 | 200 + `handled=false`/skipped | `github_webhooks.py:269-320,375-382`；路由说明见 [integration/04-im-channels.md](04-im-channels.md) |

### IM 频道连接（`app/gateway/routers/channels.py`、`channel_connections.py`）

| 情况 | 状态码 | 依据 |
|------|--------|------|
| Channel 服务未运行（`GET /api/channels/...`） | 503 | `channels.py:50` |
| 连接持久化不可用 | 503 | `channel_connections.py:202` |
| 未认证访问连接端点 | 401 | `channel_connections.py:142` |
| 未知 provider / 连接不存在 | 404 | `channel_connections.py:216-219,358,368,395,566` |
| 连接功能未开启 / provider 未启用 / 缺必填配置 / 启动或停止失败 | 400 | `channel_connections.py:480,558,575-595,622-634,661-689` |
| 单 provider 待处理绑定码超上限 | 429 | `channel_connections.py:346-349` |

---

## 核心 API 详解

### 1. Thread Runs — 对话执行

#### 创建并流式返回 `POST /api/threads/{thread_id}/runs/stream`

```json
// Request
{
  "input": {
    "messages": [
      {"role": "user", "content": "帮我分析 deer-flow 的架构"}
    ]
  },
  "config": {
    "configurable": {
      "model_name": "deepseek",
      "thinking_enabled": true,
      "subagent_enabled": false,
      "is_plan_mode": false
    }
  }
}
```

`configurable` 可选参数：
- `model_name` — 选择模型（不传则用 config.yaml 第一个）
- `thinking_enabled` — 扩展思考（DeepSeek/Claude 等）
- `subagent_enabled` — 允许子 Agent 委托
- `is_plan_mode` — 启用计划模式（TodoList middleware）

```
// Response: SSE (text/event-stream)

event: metadata
data: {"run_id": "xxx", "thread_id": "yyy"}

event: values
data: {"messages": [...], "title": "...", "artifacts": [...], "todos": [...]}

event: messages-tuple
data: [{"type": "AIMessageChunk", "content": "我来分析..."}]

event: custom
data: {"type": "task_started", ...}

event: end
data: {"usage": {"input_tokens": 5000, "output_tokens": 2000}}
```

SSE 事件类型：
- `metadata` — run_id, thread_id
- `values` — ThreadState 全量快照（messages, title, artifacts, todos）
- `messages-tuple` — 增量消息 delta（AI 文本块、tool_call、tool_result）
- `custom` — 自定义事件（子 Agent 状态变化等）
- `end` — 流结束，附带累计 token 用量

#### 后台运行 `POST /api/threads/{thread_id}/runs`

```json
// Request body 同上
// Response: 201
{ "run_id": "xxx", "thread_id": "yyy", "status": "pending" }
```

然后可以：
- `GET /api/threads/{id}/runs/{rid}` — 轮询状态
- `GET /api/threads/{id}/runs/{rid}/join` — 加入 SSE 流
- `POST /api/threads/{id}/runs/{rid}/cancel` — 取消

#### 等待完成 `POST /api/threads/{id}/runs/wait`

请求体同上，阻塞直到运行结束，返回最终 state。

### 2. Stateless Runs — 无状态运行

无需 thread 的运行：

```json
// POST /api/runs/stream
{
  "input": {
    "messages": [
      {"role": "user", "content": "1+1等于几？"}
    ]
  }
}
```

### 3. Threads — 线程管理

```json
// POST /api/threads
{}  // 创建新线程
// Response: { "thread_id": "uuid", "created_at": "...", "metadata": {} }

// GET /api/threads/{id}
// Response: 同上 + "updated_at"

// DELETE /api/threads/{id}
// 删除 LangGraph thread + 本地数据目录 + checkpoints + 历史 run 行
// + run events（用户可见会话历史）+ feedback + threads_meta + 关闭残留 browser session
// 整个清理持一条 durable `delete` reservation；除文件系统那步外各步 best-effort
// （filesystem 失败会以 422/500 中止）；
// 历史 run 只删 operation_kind="run"（保留保护本次请求的 reservation 行）；
// owner 在请求开头解析一次，所有步骤共用

// POST /api/threads/search
{ "metadata": { "key": "value" }, "limit": 10, "offset": 0 }

// GET /api/threads/{id}/state
// 获取最新 LangGraph state 快照

// POST /api/threads/{id}/state
{ "values": { "key": "value" } }
// 更新 state：经 services.reserve_checkpoint_write() 持有 durable
// `checkpoint_write` reservation，run 进行中返回 409
```

### 4. Memory — 用户记忆

```json
// GET /api/memory
// Response: { "memory": { "userContext": {...}, "history": {...}, "facts": [...] } }

// POST /api/memory/reload
// 强制从文件重新加载

// DELETE /api/memory
// 清空所有记忆

// CRUD Facts
// POST   /api/memory/facts
// DELETE /api/memory/facts/{id}
// PATCH  /api/memory/facts/{id}

// GET /api/memory/export
// POST /api/memory/import

// GET /api/memory/config
// GET /api/memory/status
```

### 5. Skills — 技能管理

```json
// GET /api/skills
// Response: { "skills": [...] }

// GET /api/skills/{name}
// Response: { "name": "...", "description": "...", "enabled": true, "path": "..." }

// PUT /api/skills/{name}
{ "enabled": true }   // 切换启用/禁用

// POST /api/skills/install
// Content-Type: multipart/form-data
// 上传 .skill 压缩包安装到 skills/custom/

// GET /api/skills/custom/{name}
// PUT /api/skills/custom/{name}
// DELETE /api/skills/custom/{name}
// GET /api/skills/custom/{name}/history
// POST /api/skills/custom/{name}/rollback
```

### 6. MCP — MCP 服务器配置

```json
// GET /api/mcp/config
// Response: { "mcp_servers": {...} }（McpConfigResponse 只返回 mcp_servers）
// 注意：extensions_config.json 里还支持顶层 mcpInterceptors（自定义 MCP tool 拦截器
// class path 列表），它不在响应模型里，但 PUT 合并时会原样保留（mcp.py:1191-1193）

// PUT /api/mcp/config
{
  "mcp_servers": {
    "github": {
      "enabled": true,
      "type": "stdio",
      "command": "npx",
      "args": ["-y", "@modelcontextprotocol/server-github"],
      "env": { "GITHUB_TOKEN": "ghp_xxx" }
    }
  }
}
```

### 7. Models — 模型列表

```json
// GET /api/models
// Response: { "models": [{"name": "...", "display_name": "...", "supports_thinking": true, ...}] }

// GET /api/models/{name}
// Response: 单个模型详情
```

### 8. Agents — 自定义 Agent 管理

```json
// POST /api/agents
{
  "name": "my-agent",
  "description": "My custom agent",
  "soul": "You are a helpful assistant...",
  "config": { "model_name": "deepseek", "thinking_enabled": true }
}

// PUT /api/agents/{name}     — 更新 SOUL.md + config.yaml
// DELETE /api/agents/{name}  — 删除

// GET /api/user-profile
// PUT /api/user-profile  — 更新 USER.md（用户档案）
```

`agents_api` 需在 config.yaml 中显式开启（默认禁用）。

### 9. Auth — 认证

```json
// POST /api/v1/auth/login/local
{ "email": "user@example.com", "password": "pass" }

// POST /api/v1/auth/register
{ "email": "user@example.com", "password": "pass", "name": "User" }

// POST /api/v1/auth/logout
// GET /api/v1/auth/me
// POST /api/v1/auth/change-password

// GET /api/v1/auth/setup-status      — 管理员是否已创建
// POST /api/v1/auth/initialize        — 初始化第一个管理员

// GET /api/v1/auth/oauth/{provider}   — OAuth 跳转
// GET /api/v1/auth/callback/{provider} — OAuth 回调
```

### 10. Uploads — 文件上传

```bash
# 上传文件
curl -F "files=@report.pdf" http://localhost:8001/api/threads/{id}/uploads

# Response
{
  "success": true,
  "files": [
    {"filename": "report.pdf", "size": 12345, "content_type": "application/pdf"}
  ]
}

# 列表
curl http://localhost:8001/api/threads/{id}/uploads/list

# 删除
curl -X DELETE http://localhost:8001/api/threads/{id}/uploads/report.pdf
```

支持自动转换 PDF/PPT/Excel/Word 为 Markdown（需开启 `auto_convert_documents`）。

### 11. Artifacts — 产物下载

```bash
# 下载 Agent 产出文件
curl http://localhost:8001/api/threads/{id}/artifacts/outputs/result.pdf -o result.pdf
```

安全策略：`text/html`、`application/xhtml+xml`、`image/svg+xml` 强制作为下载附件（防 XSS）。

### 12. Feedback — 反馈

```json
// PUT /api/threads/{id}/runs/{rid}/feedback
{ "rating": 1, "comment": "Good answer" }   // 字段名是 rating（1 或 -1），不是 score

// GET /api/threads/{id}/runs/{rid}/feedback
// GET /api/threads/{id}/runs/{rid}/feedback/stats
```

---

## Nginx 路由规则

统一入口 `http://localhost:2026` 的路由：

| 路径 | 转发目标 |
|------|----------|
| `/api/langgraph/*` | Gateway:8001（rewrite 去掉 `/langgraph`） |
| `/api/models`, `/api/memory`, `/api/mcp`, `/api/skills`, `/api/agents` | Gateway:8001 |
| `/api/threads/*` (regex) | Gateway:8001 |
| `/api/sandboxes` (regex) | **Provisioner:8002**（仅 provisioner/K8s 沙箱模式） |
| `/docs`, `/redoc`, `/openapi.json`, `/health` | Gateway:8001 |
| `/api/*` (catch-all) | Gateway:8001 |
| `/` (其他所有) | Frontend:3000 |

### CORS & CSRF

默认 same-origin（Nginx 同端口）。分离部署时设 `GATEWAY_CORS_ORIGINS` 为前端 origin 列表（逗号分隔），Gateway 的 CORSMiddleware 和 CSRFMiddleware 都会生效。

---

## OpenAPI / Swagger

```bash
# 查看 API 文档
open http://localhost:8001/docs        # Swagger UI
open http://localhost:8001/redoc       # ReDoc
curl http://localhost:8001/openapi.json # OpenAPI schema
```

生产环境设 `GATEWAY_ENABLE_DOCS=false` 关闭。
