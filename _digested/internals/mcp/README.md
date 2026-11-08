---
title: "MCP — 协议集成深度"
description: "MCP 工具生命周期：Session Pool、OAuth、缓存失效、按用户/按请求凭据注入、个人连接与 mcpLifecycle 账本，以及把长任务变成持久化任务对象的 durable task 子系统。"
type: index
topics: [mcp, session-pool, oauth, durable-tasks]
---

# MCP — 协议集成深度

> **定位**：`deerflow/mcp/` 是 MCP server 与 DeerFlow 工具管道的集成层，回答「有状态会话怎么复用、凭据怎么按 server/user/request 注入、配置改了怎么失效、长任务怎么持久化」。
> **边界**：本目录不含能力清单与 installation identity（去 [../capabilities/](../capabilities/README.md)）；`extensions_config.json` 的字段手册在 [../configuration/02-extensions-json.md](../configuration/02-extensions-json.md)；durable task 的迁移与 ORM 落在 [../persistence/](../persistence/README.md)。

## 阅读路径

1. **先看**：[session-pool-oauth-cache-invalidation.md](session-pool-oauth-cache-invalidation.md) — 会话池、作用域键、OAuth、缓存与个人连接。
2. **再看**：[durable-tasks.md](durable-tasks.md) — 长任务如何变成可恢复的持久化对象。

## 本篇目

| 文件 | 主题 | 深度 |
|---|---|---|
| [session-pool-oauth-cache-invalidation.md](session-pool-oauth-cache-invalidation.md) | Session Pool / 作用域键 v2 / OAuth 落库 / 内容签名缓存失效 / 工具加载 / 管理面 / 个人连接 | 深入 |
| [durable-tasks.md](durable-tasks.md) | driver 抽象与 runtime 桥、控制租约、永久失败分类、persistence 与 migrations、router 与通知 | 深入 |

## 宪章与约定

- 包内有独立宪章：[backend/packages/harness/deerflow/mcp/AGENTS.md](../../../backend/packages/harness/deerflow/mcp/AGENTS.md)（87 行）；写作纪律沿用 [根 README](../README.md)。

## 相关目录

- [internals 父级](../README.md) — 13 个内部机制子目录的总入口。
- [capabilities](../capabilities/README.md) — 只做清单与安装身份，最终写进 MCP 配置。
- [configuration](../configuration/README.md) — `extensions_config.json` 的结构与加载。
- [persistence](../persistence/README.md) — `mcp_tasks`、`mcp_oauth_tokens` 的表与迁移。
- [builtin-tools](../../concepts/builtin-tools/README.md) — MCP 工具如何汇入工具装配。

## 速览

- **会话按四元组隔离**：`(server_name, scope_key, owning_loop, ownership_domain)`；LRU 256 是创建与 promotion 两次准入的硬上限；`ServerBinding` 把会话钉在不可变连接定义上。
- **作用域键 v2**：`v2:[user, thread, incarnation]` JSON 编码；legacy `user:thread` 只用于 incarnation 之前的历史行。
- **凭据三条路**：OAuth server 级（refresh_token 落 `mcp_oauth_tokens`，加密 + 跨进程刷新租约）、`user_scoped_auth` 按用户、`headers_from_context` 按请求；后两者 fail-closed。
- **配置失效靠内容签名**：resolved-path + `(mtime,size,sha256)` + 配置 revision + 共享 reset 标记；2.2 起只 reconciliation 变更的 server。
- **长任务持久化**：submit 立即返回本地 ID，后台 poller 在 Agent loop 之外轮询/取消/通知，靠逐次认领租约恢复；迁移 0011–0013 + 0019/0026。
- **个人连接**：每用户 `<user_dir>/mcp.json`，运行时名 `personal_<sha256>`、per-call owner 校验，非管理员仅公网端点。
- **可选集成**：`extensions_config.example.json` 附 Parallel Search server（默认关闭，匿名 + `User-Agent: deer-flow` 标识）。
