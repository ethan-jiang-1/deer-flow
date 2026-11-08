---
title: "SSO / OIDC 接入"
description: "企业 SSO 的完整契约：discovery、授权码流、PKCE S256、nonce、provisioning 四策略、sso_failed 失败契约。以及它与本地注册之间的政策断点。"
topics: [governance, identity, sso, oidc]
---

# SSO / OIDC 接入

企业接入的第一问通常是「能不能接我们的 IdP」。DeerFlow v2.2.0 支持任意 OIDC 兼容
provider（Keycloak、Azure AD、Okta、Google），走标准授权码流。

## 1. 能力概览

| 能力 | 状态 | 证据 |
|---|---|---|
| OIDC discovery | 有，TTL 300s 缓存 | `app/gateway/auth/oidc.py` |
| JWKS 缓存 | 有，同一 TTL | `app/gateway/auth/oidc.py` |
| 授权码流 | 有 | `app/gateway/routers/auth.py:954`（`/oauth/{provider}`）、`:1030`（`/callback/{provider}`） |
| PKCE S256 | **默认开** | `config.example.yaml:3601` `pkce_enabled: true` |
| nonce 校验 | **默认开** | `config.example.yaml:3602` `nonce_enabled: true` |
| 多 provider 并存 | 有，每个 provider 一组配置 | `auth.oidc.providers.<id>` |
| 自动建号 | 有，可关 | `app/gateway/auth/user_provisioning.py:87` |
| 邮箱域名白名单 | 有 | `app/gateway/auth/user_provisioning.py:67-69` |
| 强制已验证邮箱 | **默认开** | `app/gateway/auth/user_provisioning.py:52` |
| 管理员自动提升 | 有，按邮箱列表 | `app/gateway/auth/user_provisioning.py:93`、`:117-120` |
| 失败重定向契约 | 有，`sso_failed` | `app/gateway/routers/auth.py:1051`、`:1107`、`:1118` |

这些能力**此前在本语料中一处未提**，是覆盖缺口而非能力缺口。

## 2. 配置契约

```yaml
auth:
  oidc:
    enabled: true
    frontend_base_url: https://deerflow.example.com  # 生产必须设
    providers:
      keycloak:
        display_name: Keycloak
        issuer: https://keycloak.example.com/realms/deerflow
        client_id: deerflow
        client_secret: $KEYCLOAK_CLIENT_SECRET
        scopes: [openid, email, profile]
        token_endpoint_auth_method: client_secret_post
```

| 键 | 必填 | 说明 |
|---|---|---|
| `issuer` | 是 | discovery 起点，拼 `/.well-known/openid-configuration` |
| `client_id` / `client_secret` | 是 | `client_secret` 支持 `$ENV_VAR` 引用 |
| `redirect_uri` | 推荐 | 缺省时按请求自推导；**生产必须显式设**并与 IdP 侧一致 |
| `frontend_base_url` | 生产必填 | 回调后重定向的前端地址；否则失败重定向可能指向 localhost |
| `scopes` | 是 | 至少含 `openid` |
| `token_endpoint_auth_method` | 否 | Keycloak confidential client 用 `client_secret_post` |

回调 URL 形如 `https://<gateway>/api/v1/auth/callback/<provider>`，
需在 IdP 侧登记为合法 redirect URI（`config.example.yaml:3528` 给的例子是
`http://localhost:8001/api/v1/auth/callback/keycloak`）。

## 3. 安全机制

### 3.1 PKCE 与 nonce 默认开启

`config.example.yaml:3601-3602` 两个键默认 `true`：

- **PKCE（S256）**：授权码被截获也无法换取 token。`app/gateway/auth/oidc_state.py:75` 的
  `compute_code_challenge` 实现 S256。
- **nonce 校验**：ID token 必须回带授权请求里的 nonce，防重放。

这两项是配置契约里的默认值，**不是可选的加固建议**——企业评审时可直接作为证据引用。

### 3.2 state 的存储与时限

`app/gateway/auth/oidc_state.py:20-21`：

```python
OIDC_STATE_COOKIE_PREFIX = "df_oidc_state_"
OIDC_STATE_MAX_AGE = 300  # 5 minutes
```

state 存在**签名 cookie**里（`app/gateway/auth/oidc_state.py:39` `_sign_state_payload`），
不落服务端存储——所以多副本部署无需共享 session。代价是 state 有效期固定 5 分钟，
不适合多跳 IdP 链路（企业常见于跨域联邦），超时会得到 `sso_failed`。

### 3.3 失败契约

OIDC 错误统一走**重定向**而非裸 500（`app/gateway/auth/oidc.py:74` 注释明确这是设计意图）：

