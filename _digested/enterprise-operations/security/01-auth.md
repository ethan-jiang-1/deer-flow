---
title: "认证与授权"
description: 'DeerFlow 有四条并行的认证路径（本地密码 / SSO-OIDC / PAT / 内部 token），共享同一套 Gateway 中间件链。'
topics: [security, auth, isolation-defense]
verified_against: v2.2.0
last_verified: 2026-11-08
---

# 认证与授权

DeerFlow 有四条并行的认证路径（本地密码 / SSO-OIDC / PAT / 内部 token），共享同一套 Gateway 中间件链。

## AuthMiddleware — 统一入口

`app/gateway/auth_middleware.py:75` 是请求的守门人。所有非公开路径的请求都经过它：

```
请求到达
  ├── ① 公开路径？ (/health, /docs, /api/v1/auth/login...) → 放行
  ├── ② 有 X-DeerFlow-Internal-Token 且 valid？→ 内部用户，跳过 JWT
  ├── ③ 有 access_token cookie？
  │     ├── 无 → 401 NOT_AUTHENTICATED
  │     └── 有 → JWT decode → DB 查 user → 检查 token_version
  │              → 设置 request.state.user + ContextVar
  └── ④ finally: reset_current_user() 清理
```

---

## JWT 认证

### Token 结构

`app/gateway/auth/jwt.py:12` — HS256，payload 非常简单：

```json
{"sub": "user-uuid", "exp": 1765432100, "iat": 1764827300, "ver": 1}
```

- Secret: `AUTH_JWT_SECRET` 环境变量，未设置则自动生成 `token_urlsafe(32)` 存到 `.jwt_secret`（0600 权限）
- 过期: 默认 7 天，可配 1-30 天
- `ver`: token_version — 改密时递增，所有旧 token 立即失效

### 密码安全

`app/gateway/auth/password.py:28` — 两版哈希共存：

```
v1 (legacy): bcrypt(plain_password)
v2 (current): bcrypt(base64(sha256(password)))
```

格式前缀 `$dfv{N}$` 区分版本。`verify_password()` 自动识别，`needs_rehash()` 在登录时检测并透明升级。40 个常见密码（"password123", "admin123"...）直接拒绝。

`app/gateway/auth/config.py:35` — secret 生成/加载：

```python
with open(secret_path, "w", opener=lambda p, f: os.open(p, os.O_CREAT | os.O_TRUNC, 0o600)) as f:
    f.write(secrets.token_urlsafe(32))
```

---

## CSRF 保护

`app/gateway/csrf_middleware.py:216` 的 `CSRFMiddleware` — Double Submit Cookie 模式。

**原理：**
1. 登录/注册时，Gateway 生成 64 字节随机 token（`CSRF_TOKEN_LENGTH = 64`，`csrf_middleware.py:26`；`generate_csrf_token()` 在 `:36`），同时设 cookie 和返回 body
2. 前端 JS 读取 cookie（HttpOnly=False），在后续 POST/PUT/DELETE/PATCH 请求的 `X-CSRF-Token` header 带上
3. CSRFMiddleware 用 `secrets.compare_digest()` 做常量时间比对

**为什么需要 JS 读取 cookie？** 因为是 double-submit — 前端必须主动把 cookie 值写到 header。跨域攻击者无法读取 cookie（SameSite=Strict），所以无法构造合法的 header。

**Origin 额外检查：** 登录/注册端点还额外验证 `Origin` header 必须在同源或 `GATEWAY_CORS_ORIGINS` 白名单内。无 `Origin` header 的请求（curl、mobile）允许通过。

**Proxy-aware：** 通过 `Forwarded`/`X-Forwarded-Proto`/`X-Forwarded-Host` 正确检测 HTTPS（`is_secure_request()`，`csrf_middleware.py:31`）。

---

## Internal Gateway Token

`app/gateway/internal_auth.py:20` 的 `_load_internal_auth_token()` — 组件间信任。

```python
INTERNAL_AUTH_ENV_VAR = "DEER_FLOW_INTERNAL_AUTH_TOKEN"
INTERNAL_OWNER_USER_ID_HEADER_NAME = "X-DeerFlow-Owner-User-Id"
INTERNAL_SYSTEM_ROLE = "internal"

def _load_internal_auth_token() -> str:
    token = os.environ.get(INTERNAL_AUTH_ENV_VAR)
    if token:
        return token
    return secrets.token_urlsafe(32)

_INTERNAL_AUTH_TOKEN = _load_internal_auth_token()   # 模块加载时求值一次
```

