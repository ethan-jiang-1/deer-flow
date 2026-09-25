---
title: "REST API 端点文档"
description: "v2.1.0 全部 Gateway 路由的穷举清单，以及「领域异常 → HTTP 映射」穷举表（每条带 file:line）。"
topics: [gateway, api, rest, error-handling]
---

# REST API 端点文档

本文档有两块可核对内容：

1. **§1 端点总览** — `backend/app/gateway/routers/*.py` 里 **180** 条 `(方法, 路径)`，逐条给 `file:line`、鉴权、成功码。
2. **§2 领域异常 → HTTP 映射（穷举）** — 按状态码分组，覆盖每个 `raise HTTPException(...)`、每个 `except XxxError → 状态码`，以及路由之前三层中间件的码。`operations/integration/**` 通过指针引用本节（§2.19 是路由组级签名，权威行）。

> **核对口径**：源码 = upstream tag `v2.1.0`（`345f08be`），工作区 `backend/app/gateway/routers/` 与该 tag 逐字节一致（`git diff 345f08be -- backend/app/gateway/routers/` 为空）。所有锚点行号均为该 revision 实测。AST 提取脚本口径：`raise HTTPException` 出现 **417** 次，含 helper 返回值在内的全部 `raise` 语句 **494** 处。detail 文本在表中做摘要，不逐字复制长 f-string。

---

## 1. 端点总览（v2.1.0 穷举）

**180** 条 `(方法, 路径)`：`GET` 78、`POST` 69、`DELETE` 17、`PUT` 10、`PATCH` 6。另有 3 个不在 `routers/` 内的入口见 §1.2。

鉴权列含义：

- `x:y` 来自 `@require_permission("x", "y", ...)`（`authz.py:595`）；`(owner)` = `owner_check=True`（不匹配 → **404**），`(require_existing)` = 缺失行也算失败（→ **404**）。
- `admin（require_admin_user）` = 路由体内显式 `require_admin_user()`（`deps.py:894`，非 admin → **403**）。
- `已登录（无 require_permission）` = 只被 `AuthMiddleware` 挡住（未认证 → **401**）。
- 中间件实际执行顺序是 **CSRF → Auth**（见 §3）：所有 `POST/PUT/DELETE/PATCH`（除 `/api/v1/auth/me`、`/api/webhooks/*`、auth-disabled 模式，以及带 `Authorization` 头的请求）先过 `CSRFMiddleware`——缺 token/不匹配 **403**；随后**所有**非公开路由过 `AuthMiddleware`——未认证 **401**。本节鉴权列只写路由自身的额外约束。

### 1.1 routers/ 全部端点

#### Custom Agents / User Profile

源码：`routers/agents.py` — 受 `agents_api.enabled` 门控，关闭时 **403**。

| 方法 | 路径 | 鉴权 | 成功码 | 源码 | 摘要 |
|------|------|------|--------|------|------|
| `GET` | `/api/agents` | 已登录 + `agents_api.enabled`（关闭 **403**） | 200 | `backend/app/gateway/routers/agents.py:215` | List Custom Agents |
| `GET` | `/api/agents/check` | 已登录 + `agents_api.enabled`（关闭 **403**） | 200 | `backend/app/gateway/routers/agents.py:244` | Check Agent Name |
| `GET` | `/api/agents/{name}` | 已登录 + `agents_api.enabled`（关闭 **403**） | 200 | `backend/app/gateway/routers/agents.py:277` | Get Custom Agent |
| `POST` | `/api/agents` | 已登录 + `agents_api.enabled`（关闭 **403**） | 201 | `backend/app/gateway/routers/agents.py:315` | Create Custom Agent |
| `PUT` | `/api/agents/{name}` | 已登录 + `agents_api.enabled`（关闭 **403**） | 200 | `backend/app/gateway/routers/agents.py:373` | Update Custom Agent |
| `GET` | `/api/user-profile` | 已登录 + `agents_api.enabled`（关闭 **403**） | 200 | `backend/app/gateway/routers/agents.py:512` | Get User Profile |
| `PUT` | `/api/user-profile` | 已登录 + `agents_api.enabled`（关闭 **403**） | 200 | `backend/app/gateway/routers/agents.py:537` | Update User Profile |
| `DELETE` | `/api/agents/{name}` | 已登录 + `agents_api.enabled`（关闭 **403**） | 204 | `backend/app/gateway/routers/agents.py:565` | Delete Custom Agent |

#### Artifacts

源码：`routers/artifacts.py` — owner-scoped `threads:read/write`；编辑受 412/413/415 约束。

| 方法 | 路径 | 鉴权 | 成功码 | 源码 | 摘要 |
|------|------|------|--------|------|------|
| `GET` | `/api/threads/{thread_id}/artifacts/{path:path}` | `threads:read` (owner) | 200 | `backend/app/gateway/routers/artifacts.py:339` | Get Artifact File |
| `PUT` | `/api/threads/{thread_id}/artifacts/{path:path}` | `threads:write` (owner, require_existing) | 200 | `backend/app/gateway/routers/artifacts.py:486` | Update Artifact File |

#### Assistants 兼容层

源码：`routers/assistants_compat.py` — LangGraph Platform SDK 兼容 stub。

| 方法 | 路径 | 鉴权 | 成功码 | 源码 | 摘要 |
|------|------|------|--------|------|------|
| `POST` | `/api/assistants/search` | 已登录（无 `require_permission`） | 200 | `backend/app/gateway/routers/assistants_compat.py:90` | Search assistants. |
| `GET` | `/api/assistants/{assistant_id}` | 已登录（无 `require_permission`） | 200 | `backend/app/gateway/routers/assistants_compat.py:110` | Get an assistant by ID. |
| `GET` | `/api/assistants/{assistant_id}/graph` | 已登录（无 `require_permission`） | 200 | `backend/app/gateway/routers/assistants_compat.py:119` | Get the graph structure for an assistant. |
| `GET` | `/api/assistants/{assistant_id}/schemas` | 已登录（无 `require_permission`） | 200 | `backend/app/gateway/routers/assistants_compat.py:137` | Get JSON schemas for an assistant's input/output/state. |

#### Auth / PAT / OIDC

源码：`routers/auth.py` — 登录/注册/OIDC 公开；PAT 管理要求 session（**403**）。

| 方法 | 路径 | 鉴权 | 成功码 | 源码 | 摘要 |
|------|------|------|--------|------|------|
| `POST` | `/api/v1/auth/login/local` | 公开（限流 429） | 200 | `backend/app/gateway/routers/auth.py:403` | Local email/password login. |
| `POST` | `/api/v1/auth/register` | 公开 | 201 | `backend/app/gateway/routers/auth.py:458` | Register a new user account (always 'user' role). |
| `POST` | `/api/v1/auth/logout` | 公开/session | 200 | `backend/app/gateway/routers/auth.py:487` | Logout current user by clearing the cookie. |
| `POST` | `/api/v1/auth/change-password` | 已登录（无 `require_permission`） | 200 | `backend/app/gateway/routers/auth.py:498` | Change password for the currently authenticated user. |
| `GET` | `/api/v1/auth/me` | session 或 PAT | 200 | `backend/app/gateway/routers/auth.py:562` | Get current authenticated user info, including effective permissions. |
| `POST` | `/api/v1/auth/pats` | 已登录（无 `require_permission`） | 201 | `backend/app/gateway/routers/auth.py:652` | Create a personal access token for the session user. |
| `GET` | `/api/v1/auth/pats` | session-only（PAT 403） | 200 | `backend/app/gateway/routers/auth.py:689` | List the session user's tokens. Never returns digests or raw tokens. |
| `DELETE` | `/api/v1/auth/pats/{pat_id}` | session-only（PAT 403） | 200 | `backend/app/gateway/routers/auth.py:699` | Revoke one of the session user's tokens. Revocation is immediate. |
| `GET` | `/api/v1/auth/setup-status` | 公开 | 200 | `backend/app/gateway/routers/auth.py:722` | Check if an admin account exists. Returns needs_setup=True when no admin exists. |
| `POST` | `/api/v1/auth/initialize` | 公开 | 201 | `backend/app/gateway/routers/auth.py:789` | Create the first admin account on initial system setup. |
| `GET` | `/api/v1/auth/providers` | 公开 | 200 | `backend/app/gateway/routers/auth.py:881` | List enabled SSO providers for the login page. |
| `GET` | `/api/v1/auth/oauth/{provider}` | 公开 | 200 | `backend/app/gateway/routers/auth.py:908` | Initiate OIDC login flow. |
| `GET` | `/api/v1/auth/callback/{provider}` | 公开 | 200 | `backend/app/gateway/routers/auth.py:987` | OIDC callback endpoint. |

#### Browser 自动化

源码：`routers/browser.py` — 受 `browser_control` 配置门控；未启用 **404**，依赖缺失 **501**，底层失败 **502**。

| 方法 | 路径 | 鉴权 | 成功码 | 源码 | 摘要 |
|------|------|------|--------|------|------|
| `POST` | `/api/threads/{thread_id}/browser/navigate` | `threads:write` (owner, require_existing) | 200 | `backend/app/gateway/routers/browser.py:81` | Navigate The Live Browser Session |

#### Channel Connections

源码：`routers/channel_connections.py` — runtime-config 端点 admin-only；连接码超限 **429**。

| 方法 | 路径 | 鉴权 | 成功码 | 源码 | 摘要 |
|------|------|------|--------|------|------|
| `GET` | `/api/channels/providers` | 已登录（无 `require_permission`） | 200 | `backend/app/gateway/routers/channel_connections.py:515` | — |
| `GET` | `/api/channels/connections` | 已登录（无 `require_permission`） | 200 | `backend/app/gateway/routers/channel_connections.py:545` | — |
| `DELETE` | `/api/channels/connections/{connection_id}` | 已登录（无 `require_permission`） | 204 | `backend/app/gateway/routers/channel_connections.py:555` | — |
| `DELETE` | `/api/channels/{provider}/runtime-config` | admin（`require_admin_user`，非 admin **403**） | 200 | `backend/app/gateway/routers/channel_connections.py:571` | — |
| `POST` | `/api/channels/{provider}/connect` | 已登录（无 `require_permission`） | 200 | `backend/app/gateway/routers/channel_connections.py:618` | — |
| `POST` | `/api/channels/{provider}/runtime-config` | admin（`require_admin_user`，非 admin **403**） | 200 | `backend/app/gateway/routers/channel_connections.py:653` | — |

#### Channels 状态/重启

源码：`routers/channels.py` — 重启需要 admin；channel service 未运行 **503**。

| 方法 | 路径 | 鉴权 | 成功码 | 源码 | 摘要 |
|------|------|------|--------|------|------|
| `GET` | `/api/channels/` | 登录即可 | 200 | `backend/app/gateway/routers/channels.py:30` | Get the status of all IM channels. |
| `POST` | `/api/channels/{name}/restart` | admin | 200 | `backend/app/gateway/routers/channels.py:42` | Restart a specific IM channel. |

#### Console — 跨线程可观测性

源码：`routers/console.py` — `runs:read`；无 SQL backend 时 **503**。

| 方法 | 路径 | 鉴权 | 成功码 | 源码 | 摘要 |
|------|------|------|--------|------|------|
| `GET` | `/api/console/stats` | `runs:read` | 200 | `backend/app/gateway/routers/console.py:285` | Console Stats |
| `GET` | `/api/console/runs` | `runs:read` | 200 | `backend/app/gateway/routers/console.py:356` | List Runs Across Threads |
| `GET` | `/api/console/usage` | `runs:read` | 200 | `backend/app/gateway/routers/console.py:427` | Token Usage Over Time |

#### Features — 前端能力门控

源码：`routers/features.py` — 需要认证（无细粒度权限）。

| 方法 | 路径 | 鉴权 | 成功码 | 源码 | 摘要 |
|------|------|------|--------|------|------|
| `GET` | `/api/features` | 已登录（无 `require_permission`） | 200 | `backend/app/gateway/routers/features.py:73` | List Feature Flags |

#### Feedback

源码：`routers/feedback.py` — `threads:write/read/delete` + owner；rating 非法 **400**。

| 方法 | 路径 | 鉴权 | 成功码 | 源码 | 摘要 |
|------|------|------|--------|------|------|
| `PUT` | `/api/threads/{thread_id}/runs/{run_id}/feedback` | `threads:write` (owner, require_existing) | 200 | `backend/app/gateway/routers/feedback.py:64` | Create or update feedback for a run (idempotent). |
| `DELETE` | `/api/threads/{thread_id}/runs/{run_id}/feedback` | `threads:delete` (owner, require_existing) | 200 | `backend/app/gateway/routers/feedback.py:95` | Delete the current user's feedback for a run. |
| `POST` | `/api/threads/{thread_id}/runs/{run_id}/feedback` | `threads:write` (owner, require_existing) | 200 | `backend/app/gateway/routers/feedback.py:115` | Submit feedback (thumbs-up/down) for a run. |
| `GET` | `/api/threads/{thread_id}/runs/{run_id}/feedback` | `threads:read` (owner) | 200 | `backend/app/gateway/routers/feedback.py:148` | List all feedback for a run. |
| `GET` | `/api/threads/{thread_id}/runs/{run_id}/feedback/stats` | `threads:read` (owner) | 200 | `backend/app/gateway/routers/feedback.py:160` | Get aggregated feedback stats (positive/negative counts) for a run. |
| `DELETE` | `/api/threads/{thread_id}/runs/{run_id}/feedback/{feedback_id}` | `threads:delete` (owner, require_existing) | 200 | `backend/app/gateway/routers/feedback.py:172` | Delete a feedback record. |

