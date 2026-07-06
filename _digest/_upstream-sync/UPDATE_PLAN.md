---
title: "Digest 更新计划"
description: "基于 upstream 162fb214 → 4915b5e 的 323 commits 变更，逐目录规划 digest 更新内容和优先级。"
type: index
---

# Digest 更新计划

> 基准：`162fb214` → `4915b5e`（323 commits），2026-07-07

## 优先级说明

| 级别 | 含义 |
|------|------|
| 🔴 P0 | **必须重写**——旧内容已严重过期，不更新会误导 |
| 🟡 P1 | **需要更新**——核心内容有新增或变更 |
| 🟢 P2 | **需要验证**——内容可能仍然正确，需对比确认 |
| ⚪ P3 | **建议补充**——全新子系统，值得添加但非紧急 |

---

## 🔴 P0：必须重写

### 1. `internals/middleware/` — 中间件目录

**变化**：19 → 29 个中间件。新增 10 个，ToolErrorHandlingMiddleware 大幅重构（新增 `deerflow_tool_meta` 结构化信号），顺序重排。

| 文件 | 行动 |
|------|------|
| `03-catalog.md` | 🔴 **重写**：29 个中间件完整目录，含新增的 10 个 |
| `02-chain-assembly.md` | 🔴 **重写**：两阶段组装（base 12 + lead-only 17），新的 ordering 规则 |
| `01-hooks-and-flow.md` | 🟡 **验证**：6 hook 点不变，但中间件之间的数据流变了 |
| `00-overview.md` | 🟡 **更新**：设计哲学部分可保留，数字更新 |
| `04-claude-code-comparison.md` | 🟢 **验证**：对比点可能仍然成立 |

### 2. `concepts/skills-tools/` — Skills 系统

**变化**：新增 deferred discovery（`catalog.py` + `describe.py` + `SkillCatalog`）、request-scoped secrets、slash activation（`SkillActivationMiddleware`）、`skill_context` 状态字段。

| 文件 | 行动 |
|------|------|
| `skill-md-and-tool-assembly.md` | 🔴 **重写**：加入 deferred vs legacy 双模式、secrets 生命周期、slash 激活 |

---

## 🟡 P1：需要更新

### 3. `concepts/lead-agent/` — Agent 系统

**变化**：ThreadState 新增 4 个字段（`delegations`、`skill_context`、`summary_text`、`promoted`），3 个新 reducer。

| 文件 | 行动 |
|------|------|
| `factory-and-threadstate.md` | 🟡 添加新 ThreadState 字段说明 |

### 4. `concepts/sandbox/` — Sandbox 系统

**变化**：新增 BoxLite 和 E2B 两个 provider、`WarmPoolLifecycleMixin` 共享生命周期、`env_policy.py` 环境变量擦洗。

| 文件 | 行动 |
|------|------|
| `abstract-interface-and-three-impls.md` | 🟡 从 3 种实现扩展为 5 种（+BoxLite +E2B），添加 warm pool 和 env scrubbing 说明 |

### 5. `concepts/subagent/` — Sub-agent 系统

**变化**：turn-budget cap（`MAX_TURNS_REACHED`）、step capture & persistence（`step_events.py`）、checkpointer isolation、`deferred_setup` 支持。

| 文件 | 行动 |
|------|------|
| `dual-threadpool-and-lifecycle.md` | 🟡 添加 turn-budget cap、step persistence、checkpointer isolation |

### 6. `concepts/memory/` — Memory 系统

**变化**：staleness review（同一次 LLM 调用中检测过期 fact）、token counting（tiktoken vs char 双策略）、guaranteed categories、同步更新路径修复。

| 文件 | 行动 |
|------|------|
| `extract-queue-persist-pipeline.md` | 🟡 添加 staleness review、token counting、guaranteed categories |

### 7. `internals/agent-loop/` — Agent Loop

**变化**：核心执行流不变（仍是 ReAct 循环），但中间件链大幅扩展影响了 hook 时序。

| 文件 | 行动 |
|------|------|
| `00-loop-anatomy.md` | 🟡 更新中间件数量引用 |
| `03-code-trace.md` | 🟡 更新 middleware 名称和顺序 |

### 8. `internals/configuration/` — 配置系统