三个公开函数：`create_internal_auth_headers(*, owner_user_id=None)`（`:30`）、`is_valid_internal_auth_token(token)`（`:38`）、`get_internal_user(owner_user_id=None)`（`:43`）；另有 `get_trusted_internal_owner_user_id(request)`（`:71`）供宿主读取**仅由服务端**设置的 owner 头。

**使用方：** `app/channels/manager.py:2318` — `ChannelManager._get_client()` 创建 `langgraph_sdk` client 时：

```python
headers={**create_internal_auth_headers(), **self._csrf_headers()}
```

`_csrf_headers()`（`manager.py:2300`）的 docstring 说明了为什么要同时带 CSRF 对："Internal auth does not exempt a request from `CSRFMiddleware`, so every Gateway mutation the manager sends must carry this pair."

三重保险：Internal token 跳过 JWT，CSRF header+cookie 通过 CSRFMiddleware。

**安全注意事项：**
- 自动生成的 token 不跨 worker 共享 — 多进程部署必须设统一的 `DEER_FLOW_INTERNAL_AUTH_TOKEN`
- 所有 IM channel 消息使用 `"default"` user_id — 无 per-IM-user 身份映射

---

## 登录限流

`app/gateway/routers/auth.py:149` — 进程内 IP 字典：

```
默认 5 次失败 / 5 分钟 / IP
→ 超限返回 429 Too Many Requests
→ max 10,000 条记录，超出后淘汰最老
```

🆕 v2.1.0-rc0：限流参数**可配置**（`auth.local.max_login_attempts` / `lockout_seconds`，#5110）：
- 最低 2 次——一次失败永不能锁死 IP（共享出口 IP 场景：公司代理/NAT 提高阈值）
- **live-read per login**：config 重载即生效，无需重启。降低 `lockout_seconds` 提前释放活动锁；收紧 `max_login_attempts` 保留已计数失败；延长 `lockout_seconds` 延长未过期锁但**不会复活已过期锁**

IP 来源：`request.client.host`。只有配置了 `AUTH_TRUSTED_PROXIES` 才信任 `X-Real-IP`，**不使用 `X-Forwarded-For`**（防伪造）。

**存储：** 默认 `auth.local.throttle_storage=auto`——`database.backend` 为 sqlite/postgres 时计数与锁禁写共享表，所有 Gateway 副本对同一 IP 使用同一份锁禁；只有 `memory` 档才是进程内 dict（N 个副本 = N 倍尝试机会）。详见 [identity/09-login-throttle.md](../../enterprise-it-governance/identity/09-login-throttle.md)。

---

## 🆕 Personal Access Tokens（PAT，v2.1.0-rc0 #5041）

程序化 API 访问的长期令牌，补齐 JWT session 之外的第二种认证方式：

- 核心：`app/gateway/auth/pat.py`（签发/校验/吊销），持久化 `persistence/personal_access_tokens/`（model + sql），migration `0017_personal_access_tokens`
- 用途：脚本、CI、SDK 等非浏览器调用方（此前只能走登录 session + CSRF）
- 前端 Settings 里管理（签发时一次性展示，服务端只存哈希）

### 仓储层契约（`PersonalAccessTokenRepository`）

`deerflow/persistence/personal_access_tokens/sql.py:25`，每个方法各开一个短 session。**明文 `dfp_…` token 由 app 层生成、只返回一次；仓储只持久化调用方传入的 SHA-256 digest**（模块 docstring `sql.py:1-6`）。

