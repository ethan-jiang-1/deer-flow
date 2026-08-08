---
title: "Digest 更新计划 #4"
description: "基于 upstream cd34a1a5 → e5c62cab 的 234 commits 变更，逐目录规划 digest 更新内容和优先级。"
type: index
---

# Digest 更新计划 #4

> 基准：`cd34a1a5` → `e5c62cab`（234 commits），2026-08-08
> 变更规模：931 files, +141,080 / -9,322 lines（比 #3 的 594 files 大）
> 提交构成：142 fix / 46 feat / 11 build / 6 perf / 4 test / 3 docs
> 时间跨度：2026-07-20 → 2026-08-07

## ▶ 步步为营执行清单

| 步 | 文件 | 做什么 |
|----|------|--------|
| 1 | `concepts/sandbox/abstract-interface-and-five-impls.md` | 🔴 重写+改名：5→6 实现（+Tenki），E2B/AIO 大改，orphan reconciliation，sandbox middleware |
| 2 | `concepts/memory/extract-queue-persist-pipeline.md` | 🔴 更新：+OpenViking 第 3 后端，storage 重构，markdown 存储 |
| 3 | `operations/channels/` | 🔴 更新：+Buzz 新频道，+Lark CLI/broker 集成 |
| 4 | `operations/security/01-auth.md` | 🟡 更新：pluggable authorization 落地（authz/ 子包） |
| 5 | `internals/runtime/` | 🟡 更新：worker 重构，multi-worker run ownership，rollback |
| 6 | `internals/configuration/` | 🟡 更新：config_version 28→33 |
| 7 | `concepts/community-tools/` | 🟡 更新：+browser_automation，provider 列表 |
| 8 | `internals/middleware/03-catalog.md` | 🟡 更新：34→41，+2 新中间件 |
| 9 | `frontend/` 全部文件 | 🟡 更新：257 files 大改 |
| 10 | `operations/deployment/` | 🟡 更新：lark-cli docker, openviking compose |
| 11 | `concepts/builtin-tools/` | 🟢 验证：tools 11 files |
| 12 | `concepts/skills-tools/` | 🟢 验证：skills 8 files |
| 13 | `concepts/subagent/` | 🟢 验证：subagents 5 files |
| 14 | `getting-started/06-tui.md` | 🟢 验证：tui 5 files |
| 15 | `internals/mcp/`, `internals/model-layer/` | 🟢 验证 |
| 16 | `operations/security/03-guardrail.md` | 🟢 验证：guardrails 1 file |
| 17 | ⚪ 新子系统 digest | ⚪ 新增：workspace_changes, Buzz, Lark, Browser Automation, authz, Tenki |
| 18 | 🔢 数字审计 | grep 全 digest 修复旧数字 |
| 19 | 🔗 交叉引用检查 | 确保所有链接可达 |
| 20 | 🚶 开发者旅程走查 | 模拟完整阅读路径 |

---

## 优先级说明

| 级别 | 含义 |
|------|------|
| 🔴 P0 | **必须重写**——旧内容已严重过期，不更新会误导 |
| 🟡 P1 | **需要更新**——核心内容有新增或变更 |
| 🟢 P2 | **需要验证**——内容可能仍然正确，需对比确认 |
| ⚪ P3 | **建议补充**——全新子系统，值得添加但非紧急 |

---

## 🔴 P0：必须重写（3 个领域）

### 1. `concepts/sandbox/` — Sandbox 系统（代码量最大）

**变化**：E2B 和 AIO 两个 provider 各重写了 +1000+ 行，新增第 6 个 provider，加上沙箱清理、孤儿回收。

| 关键变更 | 细节 |
|---------|------|
| **Tenki provider（新，第 6 实现）** | 云 microVM（tenki.cloud），复用 WarmPoolLifecycleMixin，懒加载 SDK，`community/tenki/` 子包 |
| **E2B provider 重构** | `e2b_sandbox_provider.py` +1576/-229，测试 +2739 |
| **AIO provider 重构** | `aio_sandbox_provider.py` +1349/-106 |
| **Orphan reconciliation** | 沙箱孤儿回收机制，测试 +2315（`test_sandbox_orphan_reconciliation.py`） |
| **Local sandbox 更新** | `sandbox/local/` 多文件改动 |
| **Sandbox middleware** | `sandbox/middleware.py` 更新 |
| **Path pattern guards / overwrite** | `sandbox/overwrite.py`, `sandbox/search.py` |

