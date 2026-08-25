---
title: "同步日志"
description: "每次同步的记录：时间、锚点变化、变更摘要、影响的 digest 更新。"
type: index
---

# 同步日志

---

## #3 — 2026-07-20（同步）

| 项目 | 值 |
|------|-----|
| **操作** | 同步 |
| **旧锚点** | `4915b5e` |
| **新锚点** | `cd34a1a5` |
| **上游新增 commits** | 200 |
| **harness 变更** | ~450 files, +4,464 / -1,641 lines（memory 重构最大） |
| **前端变更** | 88 files, +6,235 / -1,098 lines |
| **config.example.yaml** | +282 / -61 lines |
| **主要变更领域** | **memory**（pluggable backends + DeerMem 重构 + consolidation + staleness review + tool mode + template externalization，Breaking Changes）、**security**（4 CVE + 全链路 HTML 转义 + prompt injection 中性化 + SkillScan exfil 检测 + security_fail_closed + MindIE breakout 防护）、**middleware**（+5 新：TokenBudget, DelegationLedger, DurableContext, MCPRouting, ToolOutputSynopsis）、**skills**（SkillScan Phase 1 + review quality gate + per-user isolation）、**subagents**（delegation ledger + total cap + step persistence）、**sandbox**（E2B + BoxLite 正式加入 + warm pool）、**auth/authz**（OIDC/SSO + AuthorizationProvider protocol + principal context）、**frontend**（voice dictation + branching + citation panel + composer polish + slash chips）、**Monocle**（agent observability + trace-based tests）、**MCP**（routing hints + auto-promote + per-server timeout）、**Helm chart**（first-class K8s）、**community tools**（GroundRoute, Crawl4AI, Browserless, Brave image_search） |
| **影响的 digest** | concepts/memory、operations/security、internals/middleware、concepts/skills-tools、concepts/subagent、concepts/sandbox、operations/security/01-auth、internals/configuration、internals/mcp、operations/app-layer、frontend/、operations/deployment、operations/tracing、concepts/community-tools、overview/ |
| **备注** | 200 commits 指向 2.1.0 里程碑。Memory 系统是从单体到可插拔架构的 breaking change（storage_path 语义变更、config 结构重构、API 返回结构变更）。安全从 guardrail 拦截升级为全链路 defense-in-depth。更新计划见 UPDATE_PLAN_3.md。 |

---

## #4 — 2026-08-08（同步）

| 项目 | 值 |
|------|-----|
| **操作** | 同步 |
| **旧锚点** | `cd34a1a5` |
| **新锚点** | `e5c62cab` |
| **上游新增 commits** | 234 |
| **变更规模** | 931 files, +141,080 / -9,322 lines |
| **时间跨度** | 2026-07-20 → 2026-08-07 |
| **提交构成** | 142 fix / 46 feat / 11 build / 6 perf / 4 test / 3 docs |
| **主要变更领域** | **sandbox**（E2B/AIO provider 大改 + orphan reconciliation + 新 **Tenki** provider）、**memory**（新 **OpenViking** backend + storage.py 重构 + markdown 存储）、**channels**（新 **Buzz** 频道 + Nostr + **Lark CLI/broker** 集成）、**runtime**（worker 重构 + multi-worker run ownership + rollback）、**authz**（pluggable authorization 落地，新 `authz/` 子包 + RFC）、**persistence**（storage rewrite 计划）、**community**（新 **browser_automation** 工具）、**workspace_changes**（全新子系统）、**frontend**（257 files 大改） |
| **影响的 digest** | concepts/sandbox、concepts/memory、concepts/community-tools、operations/channels、operations/integration、internals/runtime、operations/security/01-auth、internals/configuration、concepts/skills-tools、concepts/builtin-tools、frontend/、operations/deployment、getting-started/06-tui、operations/security/03-guardrail、concepts/subagent |
| **备注** | 以修复为主（142 fix），无 #3 那样的 breaking 重构，但新增 **6 个全新子系统**：Buzz 频道、Lark CLI、OpenViking memory backend、Tenki sandbox、Browser Automation、Workspace Changes。E2B/AIO sandbox 的代码量最大（+4000+ 行）。更新计划见 UPDATE_PLAN_4.md。 |

---

## #5 — 2026-08-25（同步）

