---



title: "REST API 端点文档"
description: 'v2.2.0 全部 Gateway 路由的穷举清单（221 条），以及「领域异常 → HTTP 映射」穷举表（每条带 file:line）。'
topics: [gateway, api, rest, error-handling]
verified_against: v2.2.0
last_verified: 2026-11-08
---

# REST API 端点文档

本文档有两块可核对内容：

1. **§1 端点总览** — `backend/app/gateway/routers/*.py` 里 **221** 条 `(方法, 路径)`，逐条给 `file:line`、鉴权、成功码。
2. **§2 领域异常 → HTTP 映射（穷举）** — 按状态码分组，覆盖每个 `raise HTTPException(...)`、每个 `except XxxError → 状态码`，以及路由之前三层中间件的码。`enterprise-operations/integration/**` 通过指针引用本节（§2.19 是路由组级签名，权威行）。

> **核对口径**（v2.2.0，锚点 `58fc5bd5b`）：工作区 `backend/app/gateway/routers/` 与 tag `v2.2.0` 逐字节一致。所有锚点行号均为该 revision 实测（AST 逐体提取 `router.<method>(...)` 装饰器的 `lineno`，并解析各模块 `APIRouter(prefix=...)` 拼出完整路径 —— **不要**手数行号，装饰器在 `@router.post("")` 这类无路径写法上行号会偏 8–10 行）。detail 文本在表中做摘要，不逐字复制长 f-string。
>
> 相比 v2.1.0 基线（`345f08be`，180 条 / 31 个 router 文件），v2.2.0 是 **221 条 / 40 个 router 文件**（另有 `routers/AGENTS.md` 契约文档）。

---

## 1. 端点总览（v2.2.0 穷举）

**221** 条 `(方法, 路径)`：`GET` 100、`POST` 80、`DELETE` 19、`PUT` 12、`PATCH` 9、`WEBSOCKET` 1。另有 3 个不在 `routers/` 内的入口（`/health`、`/health/ready`、`/docs` 三件套）见 §1.2。

> v2.1.0 → v2.2.0 增量：**+41 条**（180 → 221）。新增 40 个文件里的 9 个新 router 带来 30 条，既有 router 增量 11 条：`agents.py` +3（`/agent-tool-groups`、`/agents/import`、`/agents/{name}/export`）、`models.py` +1（`/models/resolve`）、`feedback.py` +2（`feedback/stats`、`feedback/{feedback_id}`）、`subagent_batches.py` +1（`items/{position}`）、`channel_connections.py` +3（`wechat/qr-login` 三条）、`threads.py` +1（`{id}/read`）、`skills.py` +1（`skills/diagnostics/custom`）。

鉴权列含义：

- `x:y` 来自 `@require_permission("x", "y", ...)`（`authz.py:595`）；`(owner)` = `owner_check=True`（不匹配 → **404**），`(require_existing)` = 缺失行也算失败（→ **404**）。
- `admin（require_admin_user）` = 路由体内显式 `require_admin_user()`（`deps.py:894`，非 admin → **403**）。
- `已登录（无 require_permission）` = 只被 `AuthMiddleware` 挡住（未认证 → **401**）。
- 中间件实际执行顺序是 **CSRF → Auth**（见 §3）：所有 `POST/PUT/DELETE/PATCH`（除 `/api/v1/auth/me`、`/api/webhooks/*`、auth-disabled 模式，以及带 `Authorization` 头的请求）先过 `CSRFMiddleware`——缺 token/不匹配 **403**；随后**所有**非公开路由过 `AuthMiddleware`——未认证 **401**。本节鉴权列只写路由自身的额外约束。

### 1.1 routers/ 全部端点

#### Custom Agents / User Profile

源码：`routers/agents.py` — 受 `agents_api.enabled` 门控，关闭时 **403**；v2.2.0 权限从「已登录」改为 `agents:read`/`agents:write`（`authz.py:63-87` 新增的两个权限）🆕 v2.2.0。

| 方法 | 路径 | 鉴权 | 成功码 | 源码 | 摘要 |
|------|------|------|--------|------|------|
| `GET` | `/api/agents` | `agents:read` | 200 | `backend/app/gateway/routers/agents.py:296` | List Custom Agents |
| `GET` | `/api/agent-tool-groups` | `agents:read` | 200 | `backend/app/gateway/routers/agents.py:327` | 🆕 v2.2.0 只投影**已配置的 group 名**，供自定义 Agent 设置白名单；绝不暴露 tool provider 路径/凭据/原始工具配置 |
| `GET` | `/api/agents/check` | `agents:read` | 200 | `backend/app/gateway/routers/agents.py:343` | Check Agent Name |
| `POST` | `/api/agents/import` | `agents:write` | 201 | `backend/app/gateway/routers/agents.py:376` | 🆕 v2.2.0 导入 Agent 包（严格、带版本的**纯定义** JSON）：owner-scoped 且 **create-only**，冲突 **409**，绝不覆盖/upsert；普通创建与导入共用 `_persist_new_agent`（经 `run_drained_write` 排空） |
| `GET` | `/api/agents/{name}/export` | `agents:read` | 200 | `backend/app/gateway/routers/agents.py:407` | 🆕 v2.2.0 导出调用方**可移植**的 `AgentConfig` 字段 + SOUL；排除 `github` 安装绑定、memory 内容、会话与凭据 |
| `GET` | `/api/agents/{name}` | `agents:read` | 200 | `backend/app/gateway/routers/agents.py:458` | Get Custom Agent |
| `POST` | `/api/agents` | `agents:write` | 201 | `backend/app/gateway/routers/agents.py:496` | Create Custom Agent |
| `PUT` | `/api/agents/{name}` | `agents:write` | 200 | `backend/app/gateway/routers/agents.py:532` | Update Custom Agent；v2.2.0 用 `preserve_non_managed_fields(..., new_tool_groups=...)` 在换组后**清掉继承来的知识默认值**（显式 scope/null 仍优先；未变的组不算迁移） |
| `GET` | `/api/user-profile` | `agents:read` | 200 | `backend/app/gateway/routers/agents.py:685` | Get User Profile |
| `PUT` | `/api/user-profile` | `agents:write` | 200 | `backend/app/gateway/routers/agents.py:722` | Update User Profile |
| `DELETE` | `/api/agents/{name}` | `agents:write` | 204 | `backend/app/gateway/routers/agents.py:765` | Delete Custom Agent |

#### Artifacts

源码：`routers/artifacts.py` — owner-scoped `threads:read/write`；编辑受 412/413/415 约束。

| 方法 | 路径 | 鉴权 | 成功码 | 源码 | 摘要 |
|------|------|------|--------|------|------|
| `GET` | `/api/threads/{thread_id}/artifacts/{path:path}` | `threads:read` (owner) | 200 | `backend/app/gateway/routers/artifacts.py:394` | Get Artifact File |
| `PUT` | `/api/threads/{thread_id}/artifacts/{path:path}` | `threads:write` (owner, require_existing) | 200 | `backend/app/gateway/routers/artifacts.py:619` | Update Artifact File |

#### Assistants 兼容层

源码：`routers/assistants_compat.py` — LangGraph Platform SDK 兼容 stub。

| 方法 | 路径 | 鉴权 | 成功码 | 源码 | 摘要 |
|------|------|------|--------|------|------|
| `POST` | `/api/assistants/search` | 已登录（无 `require_permission`） | 200 | `backend/app/gateway/routers/assistants_compat.py:89` | Search assistants. |
| `GET` | `/api/assistants/{assistant_id}` | 已登录（无 `require_permission`） | 200 | `backend/app/gateway/routers/assistants_compat.py:109` | Get an assistant by ID. |
| `GET` | `/api/assistants/{assistant_id}/graph` | 已登录（无 `require_permission`） | 200 | `backend/app/gateway/routers/assistants_compat.py:118` | Get the graph structure for an assistant. |
| `GET` | `/api/assistants/{assistant_id}/schemas` | 已登录（无 `require_permission`） | 200 | `backend/app/gateway/routers/assistants_compat.py:136` | Get JSON schemas for an assistant's input/output/state. |

#### Auth / PAT / OIDC

源码：`routers/auth.py` — 登录/注册/OIDC 公开；PAT 管理要求 session（**403**）。

| 方法 | 路径 | 鉴权 | 成功码 | 源码 | 摘要 |
|------|------|------|--------|------|------|
| `POST` | `/api/v1/auth/login/local` | 公开（限流 429） | 200 | `backend/app/gateway/routers/auth.py:431` | Local email/password login. |
| `POST` | `/api/v1/auth/register` | 公开 | 201 | `backend/app/gateway/routers/auth.py:488` | Register a new user account (always 'user' role). |
| `POST` | `/api/v1/auth/logout` | 公开/session | 200 | `backend/app/gateway/routers/auth.py:517` | Logout current user by clearing the cookie. |
| `POST` | `/api/v1/auth/change-password` | 已登录（无 `require_permission`） | 200 | `backend/app/gateway/routers/auth.py:528` | Change password for the currently authenticated user. |
| `GET` | `/api/v1/auth/me` | session 或 PAT | 200 | `backend/app/gateway/routers/auth.py:592` | Get current authenticated user info, including effective permissions. |
| `POST` | `/api/v1/auth/pats` | 已登录（无 `require_permission`） | 201 | `backend/app/gateway/routers/auth.py:682` | Create a personal access token for the session user. |
| `GET` | `/api/v1/auth/pats` | session-only（PAT 403） | 200 | `backend/app/gateway/routers/auth.py:719` | List the session user's tokens. Never returns digests or raw tokens. |
| `DELETE` | `/api/v1/auth/pats/{pat_id}` | session-only（PAT 403） | 200 | `backend/app/gateway/routers/auth.py:729` | Revoke one of the session user's tokens. Revocation is immediate. |
| `GET` | `/api/v1/auth/setup-status` | 公开 | 200 | `backend/app/gateway/routers/auth.py:752` | Check if an admin account exists. Returns needs_setup=True when no admin exists. |
| `POST` | `/api/v1/auth/initialize` | 公开 | 201 | `backend/app/gateway/routers/auth.py:820` | Create the first admin account on initial system setup. |
| `GET` | `/api/v1/auth/providers` | 公开 | 200 | `backend/app/gateway/routers/auth.py:930` | List enabled SSO providers for the login page. |
| `GET` | `/api/v1/auth/oauth/{provider}` | 公开 | 200 | `backend/app/gateway/routers/auth.py:954` | Initiate OIDC login flow. |
| `GET` | `/api/v1/auth/callback/{provider}` | 公开 | 200 | `backend/app/gateway/routers/auth.py:1030` | OIDC callback endpoint. |

#### Browser 自动化

源码：`routers/browser.py` — 受 `browser_control` 配置门控；未启用 **404**，依赖缺失 **501**，底层失败 **502**。

| 方法 | 路径 | 鉴权 | 成功码 | 源码 | 摘要 |
|------|------|------|--------|------|------|
| `POST` | `/api/threads/{thread_id}/browser/navigate` | `threads:write` (owner, require_existing) | 200 | `backend/app/gateway/routers/browser.py:75` | Navigate The Live Browser Session |
| `WEBSOCKET` | `/api/threads/{thread_id}/browser/stream` | `threads:read` (owner 校验在握手时做) | 101 | `backend/app/gateway/routers/browser.py:214` | 实时浏览器画面/输入流；nginx 有专门的 upgrade 正则（600s read timeout），必须排在通用 threads 正则之前 |

#### Channel Connections

源码：`routers/channel_connections.py` — runtime-config 端点 admin-only；连接码超限 **429**；v2.2.0 新增企业微信扫码登录三件套（**同样 admin-only**，且**只允许单 worker**）🆕。

| 方法 | 路径 | 鉴权 | 成功码 | 源码 | 摘要 |
|------|------|------|--------|------|------|
| `GET` | `/api/channels/providers` | 已登录（无 `require_permission`） | 200 | `backend/app/gateway/routers/channel_connections.py:549` | — |
| `GET` | `/api/channels/connections` | 已登录（无 `require_permission`） | 200 | `backend/app/gateway/routers/channel_connections.py:579` | — |
| `DELETE` | `/api/channels/connections/{connection_id}` | 已登录（无 `require_permission`） | 204 | `backend/app/gateway/routers/channel_connections.py:596` | — |
| `DELETE` | `/api/channels/{provider}/runtime-config` | admin（`require_admin_user`，非 admin **403**） | 200 | `backend/app/gateway/routers/channel_connections.py:612` | — |
| `POST` | `/api/channels/{provider}/connect` | 已登录（无 `require_permission`） | 200 | `backend/app/gateway/routers/channel_connections.py:658` | — |
| `POST` | `/api/channels/{provider}/runtime-config` | admin（`require_admin_user`，非 admin **403**） | 200 | `backend/app/gateway/routers/channel_connections.py:697` | — |
| `POST` | `/api/channels/wechat/qr-login` | admin（`_require_wechat_qr_login`，非 admin **403**） | 200 | `backend/app/gateway/routers/channel_connections.py:813` | 🆕 v2.2.0 起一个企业微信扫码登录会话；响应 `Cache-Control: no-store` |
| `POST` | `/api/channels/wechat/qr-login/{session_id}/poll` | admin（同上） | 200 | `backend/app/gateway/routers/channel_connections.py:824` | 🆕 v2.2.0 轮询扫码状态；可选 body `verify_code`；拿到凭据后走 `_apply_runtime_channel_config(..., "wechat", ...)` 落运行时配置 |
| `DELETE` | `/api/channels/wechat/qr-login/{session_id}` | admin（同上） | 204 | `backend/app/gateway/routers/channel_connections.py:843` | 🆕 v2.2.0 放弃扫码会话 |

三个 wechat QR 路由共用 `_require_wechat_qr_login()`（`:788`）：`require_admin_user` → channel connections 与 `config.wechat` 都必须 enabled（否则 **400**「WeChat channel connections are disabled」）→ **多 worker 直接拒**：`GATEWAY_WORKERS`/`WEB_CONCURRENCY` 解析后 `!= 1`，或 `multi_instance_declaration(config)` 非空，就 **503**（QR 会话与变更锁只活在单进程里，请求落到别的 worker 会读到不存在的 session）。`QRLoginError.status_code` 原样透传。

#### Channels 状态/重启

源码：`routers/channels.py` — 重启需要 admin；channel service 未运行 **503**。

| 方法 | 路径 | 鉴权 | 成功码 | 源码 | 摘要 |
|------|------|------|--------|------|------|
| `GET` | `/api/channels/` | 登录即可 | 200 | `backend/app/gateway/routers/channels.py:29` | Get the status of all IM channels. |
| `POST` | `/api/channels/{name}/restart` | admin | 200 | `backend/app/gateway/routers/channels.py:41` | Restart a specific IM channel. |

#### Console — 跨线程可观测性

源码：`routers/console.py` — `runs:read`；无 SQL backend 时 **503**。

| 方法 | 路径 | 鉴权 | 成功码 | 源码 | 摘要 |
|------|------|------|--------|------|------|
| `GET` | `/api/console/stats` | `runs:read` | 200 | `backend/app/gateway/routers/console.py:289` | Console Stats |
| `GET` | `/api/console/runs` | `runs:read` | 200 | `backend/app/gateway/routers/console.py:363` | List Runs Across Threads |
| `GET` | `/api/console/usage` | `runs:read` | 200 | `backend/app/gateway/routers/console.py:434` | Token Usage Over Time |

#### Features — 前端能力门控

源码：`routers/features.py` — 需要认证（无细粒度权限）。

| 方法 | 路径 | 鉴权 | 成功码 | 源码 | 摘要 |
|------|------|------|--------|------|------|
| `GET` | `/api/features` | 已登录（无 `require_permission`） | 200 | `backend/app/gateway/routers/features.py:98` | List Feature Flags — 🆕 v2.2.0 载荷 8 组：`agents_api`/`browser_control`/`mcp_tasks`/`subagent_batches`/`conversation_references`/`knowledge_base`/`scheduled_tasks`/`thread_activity` |

#### Feedback

源码：`routers/feedback.py` — `threads:write/read/delete` + owner；rating 非法 **400**。

| 方法 | 路径 | 鉴权 | 成功码 | 源码 | 摘要 |
|------|------|------|--------|------|------|
| `PUT` | `/api/threads/{thread_id}/runs/{run_id}/feedback` | `threads:write` (owner, require_existing) | 200 | `backend/app/gateway/routers/feedback.py:62` | Create or update feedback for a run (idempotent). |
| `DELETE` | `/api/threads/{thread_id}/runs/{run_id}/feedback` | `threads:delete` (owner, require_existing) | 200 | `backend/app/gateway/routers/feedback.py:93` | Delete the current user's feedback for a run. |
| `POST` | `/api/threads/{thread_id}/runs/{run_id}/feedback` | `threads:write` (owner, require_existing) | 200 | `backend/app/gateway/routers/feedback.py:113` | Submit feedback (thumbs-up/down) for a run. |
| `GET` | `/api/threads/{thread_id}/runs/{run_id}/feedback` | `threads:read` (owner) | 200 | `backend/app/gateway/routers/feedback.py:146` | List feedback for a run. |
| `GET` | `/api/threads/{thread_id}/runs/{run_id}/feedback/stats` | `threads:read` (owner) | 200 | `backend/app/gateway/routers/feedback.py:158` | 🆕 v2.2.0 该 run 的反馈聚合计数 |
| `DELETE` | `/api/threads/{thread_id}/runs/{run_id}/feedback/{feedback_id}` | `threads:delete` (owner, require_existing) | 200 | `backend/app/gateway/routers/feedback.py:170` | 🆕 v2.2.0 按 feedback_id 删除单条反馈 |

#### GitHub Webhooks

源码：`routers/github_webhooks.py` — HMAC 校验，失败 **401**；未配置 secret 时**整个路由不挂载**（404）。

