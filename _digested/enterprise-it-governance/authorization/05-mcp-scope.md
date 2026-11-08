---
title: "MCP 作用域与 personal MCP"
description: "MCP 会话按 用户:会话:incarnation 三重绑定。v2: 版本化编码、legacy 前缀冲突的过度关闭（不会泄露）、以及 stale incarnation 的防御。"
topics: [governance, authorization, mcp, isolation]
---

# MCP 作用域与 personal MCP

MCP server 的会话是有状态的：连接、认证、OAuth token 都挂在会话上。
「谁能复用谁的会话」是这一层的隔离问题。

## 1. 三重绑定

`packages/harness/deerflow/mcp_scope.py` 只有 95 行，但定义了完整的会话身份模型。
`mcp_scope.py:23-45` 的 `mcp_session_scope_key` 生成三种形态的键：

| 形态 | 键格式 | 何时用 |
|---|---|---|
| **legacy** | `{user_id}:{thread_id}` | `thread_incarnation` 为 `None` |
| **v2 版本化** | `v2:["user","thread","incarnation"]` | 有 incarnation |
| 空 incarnation | — | 直接 `RuntimeError` 拒绝 |

### 1.1 为什么需要 incarnation

`mcp_scope.py:31-32` 的解释：

> A legacy NULL incarnation retains the pre-activation scope so rolling upgrades do
> not split an existing legacy session.

**含义**：`thread_id` 是**可复用的**——同一个 thread 可能被多次运行、恢复、回滚。
如果作用域只用 `user:thread` 两个键，那么同一个 thread 的两次不同「生命周期」
会共享 MCP 会话，导致**上一次运行的认证状态泄露到下一次**。

`thread_incarnation` 是服务端拥有的、每次 thread 生命周期唯一的标识，
把它加入作用域键就切断了这种跨代复用。

### 1.2 v2 编码为什么用 JSON 元组

`mcp_scope.py:39-40`：

> A JSON tuple is an unambiguous, versioned encoding even when an opaque
> user/thread id contains the delimiter used by the legacy scope.

legacy 编码用 `:` 分隔。如果 `user_id` 本身含冒号（不透明 ID 允许），
`a:b:c` 既可以解析为 user=`a`, thread=`b:c`，也可以解析为 user=`a:b`, thread=`c`
——**歧义**。JSON 元组没有这个问题。

## 2. 归属判定的宽容与精确

`mcp_scope.py:48-71` 的 `mcp_scope_belongs_to_thread` 决定「这个会话键属于当前
user/thread 吗」。它同时接受两种编码，但**故意不比较 incarnation**（`mcp_scope.py:53-56`）：

> The incarnation is deliberately *not* compared — a caller tearing down a whole
> thread has to invalidate every generation of it, and the current generation cannot
> be read reliably at teardown time.

**设计取舍**：拆除整个 thread 时要清掉它**所有代**的 MCP 会话。
如果比较 incarnation，就只会清当前代，留下旧代的孤儿会话。

### 2.1 legacy 前缀冲突：只会过度关闭，不会泄露

`mcp_scope.py:58-61` 是一段罕见的**主动披露缺陷**的注释：

> The legacy branch is a prefix-free string compare, so a crafted `user_id`
> containing `:` can collide with another owner's legacy key. That can only
> ever **over-close** (tear down an extra session), **never leak one**, and the
> versioned encoding — which every incarnation-aware caller uses — is exact.

| 编码 | 冲突可能 | 冲突后果 |
|---|---|---|
| legacy `user:thread` | 有（冒号歧义） | **过度关闭**（多拆一个会话），不泄露 |
| v2 `v2:[...]` | 无 | — |

这个失败方向的选择是正确的：关闭过多只是性能损失，泄露是安全事故。

## 3. stale incarnation 的防御

`mcp_scope.py:74-95` 的 `runtime_thread_incarnation` 在读取 incarnation 时做两层校验：

| 检查 | 条件 | 失败行为 |
|---|---|---|
| 键必须存在 | `runtime.context` 有 `thread_incarnation` | `RuntimeError`（缺失即拒绝，只覆盖直接调用路径） |
| 值必须合法 | `None` 或非空字符串 | `RuntimeError` |
| metadata 一致性 | 若有 `__deerflow_thread_incarnation_metadata_guard` | 与持久化 metadata 比对，**不一致即拒绝** |

`mcp_scope.py:93-94` 的报错是 "received a stale thread incarnation"——
防的是**上下文与持久化状态不同步**的场景（例如恢复的 thread 带着旧的 incarnation 值继续跑）。

**例外**：直接调用工具（`runtime is None`）保留 legacy 作用域（`mcp_scope.py:76-79`），
因为它没有 Agent 的 thread 生命周期。

## 4. 企业视角的结论

