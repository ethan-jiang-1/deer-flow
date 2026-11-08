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
默认 5 次失败 / 5 分钟 / IP
→ 超限返回 429 Too Many Requests
→ max 10,000 条记录，超出后淘汰最老
```

🆕 v2.1.0-rc0：限流参数**可配置**（`auth.local.max_login_attempts` / `lockout_seconds`，#5110）：
- 最低 2 次——一次失败永不能锁死 IP（共享出口 IP 场景：公司代理/NAT 提高阈值）
- **live-read per login**：config 重载即生效，无需重启。降低 `lockout_seconds` 提前释放活动锁；收紧 `max_login_attempts` 保留已计数失败；延长 `lockout_seconds` 延长未过期锁但**不会复活已过期锁**

IP 来源：`request.client.host`。只有配置了 `AUTH_TRUSTED_PROXIES` 才信任 `X-Real-IP`，**不使用 `X-Forwarded-For`**（防伪造）。

**局限：** 进程内 dict，多 worker 共享同一 IP 可绕过。

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