| 方法 | 路径 | 鉴权 | 成功码 | 源码 | 摘要 |
|------|------|------|--------|------|------|
| `POST` | `/api/webhooks/github` | HMAC（无 JWT/CSRF） | 200 | `backend/app/gateway/routers/github_webhooks.py:173` | Receive a GitHub webhook delivery. |

#### Input Polish

源码：`routers/input_polish.py` — `runs:create`；LLM 调用失败 **503**。

| 方法 | 路径 | 鉴权 | 成功码 | 源码 | 摘要 |
|------|------|------|--------|------|------|
| `POST` | `/api/input-polish` | `runs:create` | 200 | `backend/app/gateway/routers/input_polish.py:58` | Polish Composer Input |

#### Integrations（Lark）

源码：`routers/integrations.py` — 写操作 admin-only（**403**）；Lark 流程被取代 **409**，CLI 超时 **504**，未安装 **404**；`GET /status` 对非 admin 只脱敏不拒绝（见 §2.19）。

| 方法 | 路径 | 鉴权 | 成功码 | 源码 | 摘要 |
|------|------|------|--------|------|------|
| `GET` | `/api/integrations/lark/status` | 已登录（非 admin 只回脱敏状态） | 200 | `backend/app/gateway/routers/integrations.py:262` | — |
| `POST` | `/api/integrations/lark/install` | admin | 200 | `backend/app/gateway/routers/integrations.py:272` | — |
| `POST` | `/api/integrations/lark/config/start` | admin | 200 | `backend/app/gateway/routers/integrations.py:306` | — |
| `POST` | `/api/integrations/lark/config/complete` | admin | 200 | `backend/app/gateway/routers/integrations.py:326` | — |
| `POST` | `/api/integrations/lark/config/credentials` | admin | 200 | `backend/app/gateway/routers/integrations.py:353` | — |
| `POST` | `/api/integrations/lark/auth/start` | 已登录 | 200 | `backend/app/gateway/routers/integrations.py:376` | — |
| `POST` | `/api/integrations/lark/auth/complete` | 已登录 | 200 | `backend/app/gateway/routers/integrations.py:401` | — |

#### MCP 配置（平台级）

源码：`routers/mcp.py` — 全部 admin（`require_admin_user`，detail `_ADMIN_REQUIRED_DETAIL = "Admin privileges required to manage MCP configuration."` `mcp.py:48`）；配置非法 **400**。v2.2.0 起 personal MCP 走独立前缀 `/api/mcp/personal/config`（见 §1.3）。

| 方法 | 路径 | 鉴权 | 成功码 | 源码 | 摘要 |
|------|------|------|--------|------|------|
| `GET` | `/api/mcp/config` | admin（`require_admin_user`，非 admin **403**） | 200 | `backend/app/gateway/routers/mcp.py:1147` | Get MCP Configuration |
| `POST` | `/api/mcp/cache/reset` | admin | 200 | `backend/app/gateway/routers/mcp.py:1559` | Reset MCP Tools Cache |
| `PUT` | `/api/mcp/config` | admin | 200 | `backend/app/gateway/routers/mcp.py:1588` | Update MCP Configuration（整表替换） |
| `POST` | `/api/mcp/config/servers` | admin | 200 | `backend/app/gateway/routers/mcp.py:1647` | Create MCP Servers |
| `PUT` | `/api/mcp/config/server` | admin | 200 | `backend/app/gateway/routers/mcp.py:1669` | Update MCP Server |
| `DELETE` | `/api/mcp/config/servers/{server_name:path}` | admin | 200 | `backend/app/gateway/routers/mcp.py:1694` | Delete MCP Server |
| `PATCH` | `/api/mcp/config` | admin | 200 | `backend/app/gateway/routers/mcp.py:1715` | Update MCP Server State（enabled 开关） |

#### MCP 长任务

源码：`routers/mcp_tasks.py` — owner-scoped `threads:read/write`；worker 未运行时 `app.state.mcp_tasks_available` 为假，全部 **503**。

| 方法 | 路径 | 鉴权 | 成功码 | 源码 | 摘要 |
|------|------|------|--------|------|------|
| `GET` | `/api/threads/{thread_id}/mcp-tasks` | `threads:read` (owner) | 200 | `backend/app/gateway/routers/mcp_tasks.py:93` | 🆕 v2.2.0 支持 `TaskStatus` 与 `active_only` 过滤（只把**真的仍是 active** 的 task status 报成非终态） |
| `GET` | `/api/threads/{thread_id}/mcp-tasks/{task_id}` | `threads:read` (owner) | 200 | `backend/app/gateway/routers/mcp_tasks.py:134` | 不存在/不可见统一 **404**「MCP task not found」 |
| `POST` | `/api/threads/{thread_id}/mcp-tasks/{task_id}/cancel` | `threads:write` (owner) | 200 | `backend/app/gateway/routers/mcp_tasks.py:176` | worker 未运行 **503** |

#### Memory

源码：`routers/memory.py` — 需要认证；后端不支持的操作 **501**，并发冲突 **409**。

| 方法 | 路径 | 鉴权 | 成功码 | 源码 | 摘要 |
|------|------|------|--------|------|------|
| `GET` | `/api/memory` | 已登录（无 `require_permission`） | 200 | `backend/app/gateway/routers/memory.py:255` | Get Memory Data |
| `POST` | `/api/memory/reload` | 已登录 | 200 | `backend/app/gateway/routers/memory.py:308` | Reload Memory Data |
| `DELETE` | `/api/memory` | 已登录 | 200 | `backend/app/gateway/routers/memory.py:353` | Clear All Memory Data |
| `POST` | `/api/memory/facts` | 已登录 | 200 | `backend/app/gateway/routers/memory.py:384` | Create Memory Fact |
| `DELETE` | `/api/memory/facts/{fact_id}` | 已登录 | 200 | `backend/app/gateway/routers/memory.py:423` | Delete Memory Fact |
| `PATCH` | `/api/memory/facts/{fact_id}` | 已登录 | 200 | `backend/app/gateway/routers/memory.py:457` | Patch Memory Fact |
| `GET` | `/api/memory/export` | 已登录 | 200 | `backend/app/gateway/routers/memory.py:496` | Export Memory Data |
| `POST` | `/api/memory/import` | 已登录 | 200 | `backend/app/gateway/routers/memory.py:517` | Import Memory Data |
| `GET` | `/api/memory/config` | 已登录 | 200 | `backend/app/gateway/routers/memory.py:551` | Get Memory Configuration |
| `GET` | `/api/memory/status` | 已登录 | 200 | `backend/app/gateway/routers/memory.py:601` | Get Memory Status |

#### Models — 模型目录

源码：`routers/models.py` — 需要认证；`GET /{name}` 另做 `model:use` 授权（`authz.py:413 authorize_model_use`），fail-closed 时 **403**；v2.2.0 新增 `GET /api/models/token-usage` 🆕。

| 方法 | 路径 | 鉴权 | 成功码 | 源码 | 摘要 |
|------|------|------|--------|------|------|
| `POST` | `/api/models/resolve` | 已登录（候选逐个过 `model:use`，全部被拒时降级为 `status: unavailable` 而非 403） | 200 | `backend/app/gateway/routers/models.py:103` | 🆕 v2.2.0 只读预览：把用户的任务文本解析成模型选择，**绝不**启动 run、绝不改默认模型 |
| `GET` | `/api/models` | 已登录（无 `require_permission`） | 200 | `backend/app/gateway/routers/models.py:135` | List All Models |
| `GET` | `/api/models/{model_name}` | 已登录 + `model:use`（fail-closed **403**） | 200 | `backend/app/gateway/routers/models.py:221` | Get Model Details；不存在 **404**「Model '<n>' not found」 |

#### Project Document Shelf

源码：`routers/project_documents.py` — `projects:*`（部分叠加 `threads:*`）；归档项目上架 **404**，内容缺失 **409**。

| 方法 | 路径 | 鉴权 | 成功码 | 源码 | 摘要 |
|------|------|------|--------|------|------|
| `GET` | `/api/projects/{project_id}/documents` | `projects:read` | 200 | `backend/app/gateway/routers/project_documents.py:173` | — |
| `POST` | `/api/projects/{project_id}/documents` | `projects:write` | 201 | `backend/app/gateway/routers/project_documents.py:197` | Shelf exactly one file (§17.2): 201 created, or 200 on a content dedup hit. |
| `POST` | `/api/projects/{project_id}/documents/from-thread` | `projects:write` + `threads:read` | 201 | `backend/app/gateway/routers/project_documents.py:304` | Copy one thread file (upload or output) into the shelf (§7.4). |
| `POST` | `/api/projects/{project_id}/documents/{document_id}/attach-to-thread/{thread_id}` | `projects:write` + `threads:write` (owner, require_existing) | 200 | `backend/app/gateway/routers/project_documents.py:376` | Materialize an independent copy of a shelf document into a thread (§7.3 item 3). |
| `GET` | `/api/projects/{project_id}/documents/{document_id}/content` | `projects:read` | 200 | `backend/app/gateway/routers/project_documents.py:454` | Inline text or attachment for one active shelf document (§6.5). |
| `DELETE` | `/api/projects/{project_id}/documents/{document_id}` | `projects:delete` | 204 | `backend/app/gateway/routers/project_documents.py:528` | Move one document to trash (204). Restore/purge are the Slice-D trash tier. |

#### Project Thread Files

源码：`routers/project_thread_files.py` — `projects:read` + `threads:read`。

| 方法 | 路径 | 鉴权 | 成功码 | 源码 | 摘要 |
|------|------|------|--------|------|------|
| `GET` | `/api/projects/{project_id}/thread-files` | `projects:read` + `threads:read` | 200 | `backend/app/gateway/routers/project_thread_files.py:102` | Aggregate member threads' files, paged by thread (§6.5/§7.4). |

#### Projects

源码：`routers/projects.py` — `projects:read/write/delete`；缺失/他人/已归档项目统一 **404**（fail closed）。

| 方法 | 路径 | 鉴权 | 成功码 | 源码 | 摘要 |
|------|------|------|--------|------|------|
| `POST` | `/api/projects` | `projects:write` | 201 | `backend/app/gateway/routers/projects.py:116` | — |
| `GET` | `/api/projects` | `projects:read` | 200 | `backend/app/gateway/routers/projects.py:124` | — |
| `GET` | `/api/projects/config` | `projects:read` | 200 | `backend/app/gateway/routers/projects.py:131` | Projects config for the UI (instructions byte cap, trash retention). |
| `GET` | `/api/projects/{project_id}` | `projects:read` | 200 | `backend/app/gateway/routers/projects.py:146` | — |
| `PATCH` | `/api/projects/{project_id}` | `projects:write` | 200 | `backend/app/gateway/routers/projects.py:155` | — |
| `POST` | `/api/projects/{project_id}/archive` | `projects:write` | 200 | `backend/app/gateway/routers/projects.py:165` | — |
| `POST` | `/api/projects/{project_id}/restore` | `projects:write` | 200 | `backend/app/gateway/routers/projects.py:174` | — |
| `DELETE` | `/api/projects/{project_id}` | `projects:delete` | 204 | `backend/app/gateway/routers/projects.py:183` | — |
| `GET` | `/api/projects/{project_id}/threads` | `projects:read` + `threads:read` | 200 | `backend/app/gateway/routers/projects.py:190` | — |

#### Stateless Runs

源码：`routers/runs.py` — `runs:create`/`runs:read`；可选 body `thread_id` 做 owner 检查。

| 方法 | 路径 | 鉴权 | 成功码 | 源码 | 摘要 |
|------|------|------|--------|------|------|
| `POST` | `/api/runs/stream` | `runs:create` | 200 | `backend/app/gateway/routers/runs.py:40` | Create a run and stream events via SSE. |
| `POST` | `/api/runs/wait` | `runs:create` | 200 | `backend/app/gateway/routers/runs.py:61` | Create a run and block until completion. |
| `GET` | `/api/runs/{run_id}/messages` | `runs:read` | 200 | `backend/app/gateway/routers/runs.py:113` | Return paginated messages for a run (cursor-based). |
| `GET` | `/api/runs/{run_id}/feedback` | `runs:read` | 200 | `backend/app/gateway/routers/runs.py:144` | Return all feedback for a run. |

#### Scheduled Tasks

源码：`routers/scheduled_tasks.py` — `threads:*`+`runs:create`；v2.2.0 起**所有**错误都是 `{code, message, params}` 结构化 detail（`scheduled_task_errors.py`），触发派发失败 **502**、scheduler 未运行 **409** `scheduler_not_running`（全仓少见 5xx 业务码）🆕。

| 方法 | 路径 | 鉴权 | 成功码 | 源码 | 摘要 |
|------|------|------|--------|------|------|
| `POST` | `/api/scheduled-tasks/preview-cron` | `threads:read` | 200 | `backend/app/gateway/routers/scheduled_tasks.py:234` | Preview future cron instants without creating or dispatching a task. |
| `GET` | `/api/scheduled-tasks` | `threads:read` | 200 | `backend/app/gateway/routers/scheduled_tasks.py:245` | — |
| `POST` | `/api/scheduled-tasks` | `threads:write` + `runs:create` | 200 | `backend/app/gateway/routers/scheduled_tasks.py:255` | 新增 **409** `scheduler_not_running`（本进程 poller 未跑，否则任务永不执行）；通知组非法 **422** `invalid_notification_group`，查询通知组时 scheduler 不可用 **503** `scheduler_unavailable` |
| `GET` | `/api/scheduled-tasks/{task_id}` | `threads:read` | 200 | `backend/app/gateway/routers/scheduled_tasks.py:294` | — |
| `PATCH` | `/api/scheduled-tasks/{task_id}` | `threads:write` + `runs:create` | 200 | `backend/app/gateway/routers/scheduled_tasks.py:307` | — |
| `POST` | `/api/scheduled-tasks/{task_id}/pause` | `threads:write` | 200 | `backend/app/gateway/routers/scheduled_tasks.py:358` | — |
| `POST` | `/api/scheduled-tasks/{task_id}/resume` | `threads:write` + `runs:create` | 200 | `backend/app/gateway/routers/scheduled_tasks.py:391` | — |
| `POST` | `/api/scheduled-tasks/{task_id}/trigger` | `threads:write` + `runs:create` | 200 | `backend/app/gateway/routers/scheduled_tasks.py:428` | **502** `trigger_failed`；占用中 **409** `task_changed`/`task_running` |
| `DELETE` | `/api/scheduled-tasks/{task_id}` | `threads:write` | 200 | `backend/app/gateway/routers/scheduled_tasks.py:453` | — |
| `GET` | `/api/scheduled-tasks/{task_id}/runs` | `threads:read` | 200 | `backend/app/gateway/routers/scheduled_tasks.py:473` | — |
| `GET` | `/api/threads/{thread_id}/scheduled-tasks` | `threads:read` (owner) | 200 | `backend/app/gateway/routers/scheduled_tasks.py:494` | — |
| `GET` | `/api/threads/{thread_id}/scheduled-task-events` | `threads:read` (owner) | 200 | `backend/app/gateway/routers/scheduled_tasks.py:505` | 🆕 v2.2.0 该会话中调用方任务的生命周期事件（暂停/自动暂停/完成），带标题快照所以任务删除后行仍在；`limit` 1–200 默认 50 |

#### Skills

源码：`routers/skills.py` — 管理端点经 `require_admin_user`（`_ADMIN_REQUIRED_DETAIL` `skills.py:71`，非 admin **403**）；安装/编辑被安全扫描阻断 **400**；上传超限 **413**。**读取端**（`GET /skills`、`/skills/custom`、`/skills/{name}`）对所有登录用户开放，`authorization.enabled` 时按 `provider.filter_resources("skill")` 过滤（fail-closed → 空列表 / 详情 404；fail-open → 全量）🆕 v2.2.0。

| 方法 | 路径 | 鉴权 | 成功码 | 源码 | 摘要 |
|------|------|------|--------|------|------|
| `GET` | `/api/skills` | 已登录（`authorization.enabled` 时按角色过滤） | 200 | `backend/app/gateway/routers/skills.py:498` | List All Skills |
| `POST` | `/api/skills/install` | admin（`require_admin_user`，非 admin **403**） | 200 | `backend/app/gateway/routers/skills.py:526` | Install Skill |
| `POST` | `/api/skills/install/upload` | admin | 200 | `backend/app/gateway/routers/skills.py:543` | Upload and Install Skill；包体超限 **413** |
| `POST` | `/api/skills/reload` | admin | 200 | `backend/app/gateway/routers/skills.py:598` | Reload Skills |
| `GET` | `/api/skills/custom` | 已登录（与 `GET /skills` 同一可见性过滤，否则会泄漏主列表隐藏的名字） | 200 | `backend/app/gateway/routers/skills.py:645` | List Custom Skills |
| `GET` | `/api/skills/diagnostics/custom` | admin | 200 | `backend/app/gateway/routers/skills.py:672` | 🆕 v2.2.0 列出调用方自有 custom skill 的 YAML 载入诊断；响应 `Cache-Control: no-store` |
| `GET` | `/api/skills/custom/{skill_name}/export-manifest` | admin | 200 | `backend/app/gateway/routers/skills.py:687` | Preview Custom Skill Export（槽位满 **429** `skill_export_busy`） |
| `GET` | `/api/skills/custom/{skill_name}/export` | admin | 200 | `backend/app/gateway/routers/skills.py:707` | Download Custom Skill Archive（120s idle 超时；客户端断连 **204**） |
| `GET` | `/api/skills/custom/{skill_name}` | admin | 200 | `backend/app/gateway/routers/skills.py:728` | Get Custom Skill Content |
| `PUT` | `/api/skills/custom/{skill_name}` | admin | 200 | `backend/app/gateway/routers/skills.py:760` | Edit Custom Skill |
| `DELETE` | `/api/skills/custom/{skill_name}` | admin | 200 | `backend/app/gateway/routers/skills.py:827` | Delete Custom Skill |
| `GET` | `/api/skills/custom/{skill_name}/history` | admin | 200 | `backend/app/gateway/routers/skills.py:876` | Get Custom Skill History |
| `POST` | `/api/skills/custom/{skill_name}/rollback` | admin | 200 | `backend/app/gateway/routers/skills.py:911` | Rollback Custom Skill |
| `GET` | `/api/skills/{skill_name}` | 已登录（不可见的 skill 与不存在一样 **404**，避免成为存在性探针） | 200 | `backend/app/gateway/routers/skills.py:1012` | Get Skill Details |
| `PUT` | `/api/skills/{skill_name}` | admin | 200 | `backend/app/gateway/routers/skills.py:1095` | Update Skill（enabled 开关） |

