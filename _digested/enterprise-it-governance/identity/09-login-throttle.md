---
title: "登录限速与锁禁"
description: "auth.local 的三个键：5 次/300 秒的默认策略、auto/memory/db 三档存储、多副本下锁禁是否共享。以及企业 NAT 出口导致的整办公室误锁问题。"
topics: [governance, identity, brute-force, multi-instance]
---

# 登录限速与锁禁

密码登录的唯一暴力破解防线是锁禁。它的正确性**取决于计数器存在哪里**——
这是多副本部署最容易出问题的地方。

## 1. 三个配置键

| 键 | 默认 | 约束 | 证据 |
|---|---|---|---|
| `auth.local.max_login_attempts` | `5` | `ge=2`（**最小值 2，不可设 1**） | `packages/harness/deerflow/config/auth_config.py:110` |
| `auth.local.lockout_seconds` | `300.0`（5 分钟） | `gt=0` | `packages/harness/deerflow/config/auth_config.py:125` |
| `auth.local.throttle_storage` | `auto` | `auto` / `memory` / `db` | `packages/harness/deerflow/config/auth_config.py:131` |

默认值是「保留历史上的硬编码策略」（`packages/harness/deerflow/config/auth_config.py:115`、`:129` 两处注释都这么说）。

## 2. `max_login_attempts` 为什么不能是 1

`packages/harness/deerflow/config/auth_config.py:117-120` 明确写了理由：

> Minimum 2: one failed attempt must never lock an IP, or a single typo would
> block everyone behind a shared egress — the strictest legal value locks after
> the second failure.

**这条约束是企业部署必须知道的**：办公室里几十人共用一个 NAT 出口时，
把阈值调到 1 意味着**任何一个人打错一次密码，整个办公室都被锁**。
schema 层直接禁止了这种配置（`ge=2`），不是靠文档提醒。

## 3. 客户端 IP 从哪来

限速按**客户端 IP**计数。IP 的取法决定它是「真的按人」还是「按出口」：

| 条件 | 取到的 IP | 证据 |
|---|---|---|
| 请求来自 `AUTH_TRUSTED_PROXIES` 里的代理 | `X-Real-IP` 头 | `config.example.yaml:3543-3545` |
| 否则 | TCP peer 地址 | 同上 |

Docker 栈默认信任自带的 nginx（注释里写 "the Docker stack trusts its bundled nginx"）。
**代理链没配好时**，所有请求都表现为代理的 IP，锁禁变成全局锁——
这是按 IP 限速的固有局限，不是 DeerFlow 特有。

## 4. 三档存储：多副本的核心问题

`packages/harness/deerflow/config/auth_config.py:131-145` 用长描述定义了三档行为。区别只在**计数器放在哪**：

| 档 | 计数器位置 | 多副本效果 | 何时用 |
|---|---|---|---|
| `auto`（默认） | `database.backend` 为 sqlite/postgres 时用数据库；为 memory 时退回进程内 | 有数据库则**共享**，每 IP 一个锁禁 | 默认选择，通常正确 |
| `memory` | 仅进程内 | **N 个副本 = 攻击者有 N × 5 次机会**；一个副本上的锁禁对其他副本不可见 | 单机或明确接受该风险 |
| `db` | 共享 `login_throttle` 表 | 所有副本共享同一个锁禁 | 强制要求共享（会拒绝启动） |

`packages/harness/deerflow/config/auth_config.py:139-140` 对 `memory` 的描述最直白：

> 'memory' forces the in-process counter (per process: N replicas give an attacker
> N x max_login_attempts guesses and a lockout on one replica is invisible to the others).

**8 个 Gateway 副本 + `memory` 档 = 攻击者实际可试 40 次**（8 × 5），
而不是配置里写的 5 次。这是评审时最容易被忽略的地方。

### 4.1 多副本会主动告警

`app/gateway/auth/login_throttle.py:14` 说明多实例部署用 `memory` 档时
`app.gateway.deps._validate_login_throttle_storage` 会记 **WARNING**。
所以这个问题**不会静默存在**——启动日志里能查到。

### 4.2 `db` 档的两级降级

`db` 是「操作者明确要求共享」，所以它的行为比 `auto` 严格：

| 情形 | 行为 | 证据 |
|---|---|---|
| `database.backend: memory` | 退回内存 + WARNING | `app/gateway/auth/login_throttle.py:59-64` |
| 配置的数据库引擎**不可用** | **拒绝启动** | `app/gateway/auth/login_throttle.py:66-71` |
| 解析成功 | 记 INFO，说明锁禁跨所有副本 | `app/gateway/auth/login_throttle.py:77` |

`app/gateway/auth/login_throttle.py:66-71` 的报错原文给了处置建议：

> `auth.local.throttle_storage='db'` requires the persistence engine for
> `database.backend=...` to be initialised before login ... or set
> `auth.local.throttle_storage` to 'auto' (falls back to the in-process counter
> with a warning) or 'memory'.

这体现了一个设计取舍：**`db` 档宁可拒绝启动，也不静默降级成不安全的状态**。

## 5. 热生效语义

这部分容易出错，`config.example.yaml:3550-3555` 写得很细：

> Live-read per login, so a config reload applies without a Gateway restart:
> lowering `lockout_seconds` releases an active lock early and tightening
> `max_login_attempts` keeps already-counted failures; a raised `lockout_seconds`
> extends a still-active lock but never resurrects one that already expired.

| 操作 | 对**已锁定**的 IP | 对**已计入失败**的 IP |
|---|---|---|
| 调低 `lockout_seconds` | **提前释放** | — |
| 调高 `lockout_seconds` | 延长当前锁，但**不复活已过期**的锁 | — |
| 调紧 `max_login_attempts` | — | **保留已计入的失败次数** |

`max_login_attempts` / `lockout_seconds` 是**每次登录实时读取**，改配置不需重启。
但 `throttle_storage` 是**重启生效**（`config.example.yaml:3558` 标了 "restart required"）。

## 6. 缺口

| 缺口 | 状态 | 边界 |
|---|---|---|
| 按用户 id 限速 | **无** | 只按客户端 IP；同一用户从多个 IP 尝试不受累计约束 |
| 渐进式延迟 | **无** | 只有「未达阈值 → 放行 / 达阈值 → 锁定」二元行为，无指数退避 |
| CAPTCHA / MFA | **无** | 密码正确即放行；无第二因子 |
| 未授权告警 | **无** | 锁禁事件无结构化事件、webhook 或专门日志；登录失败只返回 429 |
| 锁禁的白名单豁免 | **无** | `auth.local` 下没有 IP 白名单/豁免配置（只有 throttle 三键 + `allow_registration`）；被误锁的运维可调低 `lockout_seconds`（live-read，立即提前释放），不需要重启 |
| 按账号锁定（防撞库跨 IP） | **无** | 攻击者换 IP 即可绕过 |

## 7. 与其他章节的关系

- SSO 策略与本地注册的政策断点：[07-sso-and-oidc.md](07-sso-and-oidc.md) §5
- `allow_registration` 的陷阱：[10-registration-policy.md](10-registration-policy.md)
- 多实例部署的完整要求：[../cost/04-multi-instance.md](../cost/04-multi-instance.md)