| 维度 | 契约 | 证据 |
|------|------|------|
| 存储内容 | 只存 `token_digest`（64 字符 hex）；`scopes` 在 `create` 里 `sorted()` 后存 JSON 列 | `sql.py:41-63`；`model.py:21-27` |
| 唯一索引 | `ix_personal_access_tokens_token_digest` 是**命名 unique index**（不是列级 `unique=True`）——目的是让 `create_all` 的产出与 migration `0017` 完全一致，bootstrapped DB 也能正常 downgrade | `model.py:16`、`:21-25` |
| 摘要算法与比对 | app 层 `pat_token_digest = sha256(token).hexdigest()`；校验时先按 digest 查行，再 `hmac.compare_digest(stored_digest, digest)` **常量时间**复核 | `app/gateway/auth/pat.py:165-174`、`:210-211` |
| 吊销 | `revoke(pat_id, user_id)`：条件 UPDATE（`id` + `user_id` + `revoked_at IS NULL`）置 `revoked_at`，`rowcount != 0` → True；**owner 过滤在 SQL 里**，非属主/不存在都返回 False（对外表现为 404，不泄露存在性）。软删除——行保留供审计 | `sql.py:89-102` |
| 过期 | 在**读取时**判定：`get_active_by_digest` 对 `revoked_at is not None` 或 `expires_at <= now` 返回 `None`（SQLite 读回丢 tzinfo，先 `replace(tzinfo=UTC)` 再比较）。所以吊销/过期行永远无法通过认证，但仍存在于 `list_for_user` 输出中 | `sql.py:65-82` |
| 列表 | `list_for_user(user_id)` 按 `created_at desc`，**不过滤 revoked/expired** | `sql.py:84-87` |
| `last_used_at` 节流 | `touch_last_used(pat_id)` 按 token 进程内节流（`last_used_write_interval_seconds` 默认 300s），**永不抛异常**：写失败只记 DEBUG 并**回滚节流窗口**让下次立即重试；缓存超 4096 条整体清空以界定内存 | `sql.py:26`、`:104-132` |
| 时间戳 | 输出统一 `coerce_iso`（SQLite 读回丢 tzinfo，归一成 tz-aware） | `sql.py:31-39` |
| 认证端到端 | 分支点在 `AuthMiddleware`：`authorization is not None` 才进 PAT 路径（无头则继续看 session cookie），因此**present-but-invalid 的 Bearer 是硬 401，绝不静默回落 cookie**（这也是 CSRF Bearer skip 安全的前提；`is_auth_disabled()` 优先于该分支）。`authenticate_pat()` 内部把所有 token 判定失败——非 `dfp_` 前缀、store 未配置、查不到行、属主用户已删、digest 不符——**统一成 401 `"Invalid token"`**，不暴露是哪一步失败（防响应 oracle）；基础设施异常照常抛出并 fail closed；成功才 `touch_last_used` 并返回 `(user, frozenset(scopes))`。`extract_bearer_token` 对非 Bearer scheme/空凭证返回 `""`（≠ 缺失），所以它们走 401 而不是回落 | `pat.py:177-222`；`auth_middleware.py:110-141` |
| 用户删除的连带语义 | 不靠 FK cascade：删用户后 PAT 行仍在，但 `get_user()` 返回 None → 401（`pat.py:216-220`） | — |
| scope 校验 | `validate_scopes()` 拒绝未知 scope 与空列表，返回去重排序后的列表 | `pat.py:225-233` |

---

## 🆕 Authz Phase 4 — UI 权限收敛（v2.1.0-rc0）

- `GET /api/v1/auth/me` 现在返回 **effective route permissions**（#5228）——前端不再猜权限
- thread-delete / run-cancel UI 按 effective permissions 门控（#5294）：无权限的用户看不到可点的危险按钮，而不是点了才 403

---

## 权限模型

`app/gateway/authz.py:63-86` — 13 个权限定义：

```
threads:read · threads:write · threads:delete
runs:create · runs:read · runs:cancel
projects:read · projects:write · projects:delete
memory:read · memory:write
agents:read · agents:write
```

两个装饰器：
- `@require_auth` — 验证已认证（独立于 AuthMiddleware，可直接用于路由）
- `@require_permission("runs:cancel")` — 检查特定权限 + `owner_check`（验证 thread 归属）+ `require_existing`（对不存在返回 404 而非 403）

**默认状态：** 所有 authenticated 用户获得全部 13 个权限。**当 `authorization.enabled: true` 时**，路由权限改由 `authz.py::resolve_route_permissions()` 委托给 AuthorizationProvider（见下节），`threads:*`/`runs:*` 作为 `resource="route"` 请求求值，决策按 `authorization.fail_closed` 处理。

---

## OIDC/SSO 🆕

`app/gateway/auth/session_cookie.py` — Generic OIDC authentication with Keycloak support：

- **Session cookie**：`HttpOnly access_token` cookie。HTTPS/trusted-forwarded HTTPS 和 direct-host localhost 下持久化；public HTTP sandbox URL 降级为 session cookie
- **"Keep me signed in"**：登录表单 `remember_me` flag。`SessionCookiePolicy` 持久化 cookie max_age；CSRF cookie 同步过期。小 `HttpOnly` preference cookie 保留用户选择
- **Logout**：清除所有 auth cookie，不重新发放 CSRF cookie

