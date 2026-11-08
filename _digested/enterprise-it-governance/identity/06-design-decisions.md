---
title: "设计决策"
description: "CSRF 为什么用 double-submit、Internal Token 为什么自动生成、user_id 传递链路。"
topics: [governance, identity]
---

# 设计决策

CSRF 为什么用 double-submit、Internal Token 为什么自动生成、user_id 传递链路。

## 设计决策分析

### 为什么 CSRF 用 double-submit cookie 而非 SameSite？

Double-submit cookie 模式（cookie 中存 csrf_token，header 中传同一个值，服务端 `compare_digest` 比对）比 SameSite cookie 的兼容性更广。SameSite=Strict 在一些旧浏览器/嵌入式 WebView（IM 客户端内嵌浏览器）中不被支持。DeerFlow 同时支持浏览器和 IM channel 内嵌场景，所以选择了兼容性更好的方案。

### 为什么 Internal Token 自动生成？

`DEER_FLOW_INTERNAL_AUTH_TOKEN` 在模块加载时通过 `secrets.token_urlsafe(32)` 自动生成。这个设计的意图是**零配置启动**——单 worker 开发部署不需要手动管理内部 token。代价是多 worker 部署时必须手动设置为相同值，否则 worker 之间的内部调用会因 token 不匹配而失败。

### user_id 的传递链路

```
JWT decode (AuthMiddleware)
  → request.state.user (Starlette request context)
    → inject_authenticated_user_context() → config["context"]["user_id"]
      → RunManager → graph config
        → Sandbox provider → workspace 路径 /mnt/user-data/...
        → ThreadDataMiddleware → thread_data["user_id"]
        → 审计日志 + tracing span 属性
```

关键设计：`user_id` 被注入到 graph config 中，而不是依赖 Starlette request context。原因是 graph 在 `asyncio.create_task` 中异步执行，request context 在 task 开始前就可能已经被清理。把 `user_id` 放到 config 中确保它在 graph 执行全生命周期内可用。

### token_version 校验

JWT payload 中包含 `token_version` 字段，与 DB 中 user 记录的 `token_version` 对比。用户修改密码时 `token_version` 递增，所有旧 JWT 立即失效——不需要等 token 自然过期。这是 "sign out everywhere" 的实现机制。
