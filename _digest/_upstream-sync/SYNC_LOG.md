---
title: "同步日志"
description: "每次同步的记录：时间、锚点变化、变更摘要、影响的 digest 更新。"
type: index
---

# 同步日志

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