## AuthorizationProvider — 可插拔鉴权（已落地）🆕

`packages/harness/deerflow/authz/` 与 `guardrails/` 平级（非子模块）。核心设计：**一个 policy、两层执行**。

| 模块 | 职责 |
|------|------|
| `provider.py` | `AuthorizationProvider` Protocol + 数据类（`Principal`, `AuthzRequest`, `AuthzDecision`, `AuthzReason`） |
| `rbac.py` | `RbacAuthorizationProvider` — 内置 RBAC provider |
| `adapter.py` | `GuardrailAuthorizationAdapter` — 把 provider 适配为 `GuardrailProvider` 协议 |
| `principal.py` | `build_principal_from_context()` — 唯一 Principal 构造器（Layer 1/2 共用） |
| `enforcement.py` | `filter_tools_by_authorization()` + 🆕 `filter_resources_by_authorization()` — Layer 1 共享过滤函数 |
| `tool_filter.py` | `apply_tool_authorization()` — Layer 1 便利包装（解析 provider + 构建 Principal + 过滤） |
| `runtime.py` | `resolve_authorization_provider()` — 唯一 provider 工厂入口 |
| 🆕 `skill_filter.py` | 技能面的 Layer 1：`resolve_skill_authorization()` / `filter_available_skills_by_authorization()` |
| 🆕 `plugin_authz.py` | 插件面 Layer 2：`enforce_plugin_action` / `enforce_plugin_management` + 异步变体 + `afilter_*` |
| 🆕 `plugin_targets.py` | 插件授权目标串的**唯一**编码器（3 个构造器，禁止字符串拼接） |
| 🆕 `activation_decisions.py` | `ActivationDecisions` — Layer 1 与 Layer 2 之间的一次性判定传递 |

### 两层执行架构

```
Layer 1（组装时能力过滤）
  agent 构建阶段：apply_tool_authorization() → filter_resources(principal, "tool", candidates)
  → 角色无权使用的工具永不绑定、模型看不到、tool_search 也推不回（fail-closed）
  → 接入点：lead agent（agent.py bootstrap + default）、subagent（executor.py）、embedded client（client.py）
  🆕 技能面同构：filter_available_skills_by_authorization() 直接过滤 available_skills 名单
     （在磁盘 I/O 之前的 name set 上跑，因此同时约束 describe_skill catalog 与 slash 激活）
  🆕 插件面同构：afilter_plugin_pages / afilter_plugin_management

Layer 2（运行时执行拦截）
  middleware chain 中 LLMErrorHandlingMiddleware 之后：
  GuardrailMiddleware(GuardrailAuthorizationAdapter(provider))  ← authorization 外层
  GuardrailMiddleware(explicit_guardrail_provider)               ← guardrail 内层
  → 捕获动态资源 / 参数级限制
  🆕 插件 action 面不在 middleware 里：Gateway 路由层在**读 body 之前**调用
     authorize_plugin_action_for_request()（app/gateway/authz.py:733）
```

### AuthorizationProvider 协议（`provider.py:86`）

```python
@runtime_checkable
class AuthorizationProvider(Protocol):
    name: str
    def authorize(self, request: AuthzRequest) -> AuthzDecision: ...
    async def aauthorize(self, request: AuthzRequest) -> AuthzDecision: ...
    def filter_resources(self, principal, resource_type, candidates: list[str]) -> list[str]: ...
```

- `filter_resources` 是**必需方法**（非可选默认）——用于 Layer 1 批量可见性过滤
- `resource`/`action`/`target` 是自由字符串（非枚举），新资源类型无需 schema 变更
- Provider 通过 `resolve_variable()` class-path 加载（与 model/tool/sandbox/guardrail 同机制）
- 🆕 docstring 新增两条硬约束（`provider.py:126-131`）：**答案只能收窄 `candidates`**（调用方一律与提问时的列表取交集，点一个从未成为候选的对象拿不到任何权限）；**实现必须线程安全**（异步调用方会把同步方法 offload 到 worker 线程，它可能与 event loop 并发运行）

### 内置 RBAC provider（`rbac.py`）

