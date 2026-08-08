---
title: "认证与授权"
description: "DeerFlow 有三条并行的认证路径，共享同一套 Gateway 中间件链。"
topics: [security, auth, isolation-defense]
---

# 认证与授权

DeerFlow 有三条并行的认证路径，共享同一套 Gateway 中间件链。

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

`app/gateway/csrf_middleware.py:17` — Double Submit Cookie 模式。

**原理：**
1. 登录/注册时，Gateway 生成 64 字节随机 token，同时设 cookie 和返回 body
2. 前端 JS 读取 cookie（HttpOnly=False），在后续 POST/PUT/DELETE/PATCH 请求的 `X-CSRF-Token` header 带上
3. CSRFMiddleware 用 `secrets.compare_digest()` 做常量时间比对

**为什么需要 JS 读取 cookie？** 因为是 double-submit — 前端必须主动把 cookie 值写到 header。跨域攻击者无法读取 cookie（SameSite=Strict），所以无法构造合法的 header。

**Origin 额外检查：** 登录/注册端点还额外验证 `Origin` header 必须在同源或 `GATEWAY_CORS_ORIGINS` 白名单内。无 `Origin` header 的请求（curl、mobile）允许通过。

**Proxy-aware：** 通过 `Forwarded`/`X-Forwarded-Proto`/`X-Forwarded-Host` 正确检测 HTTPS。

---

## Internal Gateway Token

`app/gateway/internal_auth.py:11` — 组件间信任。

```python
# 模块加载时自动生成（如果未设环境变量）
_DEER_FLOW_INTERNAL_AUTH_TOKEN = os.getenv("DEER_FLOW_INTERNAL_AUTH_TOKEN")
if not _DEER_FLOW_INTERNAL_AUTH_TOKEN:
    _DEER_FLOW_INTERNAL_AUTH_TOKEN = secrets.token_urlsafe(32)
```

**使用方：** `app/channels/manager.py:628` — ChannelManager 创建 SDK client 时：

```python
headers = {
    **create_internal_auth_headers(),          # X-DeerFlow-Internal-Token
    CSRF_HEADER_NAME: self._csrf_token,        # X-CSRF-Token
    "Cookie": f"{CSRF_COOKIE_NAME}={self._csrf_token}",  # csrf_token
}
```

三重保险：Internal token 跳过 JWT，CSRF header+cookie 通过 CSRFMiddleware。

**安全注意事项：**
- 自动生成的 token 不跨 worker 共享 — 多进程部署必须设统一的 `DEER_FLOW_INTERNAL_AUTH_TOKEN`
- 所有 IM channel 消息使用 `"default"` user_id — 无 per-IM-user 身份映射

---

## 登录限流

`app/gateway/routers/auth.py:149` — 进程内 IP 字典：

```
max 5 次失败 / 5 分钟 / IP
→ 超限返回 429 Too Many Requests
→ max 10,000 条记录，超出后淘汰最老
```

IP 来源：`request.client.host`。只有配置了 `AUTH_TRUSTED_PROXIES` 才信任 `X-Real-IP`，**不使用 `X-Forwarded-For`**（防伪造）。

**局限：** 进程内 dict，多 worker 共享同一 IP 可绕过。

---

## 权限模型

`app/gateway/authz.py:48` — 6 个权限定义：

```
threads:read · threads:write · threads:delete
runs:create · runs:read · runs:cancel
```

两个装饰器：
- `@require_auth` — 验证已认证（独立于 AuthMiddleware，可直接用于路由）
- `@require_permission("runs:cancel")` — 检查特定权限 + `owner_check`（验证 thread 归属）+ `require_existing`（对不存在返回 404 而非 403）

**默认状态：** 所有 authenticated 用户获得全部 6 个权限。**当 `authorization.enabled: true` 时**，路由权限改由 `authz.py::resolve_route_permissions()` 委托给 AuthorizationProvider（见下节），`threads:*`/`runs:*` 作为 `resource="route"` 请求求值，决策按 `authorization.fail_closed` 处理。

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
| `enforcement.py` | `filter_tools_by_authorization()` — Layer 1 共享过滤函数 |
| `tool_filter.py` | `apply_tool_authorization()` — Layer 1 便利包装（解析 provider + 构建 Principal + 过滤） |
| `runtime.py` | `resolve_authorization_provider()` — 唯一 provider 工厂入口 |

### 两层执行架构

```
Layer 1（组装时能力过滤）
  agent 构建阶段：apply_tool_authorization() → filter_resources(principal, "tool", candidates)
  → 角色无权使用的工具永不绑定、模型看不到、tool_search 也推不回（fail-closed）
  → 接入点：lead agent（agent.py bootstrap + default）、subagent（executor.py）、embedded client（client.py）

Layer 2（运行时执行拦截）
  middleware chain 中 LLMErrorHandlingMiddleware 之后：
  GuardrailMiddleware(GuardrailAuthorizationAdapter(provider))  ← authorization 外层
  GuardrailMiddleware(explicit_guardrail_provider)               ← guardrail 内层
  → 捕获动态资源 / 参数级限制
```

### AuthorizationProvider 协议（`provider.py:85`）

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

### 内置 RBAC provider（`rbac.py`）

- **deny 永远优先于 allow**（包括 allow 为 `"*"`/`True`）
- 未知/缺失角色抛 `ValueError`（不返回 allow），由 `fail_closed` 决定最终行为
- 资源类型显式映射：`"tool"→"tools"`、`"model"→"models"`、`"skill"→"skills"`、`"route"→"routes"`
- 策略构造时全量校验并编译为不可变结构（`frozenset`/`_ALL` sentinel），请求路径 O(1) membership
- 不区分 `action` 维度；`allow` 缺失 = 等同 `"*"`（deny 仍生效）；未知 policy key（如 typo）构造期拒绝

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

### Principal 与身份链路

**四种 HTTP identity source**：
1. Browser session（cookie-based JWT）
2. OIDC（Keycloak callback）
3. IM channel（internal auth header）
4. Trusted header（`X-DeerFlow-Owner-User-Id`）

`is_internal` 只来自服务端 `request.state.auth_source`，客户端提交的 `is_internal`/`authz_attributes`/`channel_user_id` 被清除（`_SERVER_OWNED_AUTHZ_CONTEXT_KEYS`）。`build_principal_from_context` 是唯一 Principal 构造器，Layer 1/2 共用。

## OAuth（占位）

`app/gateway/routers/auth.py:498` — GitHub 和 Google OAuth 端点声明存在但返回 `501 NOT IMPLEMENTED`。