#### backend/app/gateway/routers/subagent_batches.py

源码：`backend/app/gateway/routers/subagent_batches.py`

| 方法 | 路径 | 鉴权 | 成功码 | 源码 | 摘要 |
|------|------|------|--------|------|------|
| `GET` | `/api/threads/{thread_id}/subagent-batches` | `threads:read` (owner) | 200 | `backend/app/gateway/routers/subagent_batches.py:43` | — |
| `GET` | `/api/threads/{thread_id}/subagent-batches/{batch_id}` | `threads:read` (owner) | 200 | `backend/app/gateway/routers/subagent_batches.py:50` | — |
| `GET` | `/api/threads/{thread_id}/subagent-batches/{batch_id}/items` | `threads:read` (owner) | 200 | `backend/app/gateway/routers/subagent_batches.py:57` | — |
| `GET` | `/api/threads/{thread_id}/subagent-batches/{batch_id}/items/{position}` | `threads:read` (owner) | 200 | `backend/app/gateway/routers/subagent_batches.py:73` | 🆕 v2.2.0 按 position 取单条 item |
| `POST` | `/api/threads/{thread_id}/subagent-batches/{batch_id}/pause` | `threads:write` (owner) | 200 | `backend/app/gateway/routers/subagent_batches.py:93` | — |
| `POST` | `/api/threads/{thread_id}/subagent-batches/{batch_id}/resume` | `threads:write` (owner) | 200 | `backend/app/gateway/routers/subagent_batches.py:100` | — |
| `POST` | `/api/threads/{thread_id}/subagent-batches/{batch_id}/cancel` | `threads:write` (owner) | 200 | `backend/app/gateway/routers/subagent_batches.py:107` | — |
| `POST` | `/api/threads/{thread_id}/subagent-batches/{batch_id}/items/{item_id}/retry` | `threads:write` (owner) | 200 | `backend/app/gateway/routers/subagent_batches.py:119` | 非 failed 状态 **409** |
| `GET` | `/api/threads/{thread_id}/subagent-batches/{batch_id}/results.jsonl` | `threads:read` (owner) | 200 | `backend/app/gateway/routers/subagent_batches.py:129` | — |

#### backend/app/gateway/routers/subagents.py

源码：`backend/app/gateway/routers/subagents.py`

| 方法 | 路径 | 鉴权 | 成功码 | 源码 | 摘要 |
|------|------|------|--------|------|------|
| `GET` | `/api/subagents` | 已登录（无 `require_permission`） | 200 | `backend/app/gateway/routers/subagents.py:164` | List Subagents |
| `POST` | `/api/subagents` | admin（`require_admin_user`，非 admin **403**） | 201 | `backend/app/gateway/routers/subagents.py:171` | Create Managed Subagent |
| `PUT` | `/api/subagents/{name}` | admin（`require_admin_user`，非 admin **403**） | 200 | `backend/app/gateway/routers/subagents.py:196` | Update Managed Subagent |
| `DELETE` | `/api/subagents/{name}` | admin（`require_admin_user`，非 admin **403**） | 204 | `backend/app/gateway/routers/subagents.py:232` | Delete Managed Subagent |

#### Suggestions

源码：`routers/suggestions.py` — `threads:read` + owner；生成失败**静默降级**为空数组（不报错）。

| 方法 | 路径 | 鉴权 | 成功码 | 源码 | 摘要 |
|------|------|------|--------|------|------|
| `GET` | `/api/suggestions/config` | 已登录（无 `require_permission`） | 200 | `backend/app/gateway/routers/suggestions.py:86` | Get Suggestions Configuration |
| `POST` | `/api/threads/{thread_id}/suggestions` | `threads:read` (owner) | 200 | `backend/app/gateway/routers/suggestions.py:98` | Generate Follow-up Questions |

#### Thread Runs / Messages

源码：`routers/thread_runs.py` — owner-scoped `runs:*`；GET stream 携带 `action` 时 **405**。

| 方法 | 路径 | 鉴权 | 成功码 | 源码 | 摘要 |
|------|------|------|--------|------|------|
| `POST` | `/api/threads/{thread_id}/runs/regenerate/prepare` | `runs:create` (owner, require_existing) | 200 | `backend/app/gateway/routers/thread_runs.py:963` | Prepare input and checkpoint for regenerating the latest assistant turn. |
| `POST` | `/api/threads/{thread_id}/runs/edit-regenerate/prepare` | `runs:create` (owner, require_existing) | 200 | `backend/app/gateway/routers/thread_runs.py:974` | Prepare input and checkpoint for editing then rerunning the latest user turn. |
| `POST` | `/api/threads/{thread_id}/runs` | `runs:create` (owner, require_existing) | 200 | `backend/app/gateway/routers/thread_runs.py:985` | Create a background run (returns immediately). |
| `POST` | `/api/threads/{thread_id}/runs/stream` | `runs:create` (owner, require_existing) | 200 | `backend/app/gateway/routers/thread_runs.py:1003` | Create a run and stream events via SSE. |
| `POST` | `/api/threads/{thread_id}/runs/wait` | `runs:create` (owner, require_existing) | 200 | `backend/app/gateway/routers/thread_runs.py:1053` | Create a run and block until it completes, returning the final state. |
| `GET` | `/api/threads/{thread_id}/runs` | `runs:read` (owner) | 200 | `backend/app/gateway/routers/thread_runs.py:1215` | List the newest runs for a thread (default 100, as a bare array). |
| `GET` | `/api/threads/{thread_id}/runs/page` | `runs:read` (owner) | 200 | `backend/app/gateway/routers/thread_runs.py:1225` | Return a newest-first keyset page of runs for a thread. |
| `GET` | `/api/threads/{thread_id}/runs/{run_id}` | `runs:read` (owner) | 200 | `backend/app/gateway/routers/thread_runs.py:1267` | Get details of a specific run. |
| `POST` | `/api/threads/{thread_id}/runs/{run_id}/cancel` | `runs:cancel` (owner, require_existing) | 200 | `backend/app/gateway/routers/thread_runs.py:1279` | Cancel a running or pending run. |
| `GET` | `/api/threads/{thread_id}/runs/{run_id}/join` | `runs:read` (owner) | 200 | `backend/app/gateway/routers/thread_runs.py:1340` | Join an existing run's SSE stream. |
| `POST` | `/api/threads/{thread_id}/runs/{run_id}/stream` | `runs:read` (owner) | 200 | `backend/app/gateway/routers/thread_runs.py:1450` | Join an existing run's SSE stream, optionally cancelling it first. |
| `GET` | `/api/threads/{thread_id}/runs/{run_id}/stream` | `runs:read` (owner) | 200 | `backend/app/gateway/routers/thread_runs.py:1463` | Join an existing run's observation-only SSE stream. |
| `GET` | `/api/threads/{thread_id}/messages` | `runs:read` (owner) | 200 | `backend/app/gateway/routers/thread_runs.py:1480` | Return displayable messages for a thread (across all runs), with feedback attached. |
| `GET` | `/api/threads/{thread_id}/messages/page` | `runs:read` (owner) | 200 | `backend/app/gateway/routers/thread_runs.py:1620` | Return a backward page ordered by the thread-global event sequence. |
| `GET` | `/api/threads/{thread_id}/runs/{run_id}/messages` | `runs:read` (owner) | 200 | `backend/app/gateway/routers/thread_runs.py:1648` | Return paginated messages for a specific run. |
| `GET` | `/api/threads/{thread_id}/runs/{run_id}/artifacts/archive` | `runs:read` (owner, require_existing) | 200 | `backend/app/gateway/routers/thread_runs.py:1762` | Return the verified terminal delivery count used by the archive. |
| `POST` | `/api/threads/{thread_id}/runs/{run_id}/artifacts/archive` | `runs:read` (owner, require_existing) | 200 | `backend/app/gateway/routers/thread_runs.py:1778` | Download the current contents of the files presented by one terminal run. |
| `GET` | `/api/threads/{thread_id}/runs/{run_id}/events` | `runs:read` (owner) | 200 | `backend/app/gateway/routers/thread_runs.py:1837` | Return the full event stream for a run (debug/audit). |
| `GET` | `/api/threads/{thread_id}/runs/{run_id}/workspace-changes` | `runs:read` (owner) | 200 | `backend/app/gateway/routers/thread_runs.py:1885` | Return workspace/output file changes recorded for one run. |
| `GET` | `/api/threads/{thread_id}/token-usage` | `threads:read` (owner) | 200 | `backend/app/gateway/routers/thread_runs.py:1908` | Thread-level token usage aggregation. |

#### Threads 生命周期与组织

源码：`routers/threads.py` — owner-scoped；冲突类操作（run 在跑）统一 **409**。

| 方法 | 路径 | 鉴权 | 成功码 | 源码 | 摘要 |
|------|------|------|--------|------|------|
| `DELETE` | `/api/threads/{thread_id}` | `threads:delete` (owner, require_existing) | 200 | `backend/app/gateway/routers/threads.py:756` | Delete local persisted filesystem data for a thread. |
| `POST` | `/api/threads` | `threads:write` | 200 | `backend/app/gateway/routers/threads.py:959` | Create a new thread. |
| `POST` | `/api/threads/{thread_id}/branches` | `threads:write` (owner, require_existing) | 200 | `backend/app/gateway/routers/threads.py:1051` | Create a new main-thread branch from a completed assistant turn. |
| `POST` | `/api/threads/search` | `threads:read` | 200 | `backend/app/gateway/routers/threads.py:1286` | Search and list threads. |
| `POST` | `/api/threads/{thread_id}/read` | `threads:read` (owner) | 200 | `backend/app/gateway/routers/threads.py:1349` | 🆕 v2.2.0 写该用户对该 thread 的读标记（`thread_read_markers`）；无 SQL 持久化 **503**，`/api/features` 的 `thread_activity.available` 是门控 |
| `PATCH` | `/api/threads/{thread_id}` | `threads:write` (owner, require_existing) | 200 | `backend/app/gateway/routers/threads.py:1365` | Merge metadata into a thread record. |
| `POST` | `/api/threads/{thread_id}/move` | `threads:write` (owner, require_existing) | 200 | `backend/app/gateway/routers/threads.py:1404` | Move a thread between projects (or out). Organizational only: history, |
| `GET` | `/api/threads/{thread_id}` | `threads:read` (owner) | 200 | `backend/app/gateway/routers/threads.py:1425` | Get thread info from metadata plus the graph's materialized state. |
| `GET` | `/api/threads/{thread_id}/goal` | `threads:read` (owner) | 200 | `backend/app/gateway/routers/threads.py:1478` | Return the active Claude-style goal for a thread, if any. |
| `PUT` | `/api/threads/{thread_id}/goal` | `threads:write` (owner) | 200 | `backend/app/gateway/routers/threads.py:1491` | Set or replace the active goal for a thread. |
| `DELETE` | `/api/threads/{thread_id}/goal` | `threads:write` (owner) | 200 | `backend/app/gateway/routers/threads.py:1517` | Clear the active goal for a thread. |
| `POST` | `/api/threads/{thread_id}/compact` | `threads:write` (owner, require_existing) | 200 | `backend/app/gateway/routers/threads.py:1548` | Manually summarize old thread context while preserving the visible history. |
| `GET` | `/api/threads/{thread_id}/state` | `threads:read` (owner) | 200 | `backend/app/gateway/routers/threads.py:1597` | Get the latest materialized graph state for a thread. |
| `POST` | `/api/threads/{thread_id}/state` | `threads:write` (owner, require_existing) | 200 | `backend/app/gateway/routers/threads.py:1646` | Replace selected thread-state fields through the materialized graph. |
| `POST` | `/api/threads/{thread_id}/history` | `threads:read` (owner) | 200 | `backend/app/gateway/routers/threads.py:1865` | Get materialized graph state history for a thread. |

#### Trash 回收站

源码：`routers/trash.py` — `projects:read/write/delete`；文件清理失败 **500**（行仍留在回收站）。

| 方法 | 路径 | 鉴权 | 成功码 | 源码 | 摘要 |
|------|------|------|--------|------|------|
| `GET` | `/api/trash/documents` | `projects:read` | 200 | `backend/app/gateway/routers/trash.py:137` | List the caller's trashed documents (most recently trashed first). |
| `POST` | `/api/trash/documents/{document_id}/restore` | `projects:write` | 200 | `backend/app/gateway/routers/trash.py:171` | Restore one trashed document into an active project (§8.2). |
| `POST` | `/api/trash/documents/{document_id}/purge` | `projects:delete` | 204 | `backend/app/gateway/routers/trash.py:208` | Permanently purge one trashed document: bytes first, then the row (§8.3). |
| `POST` | `/api/trash/purge` | `projects:delete` | 200 | `backend/app/gateway/routers/trash.py:226` | Empty the trash: purge every trashed document of the caller (§8.3). |

#### Uploads

源码：`routers/uploads.py` — owner-scoped `threads:*`；单文件/总量超限 **413**，不安全文件名静默跳过。

| 方法 | 路径 | 鉴权 | 成功码 | 源码 | 摘要 |
|------|------|------|--------|------|------|
| `POST` | `/api/threads/{thread_id}/uploads` | `threads:write` (owner) | 200 | `backend/app/gateway/routers/uploads.py:394` | Upload multiple files to a thread's uploads directory；v2.2.0 起经 staging→`os.link` 原子无覆盖提交（详见 [02-upload-security.md](02-upload-security.md)），返回 `success=bool(uploaded_files)` 与 `skipped_files` |
| `GET` | `/api/threads/{thread_id}/uploads/limits` | `threads:read` (owner) | 200 | `backend/app/gateway/routers/uploads.py:494` | Return upload limits used by the gateway for this thread. |
| `GET` | `/api/threads/{thread_id}/uploads/list` | `threads:read` (owner) | 200 | `backend/app/gateway/routers/uploads.py:505` | List all files in a thread's uploads directory. |
| `DELETE` | `/api/threads/{thread_id}/uploads/{filename}` | `threads:delete` (owner, require_existing) | 200 | `backend/app/gateway/routers/uploads.py:517` | Delete a file from a thread's uploads directory. |

#### User Preferences

源码：`routers/user_preferences.py` — 仅 session 认证（PAT/内部调用 **403**）；账号切换 **409**。

| 方法 | 路径 | 鉴权 | 成功码 | 源码 | 摘要 |
|------|------|------|--------|------|------|
| `GET` | `/api/v1/auth/preferences` | 已登录 + session provenance（PAT/内部调用 **403**） | 200 | `backend/app/gateway/routers/user_preferences.py:51` | — |
| `PATCH` | `/api/v1/auth/preferences` | 同上；body 带 `x_expected_user_id` 时账号已切换 **409** | 204 | `backend/app/gateway/routers/user_preferences.py:66` | 无响应体（204）；写入是串行化的列写 |

### 1.2 routers/ 之外的入口

| 方法 | 路径 | 鉴权 | 源码 | 说明 |
|------|------|------|------|------|
| `GET` | `/health` | 公开（`_PUBLIC_PATH_PREFIXES` 含 `/health`） | `app/gateway/app.py:1446` | 纯 liveness，进程活着即 200 `{"status":"healthy"}` |
| `GET` | `/health/ready` | 公开 | `app/gateway/app.py:1455`；实现 `app/gateway/health.py` | 并发探测 ORM engine + 生效 checkpointer/Store + stream bridge 的 Redis 后端，单端点统一 deadline；沙箱 provisioner 的 `/health` **只报告不作为门控**（每个副本共享一个 provisioner）。主判据失败或启动目标无法解析 → **503** `status: degraded`，否则 200 |
| `—` | `/docs`、`/redoc`、`/openapi.json` | 公开 | `app.py:1096-1098` | `config.enable_docs` 为假时三个 URL 都变成 `None`（不注册 → 404）；环境变量 `GATEWAY_ENABLE_DOCS` 覆盖 config |

`WS /api/threads/{thread_id}/browser/stream` 已移入 §1.1（它确实是 `routers/browser.py:215` 的 `@router.websocket`），认证细节见 §2 的 WS close code 表。

**条件挂载**：`POST /api/webhooks/github` 只在 `GITHUB_WEBHOOK_SECRET` 已设置，或显式 dev opt-in `DEER_FLOW_ALLOW_UNVERIFIED_GITHUB_WEBHOOKS=1` 时挂载（`app.py:1441`）；否则**整个路由不注册 → 404**（fail-closed：配置缺失的部署无法被伪造投递命中）。

**扩展贡献的路由**在**所有 host 路由之后** mount，因此 host 路径永远优先于扩展同路径；扩展路由器同样经 `AuthMiddleware`（它不是公开前缀）。

### 1.3 🆕 v2.2.0 新增端点组（相对 v2.1.0）

v2.1.0 的 180 条已全部保留在 §1.1；以下 9 组新 router 是 **v2.2.0 才出现**的 HTTP 面（30 条），逐组给前缀、鉴权模型与要点：

