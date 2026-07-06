---
title: "访问控制"
description: "谁在用 agent？agent 在替谁执行操作？权限边界在哪里？"
topics: [governance, compliance, audit]
---

# 访问控制

谁在用 agent？agent 在替谁执行操作？权限边界在哪里？

## 认证体系

DeerFlow 的认证是**人**的认证，不是 **agent** 的认证。Agent 本身没有独立身份——它在用户上下文里跑。

### 三层认证

| 层级 | 机制 | 作用 |
|------|------|------|
| **Web UI** | JWT（access + refresh token） | 前端用户登录 |
| **API** | CSRF token + JWT | 防跨站请求伪造 |
| **内部服务** | Internal Gateway Token（`X-DeerFlow-Internal-Token`） | Gateway ↔ LangGraph runtime、IM channels ↔ Gateway |

### JWT 认证流

```
用户登录 → POST /api/auth/login → 验证密码 → 返回 access_token + refresh_token
    → 后续请求带 Authorization: Bearer <access_token>
    → access_token 过期 → POST /api/auth/refresh → 新 access_token
```

### Internal Gateway Token

`deerflow/auth/internal_token.py` — Gateway 和 LangGraph runtime 之间的内部认证。IM channels（飞书、Slack、Telegram）也用它来调 Gateway API。这个 token 是**进程级共享的**——所有 worker 用同一个——确保内部服务调用不被 JWT 过期影响。

### 登录限速

`security/01-auth.md` — 有登录频率限制，防止暴力破解。

## 用户隔离

### Per-User 存储

```
backend/.deer-flow/users/{user_id}/
    threads/{thread_id}/user-data/{workspace,uploads,outputs}/
    memory.json
    agents/{agent_name}/
```

每个用户的 thread、memory、custom agent 都在自己的目录下。迁移脚本 `scripts/migrate_user_isolation.py` 支持将 legacy 数据迁到 per-user 布局。

### user_id 解析

- 有 auth：从 JWT 中提取
- No-auth 模式：`user_id = "default"`（所有人共享）

### No-Auth 模式的风险

`DEER_FLOW_AUTH_ENABLED=false` 或 `config.yaml` 中不配 auth 时：

| 风险 | 影响 |
|------|------|
| **所有人共享 `default` user** | thread、memory、sandbox workspace 全部混在一起 |
| **无操作溯源** | 审计日志无法区分是哪个真人触发的操作 |
| **无权限边界** | 任何人都能看到和操作所有 thread |
| **CSRF 保护可能关闭** | 取决于 gateway 配置 |

**IT 管理建议：** 在任何非本地开发环境中，必须启用认证。No-auth 模式只适用于个人单机使用。

## Agent 身份：缺失的一环

2026 年行业共识是 **Agent 应该有自己的身份（Non-Human Identity, NHI）**，独立于触发它的用户。原因：

```
用户 Alice → 触发 Agent → Agent 执行操作 → 审计记录显示 "Alice 做了 X"

但实际上是 Agent 决策了 X，Alice 只是说了 "帮我整理文件"
```

DeerFlow 目前没有 NHI 概念。Agent 操作被审计为**用户操作**。这带来了几个问题：

- **权限最小化做不到** — Agent 继承了用户的所有权限，即使任务只需要其中的一小部分
- **责任归属模糊** — 如果 agent 做了用户没预料到的事（如 LLM 自发决定删文件），审计记录显示是用户干的
- **多 agent 协作无区分** — Lead agent、subagent、ACP agent 的操作都归因到同一个 user

**行业方向：** 参考 Oasis AAM Framework、Microsoft Agent Governance Toolkit 的 Agent DID（Decentralized Identifier）和 Zero Standing Privileges（无静态权限，每次操作申请临时授权）。DeerFlow 与这些方案不矛盾——可以在上层加。

## 凭证管理

`deerflow/models/credential_loader.py` 自动从多个来源加载 LLM API 凭证：

| 来源 | 优先级 |
|------|--------|
| `config.yaml` 中的 `api_key: $ENV_VAR` | 环境变量 |
| `~/.claude/.credentials.json` | Claude Code CLI OAuth |
| `CLAUDE_CODE_OAUTH_TOKEN` | 环境变量 |
| `~/.codex/auth.json` | Codex CLI |

**安全考量：** 凭证以明文存在环境变量和文件中。在生产环境中，应该用 secret manager（如 Vault、AWS Secrets Manager）替代。`api_key: $VAR` 的 env var 解析在 AppConfig 是严格模式（缺了就报 ValueError），在 ExtensionsConfig 是宽松模式（缺了存空串）。

## Gateway API 层访问控制

| 控制 | 机制 |
|------|------|
| **CORS** | `GATEWAY_CORS_ORIGINS` 环境变量（默认 same-origin） |
| **CSRF** | CSRFMiddleware，检查 Origin/Referer header |
| **API rate limiting** | 无内置——需在 nginx 层配置 |
| **API key auth** | 无——依赖 JWT + CSRF |

## 建议的加固方向

按优先级排列：

1. **启用认证**（如果还没启用）— 这是最基本的
2. **在 nginx 层加 rate limiting** — 防止 API 滥用
3. **评估是否需要 NHI** — 如果多用户共享 agent 或者有合规要求
4. **凭证托管** — 生产环境用 secret manager 替代 env var + 明文文件
5. **加 input guardrail** — 在前置网关层做 prompt injection 检测（DeerFlow 本身不提供）

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