```python
# routers/auth.py:1118
error_code = error_map.get(exc.status_code, "sso_failed")
```

`app/gateway/auth/oidc.py:69` 的 `_json_object` 在 provider 返回非 JSON 时抛 502 而非 500，
同样是为了「keep the `sso_failed` redirect contract」（`app/gateway/auth/oidc.py:377`、`:383`）。

**对企业运维的含义**：SSO 故障表现为前端 `?error=sso_failed`，而非 5xx
——监控要盯这个查询参数，不能只盯 HTTP 状态码。

## 4. Provisioning 策略

`user_provisioning.py` 是 SSO 登录后决定「要不要建号、建成什么角色」的地方。
四个策略按顺序生效：

| # | 策略 | 默认 | 行为 | 证据 |
|---|---|---|---|---|
| 1 | `require_verified_email` | **true** | 邮箱未验证直接拒绝 | `:52` |
| 2 | `allowed_email_domains` | 无（不限制） | 域名不在表内拒绝 | `:67-69` |
| 3 | `auto_create_users` | **true** | 首次登录自动建号；关掉则仅限已有账号 | `:87` |
| 4 | `admin_emails` | `[]` | 命中的邮箱直接授 admin | `:93`、`:117-120` |

### 4.1 企业部署的实际形态

三个策略组合决定行为：

| 场景 | `auto_create_users` | `allowed_email_domains` | 效果 |
|---|---|---|---|
| 全公司开放 | `true` | `["corp.example.com"]` | 本公司邮箱自动开号 |
| 邀请制 | `false` | 任意 | 只有管理员先建好账号的人能进 |
| 强管控 | `false` | `["corp.example.com"]` | 双重限制 |

### 4.2 `admin_emails` 是启动特权通道

`_resolve_role`（`:117-120`）是简单的大小写不敏感字符串比对：

```python
return "admin" if any(e.lower() == email_lower for e in admin_emails) else "user"
```

**没有**「首次登录后取消」机制——只要邮箱还在列表里，每次登录都重新授 admin。
移除列表项后，已授的 admin 角色**不会被自动降级**（角色存在库里，
provisioning 只管登录时的赋值）。

## 5. 政策断点：SSO 策略不约束本地注册

这是 `config.example.yaml:3529-3535` 用**整段注释**警告的陷阱，值得完整引用：

> Self-registration via `POST /api/v1/auth/register` is open by default: anyone
> who can reach the Gateway may create a regular user account.
>
> The OIDC provisioning policy below (`allowed_email_domains`, `require_verified_email`,
> `auto_create_users`) is enforced only in the SSO callback. It **does NOT constrain
> local registration**, so on an SSO-provisioned deployment leaving this open lets a
> visitor create an account outside that policy. Set `allow_registration: false` there.

**具体后果**：你配了 `allowed_email_domains: ["corp.example.com"]`，
以为「只有公司邮箱能注册」，但任意访客仍可通过 `/api/v1/auth/register`
用任何邮箱自建普通账号。SSO 策略只作用于 SSO 回调路径。

**缓解**：`auth.local.allow_registration: false`（`packages/harness/deerflow/config/auth_config.py:101`）。

**不会锁死自己**：同一段注释说明首个 admin 永远通过 `/initialize` 创建
（`app/gateway/routers/auth.py:820`），与此开关无关：

> The first admin account is always created through `/initialize` regardless of this
> setting, so turning it off cannot lock you out of a fresh install.

## 6. 缺口

| 缺口 | 状态 | 边界 |
|---|---|---|
| SCIM 自动置备/回收 | **无** | 只有登录时（JIT）provisioning；离职需手工停用，无 IdP 驱动的账号销毁 |
| 组/角色映射 | **无** | 角色只有 `admin`/`user` 两档，`admin_emails` 是邮箱硬比对，不读 IdP 的 group claim |
| 后端登出（RP-initiated logout） | **无** | 本地登出清 cookie，不回跳 IdP 的 `end_session_endpoint`；IdP 侧会话仍存活 |
| 多 IdP 的租户归属 | **部分** | 支持多 provider 并存，但账号与 provider 无绑定关系——同一邮箱从两个 IdP 登录会落到同一账号 |
| state 有效期 | **固定 5 分钟** | `app/gateway/auth/oidc_state.py:21`，不可配；长链路联邦 IdP 可能超时 |

## 7. 与其他章节的关系

- 本地注册与密码策略：[10-registration-policy.md](10-registration-policy.md)
- 登录限速（含多副本共享锁禁）：[09-login-throttle.md](09-login-throttle.md)
- 三条认证路径的分工：[01-authentication-model.md](01-authentication-model.md)
- 运维操作手册（IdP 侧建 client 的步骤）：`backend/docs/SSO.md`