| 组 | router | 条数 | 鉴权模型 | 要点 |
|----|--------|------|---------|------|
| 账户生命周期 | `admin_users.py` | 2 | 全部 `require_admin_user`（handler 体内） | `GET /api/v1/admin/users`（`:60`）、`PATCH /{user_id}`（`:68`）。PATCH 无字段 **422**「nothing to update」，role 不在 `assignable_role_names()` **422**，用户不存在 **404**，降级最后一个 admin / 禁用最后一个活跃 admin **409**。role 与 disabled **各走一个串行化列写**（最后 admin 计数与写在同一事务里） |
| Capability Center | `capabilities.py` | 3 | `catalog` 公开；安装按 `scope` | `GET /api/capabilities/catalog`（`:27`，插件清单）、`GET /installations/{adapter}`（`:32`，`scope=deployment|user|all`）、`POST /installations`（`:37`）。适配器注册表在 `app/gateway/capabilities.py:218 AdapterRegistry` / `:234 registry`，注册 `mcp`/`business`/`lark`/`skills`；未知 adapter **422**「This capability only has a setup guide; no installation adapter is available」；`scope=deployment` 非 admin **403**；`scope=user` 只允许 `mcp`/`business`（其它适配器仍要 admin）；`can_manage = scope == "user" or is_admin_user(request)`。重复注册同一 adapter → `ValueError` |
| 知识检索目录 | `knowledge.py` | 3 | `threads:read` | `GET /capabilities`（`:74`）、`GET /retrieval-catalog/datasets`（`:88`）、`GET /retrieval-catalog/datasets/{dataset_id:path}/documents`（`:102`）。**只读目录 + 准入**，实际资源授权/映射归 provider 适配器 |
| 托管模型 | `managed_models.py` | 4 | admin | `GET /providers`（`:69`）、`GET /`（`:75`）、`PUT /`（`:115`）、`POST /test`（`:157`）。`route_class=RedactedModelRoute` 让密钥在响应里脱敏；`POST /test` 是流式且强制关 DeepSeek thinking；所有客户端/存储调用 off-loop |
| Personal MCP | `personal_mcp.py` | 5 | **owner-only** | `GET /api/mcp/personal/config`（`:114`）、`POST /servers`（`:134`）、`PUT /server`（`:139`）、`PATCH /`（`:144`）、`DELETE /servers/{server_name:path}`（`:149`）。与平台级 `/api/mcp/config*`（admin-only）**不同前缀、不同授权**；admin 判定经 `personal_mcp_access.py:23 personal_mcp_authority()` 绑到 Gateway 账户表 |
| 全栈插件 | `plugins.py` | 5 | 诊断 admin-only，其余已登录 | `GET /diagnostics`（`:47`）、`GET /`（`:69`）、`GET /modules/{module}/{revision}.mjs`（`:102`）、`GET /{namespace}/assets/{revision}/{path:path}`（`:113`）、`POST /{namespace}/actions/{action_name}`（`:136`）。revision = **前端模块内容哈希**（不匹配 404）；assets 用 `immutable` + `Vary: Cookie, Authorization` + `CSP: sandbox`；action 的 413/409/422/502/504 见 §2 |
| Skill 变更操作 | `skill_mutations.py` | 4 | admin | `GET /operations`（`:32`）、`GET /operations/{operation_id}`（`:40`）、`POST /operations/{operation_id}/recover`（`:45`）、`POST /owners/{owner_id}/recover`（`:50`）。worker 不可用 **503**；末页 `next_cursor: null` |
| Thread 活动流 | `thread_activity.py` | 1 | `threads:read` | `GET /api/thread-activity`（`:72`）。基于 `runs.change_seq` 的每用户增量 feed，游标 `"seq:run_id"`，非法游标 **422** `invalid_cursor`，`_MAX_CHANGE_SEQ = 2**63-1`，limit 1–500 默认 200；无 SQL 持久化 **503**「Thread activity is not available」 |
| IM 通知偏好 | `im_notification_preferences.py` | 2 | 已登录 + `X-Expected-User-Id` | `GET /api/channels/notification-preferences`（`:41`）、`PATCH /`（`:47`）。头与当前账号不符 **409**「The signed-in account changed; reload this page」；无 session factory **503** |
| 项目线程文件聚合 | `project_thread_files.py` | 1 | `projects:read` + `threads:read` | v2.1.0 已有此 router，v2.2.0 补进文档：`GET /api/projects/{project_id}/thread-files`（`:105`），按 thread 分页聚合成员线程的文件 |

**既有 router 的 v2.2.0 增量**（各 1 道，已并入 §1.1 的表）：`GET /api/agent-tool-groups`、`POST /api/agents/import`、`GET /api/agents/{name}/export`、`POST /api/models/resolve`、`GET .../feedback/stats`、`DELETE .../feedback/{feedback_id}`、`GET .../subagent-batches/{batch_id}/items/{position}`、`POST/GET/DELETE /api/channels/wechat/qr-login*`、`POST /api/threads/{thread_id}/read`、`GET /api/skills/diagnostics/custom`。

---

## 2. 领域异常 → HTTP 映射（穷举，v2.2.0）

> 小节标题固定为「领域异常 → HTTP 映射」，供 `enterprise-operations/integration/**` 以指针方式引用（`integration/01-overview.md`、`integration/05-lark-cli-managed-integration.md` 指向本文件）。**§2 的小节编号与含义在 v2.2.0 保持不变**（§2.5、§2.6、§2.7、§2.8、§2.19 均未改号），只在各小节内追加 v2.2.0 的新码。

### 2.0 状态码总表

> **口径说明（重要）**：下表「端点可达数」= 在**该端点自身函数体内**出现的该状态码的端点数（AST 统计），因此**系统性低估**——中间件产生的 401/403（`AuthMiddleware`/`CSRFMiddleware`）、`require_permission` 装饰器产生的 401/403/404、Pydantic 自动产生的 422、以及经 helper 抛出的码都不计入端点函数体。真实可达面应理解为「表值 + 中间件面」。v2.1.0 版本曾给出 400:42 / 401:173 / 403:137 / 404:123 / 422:149 这组数字，它是按「全部 `raise HTTPException` 字面量 + 中间件覆盖」估算的，v2.2.0 无法用同样口径复算（新增路由在 handler 体内调 `require_admin_user` 而非装饰器），故此处换成可复算的函数体口径，并标注不可比。

| 码 | 端点自身函数体内出现（v2.2.0，AST） | v2.1.0 旧值（不可比，见上） | 一句话语义 |
|----|-----------------------------------|---------------------------|-----------|
| 400 | 34 | 42 | 请求形状合法但**语义非法**（非法 rating / 非法 URL / 配置校验失败 / 空文件 / 非文件路径 / 预留文件名） |
| 401 | 3 | 173 | 未认证。**主要来源是中间件**（除 `/health`、`/docs`、`/redoc`、`/openapi.json`、`/api/v1/auth/oauth/`、`/api/v1/auth/callback/`、`/api/webhooks/` 与 6 个 `_PUBLIC_EXACT_PATHS` 之外的全部路由）；handler 体内只有 3 处（`plugins.py` 的 `_principal`、`mcp_tasks.py`、插件 action）。另有 GitHub HMAC 校验失败也映射 401（§2.2） |
| 403 | 4 | 137 | 已认证但**无权限**：`require_permission` 装饰器（不在统计内）、`require_admin_user`（v2.2.0 self-check 有 7 个新 router 在体内调用，不在统计内）、`agents_api` 关闭、PAT 越界（session-only 端点）、CSRF 失败、插件被管理员禁用 |
| 404 | 55 | 123 | 不存在**或不属于你**（fail closed，防枚举）；路由未挂载也 404（`/api/webhooks/github`、插件 assets/modules、不可见 skill） |
| 405 | 1（依赖注入，不在 AST） | 1 | 只用于 `GET /api/threads/{id}/runs/{rid}/stream?action=...`（`thread_runs.py` 的 `_reject_get_stream_action`） |
| 409 | 27 | 55 | **多义码**：run 在跑 / 幂等键冲突 / 资源已存在 / 状态机冲突 / 内容缺失 / 账号已变更 / 插件 viewer 变更 / 定时任务 `scheduler_not_running` / 最后一个 admin（§2.6） |
| 412 | 1 | 1 | artifact 编辑的 `expected_sha256` 不匹配 |
| 413 | 5 | 8 | 请求体/文件/归档超出上限（上传、skill 包、artifact 编辑、归档 ZIP、**插件 action 输入 256 KiB**） |
| 415 | 5（同 1 个端点） | 5 | artifact 编辑的媒体类型不支持（`.skill`、符号链接、二进制、非 UTF-8、含 NUL） |
| 416 | 1 | 1 | `GET artifact` 的 `Range` 不可满足 |
| 422 | 12 | 149 | Pydantic/FastAPI 校验失败（含 `extra="forbid"` 的未知字段）——**统计外**，凡有 body/query model 的端点都可达；handler 体内手写的领域 422 有 12 处：`admin_users`、`capabilities`（未知 adapter）、`knowledge`/`scheduled_tasks`（非法通知组）、`thread_activity`（`invalid_cursor`）、`plugins`（非 JSON object / 无效 action 输入）、`managed_models` 等 |
| 429 | 5 个端点可达 | 5 | 限流/并发槽位：登录失败锁定、IM 连接码上限、artifact 归档并发槽位、skill 导出槽位、团队/子 agent 并发 |
| 500 | 54 | — | 未预期异常的统一兜底；v2.2.0 起上传/删除/附件删除/列 skill 的 500 detail 都是**固定文本**（不再回显异常内容，避免泄漏路径/内部信息） |
| 501 | 1 | — | 后端/平台不支持该操作（memory 后端、浏览器依赖缺失等，多数经 helper） |
| 502 | 4 | — | 上游失败：浏览器底层失败、定时任务派发 `trigger_failed`、OIDC `sso_failed`、插件 action 失败 |
| 503 | 9 | — | 依赖不可用：console 无 SQL、mcp_tasks worker 未跑、thread activity 无持久化、WeChat QR 多 worker、skill mutation worker、managed 通知组 scheduler、`/health/ready` degraded、artifact 归档超时、插件 settings 不可读 |
| 504 | 6 | — | 超时：Lark CLI 超时、插件 action 30s 超时等 |

### 2.1 400 Bad Request

| 场景 | detail 摘要 | 源码锚点 |
|------|------------|---------|
| MCP 配置校验失败（所有 MCP 写路由） | `Invalid MCP configuration: ...` | `routers/mcp.py:1144-1151`（helper）；调用方 `:1163`、`:1171`、`_validate_mcp_update_request` |
| MCP 请求体字段非法 | `_validate_mcp_update_request` 内部 | 由 `:1478`、`:1508`、`:1531` 调用 |
| feedback rating 不是 ±1 | `rating must be +1 or -1` | `routers/feedback.py:72`（PUT）、`:123`（POST） |
| browser 未给 URL | `URL is required` | `routers/browser.py:97` |
| browser 导航参数非法（`ValueError`） | `str(exc)` | `routers/browser.py:104` |
| input polish 文本为空/超长 | `Input text is required` / `Input text exceeds N characters` | `routers/input_polish.py:80`、`:84` |
| IM 连接功能关闭 / provider 未启用 / 未配置 / 启停失败 | `Channel connections are disabled`、`Channel provider is not enabled`、`Channel provider is not configured`、`Failed to start/stop <name> channel...` | `routers/channel_connections.py:558`、`:575`、`:579`、`:595`、`:622`、`:630`、`:632`、`:634`、`:661`、`:665`、`:689` |
| 上传未给文件 | `No files provided` | `routers/uploads.py:414` |
| 上传目录初始化 `ValueError` | `str(exc)` | `routers/uploads.py:437` |
| uploads list/delete 的 `ValueError` | `str(exc)` | `routers/uploads.py:511`、`:531` |
| delete 路径穿越 | `Invalid path`（`PathTraversalError`） | `routers/uploads.py:529` |
| artifact 路径不是普通文件 | `Path is not a file: <path>` | `routers/artifacts.py:89` |
| 项目文档文件名非法（空/含分隔符/超 255 UTF-8 字节） | `str(exc)` | `routers/project_documents.py:229`、`:345` |
| 项目文档内容为空 | `Empty file` | `routers/project_documents.py:234`、`:350` |
| skill 安装文件名不以 `.skill` 结尾 | `Skill archive filename must end with .skill` | `routers/skills.py:579` |
| skill multipart 解析失败（非超限） | `MultiPartException.message` | `routers/skills.py:590` |
| skill 编辑/回滚被安全扫描阻断 | `Security scan blocked the edit: ...` / `Rollback blocked by security scanner: ...` | `routers/skills.py:800`、`:906` |
| skill 内容/名称 `ValueError` | `str(e)` | `routers/skills.py:544`、`:820`、`:870`、`:915` |
| skill 无历史 / 选中历史项无 `prev_content` / `history_index` 越界 | `Custom skill '<n>' has no history`、`Selected history entry has no previous content...`、`history_index is out of range` | `routers/skills.py:897`、`:900`、`:928` |
| memory fact 校验失败（confidence / agent_name / 空内容） | `Invalid confidence value...`、`An agent name is required...`、`Memory fact content cannot be empty.` | `routers/memory.py:113-124`（`_map_memory_fact_value_error`），调用点 `:325`、`:383` |
| thread search 元数据过滤器非法 | `str(exc)`（`InvalidMetadataFilterError`） | `routers/threads.py:1198` |
| Lark 流程 `ValueError` | `str(e)` | `routers/integrations.py:279`、`:299`、`:326`、`:349`、`:374`、`:399` |
| GitHub webhook 缺 `X-GitHub-Event` / JSON 非法 | `Missing X-GitHub-Event header`、`Invalid JSON body` | `routers/github_webhooks.py:255`、`:267` |
| auth：邮箱已注册 / 改密码各类拒绝 | `Email already registered`、`Current password is incorrect`、`OAuth users cannot change password`、`Password changes are not available when DEER_FLOW_AUTH_DISABLED=1.` | `routers/auth.py:475`、`:520`、`:529`、`:532`、`:540`、`:810` |
| auth：PAT 名称非法 | `str(exc)` | `routers/auth.py:667` |
| auth：OIDC provider 非法 / 缺 code/state | `Invalid provider ID`、`Unknown SSO provider: x`、`Missing code or state parameter` | `routers/auth.py:929`、`:933`、`:1017`、`:1021`、`:1024` |
| run 准入：模型不在 allowlist | `Model 'x' is not in the configured model allowlist` | `app/gateway/services.py:2204`（`start_run` `:2128`） |
| run 准入：`input.messages` 不是列表 | `input.messages must be a list` | `app/gateway/services.py:2423`（`start_run` `:2128`） |
| checkpoint 配置非法 / 线程不匹配 / configurable 非对象 | `checkpoint must be an object`、`checkpoint thread_id does not match request thread_id`、`request config configurable must be an object` | `app/gateway/services.py:1839`、`:1842`、`:1875`（`apply_checkpoint_to_run_config` `:1824`） |
| run 输入归一化失败 | 见 `normalize_input` | `app/gateway/services.py:682`（`normalize_input`） |

> **400 vs 422 的边界**：Pydantic 模型/路径参数/query 的**形状**问题一律由 FastAPI 自动给 **422**（§2.11）；router 里手写的 400 用于「形状对但语义错」。MCP 是唯一把「配置内容非法」也写成 400 的领域（因为它同时被 Pydantic 校验与 runtime `validate_raw_extensions_config` 校验）。

---

### 2.2 401 Unauthorized

| 场景 | detail 摘要 | 源码锚点 |
|------|------------|---------|
| 中间件：非公开路径无 session cookie | `Authentication required`（code `NOT_AUTHENTICATED`） | `app/gateway/auth_middleware.py:169` |
| 中间件：Bearer PAT 无效 | 直接回传 `exc.status_code`（401 `token_expired` / `token_invalid` / `user_not_found`） | `app/gateway/auth_middleware.py:130-134` |
| `require_auth` 装饰器 | `Authentication required` | `app/gateway/authz.py:946` |
| `require_permission` 装饰器 | `Authentication required` | `app/gateway/authz.py:1029` |
| `AuthContext.require_user()` | `Authentication required` | `app/gateway/authz.py:130` |
| 本地登录密码错 | `Incorrect email or password`（code `INVALID_CREDENTIALS`） | `routers/auth.py:417` |
| **GitHub webhook HMAC 校验失败** | `Invalid or missing X-Hub-Signature-256` | `routers/github_webhooks.py:252` — 注意这里用的是 **401**，不是 403 |
| scheduled tasks 手写认证检查（11 处） | `Authentication required` | `routers/scheduled_tasks.py:171`、`:195`、`:258`、`:273`、`:384`、`:416`、`:446`、`:466`、`:496`、`:509` |
| MCP task 手写认证检查 | `Authentication required` | `routers/mcp_tasks.py:59`（`_current_user_id`），被 `:68`、`:87`、`:106` 调用 |
| subagent batch 手写认证检查 | `Authentication required` | `routers/subagent_batches.py:26`（`_user_id`），被全部 8 个端点调用 |
> **fail-closed 的 404 是刻意的**：`require_permission(owner_check=True)` 对「行不存在」或「owner 不同」都返回 **404**，不会返回 403 —— 见 `authz.py:676-719` 的注释。

---

### 2.3 403 Forbidden

| 场景 | detail 摘要 | 源码锚点 |
|------|------------|---------|
| `require_permission`：已认证但缺权限 | `Permission denied: <resource>:<action>` | `app/gateway/authz.py:670` |
| `require_admin_user`：非 admin | 各路由自定义（`_ADMIN_REQUIRED_DETAIL` 等） | `app/gateway/deps.py:894-903`；调用点见 §1.1 中 `admin（require_admin_user）` 行（mcp 5、skills 6、integrations install/配置类、channels restart、channel_connections runtime-config 2） |
| `agents_api.enabled=false` | `Custom-agent management API is disabled. Set agents_api.enabled=true ...` | `routers/agents.py:114-121`（`_require_agents_api_enabled`），8 个 agents/user-profile 路由全部调用 |
| 自注册关闭 | `Self-registration is disabled on this deployment` | `routers/auth.py:467` |
| 改密码要求交互式 session | `Password changes require interactive session authentication` | `routers/auth.py:516` |
| OIDC state cookie 缺失/过期或 state 不匹配 | `Missing or expired OIDC state cookie`、`OIDC state mismatch` | `routers/auth.py:1029`、`:1032` |
| 模型对当前角色不可用 | `Model '<n>' is not available for your role` | `routers/models.py:180`、`:196`；`_AuthorizationUnavailable(fail_closed=True)` → `:178` |
| 偏好端点非 session 认证（PAT / 内部 token） | `Preferences require an authenticated browser session` | `routers/user_preferences.py:27` |
| 中间件：PAT 访问非 allowlist 路由（默认拒绝） | `PAT credentials are not permitted on this route` | `app/gateway/auth_middleware.py:136-141` |
| CSRF：跨站 auth 请求 | `Cross-site auth request denied.` | `app/gateway/csrf_middleware.py:226` |
| CSRF：缺 token | `CSRF token missing. Include X-CSRF-Token header.` | `app/gateway/csrf_middleware.py:244` |
| CSRF：token 不匹配（常数时间比较） | `CSRF token mismatch.` | `app/gateway/csrf_middleware.py:250` |

