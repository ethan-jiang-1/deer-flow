---
title: "Gateway API 层访问控制"
description: "扩展面的身份投影、插件管理路由的 resolver 语义。"
topics: [governance, identity]
---

# Gateway API 层访问控制

扩展面的身份投影、插件管理路由的 resolver 语义。

## Gateway API 层访问控制

| 控制 | 机制 |
|------|------|
| **CORS** | `GATEWAY_CORS_ORIGINS` 环境变量（默认 same-origin） |
| **CSRF** | CSRFMiddleware，检查 Origin/Referer header |
| **API rate limiting** | 无内置——需在 nginx 层配置 |
| **API key auth** | 无——依赖 JWT + CSRF |

### 🆕 2.2.0：扩展面的身份投影与两处独立否决

插件读不到宿主的 `AuthContext`，只拿到一个**投影** `ExtensionPrincipal`（`app/gateway/app.py:1198` 的 `_resolve_extension_principal`）：`user_id` / `is_admin` / `is_internal` / `roles`。设计意图原文是 "a projection, not a handle"——插件只能问"我是谁、我是不是管理员、我是什么角色"，不能借宿主的内部结构获得别的东西。

| 规则 | 位置 | 效果 |
|------|------|------|
| **PAT 永不带 admin** | `app/gateway/app.py:1214-1221` | PAT 调用者即使属主是 admin，`is_admin=False` 且 `roles` 元组被**清空**（不是只去掉 `admin` 一项） |
| **Agent run 句柄只认两种来源** | `app/gateway/extension_agent_runs.py:70-73` | 只接受 `AUTH_SOURCE_SESSION` / `AUTH_SOURCE_AUTH_DISABLED`；PAT 与 internal-owner 委托被拒 |
| **PAT 路由白名单默认拒绝** | `app/gateway/auth/pat.py:60` | `/api/plugins/*`、`/api/skill-mutations/*`、`/api/v1/admin/*` 不在表内 ⇒ PAT 够不到即使有 scope |

第二条的理由值得 IT 注意（注释原文在 `app/gateway/extension_agent_runs.py:70-73`）：原话是 "PAT revocation and internal-owner delegation need separate durable grants. Never turn either into an unrestricted session capability."——PAT 撤销是**立即生效**的，但它可能已经被换成一个长期持有的句柄（agent run 句柄），句柄不会跟着撤销。所以这条路直接封掉，而不是靠事后修补。

### 🆕 插件管理路由的 resolver 语义

插件自有的管理路由用 `deerflow_extension_api/auth.py:87` 的 `require_plugin_management(request, namespace, *, scope="read")`：

- 宿主在 `app.state` 上装两个 resolver（同步 `EXTENSION_PLUGIN_AUTHZ_RESOLVER_KEY`、异步 `..._ASYNC_KEY`），handler 只负责"问"，不负责"判"。
- **异步变体只读异步 key，不做同步回退**——否则一个慢的同步 provider 会在 event loop 上阻塞。
- 答案必须是 **`is True`**（不是 truthy）：`None`（宿主没接线）与任何非 `True` 值都等价于拒绝。
- resolver 抛异常 → 记 `None` → handler 抛 `PermissionError`。

⚠️ **已知缺口**：这个 `PermissionError` **没有被 Gateway 翻译**成 403——如果插件路由不自己捕获，客户端看到的是 **500**。这是个宿主侧的一致性问题，插件作者必须自己 try/except。

### 运维侧的两条核实结论

| 结论 | 证据 |
|---|---|
| `/api/plugins`、`/api/skill-mutations`、`/api/v1/admin` **均未**出现在 `_PAT_ROUTE_RULES` 中 | `app/gateway/auth/pat.py:60` 起的规则表里无对应 path pattern |
| CORS 允许来源只从 `GATEWAY_CORS_ORIGINS` 读取，逗号分隔，空值即不放开 | `app/gateway/csrf_middleware.py:116`、`:127` |

所以「PAT 能不能调插件管理接口」的答案是**不能**——不是靠 scope 拦截，
而是这些路由根本不在白名单内，默认拒绝直接生效。
