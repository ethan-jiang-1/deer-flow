---
title: "authz — 授权决策内核"
description: "14 个文件的资源级授权决策层：RBAC 角色映射与 13 个路由权限、扩展路由的 principal/resolver 与 fail-closed、sandbox:execute 在 acquire/复用前的重查。"
type: index
topics: [authz, rbac, plugin-authorization, sandbox, internals]
---

# authz — 授权决策内核

> **定位**：`backend/packages/harness/deerflow/authz/`（14 文件 / 1,960 行）的源码级契约。它把已认证身份编译成 `Principal`，交给可插拔的 `AuthorizationProvider` 对 `resource/action/target` 出 allow/deny；本页聚焦三类高风险决策（RBAC / 插件扩展路由 / sandbox 执行）和 Gateway 调用链，工具/技能装配期过滤与 Guardrail 适配不展开。
> **边界**：不替代 [04-rbac-permissions.md](../../enterprise-it-governance/authorization/04-rbac-permissions.md) 的权限判断——13 个 `resource:action`、路由守卫、默认关闭与 `fail_closed` 全表以那里为准；不替代 [01-auth.md](../../enterprise-operations/security/01-auth.md) 的认证部署——本地密码 / OIDC / PAT / internal token 怎么进来不在本页；也不覆盖 sandbox 的 lease/隔离（[02-sandbox-isolation.md](../../enterprise-operations/security/02-sandbox-isolation.md)）或扩展安装/路由注册。

## 阅读路径

