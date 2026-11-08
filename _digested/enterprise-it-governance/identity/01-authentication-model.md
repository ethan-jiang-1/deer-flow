---
title: "认证模型"
description: "DeerFlow 有三条并行认证路径，共享同一套 Gateway 中间件链。"
topics: [governance, identity]
---

# 认证模型

DeerFlow 有三条并行认证路径，共享同一套 Gateway 中间件链。

## 认证体系

DeerFlow 的认证是**人**的认证，不是 **agent** 的认证。Agent 本身没有独立身份——它在用户上下文里跑。

### 三层认证

| 层级 | 机制 | 作用 |
|------|------|------|
| **Web UI** | JWT（access + refresh token） | 前端用户登录 |
| **API** | CSRF token + JWT | 防跨站请求伪造 |
| **内部服务** | Internal Gateway Token（`X-DeerFlow-Internal-Token`） | IM channels ↔ Gateway 等内部 HTTP 调用 |

### JWT 认证流

```
用户登录 → POST /api/v1/auth/login/local → 验证密码 → 设置 HttpOnly session cookie
    → 后续请求自动带该 cookie（或改用 Authorization: Bearer <PAT>）
    → cookie/JWT 过期 → 重新登录（无 refresh 端点，登录响应体只返回 expires_in/needs_setup）
```

### Internal Gateway Token

`backend/app/gateway/internal_auth.py` — Gateway 与其内部调用方（IM channels 等，同进程内通过 HTTP 回调 Gateway API）之间的内部认证（`internal_auth.py:1`）。Token 通过 header `X-DeerFlow-Internal-Token` 传递（`:13`），来自环境变量 `DEER_FLOW_INTERNAL_AUTH_TOKEN`，未设置时进程启动时随机生成（`:15`、`:19-23`）——所以**多 worker 部署必须显式设置同一个 env 值**才能共享；它不随 JWT 过期，内部服务调用因此不受会话过期影响。

### 登录限速

`security/01-auth.md` — 有登录频率限制，防止暴力破解。

