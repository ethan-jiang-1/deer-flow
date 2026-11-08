---
title: "MCP — 协议集成深度"
description: "MCP 工具生命周期：Session Pool、OAuth、缓存失效、按用户凭据注入、个人连接与 mcpLifecycle 账本，以及把长任务变成持久化任务对象的 durable task 子系统。"
type: index
---

# MCP — 协议集成深度

`deerflow/mcp/` 是 MCP（Model Context Protocol）服务器与 DeerFlow 工具管道的集成层。它解决七类问题：**会话生命周期**（stdio 有状态服务器跨调用复用，按 `(server_name, scope_key, owning_loop, ownership_domain)` 隔离）、**鉴权**（OAuth server 级令牌 + 落库 refresh_token + user_auth 按用户凭据 + headers_from_context 按请求凭据）、**配置热生效**（extensions_config 的 content-signature 缓存失效 + 选择性 reconciliation）、**长任务**（把请求/响应式工具调用升级为可恢复的持久化任务）、**管理面**（Gateway `/api/mcp` 的增删改/启停 API，Settings 页的数据源）、**个人连接**（每个用户自己的 `<user_dir>` 个人 MCP 配置文件，与部署配置互不可见），以及**可选集成**（Parallel Search server）。

→ Back to [parent README](../README.md)

## 能力一览

| 能力 | 关键模块 | 说明 |
|------|----------|------|
| Session Pool | `session_pool.py` | 按 `(server_name, scope_key, owning_loop, domain)` 复用持久会话，LRU 256 硬上限（创建与 promotion 两次准入），跨线程安全；`ServerBinding` 把会话钉在一个不可变连接定义上 |
| 会话作用域 🆕 2.2 | `mcp_scope.py` | 作用域键 v2：`v2:[user, thread, incarnation]` JSON 编码，legacy `user:thread` 仅用于 incarnation 之前的历史行 |
| OAuth | `oauth.py` + `oauth_store.py` | `client_credentials` / `refresh_token`，自动刷新 + Bearer header 注入（值过 `illegal_header_value_reason` 检查），per-server `threading.Lock` 双检查；🆕 2.2 refresh_token 落 `mcp_oauth_tokens`（加密、跨进程刷新租约、`invalid_grant` → 重新授权） |
| 缓存失效 | `cache.py` | resolved-path + `(mtime,size,sha256)` content-signature 检测 + 配置 revision + 共享 reset 标记；🆕 2.2 选择性 reconciliation（只换变更的 server） |
| 生命周期账本 🆕 2.2 | `lifecycle.py` | `mcpLifecycle` 能力句柄：谁在引用哪些 server/transport，供强制重绑与 OAuth token 保留期判定 |
| 按用户凭据 | `user_scoped_auth.py` | 共享 HTTP/SSE server 的 per-user credential 注入，fail-closed |
| 按请求凭据 🆕 同步#6 | `context_headers.py` + `headers.py` | `headers_from_context` 把 run request 的 `config.context.secrets` 映射为 HTTP/SSE header，大小写不敏感写入 + 值合法性拒绝，fail-closed |
| 个人连接 🆕 2.2 | `user_config.py` + `user_tools.py` + `personal_access.py` + `personal_network.py` | 每用户 `<user_dir>` 下的个人 MCP 配置文件（`mcp.json`），运行时名 `personal_<sha256>`、per-call owner 校验、管理员权限复核、非管理员仅公网端点 |
| 管理面 🆕 同步#6 | `app/gateway/routers/mcp.py` + `personal_mcp.py` | Settings 页管理 MCP servers：`GET/PUT /api/mcp/config`、逐 server `POST/PUT/DELETE`、`PATCH` 启停、`POST /api/mcp/cache/reset`；🆕 2.2 增加 `/api/mcp/personal/config*`；敏感值掩码 + stdio 启动策略校验 |
| 可选集成 🆕 同步#6 | `extensions_config.example.json` | Parallel Search server（默认关闭，匿名 + `User-Agent: deer-flow` 标识） |
| Durable Task | `tasks/` + `app/mcp_tasks/` | 长任务持久化：submit 立即返回本地 ID，后台轮询/取消/通知；🆕 2.2 逐次认领租约令牌 + 控制租约心跳、线程 incarnation 绑定、personal 连接作用域 |

## 文件导航

1. **[session-pool-oauth-cache-invalidation.md](session-pool-oauth-cache-invalidation.md)** — Session Pool（含作用域键 v2、`ServerBinding`/选择性 reconciliation、`mcpLifecycle` 账本）、OAuth Token 管理与落库、缓存失效与跨循环初始化、工具加载、传输类型与 routing hints、Settings 页管理面、个人 MCP 连接、per-server 超时与前缀。
2. **[durable-tasks.md](durable-tasks.md)** — MCP 持久化长任务子系统：driver 抽象 / ordinary 实现 / runtime 桥、控制租约心跳与永久失败分类、task tool caller（含 personal 连接作用域）、persistence 与 migrations 0011–0013 + 0019/0026、`/mcp_tasks` router + chat UI 通知、per-user credential injection、`mcp_tasks` config。
