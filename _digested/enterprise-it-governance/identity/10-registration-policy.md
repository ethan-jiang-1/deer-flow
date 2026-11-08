---
title: "注册策略"
description: 'allow_registration 这一个布尔值决定访客能否自建账号。它与 SSO provisioning 策略互不覆盖，是配置注释里用整段文字警告的陷阱。'
topics: [governance, identity, registration]
verified_against: v2.2.0
last_verified: 2026-11-08
---

# 注册策略

`auth.local.allow_registration` 是一个布尔值，但它的作用域**比看起来窄**——
这是 SSO 部署最容易出错的单点。

## 1. 键与默认值

| 键 | 默认 | 约束 | 证据 |
|---|---|---|---|
| `auth.local.allow_registration` | **`true`（开放）** | 布尔 | `packages/harness/deerflow/config/auth_config.py:101-107` |

默认开放的含义（`packages/harness/deerflow/config/auth_config.py:103-104`）：

> Allow visitors to self-register a local account via `POST /api/v1/auth/register`.

只要能访问 Gateway，任何人都能 `POST /api/v1/auth/register`（`app/gateway/routers/auth.py:488`）
创建一个普通账号。

## 1.1 密码本身的防线

注册与改密共用 `_validate_strong_password`（`app/gateway/routers/auth.py:117-127`），
该函数只检查常见密码黑名单；最小长度由两个请求模型的 `Field(min_length=8)` 保证
（`:134` 注册、`:144` 改密），不在该函数内。

| 检查 | 值 | 证据 |
|---|---|---|
| 最小长度 | 8 位 | `app/gateway/routers/auth.py:134`（注册）、`:144`（改密） |
| 常见密码黑名单 | 36 条，大小写不敏感 | `app/gateway/routers/auth.py:64-113`、`:114` |

`app/gateway/routers/auth.py:59-63` 的注释明确了这道防线的定位与边界：

> Top common-password blocklist. Drawn from the public SecLists "10k worst
> passwords" set, lowercased + length>=8 only (shorter ones already fail
> the min_length check). Kept tight on purpose: this is the **lower bound**
> defense, not a full HIBP / passlib check, and runs in-process per request.

**边界**：36 条是精选子集，不是完整的 10k 列表；不做字符类别要求；
不做 HIBP 泄露库查询；不提供可配置的策略强度。要更强的密码策略，
只能在 IdP 侧（SSO）实现——本地密码通道的强度上限是固定的。

## 2. 作用域陷阱：它管本地注册，不管 SSO

`packages/harness/deerflow/config/auth_config.py:105-107` 的字段描述直接点明：

> Set to false when accounts are provisioned exclusively through SSO — the OIDC
> provisioning policy (`allowed_email_domains`, `require_verified_email`,
> `auto_create_users`) **does not apply** to local registration.

`config.example.yaml:3529-3535` 用整段注释展开了这个后果：

> Self-registration via `POST /api/v1/auth/register` is open by default: anyone
> who can reach the Gateway may create a regular user account.
>
> The OIDC provisioning policy below (`allowed_email_domains`, `require_verified_email`,
> `auto_create_users`) is enforced **only in the SSO callback**. It does NOT constrain
> local registration, so on an SSO-provisioned deployment leaving this open lets a
> visitor create an account outside that policy. Set `allow_registration: false` there.

### 2.1 具体失效场景

假设企业这样配置 SSO：

```yaml
auth:
  oidc:
    providers:
      corp:
        allowed_email_domains: [corp.example.com]
        require_verified_email: true
```

**预期**：「只有公司邮箱能开号」。

**实际**：访客访问 `POST /api/v1/auth/register`，用任意邮箱（甚至外域邮箱）
自建普通账号成功。`allowed_email_domains` 只在 SSO 回调路径里被检查
（`app/gateway/auth/user_provisioning.py:67-69`），本地注册路径完全不经过它。

