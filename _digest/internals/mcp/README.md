---
title: "MCP — 协议集成深度"
description: "MCP 工具生命周期：Session Pool、OAuth、缓存失效、按用户凭据注入，以及把长任务变成持久化任务对象的 durable task 子系统。"
type: index
---

# MCP — 协议集成深度

`deerflow/mcp/` 是 MCP（Model Context Protocol）服务器与 DeerFlow 工具管道的集成层。它解决六类问题：**会话生命周期**（stdio 有状态服务器跨调用复用，按 `(server_name, scope_key, owning_loop)` 隔离）、**鉴权**（OAuth server 级令牌 + user_auth 按用户凭据 + headers_from_context 按请求凭据）、**配置热生效**（extensions_config 的 content-signature 缓存失效）、**长任务**（把请求/响应式工具调用升级为可恢复的持久化任务）、**管理面**（Gateway `/api/mcp` 的增删改/启停 API，Settings 页的数据源），以及**可选集成**（Parallel Search server）。

→ Back to [parent README](../README.md)

## 能力一览

| 能力 | 关键模块 | 说明 |
|------|----------|------|
| Session Pool | `session_pool.py` | 按 `(server_name, scope_key, owning_loop)` 复用持久会话，LRU 256 硬上限（创建与 promotion 两次准入），跨线程安全 |
| OAuth | `oauth.py` | `client_credentials` / `refresh_token`，自动刷新 + Bearer header 注入（值过 `illegal_header_value_reason` 检查），双检查锁防并发刷新 |
| 缓存失效 | `cache.py` | resolved-path + `(mtime,size,sha256)` content-signature 检测，跨事件循环初始化锁安全 |
| 按用户凭据 | `user_scoped_auth.py` | 共享 HTTP/SSE server 的 per-user credential 注入，fail-closed |
| 按请求凭据 🆕 同步#6 | `context_headers.py` + `headers.py` | `headers_from_context` 把 run request 的 `config.context.secrets` 映射为 HTTP/SSE header，大小写不敏感写入 + 值合法性拒绝，fail-closed |
| 管理面 🆕 同步#6 | `app/gateway/routers/mcp.py` | Settings 页管理 MCP servers：`GET/PUT /api/mcp/config`、逐 server `POST/PUT/DELETE`、`PATCH` 启停；敏感值掩码 + stdio 启动策略校验 |
| 可选集成 🆕 同步#6 | `extensions_config.example.json` | Parallel Search server（默认关闭，匿名 + `User-Agent: deer-flow` 标识） |
| Durable Task | `tasks/` + `app/mcp_tasks/` | 长任务持久化：submit 立即返回本地 ID，后台轮询/取消/通知 |

## 文件导航

1. **[session-pool-oauth-cache-invalidation.md](session-pool-oauth-cache-invalidation.md)** — Session Pool、OAuth Token 管理、缓存失效、工具加载、routing hints、per-server 超时与前缀。
2. **[durable-tasks.md](durable-tasks.md)** — MCP 持久化长任务子系统：driver 抽象 / ordinary 实现 / runtime 桥、task tool caller、persistence 与 migrations 0011–0013、`/mcp_tasks` router + chat UI 通知、per-user credential injection、`mcp_tasks` config。
