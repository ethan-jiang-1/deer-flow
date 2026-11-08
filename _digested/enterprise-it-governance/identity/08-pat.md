---
title: "个人访问令牌（PAT）"
description: "程序化访问的凭据模型：dfp_ 前缀、base62(32) 随机体、SHA-256 摘要存储、9 个作用域，以及默认拒绝的路由边界——PAT 只能缩小权限，不能放大。"
topics: [governance, identity, pat, api]
---

# 个人访问令牌（PAT）

企业里「CI 要调 API」「脚本要批量建 thread」这类需求，答案就是 PAT。
它的设计约束很清楚：**一个 PAT 只能缩小其所属用户的权限，永远不能放大**。

## 1. 令牌形态

`app/gateway/auth/pat.py:3-6` 的模块注释给了完整定义：

> Tokens are `dfp_` + base62(32 CSPRNG bytes), shown exactly once in the
> create response and persisted only as a SHA-256 digest. Validation is a
> digest-indexed lookup plus a constant-time re-comparison, with a single
> generic failure surface so a 401 never reveals which check failed.

| 属性 | 值 | 证据 |
|---|---|---|
| 前缀 | `dfp_` | `app/gateway/auth/pat.py:22` `PAT_TOKEN_PREFIX` |
| 随机体 | 32 字节 CSPRNG，base62 定宽编码 | `app/gateway/auth/pat.py:23` `PAT_RANDOM_BYTES`、`:141-165` |
| 明文可见次数 | **仅创建时一次** | `app/gateway/auth/pat.py:3-4` |
| 存储形式 | SHA-256 摘要 | `app/gateway/auth/pat.py:175` |
| 校验 | 摘要索引查找 + 常数时间复比 | `app/gateway/auth/pat.py:4` |
| 失败面 | 单一通用 401，不泄露具体哪步失败 | `app/gateway/auth/pat.py:4-5` |
| `last_used_at` 写入 | 每 token 节流 300s | `app/gateway/auth/pat.py:26-27` |

**对企业审计的含义**：库里只有摘要，**无法**从数据库还原出明文令牌。
因此「令牌泄露了」的唯一处置是吊销重发，没有「查一下是不是这个」的路径。

## 2. 作用域模型

`app/gateway/auth/pat.py:28-40` 定义 9 个允许作用域，与 `authz.py` 的 `resource:action` 完全同名：

| 作用域 | 覆盖 |
|---|---|
| `threads:read` / `write` / `delete` | 会话生命周期 |
| `runs:create` / `read` / `cancel` | 运行生命周期 |
| `projects:read` / `write` / `delete` | 项目工作区 |

### 2.1 刻意不给的四个作用域

`app/gateway/auth/pat.py:42-48` 用独立注释说明为什么 `memory:read/write` 与 `agents:read/write` **不开放**给 PAT：

> Deliberately NOT in PAT_ALLOWED_SCOPES: the route permissions "memory:read",
> "memory:write", "agents:read", and "agents:write" exist in authz (they guard
> the memory/agent routers), but PATs stay on the thread/run lifecycle only —
> `_PAT_ROUTE_RULES` default-denies the memory/agent routes for PAT callers
> regardless of scopes, so admitting these scopes would not even reach those routes.
> Opening them to PATs is a product decision that must change all three of: this set,
> `_PAT_ROUTE_RULES`, and the API docs.

所以「我要求 PAT 能读 memory」在 v2.2.0 是**产品级别的不可用**，不是配置问题。

### 2.2 作用域校验

`app/gateway/auth/pat.py:238-243` 的 `validate_scopes` 拒绝未知作用域并去重排序。
创建时传 `agents:write` 会直接报错，而不是静默忽略。

### 2.3 账号状态联动：离职与停用的实际效果

`app/gateway/auth/pat.py:201-234` 的 `authenticate_pat` 在令牌本身有效之外，还做两次账号检查：

| 检查 | 行为 | 证据 |
|---|---|---|
| 归属用户已删除 | 令牌**即使行还在也失效** | `app/gateway/auth/pat.py:224-228` |
| 账号被停用（`disabled`） | 令牌在磁盘上仍有效，但解析不到任何权限 | `app/gateway/auth/pat.py:229-233` |

`app/gateway/auth/pat.py:224-228` 的注释说明了设计意图：