| 项目 | 值 |
|------|-----|
| **操作** | 同步 |
| **旧锚点** | `e5c62cab` |
| **新锚点** | `431892e1` |
| **上游新增 commits** | 108 |
| **变更规模** | 601 files, +66,827 / -4,637 lines |
| **时间跨度** | 2026-08-08 → 2026-08-25 |
| **提交构成** | 22 feat / 65 fix / 1 perf / 9 docs / 4 build / 3 test |
| **config** | config_version 33 → **36**（config.example.yaml +244/-33，extensions_config.example.json +25） |
| **主要变更领域** | **subagents**（unified capacity + durable batch execution + managed subagents + delegation scopes + isolated date-only context）、**MCP**（durable task 完整落地：task_tool_caller + tasks/driver+ordinary+runtime + persistence/migrations 0011-0013 + gateway router + 通知/chat UI + per-user credential injection + interceptors + OpenViking tools）、**sandbox**（新 **OpenSandbox** provider，第 7 实现 + sandbox:execute 授权落地）、**memory**（新 **Honcho** 后端，第 5 个 + hybrid fact eviction）、**extensions**（packaged 管理：CLI + gateway contribution points + extension-api 5 个新模块 + 参考示例包）、**tool receipts**（确定性模型可见收据 ledger，RFC #4651 layer 1，middleware 35→36）、**threads**（branched conversations）、**knowledge**（新 **RAGFlow** 只读检索）、**MiniMax Code**（原生 ACP agent）、**scheduler**（recursion_limit 可配置 + busy 入队 + 多实例恢复）、**frontend**（68 files：分支会话树 + subagent batches + background tasks） |
| **影响的 digest** | concepts/subagent、internals/mcp、concepts/sandbox、operations/security、concepts/memory、concepts/community-tools、internals/middleware、internals/harness-hooks、operations/app-layer、internals/runtime、internals/configuration、getting-started、operations/channels、operations/scheduler、concepts/builtin-tools、frontend |
| **备注** | 无 breaking 重构，以 fix 为主（65 fix）+ 六个方向能力落地。最大新增：MCP durable task 子系统、subagent batch 子系统、extensions packaged 管理、OpenSandbox、Honcho、RAGFlow。更新计划见 UPDATE_PLAN_5.md。 |

---

## #2 — 2026-07-07（同步）

| 项目 | 值 |
|------|-----|
| **操作** | 同步 |
| **旧锚点** | `162fb214` |
| **新锚点** | `4915b5e` |
| **上游新增 commits** | 323 |
| **harness 变更** | 222 files, +26,161 / -2,126 lines |
| **前端变更** | 308 files, +30,943 / -2,219 lines |
| **config.example.yaml** | +734 / -51 lines |
| **主要变更领域** | middleware（5→29 个，加了 24 个新中间件）、skills（deferred discovery、request-scoped secrets、slash activation）、sandbox（BoxLite、E2B、warm pool）、subagents（turn-budget cap、step capture、checkpointer isolation）、TUI（全新 `deerflow` 终端）、Gateway（console、trace correlation、Redis stream bridge、Alembic migrations）、memory（staleness review、token counting）、channels（GitHub webhook、user-owned connections）、testing（record/replay e2e） |
| **影响的 digest** | concepts/lead-agent、concepts/sandbox、concepts/subagent、concepts/memory、concepts/skills-tools、internals/middleware、internals/agent-loop、internals/model-layer、internals/harness-hooks、internals/configuration、internals/runtime、testing/、operations/security、operations/app-layer、operations/channels、frontend/ |
| **备注** | 这是 323 个 commit 的大版本跳跃（从 2.0-m1 → 2.1-dev）。中间件链从 19 增长到 29 个，需要全面重写相关 digest。TUI 和 deferred skill discovery 是全新子系统。 |

---

## #1 — 2026-07-06（初始锚定）

| 项目 | 值 |
|------|-----|
| **操作** | 初始锚定——记录 digest 内容对应的上游版本 |
| **锚点 commit** | `162fb214` |
| **commit 内容** | `fix(mcp): skip session pooling for HTTP/SSE transports (#3203)` |
| **上游当时 HEAD** | `fd41fdb`（已领先） |
| **落后上游** | [compare/162fb214...main](https://github.com/bytedance/deer-flow/compare/162fb214...main) |
| **digest 更新** | 无（首次锚定，digest 内容基于此版本） |

---

## 模板（下次同步时复制填写）

```
## #N — YYYY-MM-DD

| 项目 | 值 |
|------|-----|
| **操作** | 同步 |
| **旧锚点** | <OLD_COMMIT> |
| **新锚点** | <NEW_COMMIT> |
| **上游新增 commits** | N |
| **变更文件** | <git diff --stat 摘要> |
| **影响的 digest** | <哪些目录被更新> |
| **备注** | |
```