### 2.2 两套策略的关系

```
                    ┌─────────────────────────┐
   SSO 回调 ───────▶│ user_provisioning.py    │──▶ allowed_email_domains
  /auth/callback/   │ 四策略按序生效          │    require_verified_email
                    └─────────────────────────┘    auto_create_users
                                                  admin_emails
                    ┌─────────────────────────┐
   本地注册 ────────▶│ allow_registration      │──▶ 仅此一个开关
  /auth/register    │ （不经过上面的策略）    │
                    └─────────────────────────┘
```

**没有任何一层把两者串起来**——这是设计上的两条并行路径，需要操作者同时配置。

## 3. 关闭它不会锁死自己

`config.example.yaml:3537-3538` 明确保证：

> The first admin account is always created through `/initialize` regardless of this
> setting, so turning it off cannot lock you out of a fresh install.

首个 admin 走 `POST /api/v1/auth/initialize`（`app/gateway/routers/auth.py:820`），
与 `allow_registration` 无关。所以「关掉注册会不会导致全新部署进不去」的答案是**不会**。

`GET /api/v1/auth/setup-status`（`app/gateway/routers/auth.py:752`）可查是否还需要初始化。

## 4. 决策表

| 部署形态 | `allow_registration` | 理由 |
|---|---|---|
| 纯 SSO（账号从 IdP 来） | **`false`** | 否则绕过 IdP 的域名/验证策略 |
| 纯本地账号（无 SSO） | 按需；生产通常设 `false`，由管理员建号 | 默认 `true` 意味着能访问即能开号 |
| SSO + 部分本地账号 | **`false`** | 本地账号由管理员建，不开自助注册 |
| 公网可访问的 Demo | `true` 可接受 | 但需配合限速与资源配额 |

**唯一需要 `true` 的场景**是「希望陌生人自助注册」——这在企业部署里通常不成立。

## 5. 与其他开关的组合

三个与「谁能进」相关的开关必须一起看：

| 开关 | 位置 | 控制 |
|---|---|---|
| `allow_registration` | `auth.local` | 访客能否自建本地账号 |
| `auth.oidc.enabled` | `auth.oidc` | 是否显示 SSO 登录入口 |
| `auth.local.throttle_storage` 等 | `auth.local` | 密码登录是否可暴力破解 |

**没有**「禁用密码登录」的总开关——即使 `oidc.enabled: true`，
`POST /api/v1/auth/login/local`（`app/gateway/routers/auth.py:431`）仍然可用。
这意味着 SSO 部署里密码通道始终是并存的第二条路，只能靠限速与强密码策略约束。

## 6. 缺口

| 缺口 | 状态 | 边界 |
|---|---|---|
| 禁用本地密码登录 | **无** | 无 `local.enabled: false` 类开关；SSO 部署里密码端点始终开放 |
| 邮箱验证流程 | **无** | 本地注册不验证邮箱归属；`require_verified_email` 只作用于 SSO 的 `email_verified` claim |
| 注册审批队列 | **无** | 要么直接建号，要么拒绝，无「待审批」中间态 |
| 邀请码 / 域名白名单（本地路径） | **无** | `allowed_email_domains` 不作用于本地注册（见 §2） |
| 密码强度策略 | **有硬下限，不可配** | 最小 8 位（`app/gateway/routers/auth.py:134`、`:144`）+ **36 条**常见密码黑名单（`app/gateway/routers/auth.py:64-113`，取自 SecLists 10k 最差密码）。无大写/数字/符号组合要求，且**不可通过 `config.yaml` 调整** |

## 7. 与其他章节的关系

- SSO provisioning 四策略的完整说明：[07-sso-and-oidc.md](07-sso-and-oidc.md) §4、§5
- 登录限速：[09-login-throttle.md](09-login-throttle.md)
- 四条认证路径：[01-authentication-model.md](01-authentication-model.md)