| 文件 | 行动 |
|------|------|
| `abstract-interface-and-five-impls.md` | 🔴 **重写 + 改名**：`abstract-interface-and-six-impls.md`，加 Tenki，E2B/AIO 新生命周期，orphan reconciliation |
| `concepts/community-tools/04-aio-sandbox.md` | 🟡 更新：AIO provider 重构后的新行为 |
| `operations/security/02-sandbox-isolation.md` | 🟢 验证：6 种实现、孤儿回收对隔离的影响 |

### 2. `concepts/memory/` — Memory 系统（+第 3 后端）

**变化**：在 #3 的可插拔后端架构之上，新增第三个后端 OpenViking，同时 storage 层大改。

| 关键变更 | 细节 |
|---------|------|
| **OpenViking backend（新）** | `agents/memory/backends/openviking/`（manager + config + session），官方 OpenViking adapter（#4707），docs/OPENVIKING.md + docker-compose.openviking.yaml |
| **DeerMem storage 重构** | `backends/deermem/.../storage.py` +1463/-116 |
| **Markdown 存储** | `test_memory_storage_markdown.py` +1189——memory 支持 markdown 格式持久化 |
| **阻塞 IO 检测** | `test_detect_blocking_io_static.py` +992，memory 后端也有相应测试 |

| 文件 | 行动 |
|------|------|
| `extract-queue-persist-pipeline.md` | 🔴 更新：后端数 2→3（deermem, noop, openviking），OpenViking 配置（`memory.backend_config` 新增段）、markdown 存储 |

### 3. `operations/channels/` — IM 频道（2 个新通道）

**变化**：新增 Buzz 频道 + Lark CLI 集成，DingTalk/Feishu 也有更新。

| 关键变更 | 细节 |
|---------|------|
| **Buzz 频道（新）** | `app/channels/buzz.py` +1413，`buzz_nostr.py`（Nostr 协议）+201，`buzz_run_policy.py`，`dedupe_store.py` +276（消息去重存储），测试 +2015 |
| **Lark CLI / Lark broker（新）** | `integrations/lark_cli.py` +1724（CLI 交互），`integrations/lark_broker.py`（broker 服务），docker/lark-cli-broker + lark-cli-init，新 CI workflow `lark-cli-images.yaml` |
| **DingTalk 更新** | `dingtalk.py` +276/-3 |
| **Feishu 更新** | `feishu.py` +48/-23 |
| **Channel manager** | `channels/manager.py` +547/-94 |

| 文件 | 行动 |
|------|------|
| `00-overview.md` | 🟡 更新：频道列表 +Buzz +Lark |
| `05-user-connections.md` | 🟡 验证：Buzz/Lark 的用户连接模型 |
| 新增 `06-buzz.md` + `07-lark-cli.md` | ⚪ P3：新通道 digest |

---

## 🟡 P1：需要更新（6 个领域）

### 4. `operations/security/01-auth.md` — Pluggable Authorization 落地

**变化**：UPDATE_PLAN_3 里还是 P3 的 AuthorizationProvider，这轮真正实现了。

| 关键变更 | 细节 |
|---------|------|
| **`authz/` 子包（新，8 文件）** | `provider.py`（协议）、`adapter.py`、`enforcement.py`、`principal.py`、`rbac.py`（RBAC）、`runtime.py`、`tool_filter.py`（工具级鉴权过滤）、`__init__.py` |
| **RFC + 实现笔记** | `docs/plans/2026-07-10-pluggable-authorization-rfc.md` + `-implementation-notes.md` |
| **Gateway 测试** | `test_gateway_services.py` +1136 |

| 文件 | 行动 |
|------|------|
| `01-auth.md` | 🟡 更新：AuthorizationProvider protocol、RBAC、principal resolution、tool_filter |
| 新增 `02-authorization.md` | ⚪ P3：这次有真实代码可以写了 |