```python
# The owning user was deleted or became unresolvable; the token is
# dead even though its row survives (deleting a user revokes their
# PATs, without needing a FK cascade).
```

**对企业离职流程的含义**：停用账号（而非删除）就能立即阻断该用户的所有 PAT，
不需要逐个找令牌吊销。这是 `#3462 gap 3` 修复带来的能力。

三类失败（未知/已吊销/已过期）与这类账号问题**共用同一个通用 401**
（`app/gateway/auth/pat.py:201-206`），响应无法被用作探测哪个检查失败的 oracle。

## 3. 默认拒绝的路由边界

这是 PAT 设计里最值得企业安全评审注意的部分。

`app/gateway/auth/pat.py:52-58` 说明问题背景：

> Default-deny route boundary for PAT callers (#5041 review P1-1): scope
> intersection in AuthMiddleware only constrains routes that consult
> `request.state.auth.permissions` (`@require_permission`). Authenticated
> mutation routes **without** that decorator — memory deletion, agent creation,
> credential switching, channel configuration — would otherwise accept a PAT
> holding a single read scope.

**问题**：如果只做「作用域求交」，那么一个只有 `threads:read` 的 PAT，
仍能打到那些**没有** `@require_permission` 装饰的变更路由上（删 memory、建 agent、
切凭据、改 channel 配置）——因为求交只对显式声明权限的路由生效。

**解法**：显式枚举规则（`app/gateway/auth/pat.py:60` 起，`:60-125`）：

> A route is reachable by PAT only when it is explicitly listed here, and only
> together with the thread/run lifecycle the v1 scopes govern; everything else
> answers 403 regardless of scopes.

| 路径 | 允许方法 |
|---|---|
| `/api/threads` | POST |
| `/api/threads/search` | POST |
| `/api/threads/{id}` | GET, PATCH, DELETE |
| `/api/threads/{id}/goal` | GET, PUT, DELETE |
| `/api/threads/{id}/state` | GET, POST |
| `/api/threads/{id}/compact\|history\|branches` | POST |
| `/api/threads/{id}/move` | POST |
| `/api/projects/...` | 仅 projects router 实现的方法 |

**默认拒绝的收益**：将来新增的路由**自动**对 PAT 不可见，直到被显式加入白名单。
新路由忘记考虑 PAT 时，默认是安全的。

强制点在 `app/gateway/auth_middleware.py:165` 与 `app/gateway/app.py:1210`（后者额外压掉 PAT 的 admin 能力）。

## 4. 管理接口

| 操作 | 端点 | 证据 |
|---|---|---|
| 创建 | `POST /api/v1/auth/pats` | `app/gateway/routers/auth.py:682` |
| 列出 | `GET /api/v1/auth/pats` | `app/gateway/routers/auth.py:719` |

两个端点都带 `dependencies=[Depends(require_session_source)]`——**PAT 不能用 PAT 管理自己**，
必须用 session 登录态操作。这防止一个泄露的 PAT 自我续期或自我提权。

## 5. 缺口

| 缺口 | 状态 | 边界 |
|---|---|---|
| 吊销单个令牌 | **有** | `DELETE /api/v1/auth/pats/{pat_id}`（`app/gateway/routers/auth.py:729`） |
| 批量吊销 / 管理员吊销他人 | **无** | 无「全部吊销」或按用户批量吊销的管理面；admin 也只能管自己的 |
| 过期时间 | **无（但有账号级联动）** | 令牌本身不设过期；但**删用户即失效**、**停用账号即阻断**（见 §2.3） |
| 使用审计 | **部分** | 有 `last_used_at`（300s 节流，`app/gateway/auth/pat.py:26-27`）；**无**每次调用的来源 IP / UA 记录 |
| 组织级令牌 | **无** | PAT 绑定到具体用户账号，无 service account 概念 |
| 作用域粒度 | **粗** | 9 个作用域是路由级；无「只读某个 project」这类资源级限定 |


## 6. 与其他章节的关系

- 三条认证路径的分工：[01-authentication-model.md](01-authentication-model.md)
- RBAC 的 13 个权限与 PAT 的 9 个作用域的区别：[../authorization/04-rbac-permissions.md](../authorization/04-rbac-permissions.md)
- Agent 无独立身份的问题：[04-agent-identity-gap.md](04-agent-identity-gap.md)