> **401 vs 403 语义**：401 = 没有可用身份（含 PAT 无效、GitHub HMAC 失败）；403 = 有身份但策略拒绝（权限、admin、feature flag、PAT 越界、CSRF/Origin）。

---

### 2.4 404 Not Found（本版**没有 410**）

| 场景 | detail 摘要 | 源码锚点 |
|------|------------|---------|
| `require_permission(owner_check=True)`：线程行缺失或 owner 不同 | `Thread <id> not found` | `app/gateway/authz.py:716` |
| 项目缺失/他人/已归档（fail closed，不可区分） | `Project not found` | `routers/projects.py:90`；调用点 `:151`、`:161`、`:170`、`:179`、`:187`、`:195` |
| 项目文档缺失/他人 | `Project document not found` | `routers/project_documents.py:103`；调用点 `:197`、`:212`、`:289`、`:300`、`:309`、`:326`、`:372`、`:374`、`:436`、`:494` |
| 项目 thread-files 视图 | `Project not found` | `routers/project_thread_files.py:67`；调用点 `:122` |
| 回收站文档缺失/他人 | `Trash document not found` | `routers/trash.py:115`；调用点 `:191`、`:198`、`:201`、`:223` |
| agent 不存在 | `Agent '<n>' not found` | `routers/agents.py:302`、`:394`（`FileNotFoundError`） |
| assistant 兼容层不存在 | `Assistant <id> not found` | `routers/assistants_compat.py:115`、`:127`、`:144` |
| thread 不存在 / 项目不存在（create、move） | `Thread not found`、`Project not found`、`Thread or project not found` | `routers/threads.py:905`、`:908`、`:1265`、`:1305`、`:1436` |
| run 不存在（thread-scoped 与 stateless） | `Run <id> not found` | `routers/thread_runs.py:1151`、`:1178`、`:1222`；`routers/runs.py:104`（`_resolve_run`） |
| scheduled task 不存在 | `Scheduled task not found` | `routers/scheduled_tasks.py:202`、`:261`、`:276`、`:295`、`:374`、`:387`、`:400`、`:419`、`:434`、`:449`、`:452`、`:474`、`:499` |
| MCP task 不存在 | `MCP task not found` | `routers/mcp_tasks.py:97`、`:125` |
| subagent batch 不存在/不属于该线程 | `Subagent batch not found` | `routers/subagent_batches.py:36`（`_owned_batch`），被 7 个端点调用 |
| managed subagent 不存在 | `Managed subagent '<n>' not found` | `routers/subagents.py:204`、`:219`、`:238` |
| custom skill / skill 不存在（含历史文件） | `Custom skill '<n>' not found`、`Skill '<n>' not found` | `routers/skills.py:449`、`:490`、`:520`、`:545`、`:560`、`:594`、`:616`、`:700` |
| memory fact 不存在 | `Memory fact '<id>' not found.` | `routers/memory.py:353`、`:386`（`KeyError`） |
| feedback / 反馈条目不存在 | `No feedback found for this run`、`Feedback <id> not found` | `routers/feedback.py:79`、`:81`、`:109`、`:183`、`:185`、`:188` |
| PAT 不存在 | `Token not found` | `routers/auth.py:706` |
| 上传文件不存在 | `File not found: <name>` | `routers/uploads.py:461` |
| artifact 不存在 | `Artifact not found: <path>` | `routers/artifacts.py:82` |
| checkpoint 不存在 | `Checkpoint not found`、`Checkpoint <id> not found` | `routers/threads.py:1504`、`:1518`；`app/gateway/services.py:1869` |
| Lark 集成未安装 | `str(e)`（`FileNotFoundError`） | `routers/integrations.py:277`、`:297`、`:322`、`:347`、`:370`、`:395` |
| browser 线程不存在 / 浏览器功能未启用 | `Thread <id> not found`、`Browser automation is not enabled` | `routers/browser.py:85`、`:88` |
| input polish 关闭 | `Input polishing is disabled` | `routers/input_polish.py:73` |
| **GitHub webhook 路由未挂载**（未配置 secret） | 无 handler | `app/gateway/app.py:970-976` |

> 本仓库刻意**不用 410**：删除后的 thread 走 `authz.require_existing=True` → 404；删除后的文档走回收站 → 404。这样攻击者无法区分「曾经存在」与「从未存在」。

---

### 2.5 405 Method Not Allowed

| 场景 | detail 摘要 | 源码锚点 |
|------|------------|---------|
| `GET /api/threads/{thread_id}/runs/{run_id}/stream` 带 `?action=interrupt` 或 `?action=rollback` | `action` is only supported on POST requests，响应头 `Allow: POST` | `routers/thread_runs.py:1248-1252`（`_reject_get_stream_action`），作为 `dependencies=[Depends(...)]` 挂在 `:1347` |

语义：SameSite=Lax 下跨站顶层安全导航仍会带 session cookie，所以必须在**线程 owner 检查之前**拒绝状态变更；`GET` join 永远是只读观察。

---

### 2.6 409 Conflict（**五种完全不同的语义**）

**(a) 线程/run 正在执行 → 409**（同一个 detail 家族，不同措辞）

| detail 摘要 | 源码锚点 |
|------------|---------|
| `Thread has a run in flight. Save after the run finishes.`（artifact 编辑） | `routers/artifacts.py:695`（`ConflictError`） |
| `Thread has work in flight. Delete it after the work finishes.` | `routers/threads.py:777` |
| `Thread has work in flight. Branch it after the work finishes.` | `routers/threads.py:1066` |
| `Thread has a run in flight. Set the goal after the run finishes.` | `routers/threads.py:1359` |
| `Thread has a run in flight. Clear the goal after the run finishes.` | `routers/threads.py:1377` |
| `Thread has a run in flight. Compact after the run finishes.` | `routers/threads.py:1428` |
| `Context compaction is disabled.`（`ContextCompactionDisabled`） | `routers/threads.py:1432` |
| `Thread has a run in flight. Update state after the run finishes.` | `routers/threads.py:1562` |
| `Run <id> is not active on this worker and cannot be streamed` | `routers/thread_runs.py:1034`、`:1351`、`:1400` |
| `Artifacts are currently being modified; try again shortly` | `routers/thread_runs.py:1811` |
| `Scheduled task is currently running; retry after the active execution finishes` | `routers/scheduled_tasks.py:369`（+ `:95`） |
| `Scheduled task is already launching or running; ...` | `routers/scheduled_tasks.py:382`、`:469` |
| `Scheduled task has an active <queued/launching/running> occurrence; ...`（`queued` 追加「可 pause 取消」） | `_ensure_task_mutable` `scheduled_tasks.py:90-104`；`_active_occurrence_conflict_detail` `:40-44`；调用点 `:371`、`:429` |

**(b) 幂等键冲突 → 409**

| detail | 锚点 |
|--------|------|
| `Idempotency-Key already used with a different request`（同键但 `input`/`assistant_id`/`conversation_references` 不同） | `app/gateway/services.py:2688`、`:2714` |
| `ConflictError` 透传（`multitask_strategy` 拒绝/回滚时的活动 run 冲突） | `app/gateway/services.py:2744`（`start_run` 内 `except UnsupportedStrategyError`） |

适用于 `POST /api/threads/{id}/runs`、`/runs/stream`、`/runs/wait`（`thread_runs.py:925/943/998`），stateless `/api/runs/*` **不在**该契约内。

**(c) 资源名已存在 → 409**

| detail | 锚点 |
|--------|------|
| `Agent '<n>' already exists` | `routers/agents.py:361` |
| `Managed subagent '<n>' already exists` / `Subagent name '<n>' is reserved by a built-in or config.yaml definition.` | `routers/subagents.py:180`、`:185` |
| `SkillAlreadyExistsError` | `routers/skills.py:249`（`_install_skill_archive`，`POST /api/skills/install` 路径） |
| `Agent '<n>' only exists in the legacy shared layout ...`（迁移提示）/ `Directory for '<n>' contains memory data but is not a custom agent ...` | `routers/agents.py:412`、`:589`、`:596` |

**(d) 状态机 / 生命周期冲突 → 409**

| detail | 锚点 |
|--------|------|
| `System already initialized` | `routers/auth.py:800`、`:814` |
| Lark 流程被更新的 generation 取代（`LarkFlowSupersededError`） | `routers/integrations.py:324`、`:372`、`:397` |
| `Run <id> is not cancellable (status: <s>)` / `... not active on this worker and cannot be cancelled` | `routers/thread_runs.py:1337`、`:1414` + `_cancel_conflict_detail` `:333-336` |
| `Only failed items can be retried` | `routers/subagent_batches.py:101` |
| `The signed-in account changed; reload this page` | `routers/user_preferences.py:31` |
| checkpoint 模式不匹配（`CheckpointModeMismatchError`） | `threads.py:96-108`（`_checkpoint_mode_http_error`）→ **409**；同一 helper 对「进程正在切换模式」返回 **503** |

**(e) 业务内容缺失 / 重复 → 409**

| detail | 锚点 |
|--------|------|
| `content_missing`（shelf 内容缺失） | `routers/project_documents.py:369`、`:446`；`routers/trash.py:203` |
| `A fact with the same content already exists.` | `routers/memory.py:120`（`_map_memory_fact_value_error`） |
| `Memory changed concurrently; reload and retry.`（`MemoryConflictError`） | `routers/memory.py:128-130`（`_map_memory_manager_error`），调用点 `:279`、`:298`、`:328`、`:355`、`:388`、`:428` |
| `Fact was not stored because the configured memory.max_facts capacity policy evicted it` | `routers/memory.py:334` |

---

### 2.7 412 Precondition Failed

| 场景 | detail | 锚点 |
|------|--------|------|
| `PUT /api/threads/{id}/artifacts/{path}` 的 `expected_sha256` 与磁盘不符 | `Artifact changed since it was opened` | `routers/artifacts.py:102` |

---

### 2.8 413 Content Too Large

| 场景 | detail 摘要 | 锚点 |
|------|------------|------|
| 上传文件数超过 `uploads.max_files`（默认 10） | `Too many files: maximum is <n>` | `routers/uploads.py:418` |
| 单文件超过 `uploads.max_file_size`（默认 50 MiB） | `File too large: <name>` | `app/gateway/upload_ingestion.py:330` |
| 单请求总量超过 `uploads.max_total_size`（默认 100 MiB） | `Total upload size too large` | `app/gateway/upload_ingestion.py:332` |
| 项目 shelf 上传/晋升超限 | `File too large: <name>` | `routers/project_documents.py:228`、`:344` |
| artifact 编辑超过 `MAX_EDITABLE_ARTIFACT_BYTES`（stat 与实读两处） | `Artifact is too large to edit` | `routers/artifacts.py:91`、`:96`、`:113` |
| `.skill` 归档成员预览过大 | `Skill archive member is too large to preview` | `routers/artifacts.py:247`、`:255`（`_read_skill_archive_member` `:244`） |
| skill 包上传超过 100 MiB（+ 1 MiB multipart framing） | `Skill archive exceeds the 100 MiB upload limit` | `routers/skills.py:584`（`except _SkillArchiveUploadTooLargeError`），类 `:77`，抛点 `:97`、`:367`、`:390`、`:396` |
| run 产出归档 ZIP 超限（>50 文件 / 单文件 50MiB / 总量 100MiB） | `_too_large(...)` | `app/gateway/artifact_archive.py:59`（`_too_large`，显式传 413） |
| skill 导出超资源上限 | `skill_export_limit_exceeded` | `packages/harness/deerflow/skills/export.py:90` → `routers/skills.py:694-695`、`:719-720` 经 `export_http_error`（`app/gateway/skill_export.py:184`） |

> **没有全局 body-size 中间件**：413 全部由上述各处理器显式抛出。`02-upload-security.md` 记录的文件名/路径/符号链接防御是**磁盘层**，不产生 413。

---

### 2.9 415 Unsupported Media Type

只出现在 `PUT /api/threads/{thread_id}/artifacts/{path:path}`（`routers/artifacts.py:626`）：

| 场景 | detail | 锚点 |
|------|--------|------|
| 目标是 `.skill` 归档 | `Skill archives cannot be edited in the artifacts panel` | `:78`（`_normalize_editable_artifact_path`） |
| 目标是符号链接 | `Symlinked artifacts cannot be edited` | `:88`（`_load_editable_artifact`） |
| 内容含 NUL 字节 | `Binary artifacts cannot be edited` | `:98` |
| 内容不是合法 UTF-8 | `Only UTF-8 text artifacts can be edited` | `:102` |
| 提交的新内容含 NUL | `Binary content cannot be saved as an artifact` | `:115`（`_encode_artifact_update`） |

---

### 2.10 416 Range Not Satisfiable

| 场景 | detail + 头 | 锚点 |
|------|------------|------|
| `GET artifact` 的 `Range` 头非法/多段/越界/空文件/suffix ≤ 0 | `Requested range is not satisfiable`，附 `Accept-Ranges: bytes` 与 `Content-Range: bytes */<size>` | `routers/artifacts.py:206-212`（`unsatisfied()`），触发点紧随其后 |

合法单段范围返回 **206** + `Content-Range`。

---

### 2.11 422 Unprocessable Content

两类来源：

**(a) FastAPI 自动（`RequestValidationError`）** — 覆盖所有带校验参数/请求体的端点。典型：

| 场景 | 锚点 |
|------|------|
| `RunCreateRequest` 的兼容占位收到非 null 值（`on_completion`、`webhook`、`after_seconds`、`feedback_keys`、`stream_resumable` 只接受 null/false；`multitask_strategy` 无 `enqueue`）；未声明字段被 `extra="forbid"` 拒绝（`checkpoint_during`、`durability` 等） | `app/gateway/run_models.py:29-58` |
| `thread_id` 违反 `^[A-Za-z0-9_-]{1,64}$` | `ThreadId`（各 router 共享 `deerflow.utils.thread_id`） |
| `PATCH /api/threads/{id}` 的 `deerflow_archived` 非布尔 | `routers/threads.py:515`（`validate_archive_flag`）→ Pydantic 422 |
| 元数据过滤条目非法（Pydantic 层） | `routers/threads.py:472`（`_validate_metadata_filters`） |
| `conversation_references` 超过 3 条，或同时出现在顶层与 `context` | `app/gateway/run_models.py`（`MAX_CONVERSATION_REFERENCES`） |

**(b) router 手写 422**

| 场景 | detail 摘要 | 锚点 |
|------|------------|------|
| agent `model` 不是配置的 profile | `Unknown model '<m>'. Use a model name defined under `models:` ...` | `routers/agents.py:186`（`_validate_model_exists` `:166`），调用点 `:389`（import）、`:519`（create）、`:591`（update） |
| managed subagent `model` 非法 | `Unknown model '<m>'. Use 'inherit' or a configured model name.` | `routers/subagents.py:82` |
| managed subagent 名称非法 / Pydantic 校验失败 | `str(exc)` / `exc.errors()` | `routers/subagents.py`（`create`/`update` 体内的 ValueError 分支） |
| scheduled task：`assistant_id` 为空/非法/未知 | 编码错误 `invalid_assistant`、`unknown_assistant` | `routers/scheduled_tasks.py:70`、`:78`、`:83`、`:89` |
| scheduled task：`context_mode`/`schedule_type`/cron/once 校验 | 编码错误（`invalid_request` 等），消息仍是英文 | `routers/scheduled_tasks.py`（`scheduled_task_validation.py` 共享校验 + `scheduler_error(422, ...)`）；v2.2.0 把散落的字面量收敛进 `scheduled_task_errors.py` |
| 通知组非法 | `invalid_notification_group`（422），消息 `Select a connected notification group belonging to this user` | `routers/scheduled_tasks.py:119`、`:147` |
| run 历史游标两个字段未成对出现 | `before_created_at and before_run_id must be provided together` | `routers/thread_runs.py:1242` |
| messages/page 不支持 `after_seq` | `after_seq is not supported by this backward-only endpoint` | `routers/thread_runs.py:1630` |
| thread goal 参数非法（如 `max_continuations > 8`） | `str(exc)` | `routers/threads.py:580-590`（`ThreadGoalRequest`，Pydantic 界）；语义校验在 `build_goal_state` |
| thread state 未知字段 | `Unknown thread-state field(s): [...]` | `routers/threads.py:1704` |
| subagent batch item 状态过滤值非法 | `Unknown batch item status` | `routers/subagent_batches.py:68` |
| skill 归档上传：非 multipart / 缺 `archive` 文件 | `Expected a multipart form upload`、`Multipart field 'archive' must contain a file` | `routers/skills.py:404`、`:575` |
| skill 导出：非法 skill 名 / 平台不支持 / 非法 revision / 目录结构不支持 | `skill_export_unsupported` | `packages/harness/deerflow/skills/export.py`（`SkillExportError`）→ `routers/skills.py:694-695`、`:719-720` |
| **🆕 v2.2.0** admin：无字段 / 未知 role | `nothing to update: provide system_role and/or disabled`、`unknown role '<r>'; assignable roles: [...]` | `routers/admin_users.py:89`、`:96`（尚有 `:114`、`:116` 两条 409） |
| **🆕 v2.2.0** capability：未知 adapter | `This capability only has a setup guide; no installation adapter is available` | `app/gateway/capabilities.py:225`（`AdapterRegistry.get`） |
| **🆕 v2.2.0** thread activity：非法游标 | `invalid_cursor` | `routers/thread_activity.py:72` |
| **🆕 v2.2.0** plugins：输入不是 JSON object / action 输入无效 | `Plugin action requires a JSON object.`、`Invalid plugin action input.` | `routers/plugins.py:179`、`:197` |
| **🆕 v2.2.0** knowledge：scope 选择不被该 assistant 支持 | details 说明哪一项被拒（前端据此回退选择器） | `app/gateway/knowledge_scope_admission.py:55`（`admit_message_knowledge_scope`），辅助 `:21`（`assistant_supports_knowledge_scope`） |