### 5. `internals/runtime/` — Run Worker 重构

| 关键变更 | 细节 |
|---------|------|
| **Worker 重构** | `runtime/runs/worker.py` +1024/-240，`test_run_worker_rollback.py` +1323（回滚），`test_thread_regenerate_prepare.py` +1215 |
| **Multi-worker run ownership** | `test_multi_worker_run_ownership.py` +988 |
| **Persistence 大改（27 files）** | `persistence/` 子包 + docs/plans/STORAGE_REWRITE_CHANGES.md |

| 文件 | 行动 |
|------|------|
| `internals/runtime/` 全部 | 🟡 更新：worker 生命周期、run ownership、rollback |
| `internals/runtime/goal-continuation.md` | 🟢 验证 |

### 6. `internals/configuration/` — Config 更新

**变化**：`config_version: 28 → 33`，config.example.yaml +518/-25。

| 文件 | 行动 |
|------|------|
| `01-config-yaml.md` | 🟡 更新：新段（openviking memory, authz, sandbox.tenki 等） |
| `04-config-reference.md` | 🟡 更新：字段列表，version 28→33 |

### 7. `concepts/community-tools/` — 新社区工具

| 关键变更 | 细节 |
|---------|------|
| **Browser Automation（新）** | `community/browser_automation/`（session.py +1020, tools.py），测试 +1066 |
| **Tenki** | 见 sandbox P0 |
| **community 子包** | 26 files 改动 |

| 文件 | 行动 |
|------|------|
| `00-overview.md` | 🟡 更新 provider 列表 +browser_automation |
| 新增 `06-browser-automation.md` | ⚪ P3 |

### 8. `internals/middleware/` — 中间件 +2

**变化**：中间件文件数 34 → 41。

| 新增中间件 | 作用 |
|-----------|------|
| **ConfiguredExtensionsMiddleware** | `configured_extensions.py`——配置驱动的扩展注入 |
| **ModelLengthFinishReasonMiddleware** | `model_length_finish_reason_middleware.py` + `model_length_termination_detectors.py`——模型长度终止检测 |

| 文件 | 行动 |
|------|------|
| `03-catalog.md` | 🟡 更新：+2 新中间件，数字 34→41 |
| `02-chain-assembly.md` | 🟢 验证：顺序是否变化 |

### 9. `frontend/` — 257 files 大改

**变化**：56 components + 55 core + 28 app + 76 test + 16 e2e。`hooks.ts` +1080。

| 文件 | 行动 |
|------|------|
| `00-overview.md` | 🟡 更新功能列表 |
| `02-message-rendering.md` / `03-state-management.md` | 🟡 更新 |
| `04-workspace-layout.md` / `05-subagent-ui.md` | 🟢 验证 |

### 10. `operations/deployment/` — 新部署组件

| 文件 | 行动 |
|------|------|
| `01-docker.md` | 🟡 更新：lark-cli-broker/init 镜像、openviking compose |
| `02-nginx-and-k8s.md` | 🟢 验证 |

---

## 🟢 P2：需要验证（4 个领域）

| 领域 | 变化 | 行动 |
|------|------|------|
| `concepts/builtin-tools/` | tools 11 files | 🟢 验证工具变更 |
| `concepts/skills-tools/` | skills 8 files（skill_tool_policy_middleware, skill_activation） | 🟢 验证 |
| `concepts/subagent/` | subagents 5 files（subagent_limit_middleware） | 🟢 验证 |
| `getting-started/06-tui.md` | tui 5 files | 🟢 验证 |
| `internals/mcp/`, `internals/model-layer/` | 各 2 files | 🟢 验证 |
| `operations/security/03-guardrail.md` | guardrails 1 file | 🟢 验证 |

---

## ⚪ P3：建议补充（6 个新主题）