#### GitHub Webhooks

源码：`routers/github_webhooks.py` — HMAC 校验，失败 **401**；未配置 secret 时**整个路由不挂载**（404）。

| 方法 | 路径 | 鉴权 | 成功码 | 源码 | 摘要 |
|------|------|------|--------|------|------|
| `POST` | `/api/webhooks/github` | HMAC（无 JWT/CSRF） | 200 | `backend/app/gateway/routers/github_webhooks.py:173` | Receive a GitHub webhook delivery. |

#### Input Polish

源码：`routers/input_polish.py` — `runs:create`；LLM 调用失败 **503**。

| 方法 | 路径 | 鉴权 | 成功码 | 源码 | 摘要 |
|------|------|------|--------|------|------|
| `POST` | `/api/input-polish` | `runs:create` | 200 | `backend/app/gateway/routers/input_polish.py:65` | Polish Composer Input |

#### Integrations（Lark）

源码：`routers/integrations.py` — 写操作 admin-only（**403**）；Lark 流程被取代 **409**，CLI 超时 **504**，未安装 **404**；`GET /status` 对非 admin 只脱敏不拒绝（见 §2.19）。

| 方法 | 路径 | 鉴权 | 成功码 | 源码 | 摘要 |
|------|------|------|--------|------|------|
| `GET` | `/api/integrations/lark/status` | 已登录（无 `require_permission`） | 200 | `backend/app/gateway/routers/integrations.py:260` | Get Lark/Feishu Integration Status |
| `POST` | `/api/integrations/lark/install` | admin（`require_admin_user`，非 admin **403**） | 200 | `backend/app/gateway/routers/integrations.py:270` | Install Lark/Feishu Skill Pack |
| `POST` | `/api/integrations/lark/config/start` | 已登录（无 `require_permission`） | 200 | `backend/app/gateway/routers/integrations.py:288` | Start Lark/Feishu App Configuration |
| `POST` | `/api/integrations/lark/config/complete` | 已登录（无 `require_permission`） | 200 | `backend/app/gateway/routers/integrations.py:308` | Complete Lark/Feishu App Configuration |
| `POST` | `/api/integrations/lark/config/credentials` | 已登录（无 `require_permission`） | 200 | `backend/app/gateway/routers/integrations.py:335` | Switch Lark/Feishu App Credentials |
| `POST` | `/api/integrations/lark/auth/start` | 已登录（无 `require_permission`） | 200 | `backend/app/gateway/routers/integrations.py:358` | Start Lark/Feishu Browser Authorization |
| `POST` | `/api/integrations/lark/auth/complete` | 已登录（无 `require_permission`） | 200 | `backend/app/gateway/routers/integrations.py:383` | Complete Lark/Feishu Browser Authorization |

#### MCP 配置

源码：`routers/mcp.py` — 全部经 `require_admin_user`（**403**）；配置非法 **400**，非预期异常 **500**。

| 方法 | 路径 | 鉴权 | 成功码 | 源码 | 摘要 |
|------|------|------|--------|------|------|
| `GET` | `/api/mcp/config` | admin（`require_admin_user`，非 admin **403**） | 200 | `backend/app/gateway/routers/mcp.py:1116` | Get MCP Configuration |
| `POST` | `/api/mcp/cache/reset` | admin（`require_admin_user`，非 admin **403**） | 200 | `backend/app/gateway/routers/mcp.py:1423` | Reset MCP Tools Cache |
| `PUT` | `/api/mcp/config` | admin（`require_admin_user`，非 admin **403**） | 200 | `backend/app/gateway/routers/mcp.py:1444` | Update MCP Configuration |
| `POST` | `/api/mcp/config/servers` | admin（`require_admin_user`，非 admin **403**） | 200 | `backend/app/gateway/routers/mcp.py:1504` | Add MCP Servers |
| `PUT` | `/api/mcp/config/server` | admin（`require_admin_user`，非 admin **403**） | 200 | `backend/app/gateway/routers/mcp.py:1527` | Update MCP Server |
| `DELETE` | `/api/mcp/config/servers/{server_name:path}` | admin（`require_admin_user`，非 admin **403**） | 200 | `backend/app/gateway/routers/mcp.py:1553` | Delete MCP Server |
| `PATCH` | `/api/mcp/config` | admin（`require_admin_user`，非 admin **403**） | 200 | `backend/app/gateway/routers/mcp.py:1575` | Update MCP Server State |

#### MCP 长任务

源码：`routers/mcp_tasks.py` — owner-scoped `threads:read/write`；取消时 worker 未运行 **503**。

| 方法 | 路径 | 鉴权 | 成功码 | 源码 | 摘要 |
|------|------|------|--------|------|------|
| `GET` | `/api/threads/{thread_id}/mcp-tasks` | `threads:read` (owner) | 200 | `backend/app/gateway/routers/mcp_tasks.py:68` | — |
| `GET` | `/api/threads/{thread_id}/mcp-tasks/{task_id}` | `threads:read` (owner) | 200 | `backend/app/gateway/routers/mcp_tasks.py:87` | — |
| `POST` | `/api/threads/{thread_id}/mcp-tasks/{task_id}/cancel` | `threads:write` (owner) | 200 | `backend/app/gateway/routers/mcp_tasks.py:106` | — |

#### Memory

源码：`routers/memory.py` — 需要认证；后端不支持的操作 **501**，并发冲突 **409**。

| 方法 | 路径 | 鉴权 | 成功码 | 源码 | 摘要 |
|------|------|------|--------|------|------|
| `GET` | `/api/memory` | 已登录（无 `require_permission`） | 200 | `backend/app/gateway/routers/memory.py:211` | Get Memory Data |
| `POST` | `/api/memory/reload` | 已登录（无 `require_permission`） | 200 | `backend/app/gateway/routers/memory.py:257` | Reload Memory Data |
| `DELETE` | `/api/memory` | 已登录（无 `require_permission`） | 200 | `backend/app/gateway/routers/memory.py:290` | Clear All Memory Data |
| `POST` | `/api/memory/facts` | 已登录（无 `require_permission`） | 200 | `backend/app/gateway/routers/memory.py:312` | Create Memory Fact |
| `DELETE` | `/api/memory/facts/{fact_id}` | 已登录（无 `require_permission`） | 200 | `backend/app/gateway/routers/memory.py:345` | Delete Memory Fact |
| `PATCH` | `/api/memory/facts/{fact_id}` | 已登录（无 `require_permission`） | 200 | `backend/app/gateway/routers/memory.py:369` | Patch Memory Fact |
| `GET` | `/api/memory/export` | 已登录（无 `require_permission`） | 200 | `backend/app/gateway/routers/memory.py:402` | Export Memory Data |
| `POST` | `/api/memory/import` | 已登录（无 `require_permission`） | 200 | `backend/app/gateway/routers/memory.py:416` | Import Memory Data |
| `GET` | `/api/memory/config` | 已登录（无 `require_permission`） | 200 | `backend/app/gateway/routers/memory.py:441` | Get Memory Configuration |
| `GET` | `/api/memory/status` | 已登录（无 `require_permission`） | 200 | `backend/app/gateway/routers/memory.py:491` | Get Memory Status |

#### Models — 模型目录

源码：`routers/models.py` — 需要认证；`GET /{name}` 另做 `model:use` 授权，fail-closed 时 403。

| 方法 | 路径 | 鉴权 | 成功码 | 源码 | 摘要 |
|------|------|------|--------|------|------|
| `GET` | `/api/models` | 已登录（无 `require_permission`） | 200 | `backend/app/gateway/routers/models.py:50` | List All Models |
| `GET` | `/api/models/{model_name}` | 已登录（无 `require_permission`） | 200 | `backend/app/gateway/routers/models.py:138` | Get Model Details |

#### Project Document Shelf

源码：`routers/project_documents.py` — `projects:*`（部分叠加 `threads:*`）；归档项目上架 **404**，内容缺失 **409**。

| 方法 | 路径 | 鉴权 | 成功码 | 源码 | 摘要 |
|------|------|------|--------|------|------|
| `GET` | `/api/projects/{project_id}/documents` | `projects:read` | 200 | `backend/app/gateway/routers/project_documents.py:142` | — |
| `POST` | `/api/projects/{project_id}/documents` | `projects:write` | 201 | `backend/app/gateway/routers/project_documents.py:166` | Shelf exactly one file (§17.2): 201 created, or 200 on a content dedup hit. |
| `POST` | `/api/projects/{project_id}/documents/from-thread` | `projects:write` + `threads:read` | 201 | `backend/app/gateway/routers/project_documents.py:270` | Copy one thread file (upload or output) into the shelf (§7.4). |
| `POST` | `/api/projects/{project_id}/documents/{document_id}/attach-to-thread/{thread_id}` | `projects:write` + `threads:write` (owner, require_existing) | 200 | `backend/app/gateway/routers/project_documents.py:338` | Materialize an independent copy of a shelf document into a thread (§7.3 item 3). |
| `GET` | `/api/projects/{project_id}/documents/{document_id}/content` | `projects:read` | 200 | `backend/app/gateway/routers/project_documents.py:412` | Inline text or attachment for one active shelf document (§6.5). |
| `DELETE` | `/api/projects/{project_id}/documents/{document_id}` | `projects:delete` | 204 | `backend/app/gateway/routers/project_documents.py:486` | Move one document to trash (204). Restore/purge are the Slice-D trash tier. |

#### Project Thread Files

源码：`routers/project_thread_files.py` — `projects:read` + `threads:read`。

| 方法 | 路径 | 鉴权 | 成功码 | 源码 | 摘要 |
|------|------|------|--------|------|------|
| `GET` | `/api/projects/{project_id}/thread-files` | `projects:read` + `threads:read` | 200 | `backend/app/gateway/routers/project_thread_files.py:105` | Aggregate member threads' files, paged by thread (§6.5/§7.4). |

#### Projects

源码：`routers/projects.py` — `projects:read/write/delete`；缺失/他人/已归档项目统一 **404**（fail closed）。

| 方法 | 路径 | 鉴权 | 成功码 | 源码 | 摘要 |
|------|------|------|--------|------|------|
| `POST` | `/api/projects` | `projects:write` | 201 | `backend/app/gateway/routers/projects.py:118` | — |
| `GET` | `/api/projects` | `projects:read` | 200 | `backend/app/gateway/routers/projects.py:126` | — |
| `GET` | `/api/projects/config` | `projects:read` | 200 | `backend/app/gateway/routers/projects.py:133` | Projects config for the UI (instructions byte cap, trash retention). |
| `GET` | `/api/projects/{project_id}` | `projects:read` | 200 | `backend/app/gateway/routers/projects.py:148` | — |
| `PATCH` | `/api/projects/{project_id}` | `projects:write` | 200 | `backend/app/gateway/routers/projects.py:157` | — |
| `POST` | `/api/projects/{project_id}/archive` | `projects:write` | 200 | `backend/app/gateway/routers/projects.py:167` | — |
| `POST` | `/api/projects/{project_id}/restore` | `projects:write` | 200 | `backend/app/gateway/routers/projects.py:176` | — |
| `DELETE` | `/api/projects/{project_id}` | `projects:delete` | 204 | `backend/app/gateway/routers/projects.py:185` | — |
| `GET` | `/api/projects/{project_id}/threads` | `projects:read` + `threads:read` | 200 | `backend/app/gateway/routers/projects.py:193` | — |

#### Stateless Runs

源码：`routers/runs.py` — `runs:create`/`runs:read`；可选 body `thread_id` 做 owner 检查。

| 方法 | 路径 | 鉴权 | 成功码 | 源码 | 摘要 |
|------|------|------|--------|------|------|
| `POST` | `/api/runs/stream` | `runs:create` | 200 | `backend/app/gateway/routers/runs.py:35` | Create a run and stream events via SSE. |
| `POST` | `/api/runs/wait` | `runs:create` | 200 | `backend/app/gateway/routers/runs.py:61` | Create a run and block until completion. |
| `GET` | `/api/runs/{run_id}/messages` | `runs:read` | 200 | `backend/app/gateway/routers/runs.py:110` | Return paginated messages for a run (cursor-based). |
| `GET` | `/api/runs/{run_id}/feedback` | `runs:read` | 200 | `backend/app/gateway/routers/runs.py:141` | Return all feedback for a run. |

#### Scheduled Tasks

源码：`routers/scheduled_tasks.py` — `threads:write`+`runs:create`；`_ensure_task_mutable` 用 **409**，触发派发失败 **502**（全仓少见 5xx 业务码）。

