---
title: "Digest 更新计划"
description: "基于 upstream 162fb214 → 4915b5e 的 323 commits 变更，逐目录规划 digest 更新内容和优先级。"
type: index
---

# Digest 更新计划

> 基准：`162fb214` → `4915b5e`（323 commits），2026-07-07

## ▶ 步步为营执行清单

| 步 | 文件 | 做什么 |
|----|------|--------|
| 1 | `internals/middleware/03-catalog.md` | 🔴 重写：29 个中间件完整目录 |
| 2 | `internals/middleware/02-chain-assembly.md` | 🔴 重写：两阶段组装 |
| 3 | `internals/middleware/00-overview.md` | 🟡 更新数字 19→29 |
| 4 | `concepts/skills-tools/skill-md-and-tool-assembly.md` | 🔴 重写：加 deferred discovery + secrets |
| 5 | `concepts/skills-tools/` 拆子目录 | 🟡 新增 deferred-discovery.md + request-secrets.md |
| 6 | `concepts/lead-agent/factory-and-threadstate.md` | 🟡 加 4 个新 ThreadState 字段 |
| 7 | `concepts/sandbox/abstract-interface-and-three-impls.md` | 🟡 3→5 种实现 |
| 8 | `concepts/subagent/dual-threadpool-and-lifecycle.md` | 🟡 加 turn-budget cap, step persistence |
| 9 | `concepts/memory/extract-queue-persist-pipeline.md` | 🟡 加 staleness review, token counting |
| 10 | `internals/agent-loop/00-loop-anatomy.md` | 🟡 更新数字 |
| 11 | `internals/agent-loop/03-code-trace.md` | 🟡 更新 middleware 名称 |
| 12 | `internals/configuration/01-config-yaml.md` | 🟡 加新 sections |
| 13 | `operations/security/03-guardrail.md` | 🟡 加 InputSanitization + env scrubbing |
| 14 | `operations/app-layer/00-overview.md` | 🟡 加新路由 |
| 15 | `operations/app-layer/01-api-reference.md` | 🟡 加新端点 |
| 16 | 🔢 数字审计 | grep 全 digest 修复旧数字 |
| 17 | 🔗 交叉引用检查 | 确保所有链接可达 |
| 18 | `overview/01-system-overview.md` | 🟢 更新全览数字 |
| 19 | `getting-started/06-tui.md` | ⚪ 新：TUI 终端 |
| 20 | `internals/runtime/goal-continuation.md` | ⚪ 新：Goal 续跑 |
| 21 | `testing/07-record-replay.md` | ⚪ 新：record/replay |
| 22 | 🔢 全量 grep 数字审计 | 搜 `19`、`3 种`、`16 个`、`26 个`，逐个核实修复 |
| 23 | 🔗 交叉引用检查 | 确保所有 digest 间链接可达、名称匹配 |
| 24 | 📋 矛盾检测 10 条 | 逐条核对旧断言是否被新代码推翻 |
| 25 | 🗂️ 结构一致性 | 确认目录结构不需要进一步调整 |
| 26 | 🚶 开发者旅程走查 | 模拟 overview→concepts→internals→operations 完整阅读路径 |

---

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

---

# Part 2：质量保证 — 自洽性检查

> 加了新内容之后，旧的消化内容是否还逻辑自洽、结构合理、没有矛盾？

## A. 交叉引用完整性

更新任何文件后，必须检查所有引用它的地方是否仍然一致。

| 引用关系 | 检查点 |
|---------|--------|
| `overview/01-system-overview.md` → middleware 数量 | 改为 29 |
| `internals/agent-loop/` → middleware 数量 | 改为 29 |
| `internals/agent-loop/03-code-trace.md` → middleware 名称列表 | 更新为新的 29 个名称 |
| `concepts/sandbox/` → 实现数量 | 改为 5（Local, AIO, BoxLite, E2B, Provisioner） |
| `concepts/lead-agent/` → ThreadState 字段 | 补充 4 个新字段 |
| `operations/security/02-sandbox-isolation.md` → sandbox 数量 | 改为 5 |
| 所有 README.md 中引用 middleware 数量的地方 | grep `19` → 改为 `29` |
| `overview/figures/agent-loop.svg` | 更新 middleware 链可视化 |

**执行方式**：grep 全 digest 目录搜索 `19`（旧中间件数）、`3 种`（sandbox 数）、`three`（sandbox），逐个核实。

## B. 内容矛盾检测

新功能可能让旧内容变成错误。需要逐条验证：

