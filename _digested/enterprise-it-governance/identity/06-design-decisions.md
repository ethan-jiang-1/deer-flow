---
title: "设计决策"
description: "五处有据可查的取舍：CSRF 为什么是 double-submit 加 SameSite=strict 两层、Internal Token 为什么自动生成、user_id 为什么进 graph config、token_version 如何实现全端登出。"
topics: [governance, identity, design]
---

# 设计决策

这一篇记录五个**能追到代码与注释的**取舍。每条都标出证据位置，
便于评审时逐条核对，而不是接受「框架就是这么设计的」这种说法。

## 1. CSRF：两层，不是二选一

常见误解是「DeerFlow 用 double-submit 所以不用 SameSite」。实际是**两层同时用**。

| 层 | 实现 | 证据 |
|---|---|---|
| cookie | `csrf_token`，随机 64 字节 URL-safe | `app/gateway/csrf_middleware.py:24`、`:28`、`:36-38` |
| header | `X-CSRF-Token` | `app/gateway/csrf_middleware.py:25` |
| cookie 属性 | `samesite="strict"` | `app/gateway/routers/auth.py:888` |
| 比对 | 常数时间比较 | `app/gateway/csrf_middleware.py:20` `constant_time_equals` |
| 生效方法 | POST / PUT / DELETE / PATCH | `app/gateway/csrf_middleware.py:26` |
| 豁免 | GET / HEAD / OPTIONS / TRACE（RFC 7231） | `app/gateway/csrf_middleware.py:41-45` |
| CSRF cookie 可读性 | `httponly=False`（注释："Must be JS-readable for Double Submit Cookie pattern"） | `routers/auth.py:886` |

### 1.1 豁免清单

`app/gateway/csrf_middleware.py:27` 只有一个精确路径豁免：

```python
_CSRF_EXEMPT_EXACT_PATHS: frozenset[str] = frozenset({"/api/v1/auth/me"})
```

**为什么豁免 `/auth/me`**：它是 GET 语义的「读当前用户」端点，
但某些客户端以 POST 调用。豁免使用**精确路径匹配**（不是前缀），
所以不会误豁免 `/api/v1/auth/me/something`。

### 1.2 SameSite=strict 为什么不够

`routers/auth.py:888` 给 CSRF cookie 设 `samesite="strict"`，比 `lax` 更严。
但 SameSite 依赖**浏览器实现**——IM 客户端内嵌 WebView、
旧浏览器、以及非浏览器客户端（脚本、CLI）都不保证遵守。

double-submit 是**服务端**验证，不依赖客户端行为，所以两层叠加：
SameSite 挡住大部分场景，double-submit 兜住剩下的。

对比：access token cookie 用 `lax`（`routers/auth.py:521`、`:523`），
CSRF cookie 用 `strict`。这个差异是刻意的——CSRF cookie 不需要在跨站导航时发送。

## 2. Internal Token 为什么自动生成

`app/gateway/internal_auth.py:21-24`：

```python
token = os.environ.get(INTERNAL_AUTH_ENV_VAR)
if token:
    return token
...
return secrets.token_urlsafe(32)
```

| 设计意图 | 代价 |
|---|---|
| **零配置启动**——单 worker 开发不需要管凭据 | 多 worker/多副本时**必须**显式设同一个 env 值 |
| 不落盘、不产生默认弱口令 | 重启即换值（未设 env 时），正在跑的内部调用会失败 |

env 名为 `DEER_FLOW_INTERNAL_AUTH_TOKEN`（`internal_auth.py:16`）。
未设置时每个进程各自随机，**进程之间互不认**——这是多实例部署必须检查的项
（见 [../cost/04-multi-instance.md](../cost/04-multi-instance.md)）。

## 3. user_id 为什么进 graph config

`app/gateway/services.py:1116` 的 `inject_authenticated_user_context` 把 `user_id`
写进 **graph config**，而不是依赖 Starlette 的 request context。

**原因**：graph 在 `asyncio.create_task` 中异步执行，
request context（`contextvars`）在 task 真正开始或后续 step 时可能已经不可用。
把 `user_id` 放进 config 后，它在 graph 的**全生命周期**内都可读。

传递链路：

```
AuthMiddleware / JWT decode
  → request.state.auth (AuthContext)
    → inject_authenticated_user_context()  → config["context"]["user_id"]
      → subagent batch: batch["user_id"]   ← 继承同一值
        → Sandbox provider → workspace 路径（含 user_id）
        → ThreadDataMiddleware → thread_data["user_id"]
```

`packages/harness/deerflow/subagents/batch_acceptance.py:38` 是第三环的证据：
subagent 批次直接从 `batch["user_id"]` 取值，所以**整棵 agent 树共享一个 user_id**
（这正是 [04-agent-identity-gap.md](04-agent-identity-gap.md) 的根因）。

## 4. token_version：全端登出

| 环 | 实现 | 证据 |
|---|---|---|
| JWT 载荷字段 | `ver`（注释：`token_version — must match User.token_version`） | `app/gateway/auth/jwt.py:18` |
| 签发时写入 | `payload = {"sub": ..., "ver": token_version}` | `app/gateway/auth/jwt.py:36` |
| 用户记录 | `token_version: int = Field(default=0, ...)` | `app/gateway/auth/models.py:36` |
| 触发递增 | 改密时 `user.token_version += 1` | `app/gateway/auth/reset_admin.py:68` |

**效果**：改密后所有旧 JWT 立即失效，不必等自然过期。这是「sign out everywhere」
的实现机制，也是 `reset_admin.py` 能在忘记密码时强制踢掉所有会话的原因。

**边界**：只作用于 **JWT**。PAT 不走这条链路（`pat.py` 用摘要查表），
所以改密**不会**吊销已签发的 PAT——需要单独删除或停用账号。

## 5. 状态变更方法白名单

`csrf_middleware.py:26` 只对四个方法做 CSRF 检查：

```python
_CSRF_STATE_CHANGING_METHODS = frozenset({"POST", "PUT", "DELETE", "PATCH"})
```

**注意**：`HEAD` 与 `OPTIONS` 被当作安全方法。若将来新增用 GET 实现的状态变更端点，
CSRF 会自动放行——所以「用 GET 做写操作」在这套设计里是**必须避免**的。

## 6. 缺口

| 缺口 | 状态 | 边界 |
|---|---|---|
| PAT 随改密失效 | **无** | `token_version` 只影响 JWT（见 §4 边界） |
| 会话级的「踢出单个设备」 | **无** | `token_version` 是全体递增，不能按设备 |
| Internal token 轮转 | **无** | 只能换 env 值并重启全部进程 |
| CSRF 豁免的可配置性 | **无** | 豁免清单硬编码（`csrf_middleware.py:27`） |

## 7. 与其他章节的关系

- 四条认证路径：[01-authentication-model.md](01-authentication-model.md)
- 内部 token 的多实例约束：[02-internal-token.md](02-internal-token.md)
- Agent 身份缺口（继承 user_id 的后果）：[04-agent-identity-gap.md](04-agent-identity-gap.md)