| 方法 | 路径 | 鉴权 | 成功码 | 源码 | 摘要 |
|------|------|------|--------|------|------|
| `POST` | `/api/scheduled-tasks/preview-cron` | `threads:read` | 200 | `backend/app/gateway/routers/scheduled_tasks.py:167` | Preview future cron instants without creating or dispatching a task. |
| `GET` | `/api/scheduled-tasks` | `threads:read` | 200 | `backend/app/gateway/routers/scheduled_tasks.py:178` | — |
| `POST` | `/api/scheduled-tasks` | `threads:write` + `runs:create` | 200 | `backend/app/gateway/routers/scheduled_tasks.py:189` | — |
| `GET` | `/api/scheduled-tasks/{task_id}` | `threads:read` | 200 | `backend/app/gateway/routers/scheduled_tasks.py:254` | — |
| `PATCH` | `/api/scheduled-tasks/{task_id}` | `threads:write` + `runs:create` | 200 | `backend/app/gateway/routers/scheduled_tasks.py:268` | — |
| `POST` | `/api/scheduled-tasks/{task_id}/pause` | `threads:write` | 200 | `backend/app/gateway/routers/scheduled_tasks.py:380` | — |
| `POST` | `/api/scheduled-tasks/{task_id}/resume` | `threads:write` + `runs:create` | 200 | `backend/app/gateway/routers/scheduled_tasks.py:412` | — |
| `POST` | `/api/scheduled-tasks/{task_id}/trigger` | `threads:write` + `runs:create` | 200 | `backend/app/gateway/routers/scheduled_tasks.py:441` | — |
| `DELETE` | `/api/scheduled-tasks/{task_id}` | `threads:write` | 200 | `backend/app/gateway/routers/scheduled_tasks.py:462` | — |
| `GET` | `/api/scheduled-tasks/{task_id}/runs` | `threads:read` | 200 | `backend/app/gateway/routers/scheduled_tasks.py:485` | — |
| `GET` | `/api/threads/{thread_id}/scheduled-tasks` | `threads:read` (owner) | 200 | `backend/app/gateway/routers/scheduled_tasks.py:505` | — |

#### Skills

源码：`routers/skills.py` — 管理端点经 `require_admin_user`（**403**）；安装/编辑被安全扫描阻断 **400**；上传超限 **413**。

| 方法 | 路径 | 鉴权 | 成功码 | 源码 | 摘要 |
|------|------|------|--------|------|------|
| `GET` | `/api/skills` | 已登录（无 `require_permission`） | 200 | `backend/app/gateway/routers/skills.py:277` | List All Skills |
| `POST` | `/api/skills/install` | admin（`require_admin_user`，非 admin **403**） | 200 | `backend/app/gateway/routers/skills.py:293` | Install Skill |
| `POST` | `/api/skills/install/upload` | admin（`require_admin_user`，非 admin **403**） | 200 | `backend/app/gateway/routers/skills.py:324` | Upload and Install Skill |
| `POST` | `/api/skills/reload` | admin（`require_admin_user`，非 admin **403**） | 200 | `backend/app/gateway/routers/skills.py:362` | Reload Skills |
| `GET` | `/api/skills/custom` | 已登录（无 `require_permission`） | 200 | `backend/app/gateway/routers/skills.py:379` | List Custom Skills |
| `GET` | `/api/skills/custom/{skill_name}/export-manifest` | admin（`require_admin_user`，非 admin **403**） | 200 | `backend/app/gateway/routers/skills.py:396` | Preview Custom Skill Export |
| `GET` | `/api/skills/custom/{skill_name}/export` | admin（`require_admin_user`，非 admin **403**） | 200 | `backend/app/gateway/routers/skills.py:416` | Download Custom Skill Archive |
| `GET` | `/api/skills/custom/{skill_name}` | admin（`require_admin_user`，非 admin **403**） | 200 | `backend/app/gateway/routers/skills.py:437` | Get Custom Skill Content |
| `PUT` | `/api/skills/custom/{skill_name}` | admin（`require_admin_user`，非 admin **403**） | 200 | `backend/app/gateway/routers/skills.py:459` | Edit Custom Skill |
| `DELETE` | `/api/skills/custom/{skill_name}` | admin（`require_admin_user`，非 admin **403**） | 200 | `backend/app/gateway/routers/skills.py:499` | Delete Custom Skill |
| `GET` | `/api/skills/custom/{skill_name}/history` | admin（`require_admin_user`，非 admin **403**） | 200 | `backend/app/gateway/routers/skills.py:529` | Get Custom Skill History |
| `POST` | `/api/skills/custom/{skill_name}/rollback` | admin（`require_admin_user`，非 admin **403**） | 200 | `backend/app/gateway/routers/skills.py:555` | Rollback Custom Skill |
| `GET` | `/api/skills/{skill_name}` | 已登录（无 `require_permission`） | 200 | `backend/app/gateway/routers/skills.py:609` | Get Skill Details |
| `PUT` | `/api/skills/{skill_name}` | admin（`require_admin_user`，非 admin **403**） | 200 | `backend/app/gateway/routers/skills.py:681` | Update Skill |

#### backend/app/gateway/routers/subagent_batches.py

源码：`backend/app/gateway/routers/subagent_batches.py`

| 方法 | 路径 | 鉴权 | 成功码 | 源码 | 摘要 |
|------|------|------|--------|------|------|
| `GET` | `/api/threads/{thread_id}/subagent-batches` | `threads:read` (owner) | 200 | `backend/app/gateway/routers/subagent_batches.py:41` | — |
| `GET` | `/api/threads/{thread_id}/subagent-batches/{batch_id}` | `threads:read` (owner) | 200 | `backend/app/gateway/routers/subagent_batches.py:48` | — |
| `GET` | `/api/threads/{thread_id}/subagent-batches/{batch_id}/items` | `threads:read` (owner) | 200 | `backend/app/gateway/routers/subagent_batches.py:55` | — |
| `POST` | `/api/threads/{thread_id}/subagent-batches/{batch_id}/pause` | `threads:write` (owner) | 200 | `backend/app/gateway/routers/subagent_batches.py:71` | — |
| `POST` | `/api/threads/{thread_id}/subagent-batches/{batch_id}/resume` | `threads:write` (owner) | 200 | `backend/app/gateway/routers/subagent_batches.py:78` | — |
| `POST` | `/api/threads/{thread_id}/subagent-batches/{batch_id}/cancel` | `threads:write` (owner) | 200 | `backend/app/gateway/routers/subagent_batches.py:85` | — |
| `POST` | `/api/threads/{thread_id}/subagent-batches/{batch_id}/items/{item_id}/retry` | `threads:write` (owner) | 200 | `backend/app/gateway/routers/subagent_batches.py:97` | — |
| `GET` | `/api/threads/{thread_id}/subagent-batches/{batch_id}/results.jsonl` | `threads:read` (owner) | 200 | `backend/app/gateway/routers/subagent_batches.py:107` | — |

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
| `GET` | `/api/suggestions/config` | 已登录（无 `require_permission`） | 200 | `backend/app/gateway/routers/suggestions.py:92` | Get Suggestions Configuration |
| `POST` | `/api/threads/{thread_id}/suggestions` | `threads:read` (owner) | 200 | `backend/app/gateway/routers/suggestions.py:105` | Generate Follow-up Questions |

#### Thread Runs / Messages

源码：`routers/thread_runs.py` — owner-scoped `runs:*`；GET stream 携带 `action` 时 **405**。

| 方法 | 路径 | 鉴权 | 成功码 | 源码 | 摘要 |
|------|------|------|--------|------|------|
| `POST` | `/api/threads/{thread_id}/runs/regenerate/prepare` | `runs:create` (owner, require_existing) | 200 | `backend/app/gateway/routers/thread_runs.py:903` | Prepare input and checkpoint for regenerating the latest assistant turn. |
| `POST` | `/api/threads/{thread_id}/runs/edit-regenerate/prepare` | `runs:create` (owner, require_existing) | 200 | `backend/app/gateway/routers/thread_runs.py:914` | Prepare input and checkpoint for editing then rerunning the latest user turn. |
| `POST` | `/api/threads/{thread_id}/runs` | `runs:create` (owner, require_existing) | 200 | `backend/app/gateway/routers/thread_runs.py:925` | Create a background run (returns immediately). |
| `POST` | `/api/threads/{thread_id}/runs/stream` | `runs:create` (owner, require_existing) | 200 | `backend/app/gateway/routers/thread_runs.py:943` | Create a run and stream events via SSE. |
| `POST` | `/api/threads/{thread_id}/runs/wait` | `runs:create` (owner, require_existing) | 200 | `backend/app/gateway/routers/thread_runs.py:998` | Create a run and block until it completes, returning the final state. |
| `GET` | `/api/threads/{thread_id}/runs` | `runs:read` (owner) | 200 | `backend/app/gateway/routers/thread_runs.py:1093` | List the newest runs for a thread (default 100, as a bare array). |
| `GET` | `/api/threads/{thread_id}/runs/page` | `runs:read` (owner) | 200 | `backend/app/gateway/routers/thread_runs.py:1103` | Return a newest-first keyset page of runs for a thread. |
| `GET` | `/api/threads/{thread_id}/runs/{run_id}` | `runs:read` (owner) | 200 | `backend/app/gateway/routers/thread_runs.py:1145` | Get details of a specific run. |
| `POST` | `/api/threads/{thread_id}/runs/{run_id}/cancel` | `runs:cancel` (owner, require_existing) | 200 | `backend/app/gateway/routers/thread_runs.py:1157` | Cancel a running or pending run. |
| `GET` | `/api/threads/{thread_id}/runs/{run_id}/join` | `runs:read` (owner) | 200 | `backend/app/gateway/routers/thread_runs.py:1217` | Join an existing run's SSE stream. |
| `POST` | `/api/threads/{thread_id}/runs/{run_id}/stream` | `runs:read` (owner) | 200 | `backend/app/gateway/routers/thread_runs.py:1333` | Join an existing run's SSE stream, optionally cancelling it first. |
| `GET` | `/api/threads/{thread_id}/runs/{run_id}/stream` | `runs:read` (owner) | 200 | `backend/app/gateway/routers/thread_runs.py:1351` | Join an existing run's observation-only SSE stream. |
| `GET` | `/api/threads/{thread_id}/messages` | `runs:read` (owner) | 200 | `backend/app/gateway/routers/thread_runs.py:1363` | Return displayable messages for a thread (across all runs), with feedback attached. |
| `GET` | `/api/threads/{thread_id}/messages/page` | `runs:read` (owner) | 200 | `backend/app/gateway/routers/thread_runs.py:1502` | Return a backward page ordered by the thread-global event sequence. |
| `GET` | `/api/threads/{thread_id}/runs/{run_id}/messages` | `runs:read` (owner) | 200 | `backend/app/gateway/routers/thread_runs.py:1530` | Return paginated messages for a specific run. |
| `GET` | `/api/threads/{thread_id}/runs/{run_id}/artifacts/archive` | `runs:read` (owner, require_existing) | 200 | `backend/app/gateway/routers/thread_runs.py:1642` | Return the verified terminal delivery count used by the archive. |
| `POST` | `/api/threads/{thread_id}/runs/{run_id}/artifacts/archive` | `runs:read` (owner, require_existing) | 200 | `backend/app/gateway/routers/thread_runs.py:1654` | Download the current contents of the files presented by one terminal run. |
| `GET` | `/api/threads/{thread_id}/runs/{run_id}/events` | `runs:read` (owner) | 200 | `backend/app/gateway/routers/thread_runs.py:1712` | Return the full event stream for a run (debug/audit). |
| `GET` | `/api/threads/{thread_id}/runs/{run_id}/workspace-changes` | `runs:read` (owner) | 200 | `backend/app/gateway/routers/thread_runs.py:1749` | Return workspace/output file changes recorded for one run. |
| `GET` | `/api/threads/{thread_id}/token-usage` | `threads:read` (owner) | 200 | `backend/app/gateway/routers/thread_runs.py:1769` | Thread-level token usage aggregation. |

#### Threads 生命周期与组织

源码：`routers/threads.py` — owner-scoped；冲突类操作（run 在跑）统一 **409**。