| 子系统 | 建议文件 | 内容 |
|--------|---------|------|
| **Workspace Changes** | `internals/runtime/workspace-changes.md` | 全新子系统：记录 agent 对 workspace 的文件改动（api/diff/recorder/scanner/types），前端展示 "change review" |
| **Pluggable Authorization** | `operations/security/02-authorization.md` | authz/ 子包：provider protocol、RBAC、principal、tool_filter |
| **Buzz 频道** | `operations/channels/06-buzz.md` | Buzz + Nostr 频道、dedupe_store、run policy |
| **Lark CLI** | `operations/channels/07-lark-cli.md` | lark_cli + lark_broker、CLI 交互、docker 镜像 |
| **Browser Automation** | `concepts/community-tools/06-browser-automation.md` | 浏览器自动化 session/tools |
| **OpenViking Memory** | `concepts/memory/openviking-backend.md` | 第三个 memory 后端、HTTP 集成 |

---

## 执行顺序建议

1. 🔴 **concepts/sandbox/** — 代码量最大，先做
2. 🔴 **concepts/memory/** — OpenViking 新后端
3. 🔴 **operations/channels/** — 2 个新通道
4. 🟡 **operations/security/01-auth.md** — authz 落地
5. 🟡 **internals/runtime/ + configuration/** — worker + config
6. 🟡 **internals/middleware/** + **concepts/community-tools/** — +2 中间件 + 新工具
7. 🟡 **frontend/** — 大改
8. 🟢 验证其余文件
9. ⚪ 新子系统 digest
10. 🔢 数字审计 → 🔗 交叉引用 → 🚶 旅程走查

预计工作量：🔴 3 文件重写 + 🟡 12 文件更新 + 🟢 10 文件验证 + ⚪ 6 新文件 ≈ **31 个文件**。

---

## 数字一致性审计

| 数字 | 旧值 | 新值 | 搜索 pattern |
|------|------|------|-------------|
| Sandbox 实现数 | 5 | **6**（+Tenki） | `grep -r "five\|5 种\|五个" _digest/` |
| 中间件数 | 34 | **41**（文件数；+2 真实新中间件） | `grep -r "34.*middleware\|middleware.*34" _digest/` |
| Config version | 28 | **33** | `grep -r "28\|config_version" _digest/` |
| Memory 后端数 | 2（deermem, noop） | **3**（+openviking） | 更新 `concepts/memory/` |
| 频道数 | 5 | **6+**（+Buzz +Lark CLI） | 更新 `operations/channels/` |

---

## 开发者旅程连贯性

```
overview/01-system-overview.md       → sandbox 6？middleware 41？config 33？
concepts/sandbox/                    → 6 种实现，文件名已改？
concepts/memory/                     → 3 后端，OpenViking 已说明？
operations/channels/                 → Buzz + Lark 已说明？
operations/security/01-auth.md       → AuthorizationProvider 落地已说明？
internals/middleware/03-catalog.md   → 41 个完整目录？
internals/runtime/                   → worker 重构、run ownership 已说明？
frontend/                            → 新功能已更新？
```

---

## Part 2：质量保证 — 自洽性检查

### 交叉引用完整性

| 引用关系 | 检查点 |
|---------|--------|
| `concepts/sandbox/` 文件名 | five → six |
| 所有引用 sandbox 数量的地方 | grep `5 种` → `6 种` |
| `internals/middleware/03-catalog.md` → 中间件数 | 34 → 41 |
| `overview/01-system-overview.md` → 中间件/sandbox/config 数字 | 同步更新 |
| `operations/channels/` → 频道列表 | 加 Buzz、Lark |

### 内容矛盾检测

| 旧内容断言 | 新代码现实 | 风险 |
|-----------|-----------|------|
| "Sandbox 有 5 种实现" | 现在有 6 种（+Tenki） | 🟡 需更新 |
| "中间件共 34 个" | 文件数 41，+2 新中间件 | 🟡 需更新 |
| "Memory 有 deermem/noop 两个后端" | +OpenViking 第三后端 | 🟡 需更新 |
| "Auth 只有 OIDC/SSO + API key" | +AuthorizationProvider 落地 + RBAC + tool_filter | 🟡 需更新 |
| "频道有 5 个" | +Buzz +Lark | 🟡 需更新 |
| "AIO/E2B sandbox 生命周期" | 大幅重构 + orphan reconciliation | 🟡 需更新 |