---

### 2.12 429 Too Many Requests

| 场景 | detail 摘要 | 锚点 |
|------|------------|------|
| 同一 IP 登录失败超过 `local_auth.max_login_attempts`，锁定未过期 | `Too many login attempts. Try again later.` | `routers/auth.py:322-325`（`_check_rate_limit`），由 `login_local` 调用 |
| 单个 owner 每 provider 的 pending IM 连接码超过 `_MAX_PENDING_CONNECT_CODES_PER_PROVIDER = 5` | `Too many pending channel connection codes. Wait for existing codes to expire or use one of them.` | `routers/channel_connections.py:343-348`（常量 `:28`） |
| run 产出归档 ZIP 并发构建槽位（`Semaphore(4)`）已满 | `Too many artifact archives are being created; try again shortly` | `routers/thread_runs.py:1702`（`ArtifactArchiveError(..., 429)`） |
| skill 导出槽位（每进程全用户 `BoundedSemaphore(2)`）已满 | `skill_export_busy`：`Both export slots in this Gateway process are in use across all users. ...` | `app/gateway/skill_export.py:71` |

---

### 2.13 500 Internal Server Error

三类来源：

**(a) `except Exception → 500` 模板**

每个 router 都有一份「兜底 `except Exception` → 500」的模板。**v2.2.0 起不再逐条列出行号**：这些锚点在每个版本都会被无关改动整体推移（v2.1.0 基线里列的约 70 个行号在 v2.2.0 已全部失效），维护成本远超信息价值。现行的稳定结论是：

| 文件 | 兜底 500 的 detail 形态 |
|------|------------------------|
| `routers/agents.py` | `Failed to <动作>: {e}` 或固定文案 |
| `routers/artifacts.py` | 固定 `Failed to update artifact`（**不回显异常内容**，避免泄漏路径） |
| `routers/integrations.py` | `Failed to <动作>: {e}` |
| `routers/mcp.py` | `Failed to <动作>: {e}` |
| `routers/memory.py` | `Failed to <动作>: {e}`；`OSError` 另有专门分支 |
| `routers/project_documents.py` | 固定文案（不泄漏磁盘路径） |
| `routers/skills.py` | 固定文案；v2.2.0 修掉了 `GET /api/skills` 里回显异常细节的 500 |
| `routers/threads.py` | `Failed to <动作>: {e}` |
| `routers/thread_runs.py` | `ArtifactArchiveError.status_code` 原样透传（多为 409/413/429/503，不是 500） |
| `routers/trash.py` | `OSError` → 事务回滚保留回收站行，再 500 |
| `routers/uploads.py` | v2.2.0 改成**固定文案**（上传/删除不再回显异常内容，见 `routers/AGENTS.md`） |
| 🆕 v2.2.0 `routers/plugins.py` | 固定 `Plugin action failed.`，日志只记**异常类型**（文本可能含用户内容） |

**(b) 业务性 500（不是模板）**

| 场景 | detail | 锚点 |
|------|--------|------|
| 存储的 memory 数据损坏（`MemoryCorruptionError`） | `Stored memory data is corrupted.` | `routers/memory.py:137`（`_map_memory_manager_error` `:133`，调用点 `:217`） |
| 手动压缩失败（`ContextCompactionFailed`） | `Failed to compact thread context.` | `routers/threads.py:1585`、`:1592` |
| checkpoint 校验失败 | `Failed to validate checkpoint` | `app/gateway/services.py:1869` |
| skill 导出内部失败 | `{"code":"skill_export_failed", ...}` | `routers/skills.py:699`、`:724`（`export_manifest` 与 `download` 各一处） |

**(c) 未捕获的非 HTTP 异常 → Starlette/TraceMiddleware 渲染 500**

| 异常 | detail | 锚点 |
|------|--------|------|
| `TypeError`（AuthorizationProvider 返回类型违约） | `AuthorizationProvider.filter_resources must return list[str]` | `routers/models.py:207` |
| `TypeError` | `AuthorizationProvider.authorize must return AuthzDecision`（异步变体 `aauthorize` 同文案） | `app/gateway/authz.py:435`、`:333` |
| `AssertionError`（未处理的 artifact 响应类型） | `Unhandled artifact response kind: ...` | `routers/artifacts.py:531` |
| `RuntimeError`（sandbox lease 未产出 sandbox） | `Failed to acquire sandbox for artifact update` | `routers/artifacts.py:678` |

> `TraceMiddleware` 对未处理异常会先自行发送一个 CORS-opaque 的 plain 500 再 re-raise（见 harness `trace_context` 说明）。

---

### 2.14 501 Not Implemented

| 场景 | detail 摘要 | 锚点 |
|------|------------|------|
| memory 后端未实现该 tier-3/tier-2 操作（`NotImplementedError`） | `Operation '<label>' not supported by memory backend '<cls>'.` | `routers/memory.py:140-156`（`_unsupported_501`）；label 由各 handler 传入（`clear memory`、`create fact`、`delete fact`、`update fact`、`import memory`、`reload memory`），agent-scoped 分支 `:182`；`_get_memory_or_501` `:192` |
| browser 自动化依赖缺失（`ImportError`） | `Browser automation is not available` | `routers/browser.py:94` |
| **run 的 `multitask_strategy` 不受支持** | `Multitask strategy '<s>' is not yet supported. Supported strategies: ...` | `packages/harness/deerflow/runtime/runs/manager.py:1605`（`UnsupportedStrategyError`）→ `app/gateway/services.py:2744` 转 501。影响 `POST /api/threads/{id}/runs`、`/runs/stream`、`/runs/wait` 与 `POST /api/runs/*` |

---

### 2.15 502 Bad Gateway

| 场景 | detail 摘要 | 锚点 |
|------|------------|------|
| browser 导航底层失败（任何其它异常） | `Browser navigation failed` | `routers/browser.py:113`（导航失败统一一个 502） |
| OIDC discovery / provider 连接失败（登录发起） | `Failed to connect to SSO provider` | `routers/auth.py:1003`、`:1090` |
| OIDC discovery 失败（回调，改为 302 重定向到错误页） | `sso_failed` | `routers/auth.py:1051`、`:1107`、`:1120`（`_build_error_redirect` `:1147`） |
| scheduled task 手动触发派发失败 | `result['error'] or 'Scheduled task trigger failed'` | `routers/scheduled_tasks.py:449`（`scheduler_error(502, "trigger_failed", ...)`） |

---

### 2.16 503 Service Unavailable

| 场景 | detail 摘要 | 锚点 |
|------|------------|------|
| Console 需要 SQL backend（`database.backend: memory`） | `Console requires a SQL database backend; set database.backend to sqlite or postgres in config.yaml.` | `routers/console.py:121-128`（`_session_factory_or_503`），3 个 console 端点调用 |
| channel connection 持久化不可用 | `Channel connection persistence is not available` | `routers/channel_connections.py:232`；在 `GET /providers` 与 `DELETE /{provider}/runtime-config` 里被**刻意吞掉降级**，不报 503（v2.2.0 行号见 §2.16 的行为描述，精确行号未逐一核对） |
| IM channel service 未运行 | `Channel service is not running` | `routers/channels.py:50` |
| GitHub webhook 未配置签名校验 | `Webhook signature verification not configured. Set ... or ...=1 for unverified dev mode.` | `routers/github_webhooks.py:238` |
| GitHub webhook fan-out 运行时失败（保留为 failed 供人工重投） | `fan-out failed for delivery <id>: ...` | `routers/github_webhooks.py:368` |
| input polish LLM 调用失败 | `Failed to polish input` | `routers/input_polish.py:99`、`:102` |
| MCP task 取消时 worker 未运行 | `MCP task cancellation worker is not running` | `routers/mcp_tasks.py:209` |
| subagent batch worker 未运行 | `Subagent batch worker is not running` | `routers/subagent_batches.py:111` |
| 用户偏好持久化不可用 | `Preference persistence is unavailable` | `routers/user_preferences.py:47`（`_repository` `:44`） |
| 归档 ZIP 构建超时（60s deadline） | `Artifact archive creation timed out` | `app/gateway/artifact_archive.py:65` |
| skill 导出被取消 / 超时 / 锁超时 | `skill_export_cancelled`、`skill_export_timeout` | `packages/harness/deerflow/skills/export.py:84`、`:86`、`:422` |
| checkpoint 进程正在切换存储模式（非 `CheckpointModeMismatchError`） | `str(exc)` | `routers/threads.py:106`（`_checkpoint_mode_http_error`） |
| `/health/ready` 任一后端 `unreachable` | `status: degraded` | `app/gateway/health.py:412-418` |

---

### 2.17 504 Gateway Timeout

两处来源：Lark CLI 子进程超时（`routers/integrations.py`，`TimeoutError` → 504，detail 是异常文本）与插件 action 的 30s 预算 🆕 v2.2.0。

| 端点 | 锚点 |
|------|------|
| `POST /api/integrations/lark/config/start` | `:319-320` |
| `POST /api/integrations/lark/config/complete` | `:346-347` |
| `POST /api/integrations/lark/config/credentials` | `:369-370` |
| `POST /api/integrations/lark/auth/start` | `:394-395` |
| `POST /api/integrations/lark/auth/complete` | `:419-420` |
| 🆕 `POST /api/plugins/{namespace}/actions/{action_name}` | 固定 `Plugin action timed out.`，`asyncio.timeout(30)` 包住整个 handler | `routers/plugins.py:186`、`:189` |

### 2.18 成功码的非常规用法

| 码 | 场景 | 锚点 |
|----|------|------|
| 201 | create agent / import agent / project / shelf document / managed subagent / register / PAT / initialize admin | `routers/agents.py:504`（create）、`:384`（import）、`routers/projects.py:118`、`routers/project_documents.py:199`、`:307`、`routers/subagents.py:172`、`routers/auth.py:489`、`:683`、`:821` |
| **200 on dedup** | shelf 上传/晋升命中内容去重时把 201 改写成 200 | `routers/project_documents.py`（`upload_project_document` / `promote_thread_file_to_shelf` 内的 dedup 分支，v2.2.0 行号未逐一核对） |
| 202 | run 取消/流式已被接受（非 owner worker 记为 `requested`，或 store-only 无法订阅） | `routers/thread_runs.py`（`cancel_run` / `stream_existing_run` 内，v2.2.0 行号未逐一核对） |
| 204 | delete agent / disconnect connection / delete document / delete project / delete subagent / purge / cancel with `wait=true` / skill 导出客户端断连 / PATCH preferences | `routers/agents.py:772`、`routers/channel_connections.py:597`、`routers/project_documents.py:530`、`routers/projects.py:185`、`routers/subagents.py:233`、`routers/trash.py:210`、`routers/user_preferences.py:67`、`routers/channel_connections.py:844`（wechat QR 取消）、`routers/thread_runs.py`（`cancel_run`）、`routers/skills.py`（导出断连分支 `:692`、`:717`） |
| 206 | artifact `Range` 命中 | `routers/artifacts.py:199`（`_slice_byte_range`） |
| 101 | WebSocket 升级成功 | `routers/browser.py:215` |

---

## 3. 路由之前的四层中间件（先于 §2 的 router 码）

`create_app()` 里 `add_middleware()` 的**添加顺序**是 `AuthMiddleware`(`app.py:1187`) → `CSRFMiddleware`(`:1259`) → `CORSMiddleware`(`:1271`，仅当 `sorted(get_configured_cors_origins())` 非空) → 扩展贡献的中间件(`:1281`) → `TraceMiddleware`(`:1283`)。Starlette 里后添加的更靠外，所以**实际执行顺序（外 → 内）是**：

```
TraceMiddleware → (CORS，按需) → CSRFMiddleware → AuthMiddleware → router
```

> ⚠️ **v2.2.0 的扩展中间件位置**：它们夹在 `CORSMiddleware` 与 `TraceMiddleware` 之间，即在 **CORS 之内、CSRF/Auth 之外**——扩展中间件看到的请求**已经过** CORS，但**还没被 CSRF 与认证校验**。

关键推论（v2.2.0 未变）：**CSRF 在 Auth 之前**，所以一个没有 session、也没有 `X-CSRF-Token` 的 `POST` 会先撞到 **403 `CSRF token missing`**，而不是 401。

1. **`TraceMiddleware`**（`app/gateway/trace_middleware.py`）— 注入 `X-Trace-Id`；未处理异常时自行发送 CORS-opaque plain **500** 再 re-raise。
2. **`CORSMiddleware`**（按需）— 仅当 `GATEWAY_CORS_ORIGINS` 非空时挂载（`app.py:1269-1277`）；`allow_credentials=True`、`allow_methods/headers=["*"]`、`expose_headers=list(CORS_EXPOSED_HEADERS)`。CORS allowlist 与 CSRF origin 检查**共用同一个配置源**。
3. **`CSRFMiddleware`**（`csrf_middleware.py`）— 双提交 cookie。仅对状态变更方法生效（`POST/PUT/DELETE/PATCH`，`:26`），且：
   - `DEER_FLOW_AUTH_DISABLED=1` 时不检查（`:49`）
   - 豁免精确路径 `/api/v1/auth/me`（`:27`、`:55`）与 `/api/webhooks/` 前缀（`:59`）
   - auth 端点（`login/local`、`logout`、`register`、`initialize`，`:64-71`）**不走** cookie 双提交，但仍做跨源检查 → **403** `Cross-site auth request denied.`（`:226`）
   - 其它状态变更请求且无 `Authorization` 头：缺 token → **403**（`:244`）；不匹配（常数时间比较）→ **403**（`:250`）
   - 带 `Authorization: Bearer` 的请求跳过 cookie 双提交检查（origin 检查仍跑）
4. **`AuthMiddleware`**（`auth_middleware.py`）— 两级检查：cookie 存在性 → JWT 严格校验。
   - 非公开路径 + 无 cookie → **401** `NOT_AUTHENTICATED`（`:169`）
   - 无效/过期 cookie → 回传 `exc.status_code`（**401**，`token_expired`/`token_invalid`/`user_not_found`）
   - `Authorization: Bearer dfp_...`（PAT）优先级最高；无效 Bearer 是**硬 401，不回退 cookie**；PAT 不在 allowlist 路由 → **403**（`:136-141`）
   - 公开路径前缀 `_PUBLIC_PATH_PREFIXES`（`:37`）：`/health`、`/docs`、`/redoc`、`/openapi.json`、`/api/v1/auth/oauth/`、`/api/v1/auth/callback/`、`/api/webhooks/`；精确公开 `_PUBLIC_EXACT_PATHS`（`:51`）：`/api/v1/auth/{login/local,register,logout,setup-status,initialize,providers}`

越过这四层之后才是 `@require_auth` / `@require_permission` / `require_admin_user`（handler 体内）/ 路由体内的 404/409/…。

> 🆕 v2.2.0：`routers/admin_users.py`、`routers/managed_models.py`、`routers/skill_mutations.py`、`routers/plugins.py`（诊断）、`routers/capabilities.py`（安装）、`routers/channel_connections.py` 的 WeChat QR 三条，都不是用 `@require_permission` 装饰器，而是在 handler 体内调 `app/gateway/authz.py:require_admin_user` —— 因此 §2.0 的「端点自身函数体内的码」统计里它们的 **403 不计入**，但实际上都会 403。

---

## 4. 端点 → 可达状态码矩阵

**本表覆盖 221 条端点**（= §1 端点总数）；🆕「v2.2.0 新增的 41 条」排在最前面（`/api/v1/admin/users` 起至 `POST /api/threads/{thread_id}/read`），其后是 v2.1.0 已有、锚点已按 v2.2.0 重锚的 180 条。

**读法**：`/` 分隔 = 该端点**可达**的状态码；口径 = 本端点自身 raise + 同模块被调 helper 的传递闭包 + `require_permission`(401/403，`owner_check` 再加 404) + `require_admin_user`(403) + 有校验参数时的 422 + 未捕获非 HTTP 异常的 500。`401` 由 §3 的 `AuthMiddleware` 对**所有非公开路由**补上。因此这是**上界**（宁多勿漏）。成功码见 §1.1 与 §2.18。此外**所有状态变更方法**（`POST/PUT/DELETE/PATCH`）都可能先被 `CSRFMiddleware` 拦成 **403**（豁免清单见 §3），表中未逐行重复。