1. **先看**：[04-rbac-permissions.md](../../enterprise-it-governance/authorization/04-rbac-permissions.md) — 13 个权限的唯一全表、默认关闭与 `runs:cancel` 特例；本页不复制。
2. **再看**：本页 [核心契约](#核心契约) — `rbac.py` / `plugin_authz.py` / `sandbox_authz.py` 的不变量。
3. **深入**：`backend/app/gateway/authz.py` — `require_permission` 的预求值链、provider 缓存与 fail-closed 分叉。

## 本篇目

本目录只有本页；“相关页”提供上下文，不重复正文。

| 文件 | 主题 | 深度 |
|---|---|---|
| 本页 `README.md` | authz 包定位；RBAC / 插件 / sandbox 三块契约；Gateway 调用链 | 深入 |
| [04-rbac-permissions.md](../../enterprise-it-governance/authorization/04-rbac-permissions.md) | 13 权限唯一全表、默认关闭、`runs:cancel`、内部调用者 | 深入 |
| [01-auth.md](../../enterprise-operations/security/01-auth.md) | 四条认证路径与 AuthMiddleware 部署 | 深入 |
| [capabilities/README.md](../capabilities/README.md) | 插件/能力目录与安装身份；不是路由授权本身 | 概览 |

## 核心契约

### 1. `rbac.py` — 角色到资源的策略，不是权限常量表

- `roles.<role>.<resource_key>` 在构造期编译为 `(role, resource)` 不可变策略；请求侧只做成员判断。单数请求资源经 `_RESOURCE_POLICY_KEYS` 映射到配置复数键（`tool→tools`、`mcp_server→mcp_servers`、`route→routes`），插件键 `plugin_action→plugin_actions`、`plugin_management` 自映射；拼错 `allow`/`deny` 键或使用请求别名在构造期失败。`backend/packages/harness/deerflow/authz/rbac.py:26-42`、`:103-131`、`:151-205`
- `action` 只为协议兼容而接收，不是规则维度；`(role, resource, target)` 决定结果，`deny` 先于 `allow`。`rbac.py:69-75`、`:86-88`、`:230-257`
- 默认/失败语义要分四种：`allow` 缺省 → `_ALL`（允许全部候选，`deny` 仍可覆盖）；`(role, resource)` 完全没有策略 → 无限制 allow（`authz.no_policy` / `rbac:unrestricted`）；`allow: false` 或 `allow: []` → 全拒；role 缺失/未知 → `ValueError`，由调用方 `fail_closed` 决定最终结果。`rbac.py:169-172`、`:176-187`、`:220-228`、`:234-240`
- 13 个权限是 Gateway 的 route 权限，不是 RBAC 的资源类型：threads×3 / runs×3 / projects×3 / memory×2 / agents×2。route 权限的 RBAC 请求形态固定为 `resource="route"`、`target="<resource>:<action>"`；逐项路由映射只以 [04](../../enterprise-it-governance/authorization/04-rbac-permissions.md) 为唯一权限表。`backend/app/gateway/authz.py:63-86`、`:161-175`
- `authorization.enabled` 默认 `false`（`backend/packages/harness/deerflow/config/authorization_config.py:29`）；关闭时 route 直接返回全部 13 个权限（`backend/app/gateway/authz.py:288-290`）。这是部署开关，不是 RBAC 的缺省 allow；`fail_closed` 默认 `true`（`authorization_config.py:30`）。

### 2. `plugin_authz.py` — 扩展路由：两个 principal、一个 resolver、fail-closed

- 扩展路由在 `install()` 时构造，拿不到请求身份；宿主把 resolver 装到 `app.state`，扩展通过 extension-api 反问。`backend/packages/extension-api/deerflow_extension_api/auth.py:1-23`、`backend/app/gateway/app.py:1229-1235`
- 扩展看到的是 `ExtensionPrincipal` 投影（`user_id/is_admin/is_internal/roles`），不是宿主 `AuthContext`；resolver 缺失、抛错或返回错类型时 `resolve_principal` 返回 `None`，`require_admin` 因此 fail-closed；宿主投影中 PAT 的 `is_admin` 恒 false，admin-owned PAT 的 `roles` 也被清空。`backend/packages/extension-api/deerflow_extension_api/auth.py:33-65`、`backend/app/gateway/app.py:1198-1229`
- `require_plugin_management(request, namespace, scope)` 只在宿主 resolver 返回严格 `True` 时放行；未知 namespace、匿名、resolver 缺失/异常/`None` 全部 `PermissionError`；异步端点必须用 `arequire_plugin_management`，不回退同步 resolver。`backend/packages/extension-api/deerflow_extension_api/auth.py:87-142`
- 宿主 resolver 先 `_installed_plugin_namespace`，再 `resolve_plugin_authorization` 返回 `(provider, principal, app_config)`；授权关闭 → `True`，策略拒绝 → `False`，解析层不可用按 `fail_closed` 分叉，匿名/未安装 → `None`。插件 provider 用 loop-keyed cache，不复用 route cache。`backend/app/gateway/app.py:94-169`、`backend/app/gateway/authz.py:531-537`、`:644-663`
- 插件决策用的 harness `Principal` 由 `_plugin_request_principal` 构造：internal role 被 pop 后落到 `default_role`，匿名则 `None`；它与扩展侧 `ExtensionPrincipal` 是两个类型，不要混用。`backend/app/gateway/authz.py:667-675`、`:455-475`
- fail-closed 边界：disabled → no-op；`app_config=None` → `authz.config_unavailable` 且**即使 fail_open 也拒绝**；显式 deny 恒抛；provider 异常/解析失败/非 `AuthzDecision`/`allow` 非真 bool/缺 principal 才按 `fail_closed` 决定；坏 reasons 只降级 `reason_code`，不把 deny 变 allow。`plugin_authz.py:10-34`、`:117-176`、`:192-239`
- 批量过滤只返回候选子集：provider 答案与 candidate 求交，空候选不发调用；`filter_resources` 被 offload 到线程池，自定义 provider 必须线程安全。`plugin_authz.py:242-274`、`provider.py:109-130`
- target 编码由 `plugin_targets.py` 独占：action 是 `namespace/action`，management 是 `namespace/permissions.read|write`；action/page target 可字节相同，读取方必须按 `(resource,target)` 查。`plugin_targets.py:8-18`、`:33-38`、`:59-77`
- Gateway 插件 action 入口在 handler 前调用 `aenforce_plugin_action`；解析失败且 fail_closed → 403，fail_open → 放行，显式 `PluginAuthorizationError` 恒 403。`backend/app/gateway/authz.py:733-760`、`backend/app/gateway/routers/plugins.py:166-168`

### 3. `sandbox_authz.py` — `sandbox:execute` 与 #5006 复用重查

- 二进制检查：`authorize(principal, "sandbox", "execute", target="*")`；`*` 表示整个 sandbox，不是某个目录或能力。`sandbox_authz.py:54-58`、`:124-132`
- 配置关闭或没有可读配置 → no-op；provider 解析失败与 `authorize()` 异常都按 `fail_closed` 转成 `SandboxAuthorizationError` 或 fail-open 放行；deny 抛异常，工具调用边界转成友好 `ToolMessage`（eager acquire 的 deny 则跳过 acquire），不炸 run。`sandbox_authz.py:61-90`、`:135-187`；`backend/packages/harness/deerflow/agents/middlewares/read_before_write_middleware.py:305-317`
- #5006：授权是实时执行策略，不是 sandbox id 的终身属性。`ensure_sandbox_initialized` / async 在读取持久化 sandbox 状态之前、lazy acquire 之前调用 gate；因此复用与新建都重查。`backend/packages/harness/deerflow/sandbox/tools.py:2135-2142`、`:2238-2244`；`CHANGELOG.md:13376-13379`
- eager 路径也在 `before_agent` / `abefore_agent` 的 acquire 前检查；deny 时共享视图跳过 acquire，策略化 skill 视图则中止，避免旧 checkpoint sandbox 绕过新策略。`backend/packages/harness/deerflow/sandbox/middleware.py:252-272`、`:372-385`
- 组合工具调用（read-before-write 预读 + tool body + 读后盖章）用 `ContextVar` 只做一次决策；下一个独立工具调用重新决策。`backend/packages/harness/deerflow/sandbox/tools.py:68-73`、`:2067-2100`
- 这是 sandbox 的 authorization gate，不负责 lease/隔离/网络策略；lease 在 `sandbox/lease.py`，隔离与网络策略见 [02-sandbox-isolation.md](../../enterprise-operations/security/02-sandbox-isolation.md)。

### 4. 调用链：Gateway 路由 → `require_permission` → `AuthorizationProvider`

```
AuthMiddleware (auth_middleware.py:214-226)
  └─ resolve_route_permissions(user, is_internal=...)
       └─ AuthorizationProvider.aauthorize × 13  (resource="route", target="<perm>")
            ↓ 结果写入 request.state.auth.permissions
@require_permission
  └─ AuthContext.has_permission → 403 / owner check
```

- 严格说 `require_permission` **不直接**调用 provider：它在 `AuthContext.has_permission` 上做集合判断（`backend/app/gateway/authz.py:1023-1036`）；provider 求值发生在 `AuthMiddleware` 预求值（`backend/app/gateway/auth_middleware.py:214-226`）或 decorator 的 `_authenticate` 回退（`authz.py:1023-1026`）。
- `resolve_route_permissions` 对 13 个权限并行 `aauthorize`，单个失败只影响该项（fail_closed 排除该项，fail_open 保留该项）；只有 provider 解析失败才整体返回空/全量。provider 按配置签名缓存。`backend/app/gateway/authz.py:278-346`
- internal caller：`system_role="internal"` 被 pop，走 `default_role`（`authz.py:300-308`、`:455-475`）；细节见 [04 §5](../../enterprise-it-governance/authorization/04-rbac-permissions.md) 与 [02-internal-token.md](../../enterprise-it-governance/identity/02-internal-token.md)。
- PAT：启用授权时，路由权限先由 provider 求值，再与 PAT scopes 求交，只能缩小不能放大（`backend/app/gateway/auth_middleware.py:220-225`）；PAT 在扩展投影中永不 admin（`backend/app/gateway/app.py:1210-1227`）；细节见 [08-pat.md](../../enterprise-it-governance/identity/08-pat.md)。
- OIDC：认证方式不同，授权仍只看到同一 `Principal` 形状（`backend/packages/harness/deerflow/authz/principal.py:34-61`）；见 [07-sso-and-oidc.md](../../enterprise-it-governance/identity/07-sso-and-oidc.md) 与 [01-auth.md](../../enterprise-operations/security/01-auth.md)。
- 以上不是权限全表；13 项的语义、默认关闭和 `runs:cancel` 特例只在 [04](../../enterprise-it-governance/authorization/04-rbac-permissions.md) 维护。

## 宪章与约定

- 包内无独立 `AGENTS.md`（`backend/packages/harness/deerflow/authz/` 目录已核实）；写作纪律沿用 [根 README](../../README.md)：不改源码、结论带 `file:line`、缺口写三态。
- 设计权威是 [RFC](../../../docs/plans/2026-07-10-pluggable-authorization-rfc.md)（#4063）；阶段记录与回归取舍见 [implementation notes](../../../docs/plans/2026-07-10-pluggable-authorization-implementation-notes.md)（#5006 在 :461-494）；冲突以 v2.2.0 源码为准。
- 本篇锁定 v2.2.0；13 是当前基线计数，新增权限至少需同时更新 Gateway 常量、`_ALL_PERMISSIONS` 与 04 表。

## 相关目录

- [internals 父级](../README.md) — 内部机制子目录的总入口。
- [authorization](../../enterprise-it-governance/authorization/README.md) — 权限模型、Guardrail 与可配置性。
- [security](../../enterprise-operations/security/README.md) — 认证、沙箱隔离与信任边界。
- [capabilities](../capabilities/README.md) — 插件目录与扩展贡献点。
- [configuration](../configuration/README.md) — `authorization.*` 配置字段与热加载。
- [concepts/sandbox](../../concepts/sandbox/README.md) — sandbox 抽象与 lease 生命周期。

> 未核实：`examples/` 下的企业扩展是否全部通过 `require_plugin_management` / `afilter_plugin_pages` 收口；本页只核对了内核、Gateway、extension-api 与公开示例路由，未逐一审计每个扩展。