- **deny 永远优先于 allow**（包括 allow 为 `"*"`/`True`）
- 未知/缺失角色抛 `ValueError`（不返回 allow），由 `fail_closed` 决定最终行为
- 资源类型显式映射（`_RESOURCE_POLICY_KEYS`）：`"tool"→"tools"`、`"model"→"models"`、`"skill"→"skills"`、`"sandbox"→"sandbox"`、`"mcp_server"→"mcp_servers"`、`"route"→"routes"`、🆕 `"plugin_action"→"plugin_actions"`、🆕 `"plugin_management"→"plugin_management"`
- 策略构造时全量校验并编译为不可变结构（`frozenset`/`_ALL` sentinel），请求路径 O(1) membership
- 不区分 `action` 维度；`allow` 缺失 = 等同 `"*"`（deny 仍生效）；未知 policy key（如 typo）构造期拒绝
- 🆕 **没有 policy key 的 resource = 不受限**：给资源定义了 policy key，但某个 role 没写这一行 → 对该资源无限制（向后兼容"启用 authorization 但没列出新 key"的部署）
- 🆕 `plugin_management` 是**自映射**（和 `sandbox` 一样）合法；`plugin_action` 不是——把它当 config key 写在 `authorization:` 下会在**构造期**被拒
- 🆕 `known_roles` 属性（`rbac.py:133`）供 `app/gateway/authz.py` 的 `assignable_role_names()` 枚举，管理员分配角色时不能分配不存在的 role

### 配置（`config.yaml`）

```yaml
authorization:
  enabled: false                    # 默认关闭（向后兼容：所有已认证用户获得全部权限）
  fail_closed: true                 # provider 异常/未知身份 → deny
  default_role: user                # user_role 为 None 时回退（内置 RBAC 需要此角色）
  provider:
    use: deerflow.authz.rbac:RbacAuthorizationProvider
    config:
      roles:
        admin:
          tools: {allow: "*"}
          routes: {allow: "*"}
        user:
          tools: {allow: "*", deny: ["update_agent"]}
          routes: {allow: "*"}
        guest:
          tools: {allow: ["web_search", "read_file"]}
          routes: {allow: ["threads:read", "runs:read"]}
```

配置可热更新（`AuthorizationConfig` 不在 `STARTUP_ONLY_FIELDS`）。

### 🆕 插件资源的 policy（2.2.0）

```yaml
authorization:
  enabled: true
  roles:
    admin:
      tools: {allow: "*"}
      routes: {allow: "*"}
    analyst:
      tools: {allow: "*", deny: ["update_agent"]}
      routes: {allow: "*"}
      plugin_actions: ["acme.reports/run-report"]                  # 单个 action
      plugin_management: ["acme.reports/permissions.read"]         # 只读管理面
    viewer:
      plugin_management: ["acme.reports/permissions.read", "acme.reports/permissions.write"]
```

目标串由 `authz/plugin_targets.py` 的三个构造器生成，是**授权唯一 key**：

| 构造器 | 行 | 形状 | 什么时候用 |
|--------|-----|------|-----------|
| `plugin_action_target(namespace, action)` | `authz/plugin_targets.py:61` | `<namespace>/<action>` | 一次 backend action 调用 |
| `plugin_management_target(namespace, part)` | `authz/plugin_targets.py:77` | `<namespace>/permissions.read` 或 `/permissions.write` | 插件自有管理路由 |
| `plugin_page_target(namespace, surface)` | `authz/plugin_targets.py:64` | `<namespace>/<surface>` | 声明式页面（**尚未接线**，见 [06-extension-boundary.md](06-extension-boundary.md)） |

字符集是硬约束：namespace `[a-z][a-z0-9_.-]{0,95}`、action `[a-z][a-z0-9_-]{0,63}`（**允许 `-` 与 `_`，不允许 `.`**）、surface `[a-z][a-z0-9-]{0,63}`。不合法输入抛 `PluginTargetError`（`plugin_targets.py:24`），不静默降级。

### 🆕 技能面的 Layer 1 过滤（2.2.0）

`authz/skill_filter.py`（237 行）把 Layer 1 从"工具"扩到"技能"：