**变化**：config version 10→19，新增 11 个配置段（`logging.enhance`、`token_budget`、`tool_output`、`tool_progress`、`read_before_write`、`scheduler`、`stream_bridge`、`channel_connections`、`auth.oidc` 等），`checkpointer` 段标记 deprecated。

| 文件 | 行动 |
|------|------|
| `01-config-yaml.md` | 🟡 添加新 sections |
| `04-config-reference.md` | 🟡 更新字段列表 |

### 9. `operations/security/` — 安全

**变化**：新增 InputSanitizationMiddleware（prompt injection 防御）、env_policy 密钥擦洗、request-scoped secrets 完整生命周期。

| 文件 | 行动 |
|------|------|
| `03-guardrail.md` | 🟡 添加 InputSanitization + env scrubbing + secrets redaction |

### 10. `operations/app-layer/` — Gateway API

**变化**：新增 Console router、TraceMiddleware、Goal 模块、Redis StreamBridge、Alembic migrations、GitHub webhooks、channel connections。

| 文件 | 行动 |
|------|------|
| `00-overview.md` | 🟡 添加新路由和新子系统 |
| `01-api-reference.md` | 🟡 添加 console、goal、channel connections 端点 |

---

## 🟢 P2：需要验证

### 11. `internals/harness-hooks/`

**变化**：`tool_result_meta.py` 新增结构化 tool result 元数据、配置热加载改用 content digest（非 mtime）。

| 文件 | 行动 |
|------|------|
| `01-config-hot-reload.md` | 🟢 验证：mtime → content digest |
| 新增文件 | 🟢 考虑添加 `tool_result_meta.md` |

### 12. `internals/runtime/`

**变化**：StreamBridge 从单实现变为抽象协议（Memory + Redis）、Goal 模块新增。

| 文件 | 行动 |
|------|------|
| `02-stream-bridge.md` | 🟢 验证：添加 Redis 后端说明 |
| 新增文件 | 🟢 考虑添加 `goal-continuation.md` |

### 13. `testing/`

**变化**：新增 record/replay e2e 测试、大量新测试文件。

| 文件 | 行动 |
|------|------|
| `03-e2e-and-unit.md` | 🟢 添加 record/replay 模式 |

### 14. `overview/`

**变化**：架构总览需要进行数字更新（中间件数、Sandbox 实现数）。

| 文件 | 行动 |
|------|------|
| `01-system-overview.md` | 🟢 更新数字（29 middlewares, 5 sandbox impls） |
| `03-logical-architecture.md` | 🟢 SVG 可能需要更新 |

---

## ⚪ P3：建议补充

### 15. 全新子系统 — 值得写新 digest

| 子系统 | 建议文件 | 内容 |
|--------|---------|------|
| **TUI** | `getting-started/06-tui.md` | `deerflow` 终端工作台：安装、模式（`--tui`/`--print`/`--json`）、slash palette、goal 管理 |
| **Goal 续跑** | `internals/goal-continuation.md` | Thread goal 自动续跑循环：evaluator 模型、blocker 类型、no-progress breaker |
| **Record/Replay 测试** | `testing/07-record-replay.md` | `ReplayChatModel` 确定性 e2e、golden JSON、`DEERFLOW_WRITE_GOLDEN` |
| **Deferred Skill Discovery** | `concepts/skills-tools/deferred-discovery.md` | `SkillCatalog` + `describe_skill` vs legacy 全量注入 |
| **Request-Scoped Secrets** | `concepts/skills-tools/request-secrets.md` | 声明→携带→绑定→注入→擦洗→脱敏 六步生命周期 |
| **Channel Connections** | `operations/channels/user-owned-connections.md` | 用户绑定的 IM 频道：connect code、provider auth、single-active-owner |

---

## 执行顺序建议

1. 🔴 **internals/middleware/** — 影响面最大，先做
2. 🔴 **concepts/skills-tools/** — API 层变化大
3. 🟡 **concepts/lead-agent, sandbox, subagent, memory** — 核心概念更新
4. 🟡 **internals/agent-loop, configuration** — 内部机制更新
5. 🟡 **operations/security, app-layer** — 运维层更新
6. 🟢 验证其余文件
7. ⚪ 补充新子系统

预计工作量：🔴 2 文件重写 + 🟡 10 文件更新 + 🟢 5 文件验证 + ⚪ 6 新文件 = 约 23 个文件的变更。