| 旧内容断言 | 新代码现实 | 风险 |
|-----------|-----------|------|
| "Skills 在系统 prompt 中全量注入" | deferred discovery 模式下只有名字列表 | 🟡 旧断言不再普遍成立 |
| "Sandbox 有三种实现" | 现在有 5 种（+BoxLite +E2B） | 🟡 需要更新 |
| "配置热加载靠 mtime 检测" | 改为 content digest | 🟢 小改 |
| "中间件共 19 个" | 现在是 29 个 | 🔴 全 digest 散布此数字 |
| "checkpointer 配置在 checkpointer 段" | 已 deprecated，改用 database 段 | 🟡 需要更新 configuration/ |
| "Memory 是 fire-and-forget 队列" | 新增 staleness review + guaranteed categories | 🟡 补充但不矛盾 |
| "Subagent 失败即 FAILED" | 新增 MAX_TURNS_REACHED 状态 | 🟡 补充 |
| "StreamBridge 是内存实现" | 新增 Redis 后端 | 🟡 补充 |
| "DeerFlow 没有 CLI" | 现在有 `deerflow` 终端命令 | 🟡 需要更新 getting-started/ 和 cli-and-sdd/ |
| "Gateway router 有 16 个" | 新增 console、features、channel_connections、github_webhooks、scheduled_tasks | 🟡 需要更新 app-layer/ |

**执行方式**：逐条核对，更新或标注。

## C. 结构一致性

新增内容后，目录结构是否需要调整？

| 问题 | 判断 |
|------|------|
| `concepts/skills-tools/` 只有一个文件，加 deferred-discovery 和 request-secrets 后是否需要拆成子目录？ | 建议拆：`skill-md-and-tool-assembly.md` 保留为主文件，新增 `deferred-discovery.md` 和 `request-secrets.md` 作为 detail |
| `internals/` 是否需要为 Goal 模块新增子目录？ | 可放在 `internals/runtime/` 下（Goal 是 runtime 层功能） |
| `getting-started/` 是否需要添加 TUI 内容？ | 建议添加 `06-tui.md` |
| `concepts/sandbox/` 单一文件是否需要拆？ | 5 种实现仍然可以放在一个文件里，但建议加子目录结构以便后续扩展 |

## D. 数字一致性审计

全 digest 范围内需要统一的数字：

| 数字 | 旧值 | 新值 | 搜索 pattern |
|------|------|------|-------------|
| 中间件数量 | 19 | 29 | `grep -r "19.*middleware\|middleware.*19" _digest/` |
| Sandbox 实现数 | 3 | 5 | `grep -r "3.*sandbox\|three.*sandbox\|三种\|3 种" _digest/` |
| Gateway Router 数 | 16 | ~20 | `grep -r "16.*router\|16 个" _digest/` |
| Config 段数 | 26 | ~35 | `grep -r "26.*section\|26 个" _digest/` |
| ThreadState 字段数 | ~7 | ~11 | 更新 `concepts/lead-agent/` |
| Skill 加载方式 | 1（全量） | 2（legacy + deferred） | 更新 `concepts/skills-tools/` |

**执行方式**：写完所有 P0/P1 更新后，跑一次全量 grep 审计，修复不一致。

## E. 开发者旅程连贯性

更新完后，模拟一次新开发者的阅读路径，确认信息流不中断：

```
overview/01-system-overview.md    → 数字正确？
overview/03-logical-architecture.md → SVG 中间件链正确？
getting-started/01-quick-start.md  → TUI 入口已提及？
concepts/lead-agent/               → ThreadState 字段完整？
concepts/sandbox/                  → 5 种实现都已列出？
concepts/subagent/                 → MAX_TURNS_REACHED 已说明？
concepts/memory/                   → staleness + token counting 已说明？
concepts/skills-tools/             → deferred discovery + secrets 已说明？
internals/middleware/03-catalog.md → 29 个完整目录
internals/agent-loop/03-code-trace.md → middleware 名称匹配
operations/security/               → InputSanitization + env scrubbing
testing/                           → record/replay 已添加
```

---

## 修正后的执行顺序

1. 🔴 重写 `internals/middleware/` + `concepts/skills-tools/`
2. 🟡 更新核心概念文件（agent, sandbox, subagent, memory）
3. 🟡 更新内部机制文件（agent-loop, configuration）
4. 🟡 更新运维层文件（security, app-layer）
5. 🟢 验证 + 数字审计（grep 全量搜索不一致数字）
6. 🟢 交叉引用检查（确保所有链接可达、名称匹配）
7. ⚪ 新增子系统文件（TUI, goal, record/replay, deferred, secrets, connections）
8. 🔵 开发者旅程连贯性走查