| 方法 | 路径 | 鉴权 | 成功码 | 源码 | 摘要 |
|------|------|------|--------|------|------|
| `DELETE` | `/api/threads/{thread_id}` | `threads:delete` (owner, require_existing) | 200 | `backend/app/gateway/routers/threads.py:708` | Delete local persisted filesystem data for a thread. |
| `POST` | `/api/threads` | `threads:write` | 200 | `backend/app/gateway/routers/threads.py:868` | Create a new thread. |
| `POST` | `/api/threads/{thread_id}/branches` | `threads:write` (owner, require_existing) | 200 | `backend/app/gateway/routers/threads.py:955` | Create a new main-thread branch from a completed assistant turn. |
| `POST` | `/api/threads/search` | `threads:read` | 200 | `backend/app/gateway/routers/threads.py:1175` | Search and list threads. |
| `PATCH` | `/api/threads/{thread_id}` | `threads:write` (owner, require_existing) | 200 | `backend/app/gateway/routers/threads.py:1218` | Merge metadata into a thread record. |
| `POST` | `/api/threads/{thread_id}/move` | `threads:write` (owner, require_existing) | 200 | `backend/app/gateway/routers/threads.py:1257` | Move a thread between projects (or out). Organizational only: history, |
| `GET` | `/api/threads/{thread_id}` | `threads:read` (owner) | 200 | `backend/app/gateway/routers/threads.py:1278` | Get thread info from metadata plus the graph's materialized state. |
| `GET` | `/api/threads/{thread_id}/goal` | `threads:read` (owner) | 200 | `backend/app/gateway/routers/threads.py:1331` | Return the active Claude-style goal for a thread, if any. |
| `PUT` | `/api/threads/{thread_id}/goal` | `threads:write` (owner) | 200 | `backend/app/gateway/routers/threads.py:1344` | Set or replace the active goal for a thread. |
| `DELETE` | `/api/threads/{thread_id}/goal` | `threads:write` (owner) | 200 | `backend/app/gateway/routers/threads.py:1370` | Clear the active goal for a thread. |
| `POST` | `/api/threads/{thread_id}/compact` | `threads:write` (owner, require_existing) | 200 | `backend/app/gateway/routers/threads.py:1401` | Manually summarize old thread context while preserving the visible history. |
| `GET` | `/api/threads/{thread_id}/state` | `threads:read` (owner) | 200 | `backend/app/gateway/routers/threads.py:1448` | Get the latest materialized graph state for a thread. |
| `POST` | `/api/threads/{thread_id}/state` | `threads:write` (owner, require_existing) | 200 | `backend/app/gateway/routers/threads.py:1497` | Replace selected thread-state fields through the materialized graph. |
| `POST` | `/api/threads/{thread_id}/history` | `threads:read` (owner) | 200 | `backend/app/gateway/routers/threads.py:1701` | Get materialized graph state history for a thread. |

#### Trash 回收站

源码：`routers/trash.py` — `projects:read/write/delete`；文件清理失败 **500**（行仍留在回收站）。

| 方法 | 路径 | 鉴权 | 成功码 | 源码 | 摘要 |
|------|------|------|--------|------|------|
| `GET` | `/api/trash/documents` | `projects:read` | 200 | `backend/app/gateway/routers/trash.py:139` | List the caller's trashed documents (most recently trashed first). |
| `POST` | `/api/trash/documents/{document_id}/restore` | `projects:write` | 200 | `backend/app/gateway/routers/trash.py:173` | Restore one trashed document into an active project (§8.2). |
| `POST` | `/api/trash/documents/{document_id}/purge` | `projects:delete` | 204 | `backend/app/gateway/routers/trash.py:210` | Permanently purge one trashed document: bytes first, then the row (§8.3). |
| `POST` | `/api/trash/purge` | `projects:delete` | 200 | `backend/app/gateway/routers/trash.py:228` | Empty the trash: purge every trashed document of the caller (§8.3). |

#### Uploads

源码：`routers/uploads.py` — owner-scoped `threads:*`；单文件/总量超限 **413**，不安全文件名静默跳过。

| 方法 | 路径 | 鉴权 | 成功码 | 源码 | 摘要 |
|------|------|------|--------|------|------|
| `POST` | `/api/threads/{thread_id}/uploads` | `threads:write` (owner) | 200 | `backend/app/gateway/routers/uploads.py:358` | Upload multiple files to a thread's uploads directory. |
| `GET` | `/api/threads/{thread_id}/uploads/limits` | `threads:read` (owner) | 200 | `backend/app/gateway/routers/uploads.py:433` | Return upload limits used by the gateway for this thread. |
| `GET` | `/api/threads/{thread_id}/uploads/list` | `threads:read` (owner) | 200 | `backend/app/gateway/routers/uploads.py:444` | List all files in a thread's uploads directory. |
| `DELETE` | `/api/threads/{thread_id}/uploads/{filename}` | `threads:delete` (owner, require_existing) | 200 | `backend/app/gateway/routers/uploads.py:456` | Delete a file from a thread's uploads directory. |

#### User Preferences

源码：`routers/user_preferences.py` — 仅 session 认证（PAT/内部调用 **403**）；账号切换 **409**。

| 方法 | 路径 | 鉴权 | 成功码 | 源码 | 摘要 |
|------|------|------|--------|------|------|
| `GET` | `/api/v1/auth/preferences` | 已登录（无 `require_permission`） | 200 | `backend/app/gateway/routers/user_preferences.py:42` | — |
| `PATCH` | `/api/v1/auth/preferences` | 已登录（无 `require_permission`） | 204 | `backend/app/gateway/routers/user_preferences.py:57` | — |

### 1.2 routers/ 之外的入口

| 方法 | 路径 | 鉴权 | 源码 | 说明 |
|------|------|------|------|------|
| `GET` | `/health` | 公开（`_PUBLIC_PATH_PREFIXES` 含 `/health`） | `app/gateway/app.py:981` | 纯 liveness，进程活着即 200 `{"status":"healthy"}` |
| `GET` | `/health/ready` | 公开 | `app/gateway/app.py:990`；实现 `app/gateway/health.py:240` | 并发探测 ORM engine + 生效 checkpointer/Store，单端点 deadline 3s / 单探针 2s；任一 `unreachable` → **503** `degraded`，否则 200 `ready` |
| `WS` | `/api/threads/{thread_id}/browser/stream` | `_authenticate_ws`（WebSocket 升级绕过 `AuthMiddleware`，见 `browser.py:117`） | `routers/browser.py:206` | 双向实时浏览器流；认证失败 `close(4401)`、跨源 `4403`、owner store 缺失 fail-closed `4404`、坏 `frame_format` `1008`（**不是 HTTP 状态码**，是 WS close code） |
| `—` | `/docs`、`/redoc`、`/openapi.json` | 公开 | `app.py:680` | `GATEWAY_ENABLE_DOCS=false` 时不注册（404） |

**条件挂载**：`POST /api/webhooks/github` 只在 `GITHUB_WEBHOOK_SECRET` 已设置，或显式 dev opt-in `DEER_FLOW_ALLOW_UNVERIFIED_GITHUB_WEBHOOKS=1` 时挂载；否则**整个路由不存在 → 404**（`app.py:970-976`）。

### 1.3 与旧版本文档的差异（本次补齐）

此前 digest 只列了约 60 条端点。本次逐条 AST 对照后**新增列出**（组）：

- `routers/models.py`（2）、`routers/assistants_compat.py`（4）、`routers/auth.py` 全部 13 条（含 PAT 3 条、`setup-status`、`providers`、`initialize`、`change-password`）
- `routers/memory.py` 10 条（此前只提了 4 条）、`routers/agents.py` 8 条（含 `GET /api/agents/check`、`user-profile` 两向）
- `routers/artifacts.py` 2 条、`routers/uploads.py` 4 条、`routers/trash.py` 4 条、`routers/project_documents.py` 6 条、`routers/project_thread_files.py` 1 条、`routers/projects.py` 9 条
- `routers/skills.py` 14 条（此前只提了 custom CRUD + export）、`routers/subagents.py` 4 条、`routers/subagent_batches.py` 8 条、`routers/mcp_tasks.py` 3 条
- `routers/threads.py` 14 条（含 `state` 双向、`history`、`move`、`search`）、`routers/thread_runs.py` 20 条
- `routers/runs.py` 4 条、`routers/feedback.py` 6 条、`routers/suggestions.py` 2 条、`routers/scheduled_tasks.py` 11 条
- `routers/channels.py` 2 条、`routers/channel_connections.py` 6 条、`routers/console.py` 3 条、`routers/features.py` 1 条、`routers/input_polish.py` 1 条、`routers/browser.py` 1 条 + 1 个 WS、`routers/github_webhooks.py` 1 条
- `PUT /api/mcp/config`（旧文档只写 PATCH）与 `routers/mcp.py` 的 7 条

---

## 2. 领域异常 → HTTP 映射（穷举，v2.1.0）

> 小节标题固定为「领域异常 → HTTP 映射」，供 `operations/integration/**` 以指针方式引用（`integration/01-overview.md`、`integration/05-lark-cli-managed-integration.md` 指向本文件）。

### 2.0 状态码总表

| 码 | 出现位置数（AST） | 一句话语义 |
|----|------------------|-----------|
| 400 | 42 个端点可达 | 请求形状合法但**语义非法**（非法 rating / 非法 URL / 配置校验失败 / 空文件 / 非文件路径） |
| 401 | 173 个端点可达（除 6 个公开 auth 路径 + webhook + `/health`） | 未认证；另有 GitHub HMAC 校验失败也映射到 401（见 §2.2） |
| 403 | 137 个端点可达 | 已认证但**无权限**：`require_permission` 权限不足、`require_admin_user` 非 admin、`agents_api` 关闭、PAT 越界、CSRF 失败 |
| 404 | 123 个端点可达 | 不存在**或不属于你**（fail closed，防枚举）；路由未挂载也 404 |
| 405 | 1 | 只用于 `GET /api/threads/{id}/runs/{rid}/stream?action=...` |
| 409 | 55 个端点可达 | **多义码**：run 在跑 / 幂等键冲突 / 资源已存在 / 状态机冲突 / 内容缺失（见 §2.6） |
| 412 | 1 | artifact 编辑的 `expected_sha256` 不匹配 |
| 413 | 8 | 请求体/文件/归档超出上限（上传、skill 包、artifact 编辑、归档 ZIP） |
| 415 | 5（同 1 个端点） | artifact 编辑的媒体类型不支持（`.skill`、符号链接、二进制、非 UTF-8、含 NUL） |
| 416 | 1 | `GET artifact` 的 `Range` 不可满足 |
| 422 | 149 个端点可达 | Pydantic/FastAPI 校验失败（含 `extra="forbid"` 的未知字段），以及各 router 手写的领域 422 |
| 429 | 5 个端点可达 | 限流/并发槽位：登录失败锁定、IM 连接码上限、artifact 归档并发、skill 导出槽位 |
| 500 | 65 个端点可达 | `except Exception → 500` 模板；以及未捕获的 `TypeError`/`AssertionError`/`RuntimeError` |
| 501 | 15 个端点可达 | memory 后端不支持该操作；browser 依赖缺失；**run multitask_strategy 不支持** |
| 502 | 4 | 上游/外部依赖失败：browser 导航、OIDC discovery、scheduled task 派发 |
| 503 | 26 个端点可达 | 依赖未就绪：SQL/仓储不可用、channel worker 未运行、LLM 调用失败、归档/导出超时与取消、checkpoint 模式切换中、`/health/ready` |
| 504 | 5（全在 integrations） | Lark CLI `TimeoutError` |
| 200/201/202/204/206 | — | 成功码；202 用于 cancel/stream 的「已接受」，206 用于 artifact `Range` |

**本版本未出现**：402、406、407、408、**410**（任务要求重点覆盖，但 v2.1.0 全仓无 410 —— 已删除/永久移除的资源一律用 **404 + fail closed**，见 §2.4）、411、418、428、431、451。

**`raise HTTPException` 语句计数（AST，routers/ 共 417 条；含字面量与 `status.HTTP_*` 两种写法）**：
400 × 79、404 × 96、409 × 69、500 × 68、422 × 39、401 × 15、413 × 9、503 × 9、403 × 8、415 × 5、504 × 5、502 × 4、429 × 2、405 × 1、412 × 1、501 × 1，另有 1 条 `status_code=exc.status_code`（归档按 `ArtifactArchiveError.status_code` 转发）与 5 条经由 helper **返回值**（`_not_found()` / `_unsupported_501()` / `_map_memory_*()` / `export_http_error()` / `_checkpoint_mode_http_error()`）间接产生，故 79+96+69+68+39+15+9+9+8+5+5+4+2+1+1+1（= 411）+ 1 + 5 = **417**。

同范围内还有 **77 条非 `HTTPException` 的 `raise`**（裸 `raise` 透明转发、`NotImplementedError`、`ValueError`、`Unsafe*Error`、`ArtifactArchiveError`、`_SkillArchiveUploadTooLargeError` 等），其中被 router 捕获后转成 §2 中某个码的已逐条列出，未被捕获的按 **500** 计（见 §2.13(c)）。

