---
title: "端到端信任链"
description: "从外部请求到 agent 工具在沙箱中执行，经过的**每一个**安全检查点和它所保护的对象。"
topics: [security, auth, isolation-defense]
---

# 端到端信任链

从外部请求到 agent 工具在沙箱中执行，经过的**每一个**安全检查点和它所保护的对象。

## 完整链路

```
Browser / IM / Internal
  │
  ▼
┌─ Nginx (:2026) ─────────────────────────────────────────────┐
│ 反向代理 · 路由分发 · 限流（未配置）                          │
└──────────────────────────────────────────────────────────────┘
  │
  ▼
┌─ Gateway Middleware 链 ──────────────────────────────────────┐
│                                                              │
│  AuthMiddleware                                              │
│  ├─ 公开路径？→ 放行 (/health, /docs, /api/v1/auth/login..)  │
│  ├─ Internal Token？→ 合成内部用户，跳过 JWT/CSRF              │
│  ├─ JWT decode → DB user lookup → token_version 校验          │
│  └─ 设置 request.state.user + ContextVar                      │
│                                                              │
│  CSRFMiddleware                                              │
│  ├─ POST/PUT/DELETE/PATCH 到非 auth 路径？                    │
│  │   └─ compare_digest(cookie.csrf_token, header.X-CSRF-Token)│
│  └─ 登录端点额外 Origin 校验                                   │
│                                                              │
│  CORS (条件启用: GATEWAY_CORS_ORIGINS)                        │
└──────────────────────────────────────────────────────────────┘
  │
  ▼
┌─ Route Handler (services.py) ───────────────────────────────┐
│  @require_permission("runs:create")                          │
│  ├─ owner_check: 验证 user 拥有 thread                       │
│  ├─ require_existing: 不存在的 resource → 404 (非 403)       │
│  └─ model name allowlist 校验                                │
│                                                              │
│  inject_authenticated_user_context()                         │
│  └─ user_id → config["context"]["user_id"]                   │
│     (沙箱执行时即使 request context 丢失也能拿到)             │
└──────────────────────────────────────────────────────────────┘
  │
  ▼
┌─ RunManager → Agent Loop ───────────────────────────────────┐
│  asyncio.create_task(run_agent(config))                      │
│  user_id 在 config 中传递到 graph 执行                     │
└──────────────────────────────────────────────────────────────┘
  │
  ▼
┌─ Middleware Chain (每轮 step) ───────────────────────────────┐
│                                                              │
│  GuardrailMiddleware (第 6 位)                               │
│  └─ 每个 tool_call 执行前: provider.evaluate() → allow/deny  │
│                                                              │
│  SandboxAuditMiddleware (第 7 位)                             │
│  └─ bash 命令: regex 高危模式 block, 中危 warn, 日志记录     │
│                                                              │
│  LoopDetectionMiddleware (第 17 位)                          │
│  └─ 连续 5 次重复 tool_call → 强制产出 text                  │
└──────────────────────────────────────────────────────────────┘
  │
  ▼
┌─ Tool 执行层 ───────────────────────────────────────────────┐
│                                                              │
│  路径防穿越 (6 层)                                           │
│  ├─ ① .. 段检查 (tools.py:615)                               │
│  ├─ ② 虚拟路径族允许列表 (tools.py:624)                      │
│  ├─ ③ mount read_only 检查 (skills/acp)                      │
│  ├─ ④ 解析后 path.relative_to 检查 (tools.py:678)            │
│  ├─ ⑤ 沙箱层 containment (local_sandbox.py:127)              │
│  └─ ⑥ symlink 越界过滤 (list_dir.py:42 / search.py:186)      │
│                                                              │
│  命令执行                                                     │
│  ├─ allow_host_bash=false → bash 直接拒绝                    │
│  ├─ validate_local_bash_command_paths → 前缀白名单(不安全的) │
│  └─ _apply_cwd_prefix → cd workspace && (防 CWD 问题)       │
│                                                              │
│  输出处理                                                     │
│  ├─ 截断: bash(20k) · read(50k) · ls(20k) · glob(200)      │
│  ├─ 脱敏: host 路径 → mask 回虚拟路径                         │
│  └─ 错误清洗: 移除 host 路径                                 │
└──────────────────────────────────────────────────────────────┘
  │
  ▼
┌─ Sandbox Provider ──────────────────────────────────────────┐
│  Local: subprocess.run() 在 host 上                          │
│  Docker: HTTP API → 容器内执行                               │
│  K3s: HTTP API → Pod 内执行                                  │
│                                                              │
│  隔离边界: 无 · Docker namespace · Pod namespace             │
└──────────────────────────────────────────────────────────────┘
  │
  ▼
┌─ OS / Kernel ───────────────────────────────────────────────┐
│  seccomp: host默认 / unconfined(显式禁用) / host默认          │
│  AppArmor/SELinux: 未配置                                    │
│  no-new-privileges: 未配置                                   │
│  egress firewall: 无                                         │
└──────────────────────────────────────────────────────────────┘
```

本文是细粒度 14 层分析。粗粒度 7 层概览见 [00-overview.md](00-overview.md)。

## 保护层汇总

按请求到达顺序：

| # | 保护层 | 位置 | 拦截产物 | 失效后果 |
|---|--------|------|---------|---------|
| 1 | JWT 认证 | `auth_middleware.py:75` | 无凭据请求 | 任意人调 API |
| 2 | CSRF | `csrf_middleware.py:180` | 跨站伪造 | 其他站点以用户身份操作 |
| 3 | Internal Token | `internal_auth.py:32` | 未授权内部调用 | 未授权组件间通信 |
| 4 | 输入校验 | `services.py:79` / `routers/auth.py:41` | 格式错误/弱密码 | SQL注入(ORM防护)/弱凭据 |
| 5 | 权限 | `authz.py:197` | 越权访问 | 用户间数据泄露 |
| 6 | Guardrail | `guardrails/middleware.py:55` | 未授权 tool 调用 | LLM 调用危险 tool |
| 7 | SandboxAudit | `sandbox_audit_middleware.py` | 高危 bash 命令 | 文件破坏/信息泄露 |
| 8 | 路径防穿越 | `tools.py:615-678` | 路径逃逸 | 读越界文件 |
| 9 | allow_host_bash | `tools.py:1344` | host shell 调用 | 任意代码执行 |
| 10 | 输出截断 | `tools.py` 多处 | 超大输出 | OOM/context 爆炸 |
| 11 | 输出脱敏 | `tools.py:541` | host 路径泄露 | 内部目录结构外泄 |
| 12 | 沙箱进程隔离 | `sandbox/` | 容器/Pod 逃逸 | host 被控制 |
| 13 | 登录限流 | `routers/auth.py:149` | 暴力破解 | 弱密码被猜出 |
| 14 | 循环检测 | `loop_detection_middleware` | 死循环 tool call | 资源耗尽 |

## 信任边界

三条数据流的 trust boundary 不同：

```
Browser:  认证边界在 JWT cookie → user_id 隔离所有数据
Internal: 信任边界在 token 匹配 → 所有请求合并为 "default"
IM:       信任边界在平台 webhook 签名 → 然后走 Internal 路径 → "default"
```

**IM channel 是最弱的边界** — 所有 IM 用户共享 `"default"` user_id，无法区分是哪个 IM 用户发了消息。对于需要 per-user 隔离的生产部署，这需要额外改造。
