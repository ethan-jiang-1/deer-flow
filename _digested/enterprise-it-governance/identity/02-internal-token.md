---
title: "内部服务认证"
description: "X-DeerFlow-Internal-Token 的完整契约：env 来源、每进程随机生成、owner 头如何借用用户身份、internal 角色为何不是 RBAC 角色。"
topics: [governance, identity, internal]
---

# 内部服务认证

Gateway 与内部调用方（IM channel worker、scheduler、MCP assembly worker）
之间的凭据，与用户认证完全独立。

## 1. 凭据契约

`app/gateway/internal_auth.py` 只做一件事：确定内部调用者是谁。

| 项 | 值 | 证据 |
|---|---|---|
| Header 名 | `X-DeerFlow-Internal-Token` | `app/gateway/internal_auth.py:14` |
| 环境变量 | `DEER_FLOW_INTERNAL_AUTH_TOKEN` | `app/gateway/internal_auth.py:16` |
| 未设 env 时 | `secrets.token_urlsafe(32)`，进程启动随机生成 | `app/gateway/internal_auth.py:21-24` |
| Owner 头 | `X-DeerFlow-Owner-User-Id` | `app/gateway/internal_auth.py:13` |
| 停用检查 | owner 被停用即 401 | `app/gateway/auth_middleware.py:129-136` |
| 认证来源标记 | `"internal"` | `app/gateway/auth_disabled.py:17` |

## 2. 每进程随机：多副本的核心约束

`internal_auth.py:21-24`：

```python
token = os.environ.get(INTERNAL_AUTH_ENV_VAR)
if token:
    return token
...
return secrets.token_urlsafe(32)
```

| 部署形态 | 结果 |
|---|---|
| 单进程、不设 env | 零配置可用（随机值只在内存） |
| 多 worker（`GATEWAY_WORKERS > 1`）、不设 env | **各 worker 互不认**——A worker 生成 token 调 B worker → 401 |
| 多副本、不设 env | **完全失效** |
| 设了同一 env 值 | 全部互通 |

**这是内部认证最容易踩的坑**：`make dev` 单进程跑得好好的配置，
一上多副本就静默失败（内部调用报 401，但主流程看起来正常）。

## 3. owner 头：借用用户身份

内部调用者可以带 `X-DeerFlow-Owner-User-Id` 指定「我代表哪个用户」。
`app/gateway/auth_middleware.py:101-110` 是解析点：

| 情况 | 解析出的用户 | 效果 |
|---|---|---|
| 带 owner 头，用户存在且**未停用** | `id=owner`，`system_role="internal"` | **run 层继承 owner 的 user_id/上下文；路由授权仍按 `internal` → `default_role`** |
| 带 owner 头，用户**已停用** | — | **401 `ACCOUNT_DISABLED`** |
| 带 owner 头，用户无 users 行 | 允许通行 | 不存在的账号无法被停用 |
| 不带 owner 头 | `internal` 合成用户 | 走 `default_role` |

`app/gateway/auth_middleware.py:101-103` 的注释说明这是为了让
`get_effective_user_id()` 与 per-user 路径（custom skills、memory、thread data）
解析到正确的 owner，而不是回落 `"default"`。

**关键边界**：owner 头改变的是 `user.id`，不是 `system_role`——
`get_internal_user()` 无论有无 owner 都返回 `system_role="internal"`
（`internal_auth.py:64-68`），路由授权又把 internal 剔除成 `default_role`
（`authz.py:306-308`、`:466-468`）。所以**路由层拿不到 owner 的 RBAC 角色**；
owner 的 `user_role` 只在 run context 层被继承（`services.py:1171-1185`）。

### 3.1 停用检查为什么放在这里

`app/gateway/auth_middleware.py:111-119` 是一段关键的工程注释：