---

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
| 上传未给文件 | `No files provided` | `routers/uploads.py:376` |
| 上传目录初始化 `ValueError` | `str(exc)` | `routers/uploads.py:393` |
| uploads list/delete 的 `ValueError` | `str(exc)` | `routers/uploads.py:449`、`:465` |
| delete 路径穿越 | `Invalid path`（`PathTraversalError`） | `routers/uploads.py:463` |
| artifact 路径不是普通文件 | `Path is not a file: <path>` | `routers/artifacts.py:86` |
| 项目文档文件名非法（空/含分隔符/超 255 UTF-8 字节） | `str(exc)` | `routers/project_documents.py:186`、`:294` |
| 项目文档内容为空 | `Empty file` | `routers/project_documents.py:200`、`:312` |
| skill 安装文件名不以 `.skill` 结尾 | `Skill archive filename must end with .skill` | `routers/skills.py:340` |
| skill multipart 解析失败（非超限） | `MultiPartException.message` | `routers/skills.py:348` |
| skill 编辑/回滚被安全扫描阻断 | `Security scan blocked the edit: ...` / `Rollback blocked by security scanner: ...` | `routers/skills.py:469`、`:585` |
| skill 内容/名称 `ValueError` | `str(e)` | `routers/skills.py:300`、`:492`、`:522`、`:597` |
| skill 无历史 / 选中历史项无 `prev_content` / `history_index` 越界 | `Custom skill '<n>' has no history`、`Selected history entry has no previous content...`、`history_index is out of range` | `routers/skills.py:563`、`:567`、`:593` |
| memory fact 校验失败（confidence / agent_name / 空内容） | `Invalid confidence value...`、`An agent name is required...`、`Memory fact content cannot be empty.` | `routers/memory.py:113-124`（`_map_memory_fact_value_error`），调用点 `:325`、`:383` |
| thread search 元数据过滤器非法 | `str(exc)`（`InvalidMetadataFilterError`） | `routers/threads.py:1198` |
| Lark 流程 `ValueError` | `str(e)` | `routers/integrations.py:279`、`:299`、`:326`、`:349`、`:374`、`:399` |
| GitHub webhook 缺 `X-GitHub-Event` / JSON 非法 | `Missing X-GitHub-Event header`、`Invalid JSON body` | `routers/github_webhooks.py:255`、`:267` |
| auth：邮箱已注册 / 改密码各类拒绝 | `Email already registered`、`Current password is incorrect`、`OAuth users cannot change password`、`Password changes are not available when DEER_FLOW_AUTH_DISABLED=1.` | `routers/auth.py:475`、`:520`、`:529`、`:532`、`:540`、`:810` |
| auth：PAT 名称非法 | `str(exc)` | `routers/auth.py:667` |
| auth：OIDC provider 非法 / 缺 code/state | `Invalid provider ID`、`Unknown SSO provider: x`、`Missing code or state parameter` | `routers/auth.py:929`、`:933`、`:1017`、`:1021`、`:1024` |
| run 准入：模型不在 allowlist | `Model 'x' is not in the configured model allowlist` | `app/gateway/services.py:1522`（`start_run`） |
| run 准入：`input.messages` 不是列表 | `input.messages must be a list` | `app/gateway/services.py:1493`、`:1501` |
| checkpoint 配置非法 / 线程不匹配 / configurable 非对象 | `checkpoint must be an object`、`checkpoint thread_id does not match request thread_id`、`request config configurable must be an object` | `app/gateway/services.py:1353`、`:1356`、`:1389`（`apply_checkpoint_to_run_config`） |
| run 输入归一化失败 | 见 `normalize_input` | `app/gateway/services.py:480` |

> **400 vs 422 的边界**：Pydantic 模型/路径参数/query 的**形状**问题一律由 FastAPI 自动给 **422**（§2.11）；router 里手写的 400 用于「形状对但语义错」。MCP 是唯一把「配置内容非法」也写成 400 的领域（因为它同时被 Pydantic 校验与 runtime `validate_raw_extensions_config` 校验）。

---

### 2.2 401 Unauthorized

| 场景 | detail 摘要 | 源码锚点 |
|------|------------|---------|
| 中间件：非公开路径无 session cookie | `Authentication required`（code `NOT_AUTHENTICATED`） | `app/gateway/auth_middleware.py:169` |
| 中间件：Bearer PAT 无效 | 直接回传 `exc.status_code`（401 `token_expired` / `token_invalid` / `user_not_found`） | `app/gateway/auth_middleware.py:130-134` |
| `require_auth` 装饰器 | `Authentication required` | `app/gateway/authz.py:588` |
| `require_permission` 装饰器 | `Authentication required` | `app/gateway/authz.py:666` |
| `AuthContext.require_user()` | `Authentication required` | `app/gateway/authz.py:118` |
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
| checkpoint 不存在 | `Checkpoint not found`、`Checkpoint <id> not found` | `routers/threads.py:1504`、`:1518`；`app/gateway/services.py:1385` |
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
| `Thread has a run in flight. Save after the run finishes.`（artifact 编辑） | `routers/artifacts.py:556`（`ConflictError`） |
| `Thread has work in flight. Delete it after the work finishes.` | `routers/threads.py:725` |
| `Thread has work in flight. Branch it after the work finishes.` | `routers/threads.py:966` |
| `Thread has a run in flight. Set the goal after the run finishes.` | `routers/threads.py:1359` |
| `Thread has a run in flight. Clear the goal after the run finishes.` | `routers/threads.py:1377` |
| `Thread has a run in flight. Compact after the run finishes.` | `routers/threads.py:1428` |
| `Context compaction is disabled.`（`ContextCompactionDisabled`） | `routers/threads.py:1432` |
| `Thread has a run in flight. Update state after the run finishes.` | `routers/threads.py:1562` |
| `Run <id> is not active on this worker and cannot be streamed` | `routers/thread_runs.py:970`、`:1225` |
| `Artifacts are currently being modified; try again shortly` | `routers/thread_runs.py:1684` |
| `Scheduled task is currently running; retry after the active execution finishes` | `routers/scheduled_tasks.py:389` |
| `Scheduled task is already launching or running; ...` | `routers/scheduled_tasks.py:402`、`:476` |
| `Scheduled task has an active <queued/launching/running> occurrence; ...`（`queued` 追加「可 pause 取消」） | `_ensure_task_mutable` `scheduled_tasks.py:90-104`；`_active_occurrence_conflict_detail` `:40-44`；调用点 `:371`、`:429` |

**(b) 幂等键冲突 → 409**

| detail | 锚点 |
|--------|------|
| `Idempotency-Key already used with a different request`（同键但 `input`/`assistant_id`/`conversation_references` 不同） | `app/gateway/services.py:1763-1766` |
| `ConflictError` 透传（`multitask_strategy` 拒绝/回滚时的活动 run 冲突） | `app/gateway/services.py:1785` |

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
| `Run <id> is not cancellable (status: <s>)` / `... not active on this worker and cannot be cancelled` | `routers/thread_runs.py:1212` + `_cancel_conflict_detail` `:305-308` |
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
| 上传文件数超过 `uploads.max_files`（默认 10） | `Too many files: maximum is <n>` | `routers/uploads.py:380` |
| 单文件超过 `uploads.max_file_size`（默认 50 MiB） | `File too large: <name>` | `app/gateway/upload_ingestion.py:201` |
| 单请求总量超过 `uploads.max_total_size`（默认 100 MiB） | `Total upload size too large` | `app/gateway/upload_ingestion.py:203` |
| 项目 shelf 上传/晋升超限 | `File too large: <name>` | `routers/project_documents.py:194`、`:306` |
| artifact 编辑超过 `MAX_EDITABLE_ARTIFACT_BYTES`（stat 与实读两处） | `Artifact is too large to edit` | `routers/artifacts.py:88`、`:92`、`:109` |
| `.skill` 归档成员预览过大 | `Skill archive member is too large to preview` | `routers/artifacts.py:217`、`:225` |
| skill 包上传超过 100 MiB（+ 1 MiB multipart framing） | `Skill archive exceeds the 100 MiB upload limit` | `routers/skills.py:346`（`_SkillArchiveUploadTooLargeError`），常量 `:49-50`，message `:204-205` |
| run 产出归档 ZIP 超限（>50 文件 / 单文件 50MiB / 总量 100MiB） | `_too_large(...)` | `app/gateway/artifact_archive.py:60`（默认 409 之外显式传 413） |
| skill 导出超资源上限 | `skill_export_limit_exceeded` | `packages/harness/deerflow/skills/export.py:90` → `routers/skills.py:403/428` 经 `export_http_error`（`app/gateway/skill_export.py:184`） |

> **没有全局 body-size 中间件**：413 全部由上述各处理器显式抛出。`02-upload-security.md` 记录的文件名/路径/符号链接防御是**磁盘层**，不产生 413。

---

### 2.9 415 Unsupported Media Type

只出现在 `PUT /api/threads/{thread_id}/artifacts/{path:path}`（`routers/artifacts.py:486`）：

| 场景 | detail | 锚点 |
|------|--------|------|
| 目标是 `.skill` 归档 | `Skill archives cannot be edited in the artifacts panel` | `:74`（`_normalize_editable_artifact_path`） |
| 目标是符号链接 | `Symlinked artifacts cannot be edited` | `:84`（`_load_editable_artifact`） |
| 内容含 NUL 字节 | `Binary artifacts cannot be edited` | `:94` |
| 内容不是合法 UTF-8 | `Only UTF-8 text artifacts can be edited` | `:98` |
| 提交的新内容含 NUL | `Binary content cannot be saved as an artifact` | `:111`（`_encode_artifact_update`） |

---

### 2.10 416 Range Not Satisfiable

| 场景 | detail + 头 | 锚点 |
|------|------------|------|
| `GET artifact` 的 `Range` 头非法/多段/越界/空文件/suffix ≤ 0 | `Requested range is not satisfiable`，附 `Accept-Ranges: bytes` 与 `Content-Range: bytes */<size>` | `routers/artifacts.py:176-181`（`unsatisfied()`），触发点 `:184`、`:187`、`:193`、`:196`、`:203` |

合法单段范围返回 **206** + `Content-Range`。

---

### 2.11 422 Unprocessable Content

两类来源：

**(a) FastAPI 自动（`RequestValidationError`）** — 覆盖 149 个带校验参数/请求体的端点。典型：

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
| agent `model` 不是配置的 profile | `Unknown model '<m>'. Use a model name defined under `models:` ...` | `routers/agents.py:143`（`_validate_model_exists`） |
| managed subagent 名称非法 / Pydantic 校验失败 | `str(exc)` / `exc.errors()` | `routers/subagents.py:86`、`:88`、`:176`、`:211` |
| managed subagent `model` 非法 | `Unknown model '<m>'. Use 'inherit' or a configured model name.` | `routers/subagents.py:81` |
| scheduled task：`assistant_id` 为空/非法/未知 | `assistant_id must not be empty`、`Invalid assistant_id ...`、`Unknown assistant_id 'x'` | `routers/scheduled_tasks.py:72`、`:77`、`:84`、`:86`、`:89`、`:91`、`:302`、`:344` |
| scheduled task：不支持的 `context_mode` / `schedule_type`、缺 cron、once 必须未来 | `Unsupported context_mode`、`Unsupported schedule_type`、`cron schedule requires schedule_spec.cron`、`once schedule must be in the future`、`once schedule must be at least <n> seconds in the future` | `routers/scheduled_tasks.py:197`、`:200`、`:204`、`:212`、`:223`、`:226`、`:228`、`:287`、`:292`、`:313` |
| run 历史游标两个字段未成对出现 | `before_created_at and before_run_id must be provided together` | `routers/thread_runs.py:1116` |
| messages/page 不支持 `after_seq` | `after_seq is not supported by this backward-only endpoint` | `routers/thread_runs.py:1510` |
| thread goal 参数非法（如 `max_continuations > 8`） | `str(exc)` | `routers/threads.py:1357` |
| thread state 未知字段 | `Unknown thread-state field(s): [...]` | `routers/threads.py:1539` |
| subagent batch item 状态过滤值非法 | `Unknown batch item status` | `routers/subagent_batches.py:64` |
| skill 归档上传：非 multipart / 缺 `archive` 文件 | `Expected a multipart form upload`、`Multipart field 'archive' must contain a file` | `routers/skills.py:228`、`:336` |
| skill 导出：非法 skill 名 / 平台不支持 / 非法 revision / 目录结构不支持 | `skill_export_unsupported` | `packages/harness/deerflow/skills/export.py:370`、`:376`、`:441`、`:447` → `routers/skills.py:403/428` |

---

### 2.12 429 Too Many Requests

| 场景 | detail 摘要 | 锚点 |
|------|------------|------|
| 同一 IP 登录失败超过 `local_auth.max_login_attempts`，锁定未过期 | `Too many login attempts. Try again later.` | `routers/auth.py:322-325`（`_check_rate_limit`），由 `login_local` 调用 |
| 单个 owner 每 provider 的 pending IM 连接码超过 `_MAX_PENDING_CONNECT_CODES_PER_PROVIDER = 5` | `Too many pending channel connection codes. Wait for existing codes to expire or use one of them.` | `routers/channel_connections.py:343-348`（常量 `:28`） |
| run 产出归档 ZIP 并发构建槽位（`Semaphore(4)`）已满 | `Too many artifact archives are being created; try again shortly` | `routers/thread_runs.py:1579` → `App/gateway/artifact_archive.py`（`ArtifactArchiveError(..., 429)`） |
| skill 导出槽位（每进程全用户 `BoundedSemaphore(2)`）已满 | `skill_export_busy`：`Both export slots in this Gateway process are in use across all users. ...` | `app/gateway/skill_export.py:69-71` |

---

### 2.13 500 Internal Server Error

三类来源：

**(a) `except Exception → 500` 模板**（每个 router 都有，detail 通常是 `Failed to ...: {str(e)}` 或固定的安全文案）。主要锚点：

