---
title: "用户隔离"
description: "per-user 目录布局、ID 校验防路径穿越、legacy 布局的共存，以及 auth-disabled 模式下所有人共享 default 用户的四个后果。"
topics: [governance, identity, isolation]
---

# 用户隔离

隔离的粒度是 `user × thread`。所有用户数据落在以 `user_id` 命名的目录下，
`user_id` 全部经由校验后才拼进路径。

## 1. 目录布局

`packages/harness/deerflow/config/paths.py:344-358` 的 `thread_dir` docstring 给出规范：

```
user_id 提供时： {base_dir}/users/{user_id}/threads/{thread_id}/
否则（legacy）： {base_dir}/threads/{thread_id}/
```

完整布局：

```
{base_dir}/users/{user_id}/
    threads/{thread_id}/
        user-data/
            workspace/    ← 沙箱内 /mnt/user-data/workspace
            uploads/      ← 沙箱内 /mnt/user-data/uploads
            outputs/      ← 沙箱内 /mnt/user-data/outputs
        skills_view/      ← 沙箱可见的技能投影（per user×thread）
    ...
```

三类沙箱目录由同一套 helper 构造（`paths.py:364`、`:372`、`:380`），
都以 `thread_dir(thread_id, user_id=...)` 为父目录——**隔离点统一在一处**。

## 2. 路径穿越防护

`paths.py:355-358` 明确列出拒绝条件：

> Raises:
>     ValueError: If `thread_id` or `user_id` contains unsafe characters (path
>                 separators or `..`) that could cause directory traversal.

| 输入 | 结果 |
|---|---|
| 正常 id | 拼入路径 |
| 含 `/` 或路径分隔符 | `ValueError` |
| 含 `..` | `ValueError` |

**这是隔离有效性的前提**：如果没有这道校验，`user_id = "../other_user"` 就能越界。

### 2.1 与 MCP 作用域的对比

MCP 的 legacy 作用域键（`mcp_scope.py:58-61`）允许 `user_id` 含冒号并主动披露
「只会过度关闭、不会泄露」。那是不透明字符串比较的场景；
**文件路径**这一层则严格拒绝不安全字符——两者防线强度不同，因为风险不同。

## 3. legacy 布局共存

`thread_dir` 的 `user_id` 参数是 `str | None = None`：

| `user_id` | 路径 |
|---|---|
| 提供 | `{base_dir}/users/{id}/threads/{tid}/` |
| `None` | `{base_dir}/threads/{tid}/`（legacy） |

`None` 分支是为了**升级兼容**：旧版本部署的数据在 `threads/` 下，
新版本不会自动迁移它们。仓库提供 `scripts/migrate_user_isolation.py`
做一次性搬迁。

**企业含义**：升级后如果没跑迁移脚本，旧 thread 的**元数据行**仍可列出/访问，
但请求路径固定使用 effective user（`paths.py:358-362`），不会再从 `base/threads/`
读取旧文件——**旧文件实际成为孤儿**，可访问性取决于 metadata 行而不取决于文件。
所以迁移脚本必须跑，不能把「还能打开列表」当成「数据还在」。

## 4. user_id 从哪来

| 模式 | `user_id` | 证据 |
|---|---|---|
| 认证开启 | 从 session/JWT 解析出的用户 id | `user_context.py:101` |
| 内部调用带 owner 头 | 该 owner 的 id | `auth_middleware.py:106-109` |
| 认证关闭 | `"default"`（常量） | `user_context.py:98`、`:109` |

`DEFAULT_USER_ID: Final[str] = "default"`（`user_context.py:98`）——
`get_effective_user_id()` 在无上下文时回落到它（`user_context.py:109`）。

## 5. auth-disabled 模式的四个后果

`DEER_FLOW_AUTH_DISABLED=1` 时（`app/gateway/auth_disabled.py:34-35`）：

```python
def is_auth_disabled() -> bool:
    return is_auth_disabled_requested() and not is_explicit_production_environment()
```

| 项 | 值 | 证据 |
|---|---|---|
| env 变量 | `DEER_FLOW_AUTH_DISABLED` | `auth_disabled.py:11` |
| 合成用户 id | `default` | `auth_disabled.py:12` |
| 合成用户邮箱 | `default@test.local` | `auth_disabled.py:13` |
| 生产环境抑制 | `DEER_FLOW_ENV`/`ENVIRONMENT` 为 `prod`/`production` 时**忽略该开关** | `auth_disabled.py:20-21`、`:26-27` |
| 合成用户角色 | **`admin`**——RBAC 完全失效 | `auth_disabled.py:49-58` |
| 启动告警 | 有 WARNING | `auth_disabled.py:38-44` |

| 后果 | 影响 |
|---|---|
| 所有人共享 `default` 用户 | thread、memory、sandbox workspace 全部混在 `users/default/` 下 |
| 无操作溯源 | 审计无法区分是哪个真人触发的操作 |
| 无权限边界 | 合成用户是 `admin`；任何人都能看到并操作所有 thread |
| CSRF 检查跳过 | `csrf_middleware.py` 在 auth-disabled 时提前返回 |

**生产环境的自动保护**：`is_explicit_production_environment()`（`auth_disabled.py:26-27`）
一旦检测到 `prod`/`production`，就强制 `is_auth_disabled()` 为 `False`。
所以「生产环境意外开了 no-auth」这条路被封住了——但前提是 `DEER_FLOW_ENV` 设对了。

## 6. 缺口

| 缺口 | 状态 | 边界 |
|---|---|---|
| legacy 数据的自动迁移 | **无** | 需手工跑 `scripts/migrate_user_isolation.py`；不迁移则不隔离 |
| 组织/租户层隔离 | **无** | 路径有 user × project × thread 三层（`paths.py:388-394`），无 org/tenant 维度 |
| 跨用户共享 thread | **无** | 无「把这个 thread 共享给同事」的机制 |
| 存储配额按用户 | **无** | 无 per-user 磁盘配额 |
| workspace 的加密隔离 | **无** | 同一主机上的目录权限隔离，无 per-user 加密 |
| auth-disabled 的合规审计 | **部分** | 有启动 WARNING（`auth_disabled.py:38-44`），但无持续状态端点 |

## 7. 与其他章节的关系

- 认证路径：[01-authentication-model.md](01-authentication-model.md)
- 内部调用的 owner 头：[02-internal-token.md](02-internal-token.md) §3
- 沙箱挂载与容器隔离：[../execution/01-sandbox-modes.md](../execution/01-sandbox-modes.md)
- MCP 会话的 user 隔离：[../authorization/05-mcp-scope.md](../authorization/05-mcp-scope.md)