| 端点 | 可达码 | 源码锚点 |
|------|--------|---------|
| `GET /api/v1/admin/users` | 401/403/500 | `backend/app/gateway/routers/admin_users.py:59` |
| `PATCH /api/v1/admin/users/{user_id}` | 401/403/404/409/422/500 | `backend/app/gateway/routers/admin_users.py:67` |
| `GET /api/agent-tool-groups` | 401/403/500 | `backend/app/gateway/routers/agents.py:327` |
| `POST /api/agents/import` | 401/403/409/413/422/500 | `backend/app/gateway/routers/agents.py:376` |
| `GET /api/agents/{name}/export` | 401/403/404/422/500 | `backend/app/gateway/routers/agents.py:407` |
| `WEBSOCKET /api/threads/{thread_id}/browser/stream` | —（WS close code：1008/4401/4403/4404） | `backend/app/gateway/routers/browser.py:214` |
| `GET /api/capabilities/catalog` | 401/403/500 | `backend/app/gateway/routers/capabilities.py:26` |
| `GET /api/capabilities/installations/{adapter}` | 401/403/404/422/500 | `backend/app/gateway/routers/capabilities.py:31` |
| `POST /api/capabilities/installations` | 400/401/403/422/500 | `backend/app/gateway/routers/capabilities.py:36` |
| `POST /api/channels/wechat/qr-login` | 400/401/403/500/503 | `backend/app/gateway/routers/channel_connections.py:813` |
| `POST /api/channels/wechat/qr-login/{session_id}/poll` | 400/401/403/404/409/500/503 | `backend/app/gateway/routers/channel_connections.py:824` |
| `DELETE /api/channels/wechat/qr-login/{session_id}` | 401/403/404/500/503 | `backend/app/gateway/routers/channel_connections.py:843` |
| `GET /api/channels/notification-preferences` | 401/409/422/500/503 | `backend/app/gateway/routers/im_notification_preferences.py:40` |
| `PATCH /api/channels/notification-preferences` | 401/409/422/500/503 | `backend/app/gateway/routers/im_notification_preferences.py:46` |
| `GET /api/knowledge/capabilities` | 401/403/500 | `backend/app/gateway/routers/knowledge.py:72` |
| `GET /api/knowledge/retrieval-catalog/datasets` | 401/403/500/503 | `backend/app/gateway/routers/knowledge.py:86` |
| `GET /api/knowledge/retrieval-catalog/datasets/{dataset_id:path}/documents` | 401/403/404/500/503 | `backend/app/gateway/routers/knowledge.py:100` |
| `GET /api/managed-models/providers` | 401/403/500 | `backend/app/gateway/routers/managed_models.py:68` |
| `GET /api/managed-models` | 401/403/500 | `backend/app/gateway/routers/managed_models.py:74` |
| `PUT /api/managed-models` | 400/401/403/409/422/500 | `backend/app/gateway/routers/managed_models.py:114` |
| `POST /api/managed-models/test` | 400/401/403/422/500/502 | `backend/app/gateway/routers/managed_models.py:156` |
| `POST /api/models/resolve` | 400/401/403/422/500 | `backend/app/gateway/routers/models.py:103` |
| `GET /api/mcp/personal/config` | 401/403/500/503 | `backend/app/gateway/routers/personal_mcp.py:113` |
| `POST /api/mcp/personal/config/servers` | 400/401/403/409/422/500/503 | `backend/app/gateway/routers/personal_mcp.py:133` |
| `PUT /api/mcp/personal/config/server` | 400/401/403/404/409/422/500/503 | `backend/app/gateway/routers/personal_mcp.py:138` |
| `PATCH /api/mcp/personal/config` | 400/401/403/409/422/500/503 | `backend/app/gateway/routers/personal_mcp.py:143` |
| `DELETE /api/mcp/personal/config/servers/{server_name:path}` | 400/401/403/404/422/500/503 | `backend/app/gateway/routers/personal_mcp.py:148` |
| `GET /api/plugins/diagnostics` | 401/403/500 | `backend/app/gateway/routers/plugins.py:46` |
| `GET /api/plugins` | 401/403/500 | `backend/app/gateway/routers/plugins.py:68` |
| `GET /api/plugins/modules/{module}/{revision}.mjs` | 401/404/500 | `backend/app/gateway/routers/plugins.py:101` |
| `GET /api/plugins/{namespace}/assets/{revision}/{path:path}` | 401/404/500 | `backend/app/gateway/routers/plugins.py:112` |
| `POST /api/plugins/{namespace}/actions/{action_name}` | 401/403/404/409/413/422/500/502/503/504 | `backend/app/gateway/routers/plugins.py:135` |
| `GET /api/threads/{thread_id}/scheduled-task-events` | 401/403/404/422/500 | `backend/app/gateway/routers/scheduled_tasks.py:505` |
| `GET /api/skill-mutations/operations` | 401/403/422/500/503 | `backend/app/gateway/routers/skill_mutations.py:31` |
| `GET /api/skill-mutations/operations/{operation_id}` | 401/403/404/500/503 | `backend/app/gateway/routers/skill_mutations.py:39` |
| `POST /api/skill-mutations/operations/{operation_id}/recover` | 401/403/404/409/500/503 | `backend/app/gateway/routers/skill_mutations.py:44` |
| `POST /api/skill-mutations/owners/{owner_id}/recover` | 401/403/404/409/500/503 | `backend/app/gateway/routers/skill_mutations.py:49` |
| `GET /api/skills/diagnostics/custom` | 401/403/500 | `backend/app/gateway/routers/skills.py:672` |
| `GET /api/threads/{thread_id}/subagent-batches/{batch_id}/items/{position}` | 401/403/404/422/500 | `backend/app/gateway/routers/subagent_batches.py:73` |
| `GET /api/thread-activity` | 401/403/422/500/503 | `backend/app/gateway/routers/thread_activity.py:70` |
| `POST /api/threads/{thread_id}/read` | 401/403/404/500/503 | `backend/app/gateway/routers/threads.py:1349` |
| `GET /api/agents` | 401/403/500 | `backend/app/gateway/routers/agents.py:296` |
| `GET /api/agents/check` | 401/403/422 | `backend/app/gateway/routers/agents.py:343` |
| `GET /api/agents/{name}` | 401/403/404/422/500 | `backend/app/gateway/routers/agents.py:458` |
| `POST /api/agents` | 401/403/409/422/500 | `backend/app/gateway/routers/agents.py:496` |
| `PUT /api/agents/{name}` | 401/403/404/409/422/500 | `backend/app/gateway/routers/agents.py:532` |
| `GET /api/user-profile` | 401/403/500 | `backend/app/gateway/routers/agents.py:685` |
| `PUT /api/user-profile` | 401/403/422/500 | `backend/app/gateway/routers/agents.py:722` |
| `DELETE /api/agents/{name}` | 401/403/404/409/422/500 | `backend/app/gateway/routers/agents.py:765` |
| `GET /api/threads/{thread_id}/artifacts/{path:path}` | 401/403/404/416/422/500 | `backend/app/gateway/routers/artifacts.py:394` |
| `PUT /api/threads/{thread_id}/artifacts/{path:path}` | 401/403/404/409/413/415/422/500 | `backend/app/gateway/routers/artifacts.py:619` |
| `GET /api/assistants/{assistant_id}` | 401/404/422 | `backend/app/gateway/routers/assistants_compat.py:109` |
| `GET /api/assistants/{assistant_id}/graph` | 401/404/422 | `backend/app/gateway/routers/assistants_compat.py:118` |
| `GET /api/assistants/{assistant_id}/schemas` | 401/404/422 | `backend/app/gateway/routers/assistants_compat.py:136` |
| `POST /api/assistants/search` | 401/422 | `backend/app/gateway/routers/assistants_compat.py:89` |
| `POST /api/v1/auth/login/local` | 401/422/429 | `backend/app/gateway/routers/auth.py:431` |
| `POST /api/v1/auth/register` | 400/403/422 | `backend/app/gateway/routers/auth.py:488` |
| `POST /api/v1/auth/logout` | — | `backend/app/gateway/routers/auth.py:517` |
| `POST /api/v1/auth/change-password` | 400/401/403/422 | `backend/app/gateway/routers/auth.py:528` |
| `GET /api/v1/auth/me` | 401 | `backend/app/gateway/routers/auth.py:592` |
| `POST /api/v1/auth/pats` | 400/401/422 | `backend/app/gateway/routers/auth.py:682` |
| `GET /api/v1/auth/pats` | 401 | `backend/app/gateway/routers/auth.py:719` |
| `DELETE /api/v1/auth/pats/{pat_id}` | 401/404/422 | `backend/app/gateway/routers/auth.py:729` |
| `GET /api/v1/auth/setup-status` | — | `backend/app/gateway/routers/auth.py:752` |
| `POST /api/v1/auth/initialize` | 400/409/422 | `backend/app/gateway/routers/auth.py:820` |
| `GET /api/v1/auth/providers` | — | `backend/app/gateway/routers/auth.py:930` |
| `GET /api/v1/auth/oauth/{provider}` | 400/404/422/502 | `backend/app/gateway/routers/auth.py:954` |
| `GET /api/v1/auth/callback/{provider}` | 400/403/404/422/502 | `backend/app/gateway/routers/auth.py:1030` |
| `POST /api/threads/{thread_id}/browser/navigate` | 400/401/403/404/422/501/502 | `backend/app/gateway/routers/browser.py:75` |
| `GET /api/channels/providers` | 401/404/503 | `backend/app/gateway/routers/channel_connections.py:549` |
| `GET /api/channels/connections` | 401/503 | `backend/app/gateway/routers/channel_connections.py:579` |
| `DELETE /api/channels/connections/{connection_id}` | 400/401/404/422/503 | `backend/app/gateway/routers/channel_connections.py:596` |
| `DELETE /api/channels/{provider}/runtime-config` | 400/401/403/404/422/503 | `backend/app/gateway/routers/channel_connections.py:612` |
| `POST /api/channels/{provider}/connect` | 400/401/404/422/429/503 | `backend/app/gateway/routers/channel_connections.py:658` |
| `POST /api/channels/{provider}/runtime-config` | 400/401/403/404/422 | `backend/app/gateway/routers/channel_connections.py:697` |
| `GET /api/channels/` | 401 | `backend/app/gateway/routers/channels.py:29` |
| `POST /api/channels/{name}/restart` | 401/403/422/503 | `backend/app/gateway/routers/channels.py:41` |
| `GET /api/console/stats` | 401/403/503 | `backend/app/gateway/routers/console.py:289` |
| `GET /api/console/runs` | 401/403/422/503 | `backend/app/gateway/routers/console.py:363` |
| `GET /api/console/usage` | 401/403/422/503 | `backend/app/gateway/routers/console.py:434` |
| `GET /api/features` | 401 | `backend/app/gateway/routers/features.py:98` |
| `POST /api/threads/{thread_id}/runs/{run_id}/feedback` | 400/401/403/404/422 | `backend/app/gateway/routers/feedback.py:113` |
| `GET /api/threads/{thread_id}/runs/{run_id}/feedback` | 401/403/404/422 | `backend/app/gateway/routers/feedback.py:146` |
| `GET /api/threads/{thread_id}/runs/{run_id}/feedback/stats` | 401/403/404/422 | `backend/app/gateway/routers/feedback.py:158` |
| `DELETE /api/threads/{thread_id}/runs/{run_id}/feedback/{feedback_id}` | 401/403/404/422 | `backend/app/gateway/routers/feedback.py:170` |
| `PUT /api/threads/{thread_id}/runs/{run_id}/feedback` | 400/401/403/404/422 | `backend/app/gateway/routers/feedback.py:62` |
| `DELETE /api/threads/{thread_id}/runs/{run_id}/feedback` | 401/403/404/422 | `backend/app/gateway/routers/feedback.py:93` |
| `POST /api/webhooks/github` | 400/401/422/503 | `backend/app/gateway/routers/github_webhooks.py:173` |
| `POST /api/input-polish` | 400/401/403/404/422/503 | `backend/app/gateway/routers/input_polish.py:58` |
| `GET /api/integrations/lark/status` | 401/500 | `backend/app/gateway/routers/integrations.py:262` |
| `POST /api/integrations/lark/install` | 400/401/403/404/500 | `backend/app/gateway/routers/integrations.py:272` |
| `POST /api/integrations/lark/config/start` | 400/401/404/422/500/504 | `backend/app/gateway/routers/integrations.py:306` |
| `POST /api/integrations/lark/config/complete` | 400/401/404/409/422/500/504 | `backend/app/gateway/routers/integrations.py:326` |
| `POST /api/integrations/lark/config/credentials` | 400/401/404/422/500/504 | `backend/app/gateway/routers/integrations.py:353` |
| `POST /api/integrations/lark/auth/start` | 400/401/404/409/422/500/504 | `backend/app/gateway/routers/integrations.py:376` |
| `POST /api/integrations/lark/auth/complete` | 400/401/404/409/422/500/504 | `backend/app/gateway/routers/integrations.py:401` |
| `GET /api/mcp/config` | 401/403 | `backend/app/gateway/routers/mcp.py:1147` |
| `POST /api/mcp/cache/reset` | 401/403 | `backend/app/gateway/routers/mcp.py:1559` |
| `PUT /api/mcp/config` | 400/401/403/422/500 | `backend/app/gateway/routers/mcp.py:1588` |
| `POST /api/mcp/config/servers` | 400/401/403/422/500 | `backend/app/gateway/routers/mcp.py:1647` |
| `PUT /api/mcp/config/server` | 400/401/403/422/500 | `backend/app/gateway/routers/mcp.py:1669` |
| `DELETE /api/mcp/config/servers/{server_name:path}` | 401/403/422/500 | `backend/app/gateway/routers/mcp.py:1694` |
| `PATCH /api/mcp/config` | 401/403/422/500 | `backend/app/gateway/routers/mcp.py:1715` |
| `POST /api/threads/{thread_id}/mcp-tasks/{task_id}/cancel` | 401/403/404/422/503 | `backend/app/gateway/routers/mcp_tasks.py:176` |
| `GET /api/threads/{thread_id}/mcp-tasks` | 401/403/404/422 | `backend/app/gateway/routers/mcp_tasks.py:93` |
| `GET /api/threads/{thread_id}/mcp-tasks/{task_id}` | 401/403/404/422 | `backend/app/gateway/routers/mcp_tasks.py:134` |
| `GET /api/memory` | 401/409/500/501 | `backend/app/gateway/routers/memory.py:255` |
| `POST /api/memory/reload` | 401/409/500/501 | `backend/app/gateway/routers/memory.py:308` |
| `DELETE /api/memory` | 401/409/500/501 | `backend/app/gateway/routers/memory.py:353` |
| `POST /api/memory/facts` | 400/401/409/422/500/501 | `backend/app/gateway/routers/memory.py:384` |
| `DELETE /api/memory/facts/{fact_id}` | 401/404/409/422/500/501 | `backend/app/gateway/routers/memory.py:423` |
| `PATCH /api/memory/facts/{fact_id}` | 400/401/404/409/422/500/501 | `backend/app/gateway/routers/memory.py:457` |
| `GET /api/memory/export` | 401/409/500/501 | `backend/app/gateway/routers/memory.py:496` |
| `POST /api/memory/import` | 401/409/422/500/501 | `backend/app/gateway/routers/memory.py:517` |
| `GET /api/memory/config` | 401 | `backend/app/gateway/routers/memory.py:551` |
| `GET /api/memory/status` | 401/409/500/501 | `backend/app/gateway/routers/memory.py:601` |
| `GET /api/models/{model_name}` | 401/403/404/422/500 | `backend/app/gateway/routers/models.py:221` |
| `GET /api/models` | 401/500 | `backend/app/gateway/routers/models.py:135` |
| `GET /api/projects/{project_id}/documents` | 401/403/404/422 | `backend/app/gateway/routers/project_documents.py:173` |
| `POST /api/projects/{project_id}/documents` | 400/401/403/404/413/422 | `backend/app/gateway/routers/project_documents.py:197` |
| `POST /api/projects/{project_id}/documents/from-thread` | 400/401/403/404/413/422 | `backend/app/gateway/routers/project_documents.py:304` |
| `POST /api/projects/{project_id}/documents/{document_id}/attach-to-thread/{thread_id}` | 401/403/404/409/422/500 | `backend/app/gateway/routers/project_documents.py:376` |
| `GET /api/projects/{project_id}/documents/{document_id}/content` | 401/403/404/409/422 | `backend/app/gateway/routers/project_documents.py:454` |
| `DELETE /api/projects/{project_id}/documents/{document_id}` | 401/403/404/422 | `backend/app/gateway/routers/project_documents.py:528` |
| `GET /api/projects/{project_id}/thread-files` | 401/403/404/422 | `backend/app/gateway/routers/project_thread_files.py:102` |
| `POST /api/projects` | 401/403/422 | `backend/app/gateway/routers/projects.py:116` |
| `GET /api/projects` | 401/403/422 | `backend/app/gateway/routers/projects.py:124` |
| `GET /api/projects/config` | 401/403 | `backend/app/gateway/routers/projects.py:131` |
| `GET /api/projects/{project_id}` | 401/403/404/422 | `backend/app/gateway/routers/projects.py:146` |
| `PATCH /api/projects/{project_id}` | 401/403/404/422 | `backend/app/gateway/routers/projects.py:155` |
| `POST /api/projects/{project_id}/archive` | 401/403/404/422 | `backend/app/gateway/routers/projects.py:165` |
| `POST /api/projects/{project_id}/restore` | 401/403/404/422 | `backend/app/gateway/routers/projects.py:174` |
| `DELETE /api/projects/{project_id}` | 401/403/404/422 | `backend/app/gateway/routers/projects.py:183` |
| `GET /api/projects/{project_id}/threads` | 401/403/404/422 | `backend/app/gateway/routers/projects.py:190` |
| `GET /api/runs/{run_id}/messages` | 401/403/404/422 | `backend/app/gateway/routers/runs.py:113` |
| `GET /api/runs/{run_id}/feedback` | 401/403/404/422 | `backend/app/gateway/routers/runs.py:144` |
| `POST /api/runs/stream` | 400/401/403/404/409/422/501 | `backend/app/gateway/routers/runs.py:40` |
| `POST /api/runs/wait` | 400/401/403/404/409/422/501 | `backend/app/gateway/routers/runs.py:61` |
| `POST /api/scheduled-tasks/preview-cron` | 401/403/422 | `backend/app/gateway/routers/scheduled_tasks.py:234` |
| `GET /api/scheduled-tasks` | 401/403 | `backend/app/gateway/routers/scheduled_tasks.py:245` |
| `POST /api/scheduled-tasks` | 401/403/404/422 | `backend/app/gateway/routers/scheduled_tasks.py:255` |
| `GET /api/scheduled-tasks/{task_id}` | 401/403/404/422 | `backend/app/gateway/routers/scheduled_tasks.py:294` |
| `PATCH /api/scheduled-tasks/{task_id}` | 401/403/404/409/422 | `backend/app/gateway/routers/scheduled_tasks.py:307` |
| `POST /api/scheduled-tasks/{task_id}/pause` | 401/403/404/409/422 | `backend/app/gateway/routers/scheduled_tasks.py:358` |
| `POST /api/scheduled-tasks/{task_id}/resume` | 401/403/404/409/422 | `backend/app/gateway/routers/scheduled_tasks.py:391` |
| `POST /api/scheduled-tasks/{task_id}/trigger` | 401/403/404/409/422/502 | `backend/app/gateway/routers/scheduled_tasks.py:428` |
| `DELETE /api/scheduled-tasks/{task_id}` | 401/403/404/409/422 | `backend/app/gateway/routers/scheduled_tasks.py:453` |
| `GET /api/scheduled-tasks/{task_id}/runs` | 401/403/404/422 | `backend/app/gateway/routers/scheduled_tasks.py:473` |
| `GET /api/threads/{thread_id}/scheduled-tasks` | 401/403/404/422 | `backend/app/gateway/routers/scheduled_tasks.py:494` |
| `GET /api/skills` | 401/500 | `backend/app/gateway/routers/skills.py:498` |
| `POST /api/skills/install` | 400/401/403/404/409/422/500 | `backend/app/gateway/routers/skills.py:526` |
| `POST /api/skills/install/upload` | 400/401/403/404/409/413/422/500 | `backend/app/gateway/routers/skills.py:543` |
| `POST /api/skills/reload` | 401/403/500 | `backend/app/gateway/routers/skills.py:598` |
| `GET /api/skills/custom` | 401/500 | `backend/app/gateway/routers/skills.py:645` |
| `GET /api/skills/custom/{skill_name}/export-manifest` | 204/401/403/404/409/413/422/429/500/503 | `backend/app/gateway/routers/skills.py:687` |
| `GET /api/skills/custom/{skill_name}/export` | 204/401/403/404/409/413/422/429/500/503 | `backend/app/gateway/routers/skills.py:707` |
| `GET /api/skills/custom/{skill_name}` | 401/403/404/422/500 | `backend/app/gateway/routers/skills.py:728` |
| `PUT /api/skills/custom/{skill_name}` | 400/401/403/404/422/500 | `backend/app/gateway/routers/skills.py:760` |
| `DELETE /api/skills/custom/{skill_name}` | 400/401/403/404/422/500 | `backend/app/gateway/routers/skills.py:827` |
| `GET /api/skills/custom/{skill_name}/history` | 401/403/404/422/500 | `backend/app/gateway/routers/skills.py:876` |
| `POST /api/skills/custom/{skill_name}/rollback` | 400/401/403/404/422/500 | `backend/app/gateway/routers/skills.py:911` |
| `GET /api/skills/{skill_name}` | 401/404/422/500 | `backend/app/gateway/routers/skills.py:1012` |
| `PUT /api/skills/{skill_name}` | 401/403/404/422/500 | `backend/app/gateway/routers/skills.py:1095` |
| `GET /api/threads/{thread_id}/subagent-batches/{batch_id}/results.jsonl` | 401/403/404/422 | `backend/app/gateway/routers/subagent_batches.py:129` |
| `GET /api/threads/{thread_id}/subagent-batches` | 401/403/404/422 | `backend/app/gateway/routers/subagent_batches.py:43` |
| `GET /api/threads/{thread_id}/subagent-batches/{batch_id}` | 401/403/404/422 | `backend/app/gateway/routers/subagent_batches.py:50` |
| `GET /api/threads/{thread_id}/subagent-batches/{batch_id}/items` | 401/403/404/422 | `backend/app/gateway/routers/subagent_batches.py:57` |
| `POST /api/threads/{thread_id}/subagent-batches/{batch_id}/pause` | 401/403/404/422 | `backend/app/gateway/routers/subagent_batches.py:93` |
| `POST /api/threads/{thread_id}/subagent-batches/{batch_id}/resume` | 401/403/404/422 | `backend/app/gateway/routers/subagent_batches.py:100` |
| `POST /api/threads/{thread_id}/subagent-batches/{batch_id}/cancel` | 401/403/404/422/503 | `backend/app/gateway/routers/subagent_batches.py:107` |
| `POST /api/threads/{thread_id}/subagent-batches/{batch_id}/items/{item_id}/retry` | 401/403/404/409/422 | `backend/app/gateway/routers/subagent_batches.py:119` |
| `GET /api/subagents` | 401 | `backend/app/gateway/routers/subagents.py:164` |
| `POST /api/subagents` | 401/403/409/422 | `backend/app/gateway/routers/subagents.py:171` |
| `PUT /api/subagents/{name}` | 401/403/404/422 | `backend/app/gateway/routers/subagents.py:196` |
| `DELETE /api/subagents/{name}` | 401/403/404/422 | `backend/app/gateway/routers/subagents.py:232` |
| `POST /api/threads/{thread_id}/suggestions` | 401/403/404/422 | `backend/app/gateway/routers/suggestions.py:98` |
| `GET /api/suggestions/config` | 401 | `backend/app/gateway/routers/suggestions.py:86` |
| `GET /api/threads/{thread_id}/runs` | 401/403/404/422 | `backend/app/gateway/routers/thread_runs.py:1215` |
| `GET /api/threads/{thread_id}/runs/page` | 401/403/404/422 | `backend/app/gateway/routers/thread_runs.py:1225` |
| `GET /api/threads/{thread_id}/runs/{run_id}` | 401/403/404/422 | `backend/app/gateway/routers/thread_runs.py:1267` |
| `POST /api/threads/{thread_id}/runs/{run_id}/cancel` | 401/403/404/409/422 | `backend/app/gateway/routers/thread_runs.py:1279` |
| `GET /api/threads/{thread_id}/runs/{run_id}/join` | 401/403/404/409/422 | `backend/app/gateway/routers/thread_runs.py:1340` |
| `POST /api/threads/{thread_id}/runs/{run_id}/stream` | 401/403/404/409/422/503 | `backend/app/gateway/routers/thread_runs.py:1450` |
| `GET /api/threads/{thread_id}/runs/{run_id}/stream` | 401/403/404/409/422/503 | `backend/app/gateway/routers/thread_runs.py:1463` |
| `GET /api/threads/{thread_id}/messages` | 401/403/404/422 | `backend/app/gateway/routers/thread_runs.py:1480` |
| `GET /api/threads/{thread_id}/messages/page` | 401/403/404/422 | `backend/app/gateway/routers/thread_runs.py:1620` |
| `GET /api/threads/{thread_id}/runs/{run_id}/messages` | 401/403/404/422 | `backend/app/gateway/routers/thread_runs.py:1648` |
| `GET /api/threads/{thread_id}/runs/{run_id}/artifacts/archive` | 401/403/404/409/422 | `backend/app/gateway/routers/thread_runs.py:1762` |
| `POST /api/threads/{thread_id}/runs/{run_id}/artifacts/archive` | 401/403/404/409/413/422/429/503 | `backend/app/gateway/routers/thread_runs.py:1778` |
| `GET /api/threads/{thread_id}/runs/{run_id}/events` | 401/403/404/422 | `backend/app/gateway/routers/thread_runs.py:1837` |
| `GET /api/threads/{thread_id}/runs/{run_id}/workspace-changes` | 401/403/404/422 | `backend/app/gateway/routers/thread_runs.py:1885` |
| `GET /api/threads/{thread_id}/token-usage` | 401/403/404/422 | `backend/app/gateway/routers/thread_runs.py:1908` |
| `POST /api/threads/{thread_id}/runs/regenerate/prepare` | 401/403/404/409/422/500 | `backend/app/gateway/routers/thread_runs.py:963` |
| `POST /api/threads/{thread_id}/runs/edit-regenerate/prepare` | 401/403/404/409/422/500 | `backend/app/gateway/routers/thread_runs.py:974` |
| `POST /api/threads/{thread_id}/runs` | 400/401/403/404/409/422/501 | `backend/app/gateway/routers/thread_runs.py:985` |
| `POST /api/threads/{thread_id}/runs/stream` | 400/401/403/404/409/422/501 | `backend/app/gateway/routers/thread_runs.py:1003` |
| `POST /api/threads/{thread_id}/runs/wait` | 400/401/403/404/409/422/501 | `backend/app/gateway/routers/thread_runs.py:1053` |
| `POST /api/threads/search` | 400/401/403/422 | `backend/app/gateway/routers/threads.py:1286` |
| `PATCH /api/threads/{thread_id}` | 401/403/404/422/500 | `backend/app/gateway/routers/threads.py:1365` |
| `POST /api/threads/{thread_id}/move` | 401/403/404/422 | `backend/app/gateway/routers/threads.py:1404` |
| `GET /api/threads/{thread_id}` | 401/403/404/409/422/500/503 | `backend/app/gateway/routers/threads.py:1425` |
| `GET /api/threads/{thread_id}/goal` | 401/403/404/422/500 | `backend/app/gateway/routers/threads.py:1478` |
| `PUT /api/threads/{thread_id}/goal` | 401/403/404/409/422/500 | `backend/app/gateway/routers/threads.py:1491` |
| `DELETE /api/threads/{thread_id}/goal` | 401/403/404/409/422/500 | `backend/app/gateway/routers/threads.py:1517` |
| `POST /api/threads/{thread_id}/compact` | 401/403/404/409/422/500/503 | `backend/app/gateway/routers/threads.py:1548` |
| `GET /api/threads/{thread_id}/state` | 401/403/404/409/422/500/503 | `backend/app/gateway/routers/threads.py:1597` |
| `POST /api/threads/{thread_id}/state` | 401/403/404/409/422/500/503 | `backend/app/gateway/routers/threads.py:1646` |
| `POST /api/threads/{thread_id}/history` | 401/403/404/409/422/500/503 | `backend/app/gateway/routers/threads.py:1865` |
| `DELETE /api/threads/{thread_id}` | 401/403/404/409/422/500 | `backend/app/gateway/routers/threads.py:756` |
| `POST /api/threads` | 401/403/404/422/500 | `backend/app/gateway/routers/threads.py:959` |
| `POST /api/threads/{thread_id}/branches` | 401/403/404/409/422/500/503 | `backend/app/gateway/routers/threads.py:1051` |
| `GET /api/trash/documents` | 401/403/422 | `backend/app/gateway/routers/trash.py:137` |
| `POST /api/trash/documents/{document_id}/restore` | 401/403/404/409/422 | `backend/app/gateway/routers/trash.py:171` |
| `POST /api/trash/documents/{document_id}/purge` | 401/403/404/422/500 | `backend/app/gateway/routers/trash.py:208` |
| `POST /api/trash/purge` | 401/403/500 | `backend/app/gateway/routers/trash.py:226` |
| `POST /api/threads/{thread_id}/uploads` | 400/401/403/404/413/422/500 | `backend/app/gateway/routers/uploads.py:394` |
| `GET /api/threads/{thread_id}/uploads/limits` | 401/403/404/422 | `backend/app/gateway/routers/uploads.py:494` |
| `GET /api/threads/{thread_id}/uploads/list` | 400/401/403/404/422 | `backend/app/gateway/routers/uploads.py:505` |
| `DELETE /api/threads/{thread_id}/uploads/{filename}` | 400/401/403/404/422/500 | `backend/app/gateway/routers/uploads.py:517` |
| `GET /api/v1/auth/preferences` | 401/403/409/422/503 | `backend/app/gateway/routers/user_preferences.py:51` |
| `PATCH /api/v1/auth/preferences` | 401/403/409/422/503 | `backend/app/gateway/routers/user_preferences.py:66` |