| 文件 | 锚点 |
|------|------|
| `routers/agents.py` | `:236`、`:305`、`:364`、`:491`、`:528`、`:556`、`:586` |
| `routers/artifacts.py` | `:561`（固定文案 `Failed to update artifact`） |
| `routers/integrations.py` | `:266`、`:284`、`:304`、`:331`、`:354`、`:379`、`:404` |
| `routers/mcp.py` | `:1495`、`:1518`、`:1544`、`:1566`、`:1588` |
| `routers/memory.py` | `:300`、`:330`、`:357`、`:390`、`:430`（`OSError`） |
| `routers/project_documents.py` | `:385`、`:388`、`:395` |
| `routers/skills.py` | `:266`、`:282`、`:367`、`:392`、`:407`、`:432`、`:455`、`:495`、`:525`、`:549`、`:600`、`:623`、`:751`、`:760` |
| `routers/thread_runs.py` | `:1686`（`ArtifactArchiveError.status_code`，多为 409/413/503 而非 500） |
| `routers/threads.py` | `:923`、`:927`、`:943`、`:1236`、`:1302`、`:1338`、`:1364`、`:1382`、`:1441`、`:1462`、`:1516`、`:1567`、`:1915`、`:625`、`:696`、`:1107`、`:1123`、`:233`、`:300`、`:690`、`:1514` |
| `routers/trash.py` | `:221`、`:243`（`OSError`，事务回滚保留回收站行） |
| `routers/uploads.py` | `:412`、`:468` |

**(b) 业务性 500（不是模板）**

| 场景 | detail | 锚点 |
|------|--------|------|
| 存储的 memory 数据损坏（`MemoryCorruptionError`） | `Stored memory data is corrupted.` | `routers/memory.py:131`（`_map_memory_manager_error`） |
| 手动压缩失败（`ContextCompactionFailed`） | `Failed to compact thread context.` | `routers/threads.py:1434` |
| checkpoint 校验失败 | `Failed to validate checkpoint` | `app/gateway/services.py:1383` |
| skill 导出内部失败 | `{"code":"skill_export_failed", ...}` | `routers/skills.py:407`、`:432`；`export.py:412`、`:471` |

**(c) 未捕获的非 HTTP 异常 → Starlette/TraceMiddleware 渲染 500**

| 异常 | detail | 锚点 |
|------|--------|------|
| `TypeError`（AuthorizationProvider 返回类型违约） | `AuthorizationProvider.filter_resources must return list[str]` | `routers/models.py:108` |
| `TypeError` | `AuthorizationProvider.authorize must return AuthzDecision` | `routers/models.py:186` |
| `AssertionError`（未处理的 artifact 响应类型） | `Unhandled artifact response kind: ...` | `routers/artifacts.py:476` |
| `RuntimeError`（sandbox lease 未产出 sandbox） | `Failed to acquire sandbox for artifact update` | `routers/artifacts.py:538` |

> `TraceMiddleware` 对未处理异常会先自行发送一个 CORS-opaque 的 plain 500 再 re-raise（见 harness `trace_context` 说明）。

---

### 2.14 501 Not Implemented

| 场景 | detail 摘要 | 锚点 |
|------|------------|------|
| memory 后端未实现该 tier-3/tier-2 操作（`NotImplementedError`） | `Operation '<label>' not supported by memory backend '<cls>'.` | `routers/memory.py:133-138`（`_unsupported_501`）；label = `clear memory`(`:296`)、`create fact`(`:324`)、`delete fact`(`:351`)、`update fact`(`:382`)、`import memory`(`:426`)、`reload memory`(`:270` 经 `_get_memory_or_501` `:152-165`) |
| browser 自动化依赖缺失（`ImportError`） | `Browser automation is not available` | `routers/browser.py:92-93` |
| **run 的 `multitask_strategy` 不受支持** | `Multitask strategy '<s>' is not yet supported. Supported strategies: ...` | `packages/harness/deerflow/runtime/runs/manager.py:1605`（`UnsupportedStrategyError`）→ `app/gateway/services.py:1787` 转 501。影响 `POST /api/threads/{id}/runs`、`/runs/stream`、`/runs/wait` 与 `POST /api/runs/*` |

---

### 2.15 502 Bad Gateway

| 场景 | detail 摘要 | 锚点 |
|------|------------|------|
| browser 导航底层失败（任何其它异常） | `Browser navigation failed` | `routers/browser.py:105`、`:112` |
| OIDC discovery / provider 连接失败（登录发起） | `Failed to connect to SSO provider` | `routers/auth.py:957`、`:959` |
| OIDC discovery 失败（回调，改为 302 重定向到错误页） | `sso_failed` | `routers/auth.py:1047-1064`（`_build_error_redirect`） |
| scheduled task 手动触发派发失败 | `result['error'] or 'Scheduled task trigger failed'` | `routers/scheduled_tasks.py:456` |

---

### 2.16 503 Service Unavailable

| 场景 | detail 摘要 | 锚点 |
|------|------------|------|
| Console 需要 SQL backend（`database.backend: memory`） | `Console requires a SQL database backend; set database.backend to sqlite or postgres in config.yaml.` | `routers/console.py:121-127`（`_session_factory_or_503`），3 个 console 端点调用 |
| channel connection 持久化不可用 | `Channel connection persistence is not available` | `routers/channel_connections.py:195-203`；在 `GET /providers`（`:522-524`）与 `DELETE /{provider}/runtime-config`（`:583-586`）里被**刻意吞掉降级**，不报 503 |
| IM channel service 未运行 | `Channel service is not running` | `routers/channels.py:50` |
| GitHub webhook 未配置签名校验 | `Webhook signature verification not configured. Set ... or ...=1 for unverified dev mode.` | `routers/github_webhooks.py:235` |
| GitHub webhook fan-out 运行时失败（保留为 failed 供人工重投） | `fan-out failed for delivery <id>: ...` | `routers/github_webhooks.py:359-365` |
| input polish LLM 调用失败 | `Failed to polish input` | `routers/input_polish.py:99`、`:102` |
| MCP task 取消时 worker 未运行 | `MCP task cancellation worker is not running` | `routers/mcp_tasks.py:118` |
| subagent batch worker 未运行 | `Subagent batch worker is not running` | `routers/subagent_batches.py:87` |
| 用户偏好持久化不可用 | `Preference persistence is unavailable` | `routers/user_preferences.py:33`（`_repository`） |
| 归档 ZIP 构建超时（60s deadline） | `Artifact archive creation timed out` | `app/gateway/artifact_archive.py:65` |
| skill 导出被取消 / 超时 / 锁超时 | `skill_export_cancelled`、`skill_export_timeout` | `packages/harness/deerflow/skills/export.py:84`、`:86`、`:408` |
| checkpoint 进程正在切换存储模式（非 `CheckpointModeMismatchError`） | `str(exc)` | `routers/threads.py:107-108`（`_checkpoint_mode_http_error`） |
| `/health/ready` 任一后端 `unreachable` | `status: degraded` | `app/gateway/health.py:240-266` |

---

### 2.17 504 Gateway Timeout

只在 `routers/integrations.py`（Lark CLI 的子进程 `TimeoutError`）：

| 端点 | 锚点 |
|------|------|
| `POST /api/integrations/lark/config/start` | `:301` |
| `POST /api/integrations/lark/config/complete` | `:328` |
| `POST /api/integrations/lark/config/credentials` | `:351` |
| `POST /api/integrations/lark/auth/start` | `:376` |
| `POST /api/integrations/lark/auth/complete` | `:401` |

---

### 2.18 成功码的非常规用法

| 码 | 场景 | 锚点 |
|----|------|------|
| 201 | create agent / project / shelf document / managed subagent / register / PAT / initialize admin | `routers/agents.py:311`、`routers/projects.py:116`、`routers/project_documents.py:164`、`:267`、`routers/subagents.py:170`、`routers/auth.py:458`、`:652`、`:789` |
| **200 on dedup** | shelf 上传/晋升命中内容去重时把 201 改写成 200 | `routers/project_documents.py:214-217`、`:328-331` |
| 202 | run 取消/流式已被接受（非 owner worker 记为 `requested`，或 store-only 无法订阅） | `routers/thread_runs.py:1206`、`:1287`、`:1296`、`:1310` |
| 204 | delete agent / disconnect connection / delete document / delete project / delete subagent / purge / cancel with `wait=true` / skill 导出客户端断连 | `routers/agents.py:561`、`routers/channel_connections.py:554`、`routers/project_documents.py:484`、`routers/projects.py:183`、`routers/subagents.py:231`、`routers/trash.py:208`、`routers/thread_runs.py:1194`、`:1205`、`:1302`、`:1310`、`routers/skills.py:401`、`:426` |
| 206 | artifact `Range` 命中 | `routers/artifacts.py`（`_slice_byte_range` 返回 206） |

---

### 2.19 路由级状态码签名（供 integration 文档引用的权威行）

把「一个路由组能返回哪些码」压成一行，`operations/integration/**` 只引用这里，不重复穷举：

| 路由组 | 完整状态码签名 | 关键语义 | 权威锚点 |
|--------|---------------|---------|---------|
| `POST /api/integrations/lark/install`、`/config/{start,complete,credentials}`、`/auth/{start,complete}` | **403 / 404 / 400 / 409 / 504 / 500**（另加中间件 401、参数校验 422；同步成功 200） | 403 = 非 admin（`require_admin_user`，detail = `Admin privileges required to install integrations.`）；404 = Lark 未安装 / 流程句柄缺失（`FileNotFoundError`）；400 = `ValueError`（参数或流程状态非法）；409 = `LarkFlowSupersededError`（流程被更新的 generation 取代）；504 = CLI `TimeoutError`；500 = 其余异常 | 403 `deps.py:894-903`；404/400/409/504/500 `routers/integrations.py:277`/`:279`/`:324`/`:301`/`:284`（install 同构 `:277`/`:279`/—/—/`:284`）；逐条见 §2.1/§2.4/§2.6/§2.13/§2.16/§2.17 |
| `GET /api/integrations/lark/status` | **500**（+401）；**不返回 403** | 只读，任何已认证用户可读；非 admin **不是 403**，而是把 host 文件系统路径**脱敏**（`include_host_paths=await _is_admin_user(request)`，`_is_admin_user` fail-closed：任何异常都当非 admin）；内部失败 500 | `routers/integrations.py:260-266`；脱敏开关 `:41-50`、`:263`；host-path 注释 `:185` |
| `POST /api/webhooks/github` | **400 / 401 / 422 / 503 / 200**；未配置 secret 时**路由不挂载 → 404** | 401 = HMAC 签名缺失/不匹配（`X-Hub-Signature-256`）；400 = 缺 `X-GitHub-Event` 或 JSON 非法；**200 = 已识别事件、未知事件（`handled=false`）、以及缺少 channel service 的无操作派发**；503 = 未配置签名校验（`is_route_enabled()` 的运行时兜底，正常不可达），或 fan-out 运行时失败（**故意保留为 failed**，供人工/API 重投 —— GitHub 不会自动重试任何失败投递，含 5xx） | 401 `routers/github_webhooks.py:252`；400 `:255`、`:267`；503 `:235`、`:359-368`；200 汇总 `:380-386`；条件挂载 `app.py:970-976` |

> `POST /api/webhooks/github` **没有 delivery-id 去重存储**：同一 `X-GitHub-Delivery` 重放会被**再次 fan-out** 并同样返回 200（不是幂等命中，也不会 409）。「200」保证的是 GitHub 把这次投递标为成功，而不是「只执行一次」。

> `POST /api/webhooks/github` 也**不走 `AuthMiddleware`/`CSRFMiddleware`**（`/api/webhooks/` 在公开前缀里），所以它的 401 只来自 HMAC，不是会话认证。

---

## 3. 路由之前的四层中间件（先于 §2 的 router 码）

`create_app()` 里 `add_middleware()` 的**添加顺序**是 `AuthMiddleware`(`app.py:771`) → `CSRFMiddleware`(`:816`) → `CORSMiddleware`(`:827`，仅当 `GATEWAY_CORS_ORIGINS` 配置了才加) → `TraceMiddleware`(`:840`)。Starlette 里后添加的更靠外，所以**实际执行顺序（外 → 内）是**：

```
TraceMiddleware → CORSMiddleware(可选) → CSRFMiddleware → AuthMiddleware → router
```

关键推论：**CSRF 在 Auth 之前**，所以一个没有 session、也没有 `X-CSRF-Token` 的 `POST` 会先撞到 **403 `CSRF token missing`**，而不是 401。

1. **`TraceMiddleware`**（`app/gateway/trace_middleware.py`）— 注入 `X-Trace-Id`；未处理异常时自行发送 CORS-opaque plain **500** 再 re-raise。
2. **`CORSMiddleware`**（可选）— 仅在 `GATEWAY_CORS_ORIGINS` 非空时挂载；`expose_headers` 含 `CORS_EXPOSED_HEADERS`（含 `Content-Location`）。
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
   - 公开路径前缀：`/health`、`/docs`、`/redoc`、`/openapi.json`、`/api/v1/auth/oauth/`、`/api/v1/auth/callback/`、`/api/webhooks/`；精确公开：`/api/v1/auth/{login/local,register,logout,setup-status,initialize,providers}`（`auth_middleware.py:34-57`）

越过这四层之后才是 `@require_auth` / `@require_permission` / 路由体内的 404/409/…。

---

## 4. 端点 → 可达状态码矩阵