> The internal principal is synthesized from trusted headers **without a users-row
> lookup**, so suspension has no other chance to bite on this surface (#3462 gap 3):
> enforce it here, the one gate every owner-bound internal HTTP call (IM channel
> dispatch above all) passes through.

**含义**：内部 principal 是凭 header 合成的，正常路径上不会查 users 表。
所以「账号被停用」这件事必须在这一层显式检查，否则停用某用户后，
他通过 IM channel 触发的后台任务仍会照常执行。

| 边界 | 行为 |
|---|---|
| users 表查询失败 | 记 WARNING、**跳过**停用检查（fail-open on infra error） |
| owner 无 users 行 | 放行（理由：不存在的账号无法被停用） |
| auth-disabled 模式 | 豁免（owner 头是合成身份，没有可停用的账号） |

**为什么这是必要设计**：scheduler 触发一个定时任务时，这个任务应该以
「创建它的用户」的身份访问其 thread 与 memory，而不是拥有全局权限。

**代价**：内部 token 加上任意 owner 头 = 冒充任意用户。所以
**内部 token 的保密等级等同于最高权限凭据**——泄露它等于泄露所有者的身份。

## 4. internal 不是 RBAC 角色

`internal_auth.py:17` 定义 `INTERNAL_SYSTEM_ROLE = "internal"`，
在合成用户上设置（`internal_auth.py:68`）：

```python
return SimpleNamespace(id=effective_id, system_role=INTERNAL_SYSTEM_ROLE)
```

但在路由授权时，它被**显式剔除**（`app/gateway/authz.py:300-308`）：

```python
# internal callers (IM channel workers, scheduler) have system_role="internal",
# which is not a real RBAC role. Omit it so default_role applies ...
```

| 场景 | 生效角色 |
|---|---|
| 内部调用，无 owner | `config.default_role` |
| 内部调用，有 owner | 路由层仍是 `internal` → `default_role`；run context 继承 owner 的 `user_role` |
| 外部用户 | 他自己的 `system_role` |

**企业含义**：不能靠「给 internal 分配一个角色」来管控后台任务权限——
它不是一个可分配的角色。要管控只有两条路：选一个合适的 `default_role`，
或者确保 owner 头只由可信的内部服务设置。

## 5. 不随 JWT 过期

内部 token 与用户 session 是两套生命周期：

| 对比项 | 用户 JWT | 内部 token |
|---|---|---|
| 过期 | 有 `exp` | **无** |
| 撤销 | `token_version` +1 | 换 env 值并重启 |
| 轮转 | 重新登录 | 无自动化 |
| 泄露后影响 | 单用户单会话 | **冒充任意 owner** |

`token_version` 的失效机制（见 [06-design-decisions.md](06-design-decisions.md) §4）
完全不覆盖内部 token。

## 6. 缺口

| 缺口 | 状态 | 边界 |
|---|---|---|
| 内部 token 轮转 | **无** | 只能改 env + 重启全部进程；无多活过渡期 |
| owner 停用检查的 fail-open | **有但不覆盖** | users 表查询失败时**跳过**检查（`auth_middleware.py:124-127`），仅在 run 准入时重新断言 |
| owner 头的可信来源限制 | **部分** | 只有持内部 token 的一方才能设；但无「哪个内部服务可以代表哪个用户」的映射 |
| 内部调用的审计 | **部分** | 有 `auth_source="internal"` 标记，但无「哪个内部服务」的标识（所有内部服务共用一个 token） |
| 多 token / 按服务分权 | **无** | 只有**一个** env 值，无法给 scheduler 与 IM channel 不同凭据 |
| 启动时校验 | **无** | 不设 env 时静默随机生成，多副本不会在启动时报错 |

最后一条值得强调：**多副本漏配 env 不会在启动时失败**，只会在运行时表现为
内部调用 401。这应该写进部署检查清单。

## 7. 与其他章节的关系

- 四条认证路径总览：[01-authentication-model.md](01-authentication-model.md) §1
- 多实例部署的完整要求：[../cost/04-multi-instance.md](../cost/04-multi-instance.md)
- internal 角色如何影响授权：[../authorization/04-rbac-permissions.md](../authorization/04-rbac-permissions.md) §5