---

## 5. 专题：Feedback / Suggestions / Skills / RunCreateRequest / MCP 合并

### 5.1 反馈系统 (`/api/threads/{id}/runs/{rid}/feedback`)

```mermaid
flowchart TD
    subgraph CRUD
        PUT -->|upsert| U[幂等: 创建或更新]
        POST -->|create| C[已验证运行与线程交叉引用]
        GET -->|list| L[按线程/运行列出]
        GET2[GET /stats] -->|aggregate| S[总计/正面/负面]
        DELETE -->|by-run| D[删除用户反馈]
        DELETE2[DELETE /{fid}] -->|specific| F[按 ID 删除]
    end
```

| 方法 | 路径 | 说明 | 鉴权 |
|------|------|------|------|
| `PUT` | `/{thread_id}/runs/{run_id}/feedback` | 幂等性 upsert | `threads:write` + owner(`require_existing`) |
| `POST` | `/{thread_id}/runs/{run_id}/feedback` | 创建反馈 | `threads:write` + owner(`require_existing`) |
| `GET` | `/{thread_id}/runs/{run_id}/feedback` | 列出反馈 | `threads:read` + owner |
| `GET` | `/{thread_id}/runs/{run_id}/feedback/stats` | 聚合统计 | `threads:read` + owner |
| `DELETE` | `/{thread_id}/runs/{run_id}/feedback` | 删除用户反馈 | `threads:delete` + owner(`require_existing`) |
| `DELETE` | `/{thread_id}/runs/{run_id}/feedback/{fid}` | 按 ID 删除 | `threads:delete` + owner(`require_existing`) |

**请求/响应模型**：

```python
FeedbackCreateRequest:  rating: int (1 or -1); comment: str | None; message_id: str | None
FeedbackUpsertRequest:  rating: int (1 or -1); comment: str | None
FeedbackResponse:       feedback_id, run_id, thread_id, user_id, message_id, rating, comment, created_at
FeedbackStatsResponse:  run_id, total, positive, negative
```

**错误语义**：`rating` 不是 `+1/-1` → **400**；run 不存在或不属于该 thread → **404**（`feedback.py:79/81`、`:131/133`）；删除不存在的反馈 → **404**（`:109`、`:183/185/188`）。

### 5.2 建议系统 (`POST /api/threads/{id}/suggestions`)

```
REQ → 验证消息（空 → 返回 []）→ 格式化对话 → create_chat_model(thinking_enabled=False)
    → ainvoke(system + user) → _extract_response_text() → _strip_markdown_code_fence()
    → _parse_json_string_list() → 成功则清理/限 n；失败则静默降级为 []
```

- SystemInstruction 要求精确 N 个问题、与用户同语言、≤20 单词 / 40 中文字符（`routers/suggestions.py`）
- `_extract_response_text()` 处理富块/列表内容（text + output_text）
- `_parse_json_string_list()` 做括号平衡提取并逐项校验为 str
- 失败**静默降级**（永远 `{suggestions: []}`，不报错）——`suggestions.py:146` 的 `except Exception` 返回空列表

### 5.3 自定义 Skill CRUD (`/api/skills/custom/{name}`)

```mermaid
flowchart LR
    INSTALL[POST /api/skills/install .skill ZIP] --> SCAN[安全扫描]
    READ[GET /{name}] --> CONTENT[内容]
    EDIT[PUT /{name}] --> SCAN2[安全扫描] --> SAVE[保存 + 历史]
    ROLL[POST /{name}/rollback] --> SCAN3[重新扫描] --> SAVE2[保存]
    HIST[GET /{name}/history] --> LIST[变更列表]
    DEL[DELETE /{name}] --> HIST2[保留历史]
```

安全扫描（`deerflow/skills/security_scanner.py`）：LLM 驱动的内容筛查（allow/warn/block），括号平衡的 JSON 提取，模型不可用时 **fail-closed**（默认阻止）→ 编辑/回滚 **400**。

### 5.4 RunCreateRequest 完整模型

真值 `app/gateway/run_models.py:29-58`，`model_config = ConfigDict(extra="forbid")`，共 **20 个字段**，其中多个 LangGraph Platform 字段只是**兼容占位**（类型收窄为 `None` / 单一字面量，传旧值会 **422**）：

```python
class RunCreateRequest(BaseModel):   # extra="forbid"
    assistant_id: str | None
    input: dict | None
    command: dict | None
    metadata: dict | None
    config: dict | None
    context: dict | None              # DeerFlow 上下文覆盖；没有顶层 model_name 字段
    conversation_references: list[str] = []   # 上限 3（MAX_CONVERSATION_REFERENCES）；顶层与 context 同时给会 422

    interrupt_before / interrupt_after: list[str] | Literal["*"] | None
    stream_mode: list[str] | str | None
    stream_subgraphs: bool = False
    stream_resumable: Literal[False] | None    # 兼容占位：只接受 null/false

    on_disconnect: Literal["cancel", "continue"] = "cancel"
    on_completion: None = None                 # 兼容占位
    multitask_strategy: Literal["reject", "rollback", "interrupt"] = "reject"   # 没有 enqueue（→422）；运行时不支持则 501

    webhook / after_seconds / feedback_keys: None = None   # 兼容占位
    if_not_exists: Literal["create"] = "create"

    checkpoint_id: str | None
    checkpoint: dict | None
```

### 5.5 MCP 配置合并

`PUT /api/mcp/config` 实现 `_merge_preserving_secrets()`（`routers/mcp.py:897`（定义），调用点 `:1328`、`:1511`）：

1. `ExtensionsConfig.resolve_config_path()`，缺失则落到 `<project_root>/extensions_config.json`
2. 在 `extensions_config_write_lock` + 跨进程 `extensions_config_file_lock(path)` 内做**整个 read-modify-write**
3. 从磁盘读**原始** JSON 作为合并源（保留 `$VAR` 占位符与 `mcpInterceptors`、`middlewares` 等 schema 外顶层键）
4. 原子写入（Linux 上 `rename()` 撞 mount point 的 `EBUSY` 才回退为原地覆写）
5. 校验展开后的配置 → 非法一律 **400**；非预期异常 **500**

这允许前端在往返中发送掩码值（`***`），真实密钥保留在磁盘上。