**读法**：`/` 分隔 = 该端点**可达**的状态码；口径 = 本端点自身 raise + 同模块被调 helper 的传递闭包 + `require_permission`(401/403，`owner_check` 再加 404) + `require_admin_user`(403) + 有校验参数时的 422 + 未捕获非 HTTP 异常的 500。`401` 由 §3 的 `AuthMiddleware` 对**所有非公开路由**补上。因此这是**上界**（宁多勿漏）。成功码见 §1.1 与 §2.18。此外**所有状态变更方法**（`POST/PUT/DELETE/PATCH`）都可能先被 `CSRFMiddleware` 拦成 **403**（豁免清单见 §3），表中未逐行重复。

| 端点 | 可达码 | 源码锚点 |
|------|--------|---------|
| `GET /api/agents` | 401/403/500 | `backend/app/gateway/routers/agents.py:215` |
| `GET /api/agents/check` | 401/403/422 | `backend/app/gateway/routers/agents.py:244` |
| `GET /api/agents/{name}` | 401/403/404/422/500 | `backend/app/gateway/routers/agents.py:277` |
| `POST /api/agents` | 401/403/409/422/500 | `backend/app/gateway/routers/agents.py:315` |
| `PUT /api/agents/{name}` | 401/403/404/409/422/500 | `backend/app/gateway/routers/agents.py:373` |
| `GET /api/user-profile` | 401/403/500 | `backend/app/gateway/routers/agents.py:512` |
| `PUT /api/user-profile` | 401/403/422/500 | `backend/app/gateway/routers/agents.py:537` |
| `DELETE /api/agents/{name}` | 401/403/404/409/422/500 | `backend/app/gateway/routers/agents.py:565` |
| `GET /api/threads/{thread_id}/artifacts/{path:path}` | 401/403/404/416/422/500 | `backend/app/gateway/routers/artifacts.py:339` |
| `PUT /api/threads/{thread_id}/artifacts/{path:path}` | 401/403/404/409/413/415/422/500 | `backend/app/gateway/routers/artifacts.py:486` |
| `GET /api/assistants/{assistant_id}` | 401/404/422 | `backend/app/gateway/routers/assistants_compat.py:110` |
| `GET /api/assistants/{assistant_id}/graph` | 401/404/422 | `backend/app/gateway/routers/assistants_compat.py:119` |
| `GET /api/assistants/{assistant_id}/schemas` | 401/404/422 | `backend/app/gateway/routers/assistants_compat.py:137` |
| `POST /api/assistants/search` | 401/422 | `backend/app/gateway/routers/assistants_compat.py:90` |
| `POST /api/v1/auth/login/local` | 401/422/429 | `backend/app/gateway/routers/auth.py:403` |
| `POST /api/v1/auth/register` | 400/403/422 | `backend/app/gateway/routers/auth.py:458` |
| `POST /api/v1/auth/logout` | — | `backend/app/gateway/routers/auth.py:487` |
| `POST /api/v1/auth/change-password` | 400/401/403/422 | `backend/app/gateway/routers/auth.py:498` |
| `GET /api/v1/auth/me` | 401 | `backend/app/gateway/routers/auth.py:562` |
| `POST /api/v1/auth/pats` | 400/401/422 | `backend/app/gateway/routers/auth.py:652` |
| `GET /api/v1/auth/pats` | 401 | `backend/app/gateway/routers/auth.py:689` |
| `DELETE /api/v1/auth/pats/{pat_id}` | 401/404/422 | `backend/app/gateway/routers/auth.py:699` |
| `GET /api/v1/auth/setup-status` | — | `backend/app/gateway/routers/auth.py:722` |
| `POST /api/v1/auth/initialize` | 400/409/422 | `backend/app/gateway/routers/auth.py:789` |
| `GET /api/v1/auth/providers` | — | `backend/app/gateway/routers/auth.py:881` |
| `GET /api/v1/auth/oauth/{provider}` | 400/404/422/502 | `backend/app/gateway/routers/auth.py:908` |
| `GET /api/v1/auth/callback/{provider}` | 400/403/404/422/502 | `backend/app/gateway/routers/auth.py:987` |
| `POST /api/threads/{thread_id}/browser/navigate` | 400/401/403/404/422/501/502 | `backend/app/gateway/routers/browser.py:81` |
| `GET /api/channels/providers` | 401/404/503 | `backend/app/gateway/routers/channel_connections.py:515` |
| `GET /api/channels/connections` | 401/503 | `backend/app/gateway/routers/channel_connections.py:545` |
| `DELETE /api/channels/connections/{connection_id}` | 400/401/404/422/503 | `backend/app/gateway/routers/channel_connections.py:555` |
| `DELETE /api/channels/{provider}/runtime-config` | 400/401/403/404/422/503 | `backend/app/gateway/routers/channel_connections.py:571` |
| `POST /api/channels/{provider}/connect` | 400/401/404/422/429/503 | `backend/app/gateway/routers/channel_connections.py:618` |
| `POST /api/channels/{provider}/runtime-config` | 400/401/403/404/422 | `backend/app/gateway/routers/channel_connections.py:653` |
| `GET /api/channels/` | 401 | `backend/app/gateway/routers/channels.py:30` |
| `POST /api/channels/{name}/restart` | 401/403/422/503 | `backend/app/gateway/routers/channels.py:42` |
| `GET /api/console/stats` | 401/403/503 | `backend/app/gateway/routers/console.py:285` |
| `GET /api/console/runs` | 401/403/422/503 | `backend/app/gateway/routers/console.py:356` |
| `GET /api/console/usage` | 401/403/422/503 | `backend/app/gateway/routers/console.py:427` |
| `GET /api/features` | 401 | `backend/app/gateway/routers/features.py:73` |
| `POST /api/threads/{thread_id}/runs/{run_id}/feedback` | 400/401/403/404/422 | `backend/app/gateway/routers/feedback.py:115` |
| `GET /api/threads/{thread_id}/runs/{run_id}/feedback` | 401/403/404/422 | `backend/app/gateway/routers/feedback.py:148` |
| `GET /api/threads/{thread_id}/runs/{run_id}/feedback/stats` | 401/403/404/422 | `backend/app/gateway/routers/feedback.py:160` |
| `DELETE /api/threads/{thread_id}/runs/{run_id}/feedback/{feedback_id}` | 401/403/404/422 | `backend/app/gateway/routers/feedback.py:172` |
| `PUT /api/threads/{thread_id}/runs/{run_id}/feedback` | 400/401/403/404/422 | `backend/app/gateway/routers/feedback.py:64` |
| `DELETE /api/threads/{thread_id}/runs/{run_id}/feedback` | 401/403/404/422 | `backend/app/gateway/routers/feedback.py:95` |
| `POST /api/webhooks/github` | 400/401/422/503 | `backend/app/gateway/routers/github_webhooks.py:173` |
| `POST /api/input-polish` | 400/401/403/404/422/503 | `backend/app/gateway/routers/input_polish.py:65` |
| `GET /api/integrations/lark/status` | 401/500 | `backend/app/gateway/routers/integrations.py:260` |
| `POST /api/integrations/lark/install` | 400/401/403/404/500 | `backend/app/gateway/routers/integrations.py:270` |
| `POST /api/integrations/lark/config/start` | 400/401/404/422/500/504 | `backend/app/gateway/routers/integrations.py:288` |
| `POST /api/integrations/lark/config/complete` | 400/401/404/409/422/500/504 | `backend/app/gateway/routers/integrations.py:308` |
| `POST /api/integrations/lark/config/credentials` | 400/401/404/422/500/504 | `backend/app/gateway/routers/integrations.py:335` |
| `POST /api/integrations/lark/auth/start` | 400/401/404/409/422/500/504 | `backend/app/gateway/routers/integrations.py:358` |
| `POST /api/integrations/lark/auth/complete` | 400/401/404/409/422/500/504 | `backend/app/gateway/routers/integrations.py:383` |
| `GET /api/mcp/config` | 401/403 | `backend/app/gateway/routers/mcp.py:1116` |
| `POST /api/mcp/cache/reset` | 401/403 | `backend/app/gateway/routers/mcp.py:1423` |
| `PUT /api/mcp/config` | 400/401/403/422/500 | `backend/app/gateway/routers/mcp.py:1444` |
| `POST /api/mcp/config/servers` | 400/401/403/422/500 | `backend/app/gateway/routers/mcp.py:1504` |
| `PUT /api/mcp/config/server` | 400/401/403/422/500 | `backend/app/gateway/routers/mcp.py:1527` |
| `DELETE /api/mcp/config/servers/{server_name:path}` | 401/403/422/500 | `backend/app/gateway/routers/mcp.py:1553` |
| `PATCH /api/mcp/config` | 401/403/422/500 | `backend/app/gateway/routers/mcp.py:1575` |
| `POST /api/threads/{thread_id}/mcp-tasks/{task_id}/cancel` | 401/403/404/422/503 | `backend/app/gateway/routers/mcp_tasks.py:106` |
| `GET /api/threads/{thread_id}/mcp-tasks` | 401/403/404/422 | `backend/app/gateway/routers/mcp_tasks.py:68` |
| `GET /api/threads/{thread_id}/mcp-tasks/{task_id}` | 401/403/404/422 | `backend/app/gateway/routers/mcp_tasks.py:87` |
| `GET /api/memory` | 401/409/500/501 | `backend/app/gateway/routers/memory.py:211` |
| `POST /api/memory/reload` | 401/409/500/501 | `backend/app/gateway/routers/memory.py:257` |
| `DELETE /api/memory` | 401/409/500/501 | `backend/app/gateway/routers/memory.py:290` |
| `POST /api/memory/facts` | 400/401/409/422/500/501 | `backend/app/gateway/routers/memory.py:312` |
| `DELETE /api/memory/facts/{fact_id}` | 401/404/409/422/500/501 | `backend/app/gateway/routers/memory.py:345` |
| `PATCH /api/memory/facts/{fact_id}` | 400/401/404/409/422/500/501 | `backend/app/gateway/routers/memory.py:369` |
| `GET /api/memory/export` | 401/409/500/501 | `backend/app/gateway/routers/memory.py:402` |
| `POST /api/memory/import` | 401/409/422/500/501 | `backend/app/gateway/routers/memory.py:416` |
| `GET /api/memory/config` | 401 | `backend/app/gateway/routers/memory.py:441` |
| `GET /api/memory/status` | 401/409/500/501 | `backend/app/gateway/routers/memory.py:491` |
| `GET /api/models/{model_name}` | 401/403/404/422/500 | `backend/app/gateway/routers/models.py:138` |
| `GET /api/models` | 401/500 | `backend/app/gateway/routers/models.py:50` |
| `GET /api/projects/{project_id}/documents` | 401/403/404/422 | `backend/app/gateway/routers/project_documents.py:142` |
| `POST /api/projects/{project_id}/documents` | 400/401/403/404/413/422 | `backend/app/gateway/routers/project_documents.py:166` |
| `POST /api/projects/{project_id}/documents/from-thread` | 400/401/403/404/413/422 | `backend/app/gateway/routers/project_documents.py:270` |
| `POST /api/projects/{project_id}/documents/{document_id}/attach-to-thread/{thread_id}` | 401/403/404/409/422/500 | `backend/app/gateway/routers/project_documents.py:338` |
| `GET /api/projects/{project_id}/documents/{document_id}/content` | 401/403/404/409/422 | `backend/app/gateway/routers/project_documents.py:412` |
| `DELETE /api/projects/{project_id}/documents/{document_id}` | 401/403/404/422 | `backend/app/gateway/routers/project_documents.py:486` |
| `GET /api/projects/{project_id}/thread-files` | 401/403/404/422 | `backend/app/gateway/routers/project_thread_files.py:105` |
| `POST /api/projects` | 401/403/422 | `backend/app/gateway/routers/projects.py:118` |
| `GET /api/projects` | 401/403/422 | `backend/app/gateway/routers/projects.py:126` |
| `GET /api/projects/config` | 401/403 | `backend/app/gateway/routers/projects.py:133` |
| `GET /api/projects/{project_id}` | 401/403/404/422 | `backend/app/gateway/routers/projects.py:148` |
| `PATCH /api/projects/{project_id}` | 401/403/404/422 | `backend/app/gateway/routers/projects.py:157` |
| `POST /api/projects/{project_id}/archive` | 401/403/404/422 | `backend/app/gateway/routers/projects.py:167` |
| `POST /api/projects/{project_id}/restore` | 401/403/404/422 | `backend/app/gateway/routers/projects.py:176` |
| `DELETE /api/projects/{project_id}` | 401/403/404/422 | `backend/app/gateway/routers/projects.py:185` |
| `GET /api/projects/{project_id}/threads` | 401/403/404/422 | `backend/app/gateway/routers/projects.py:193` |
| `GET /api/runs/{run_id}/messages` | 401/403/404/422 | `backend/app/gateway/routers/runs.py:110` |
| `GET /api/runs/{run_id}/feedback` | 401/403/404/422 | `backend/app/gateway/routers/runs.py:141` |
| `POST /api/runs/stream` | 400/401/403/404/409/422/501 | `backend/app/gateway/routers/runs.py:35` |
| `POST /api/runs/wait` | 400/401/403/404/409/422/501 | `backend/app/gateway/routers/runs.py:61` |
| `POST /api/scheduled-tasks/preview-cron` | 401/403/422 | `backend/app/gateway/routers/scheduled_tasks.py:167` |
| `GET /api/scheduled-tasks` | 401/403 | `backend/app/gateway/routers/scheduled_tasks.py:178` |
| `POST /api/scheduled-tasks` | 401/403/404/422 | `backend/app/gateway/routers/scheduled_tasks.py:189` |
| `GET /api/scheduled-tasks/{task_id}` | 401/403/404/422 | `backend/app/gateway/routers/scheduled_tasks.py:254` |
| `PATCH /api/scheduled-tasks/{task_id}` | 401/403/404/409/422 | `backend/app/gateway/routers/scheduled_tasks.py:268` |
| `POST /api/scheduled-tasks/{task_id}/pause` | 401/403/404/409/422 | `backend/app/gateway/routers/scheduled_tasks.py:380` |
| `POST /api/scheduled-tasks/{task_id}/resume` | 401/403/404/409/422 | `backend/app/gateway/routers/scheduled_tasks.py:412` |
| `POST /api/scheduled-tasks/{task_id}/trigger` | 401/403/404/409/422/502 | `backend/app/gateway/routers/scheduled_tasks.py:441` |
| `DELETE /api/scheduled-tasks/{task_id}` | 401/403/404/409/422 | `backend/app/gateway/routers/scheduled_tasks.py:462` |
| `GET /api/scheduled-tasks/{task_id}/runs` | 401/403/404/422 | `backend/app/gateway/routers/scheduled_tasks.py:485` |
| `GET /api/threads/{thread_id}/scheduled-tasks` | 401/403/404/422 | `backend/app/gateway/routers/scheduled_tasks.py:505` |
| `GET /api/skills` | 401/500 | `backend/app/gateway/routers/skills.py:277` |
| `POST /api/skills/install` | 400/401/403/404/409/422/500 | `backend/app/gateway/routers/skills.py:293` |
| `POST /api/skills/install/upload` | 400/401/403/404/409/413/422/500 | `backend/app/gateway/routers/skills.py:324` |
| `POST /api/skills/reload` | 401/403/500 | `backend/app/gateway/routers/skills.py:362` |
| `GET /api/skills/custom` | 401/500 | `backend/app/gateway/routers/skills.py:379` |
| `GET /api/skills/custom/{skill_name}/export-manifest` | 204/401/403/404/409/413/422/429/500/503 | `backend/app/gateway/routers/skills.py:396` |
| `GET /api/skills/custom/{skill_name}/export` | 204/401/403/404/409/413/422/429/500/503 | `backend/app/gateway/routers/skills.py:416` |
| `GET /api/skills/custom/{skill_name}` | 401/403/404/422/500 | `backend/app/gateway/routers/skills.py:437` |
| `PUT /api/skills/custom/{skill_name}` | 400/401/403/404/422/500 | `backend/app/gateway/routers/skills.py:459` |
| `DELETE /api/skills/custom/{skill_name}` | 400/401/403/404/422/500 | `backend/app/gateway/routers/skills.py:499` |
| `GET /api/skills/custom/{skill_name}/history` | 401/403/404/422/500 | `backend/app/gateway/routers/skills.py:529` |
| `POST /api/skills/custom/{skill_name}/rollback` | 400/401/403/404/422/500 | `backend/app/gateway/routers/skills.py:555` |
| `GET /api/skills/{skill_name}` | 401/404/422/500 | `backend/app/gateway/routers/skills.py:609` |
| `PUT /api/skills/{skill_name}` | 401/403/404/422/500 | `backend/app/gateway/routers/skills.py:681` |
| `GET /api/threads/{thread_id}/subagent-batches/{batch_id}/results.jsonl` | 401/403/404/422 | `backend/app/gateway/routers/subagent_batches.py:107` |
| `GET /api/threads/{thread_id}/subagent-batches` | 401/403/404/422 | `backend/app/gateway/routers/subagent_batches.py:41` |
| `GET /api/threads/{thread_id}/subagent-batches/{batch_id}` | 401/403/404/422 | `backend/app/gateway/routers/subagent_batches.py:48` |
| `GET /api/threads/{thread_id}/subagent-batches/{batch_id}/items` | 401/403/404/422 | `backend/app/gateway/routers/subagent_batches.py:55` |
| `POST /api/threads/{thread_id}/subagent-batches/{batch_id}/pause` | 401/403/404/422 | `backend/app/gateway/routers/subagent_batches.py:71` |
| `POST /api/threads/{thread_id}/subagent-batches/{batch_id}/resume` | 401/403/404/422 | `backend/app/gateway/routers/subagent_batches.py:78` |
| `POST /api/threads/{thread_id}/subagent-batches/{batch_id}/cancel` | 401/403/404/422/503 | `backend/app/gateway/routers/subagent_batches.py:85` |
| `POST /api/threads/{thread_id}/subagent-batches/{batch_id}/items/{item_id}/retry` | 401/403/404/409/422 | `backend/app/gateway/routers/subagent_batches.py:97` |
| `GET /api/subagents` | 401 | `backend/app/gateway/routers/subagents.py:164` |
| `POST /api/subagents` | 401/403/409/422 | `backend/app/gateway/routers/subagents.py:171` |
| `PUT /api/subagents/{name}` | 401/403/404/422 | `backend/app/gateway/routers/subagents.py:196` |
| `DELETE /api/subagents/{name}` | 401/403/404/422 | `backend/app/gateway/routers/subagents.py:232` |
| `POST /api/threads/{thread_id}/suggestions` | 401/403/404/422 | `backend/app/gateway/routers/suggestions.py:105` |
| `GET /api/suggestions/config` | 401 | `backend/app/gateway/routers/suggestions.py:92` |
| `GET /api/threads/{thread_id}/runs` | 401/403/404/422 | `backend/app/gateway/routers/thread_runs.py:1093` |
| `GET /api/threads/{thread_id}/runs/page` | 401/403/404/422 | `backend/app/gateway/routers/thread_runs.py:1103` |
| `GET /api/threads/{thread_id}/runs/{run_id}` | 401/403/404/422 | `backend/app/gateway/routers/thread_runs.py:1145` |
| `POST /api/threads/{thread_id}/runs/{run_id}/cancel` | 401/403/404/409/422 | `backend/app/gateway/routers/thread_runs.py:1157` |
| `GET /api/threads/{thread_id}/runs/{run_id}/join` | 401/403/404/409/422 | `backend/app/gateway/routers/thread_runs.py:1217` |
| `POST /api/threads/{thread_id}/runs/{run_id}/stream` | 401/403/404/409/422/503 | `backend/app/gateway/routers/thread_runs.py:1333` |
| `GET /api/threads/{thread_id}/runs/{run_id}/stream` | 401/403/404/409/422/503 | `backend/app/gateway/routers/thread_runs.py:1351` |
| `GET /api/threads/{thread_id}/messages` | 401/403/404/422 | `backend/app/gateway/routers/thread_runs.py:1363` |
| `GET /api/threads/{thread_id}/messages/page` | 401/403/404/422 | `backend/app/gateway/routers/thread_runs.py:1502` |
| `GET /api/threads/{thread_id}/runs/{run_id}/messages` | 401/403/404/422 | `backend/app/gateway/routers/thread_runs.py:1530` |
| `GET /api/threads/{thread_id}/runs/{run_id}/artifacts/archive` | 401/403/404/409/422 | `backend/app/gateway/routers/thread_runs.py:1642` |
| `POST /api/threads/{thread_id}/runs/{run_id}/artifacts/archive` | 401/403/404/409/413/422/429/503 | `backend/app/gateway/routers/thread_runs.py:1654` |
| `GET /api/threads/{thread_id}/runs/{run_id}/events` | 401/403/404/422 | `backend/app/gateway/routers/thread_runs.py:1712` |
| `GET /api/threads/{thread_id}/runs/{run_id}/workspace-changes` | 401/403/404/422 | `backend/app/gateway/routers/thread_runs.py:1749` |
| `GET /api/threads/{thread_id}/token-usage` | 401/403/404/422 | `backend/app/gateway/routers/thread_runs.py:1769` |
| `POST /api/threads/{thread_id}/runs/regenerate/prepare` | 401/403/404/409/422/500 | `backend/app/gateway/routers/thread_runs.py:903` |
| `POST /api/threads/{thread_id}/runs/edit-regenerate/prepare` | 401/403/404/409/422/500 | `backend/app/gateway/routers/thread_runs.py:914` |
| `POST /api/threads/{thread_id}/runs` | 400/401/403/404/409/422/501 | `backend/app/gateway/routers/thread_runs.py:925` |
| `POST /api/threads/{thread_id}/runs/stream` | 400/401/403/404/409/422/501 | `backend/app/gateway/routers/thread_runs.py:943` |
| `POST /api/threads/{thread_id}/runs/wait` | 400/401/403/404/409/422/501 | `backend/app/gateway/routers/thread_runs.py:998` |
| `POST /api/threads/search` | 400/401/403/422 | `backend/app/gateway/routers/threads.py:1175` |
| `PATCH /api/threads/{thread_id}` | 401/403/404/422/500 | `backend/app/gateway/routers/threads.py:1218` |
| `POST /api/threads/{thread_id}/move` | 401/403/404/422 | `backend/app/gateway/routers/threads.py:1257` |
| `GET /api/threads/{thread_id}` | 401/403/404/409/422/500/503 | `backend/app/gateway/routers/threads.py:1278` |
| `GET /api/threads/{thread_id}/goal` | 401/403/404/422/500 | `backend/app/gateway/routers/threads.py:1331` |
| `PUT /api/threads/{thread_id}/goal` | 401/403/404/409/422/500 | `backend/app/gateway/routers/threads.py:1344` |
| `DELETE /api/threads/{thread_id}/goal` | 401/403/404/409/422/500 | `backend/app/gateway/routers/threads.py:1370` |
| `POST /api/threads/{thread_id}/compact` | 401/403/404/409/422/500/503 | `backend/app/gateway/routers/threads.py:1401` |
| `GET /api/threads/{thread_id}/state` | 401/403/404/409/422/500/503 | `backend/app/gateway/routers/threads.py:1448` |
| `POST /api/threads/{thread_id}/state` | 401/403/404/409/422/500/503 | `backend/app/gateway/routers/threads.py:1497` |
| `POST /api/threads/{thread_id}/history` | 401/403/404/409/422/500/503 | `backend/app/gateway/routers/threads.py:1701` |
| `DELETE /api/threads/{thread_id}` | 401/403/404/409/422/500 | `backend/app/gateway/routers/threads.py:708` |
| `POST /api/threads` | 401/403/404/422/500 | `backend/app/gateway/routers/threads.py:868` |
| `POST /api/threads/{thread_id}/branches` | 401/403/404/409/422/500/503 | `backend/app/gateway/routers/threads.py:955` |
| `GET /api/trash/documents` | 401/403/422 | `backend/app/gateway/routers/trash.py:139` |
| `POST /api/trash/documents/{document_id}/restore` | 401/403/404/409/422 | `backend/app/gateway/routers/trash.py:173` |
| `POST /api/trash/documents/{document_id}/purge` | 401/403/404/422/500 | `backend/app/gateway/routers/trash.py:210` |
| `POST /api/trash/purge` | 401/403/500 | `backend/app/gateway/routers/trash.py:228` |
| `POST /api/threads/{thread_id}/uploads` | 400/401/403/404/413/422/500 | `backend/app/gateway/routers/uploads.py:358` |
| `GET /api/threads/{thread_id}/uploads/limits` | 401/403/404/422 | `backend/app/gateway/routers/uploads.py:433` |
| `GET /api/threads/{thread_id}/uploads/list` | 400/401/403/404/422 | `backend/app/gateway/routers/uploads.py:444` |
| `DELETE /api/threads/{thread_id}/uploads/{filename}` | 400/401/403/404/422/500 | `backend/app/gateway/routers/uploads.py:456` |
| `GET /api/v1/auth/preferences` | 401/403/409/422/503 | `backend/app/gateway/routers/user_preferences.py:42` |
| `PATCH /api/v1/auth/preferences` | 401/403/409/422/503 | `backend/app/gateway/routers/user_preferences.py:57` |


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

`PUT /api/mcp/config` 实现 `_merge_preserving_secrets()`（`routers/mcp.py:1174-1210+`）：

1. `ExtensionsConfig.resolve_config_path()`，缺失则落到 `<project_root>/extensions_config.json`
2. 在 `extensions_config_write_lock` + 跨进程 `extensions_config_file_lock(path)` 内做**整个 read-modify-write**
3. 从磁盘读**原始** JSON 作为合并源（保留 `$VAR` 占位符与 `mcpInterceptors`、`middlewares` 等 schema 外顶层键）
4. 原子写入（Linux 上 `rename()` 撞 mount point 的 `EBUSY` 才回退为原地覆写）
5. 校验展开后的配置 → 非法一律 **400**；非预期异常 **500**

这允许前端在往返中发送掩码值（`***`），真实密钥保留在磁盘上。