- `resolve_skill_authorization()`（`:94`）：`authorization.enabled` 不是 `True`、或 provider 解析不出来 → 返回 **`None`**，调用方据此理解为"无额外强制"（= 授权前的行为）。
- `filter_available_skills_by_authorization()`（`:121`）：在 `available_skills` **名字集合**上过滤（不是加载后的 `Skill` 对象），所以在**磁盘 I/O 之前**就跑，同时约束 `describe_skill` catalog 与 slash 激活 middleware。
- 边界语义：`available_skills=None` = agent 没有 allowlist（全部启用技能），此时会**解析全部启用技能名**再过滤；`available_skills=set()` = 这个 agent 什么技能都不许用，**原样保留**。
- **候选解析失败不能绕过授权**：`_all_configured_skill_names()` 抛异常时，`fail_closed` 为真返回 `set()`、为假返回原集合——**绝不**返回 `None`（那会让每个技能都变成可激活）。
- provider 结果做**防御性交集**：只校验了 `list[str]`，所以拿 `allowed_names` 与 `candidates` 求交，防一个写坏的自定义 provider 注入额外技能名把显式 allowlist 撑大。这与 `filter_resources_by_authorization` 同一条规则。
- 接入点：`subagents/executor.py:1409` 的 `_filter_available_skills()` 与 `:1440` 的 `_resolve_skill_authorization()`。

### 🆕 `ActivationDecisions`（`authz/activation_decisions.py`，87 行）

Layer 1 已经用 provider 过滤过技能，Layer 2 在真正激活时还要再问一次——问题是**不能在同一次 tool call 里再打一次 provider**（Layer 2 是同步路径，provider 可能在慢 I/O 上）。

`ActivationDecisions` 的语义：

| 情形 | 行为 |
|------|------|
| 命中 Layer 1 记下的判定 | 直接复用，无 provider 调用 |
| 未命中 | 按**当前策略**失败（不是默认 allow），并记 `WARNING`：`prepass/consumer divergence — not a policy denial` |
| 任何情形 | **绝不**在同步路径上调用 provider |

这条 WARNING 的措辞是刻意的：它区分"策略拒绝"与"两阶段不一致"，后者是宿主 bug 的信号而不是安全问题。追溯 #4541，经过四轮 review。

### Principal 与身份链路

**四种 HTTP identity source**：
1. Browser session（cookie-based JWT）
2. OIDC（Keycloak callback）
3. IM channel（internal auth header）
4. Trusted header（`X-DeerFlow-Owner-User-Id`）

`is_internal` 只来自服务端 `request.state.auth_source`，客户端提交的 `is_internal`/`authz_attributes`/`channel_user_id` 被清除（`_SERVER_OWNED_AUTHZ_CONTEXT_KEYS`）。`build_principal_from_context` 是唯一 Principal 构造器，Layer 1/2 共用。

**🆕 扩展面的 principal 投影（2.2.0）**：`app/gateway/app.py:1198` 的 `_resolve_extension_principal` 把宿主 auth context **投影**成中性的 `ExtensionPrincipal`（"问题"而不是"句柄"——插件只能问"我是谁 / 我是不是管理员 / 我是什么角色"，拿不到宿主 `AuthContext` 内部）。

关键规则：**PAT 永不带 admin**（`app.py:1214-1221`）。PAT 调用者即使底层用户的 `system_role == "admin"`，`is_admin` 也置 `False`，且 `roles` 元组被清空（不只是去掉 `admin` 一项）——否则管理员自己签发的 PAT 就能通过 `require_admin` 把管理能力带回来。这与 `deps.is_admin_user` 的 PAT guard 是同一策略的两处实现。

同一族的约束还出现在 `app/gateway/extension_agent_runs.py:62` 的 `bind()`：只接受 `AUTH_SOURCE_SESSION` 与 `AUTH_SOURCE_AUTH_DISABLED`，**PAT 与 internal-owner 委托都被拒**——原话是 "PAT revocation and internal-owner delegation need separate durable grants. Never turn either into an unrestricted session capability."。理由是 PAT 撤销无法立即反映到一个可能被长期持有的句柄上。

**🆕 PAT 的路由白名单另有一处独立边界**：`app/gateway/auth/pat.py:60` 的 `_PAT_ROUTE_RULES` 是**默认拒绝**的枚举表——`/api/plugins/*`、`/api/skill-mutations/*`、`/api/v1/admin/*` 都不在里面，所以 PAT **够不到**插件动作面与 skill mutation 管理面，即使它持有相应 scope。`is_pat_allowed_route()`（`pat.py:130`）只做 method + 正则匹配，不做优先级回退。

## OAuth（占位）

`app/gateway/routers/auth.py:498` — GitHub 和 Google OAuth 端点声明存在但返回 `501 NOT IMPLEMENTED`。