| 问题 | 答案 | 依据 |
|---|---|---|
| 用户 A 能复用用户 B 的 MCP 会话吗？ | **不能** | 作用域键首元素是 `user_id`，JSON 解码后精确比对 |
| 同一 thread 的两次运行能复用会话吗？ | **不能**（有 incarnation 时） | v2 键含 incarnation |
| thread 删除时旧会话会被清吗？ | **会**，含所有代 | 故意不比 incarnation |
| 冒号攻击能窃取会话吗？ | **不能**，最坏是过度关闭 | `mcp_scope.py:58-61` |

## 5. personal MCP 的管理员授权规则

个人级 MCP（用户自己配的 server）不是「用户想连什么就连什么」——
`packages/harness/deerflow/mcp/personal_access.py` 有一道按网络的授权规则。

### 5.1 判定规则

`personal_access.py:20-23` 的 `requires_admin`：

```python
def requires_admin(server: McpServerConfig) -> bool:
    # Only definitions admitted under the ordinary-user policy carry True.
    # Missing markers, including legacy personal files, require authority too.
    return (server.model_extra or {}).get("personal_public_network") is not True
```

| 标记 | 需要 admin？ | 含义 |
|---|---|---|
| `personal_public_network: true` | **否** | 按普通用户策略准入（公网 server） |
| 标记缺失 / 其他值 | **是** | 含**所有历史遗留** personal 配置（无迁移，仅兼容读取） |

**fail-closed 方向**：判定用的是 `is not True`，所以任何缺失的标记都落到「需要 admin」，
而不是「放行」。注释明说 "legacy personal files require authority too"。

### 5.2 每次调用都实时查权限

`personal_access.py:37-39` 的 `require_personal_mcp_access` 在**每次使用**时检查：

```python
if requires_admin(server) and not await _is_current_admin(owner):
    raise ToolException("Current administrator access is required for this personal MCP connection; save it again under your current permissions")
```

| 设计点 | 行为 | 证据 |
|---|---|---|
| 实时查询 | 不缓存，每次判权限 | `personal_access.py:38` |
| 查询失败 | **返回 False**（不沿用旧决策） | `personal_access.py:29`、`:33-35` |
| 权限被撤销后 | 该 MCP 立即不可用，报错要求重新保存 | `personal_access.py:39` 的提示文本 |

`personal_access.py:33` 的注释点明为什么要这样：

> Authority lookup failures must not reuse a previous admin decision.

**企业含义**：把某人从 admin 降级后，他保存的 personal MCP 连接**立刻失效**，
不需要等他重新登录或等缓存过期。

### 5.3 Gateway 侧的绑定

`app/gateway/personal_mcp_access.py` 把「当前用户是不是 admin」这件事
绑到 Gateway 的**新鲜账号记录**上（模块 docstring：`personal_mcp_access.py:1`）：

| 项 | 实现 | 证据 |
|---|---|---|
| 判定函数 | `user is not None and user.system_role == "admin"` | `personal_mcp_access.py:14-15` |
| auth 关闭时 | 只有 `AUTH_DISABLED_USER_ID` 被当作 admin | `personal_mcp_access.py:12-13` |
| 跨事件循环 | 同步工具发现跑在 assembly worker 的独立 loop 上，用 `run_coroutine_threadsafe` 把查询送回 Gateway 的 loop | `personal_mcp_access.py:22-27` |

最后一条是个容易出错的工程细节：**不能**在 worker 的 loop 上直接用共享数据库连接池
（注释："Keep the shared database pool on the Gateway's owning loop"）。

### 5.4 与 OAuth token 存储的分工

| 概念 | 存哪 | 作用 |
|---|---|---|
| **会话身份** | `mcp_scope` 生成的键（内存/session pool） | 谁能复用谁的 MCP 会话 |
| **凭据** | `app/gateway/mcp_oauth_tokens.py` 的表 | MCP server 的 OAuth token |

两者都按 user 隔离，但一是**身份**、一是**凭据**，独立演进。
`mcp_oauth_tokens` 的表由迁移 `0047_mcp_oauth_tokens.py` 建立。

## 6. 缺口

| 缺口 | 状态 | 边界 |
|---|---|---|
| 组织级 MCP 的强制启用 | **无** | 用户可自行增删 personal MCP，无「必须使用公司指定的 MCP」约束 |
| MCP 调用的细粒度授权 | **部分** | 工具级 Guardrail 与 RBAC `tools` 策略可按工具名 allow/deny（含 MCP 工具，`authz/tool_filter.py:22-72`）；缺的是 per-server 命名空间/资源级 ACL |
| MCP server 白名单 | **部分** | 非 admin 的 personal server 必须过 `validate_public_http_url`（`routers/personal_mcp.py:58-61`），只允许公网 HTTP(S)；无运营方域名白名单 |
| 会话审计 | **部分** | 有 session pool 与 OAuth cache 失效机制（`session-pool-oauth-cache-invalidation.md`），无「谁在何时连了哪个 MCP」的结构化事件 |

## 7. 与其他章节的关系

- 13 个路由权限（MCP 不在其中）：[04-rbac-permissions.md](04-rbac-permissions.md)
- 工具级授权的另一条线：[01-guardrail-layer.md](01-guardrail-layer.md)
- MCP 协议与 durable task：`_digested/internals/mcp/`
