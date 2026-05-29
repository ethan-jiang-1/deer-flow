# DeerFlow 架构分析

> 内部设计、数据流、核心抽象。

**回答的核心问题**：整体分层结构（同心圆模型）、进程拓扑、各模块职责边界、请求如何在各层之间流转。

> **约束：不修改项目源代码。** 本 `_digest/` 下所有内容仅作研究记录。详见 [根 README](../README.md)。

---

## 阅读顺序

### 第一步：全局认知

[01-system-overview.md](01-system-overview.md) — 同心圆分层架构（Agent Loop → Services → Harness → Gateway → Access）、进程拓扑、目录映射。

[02-harness-app-boundary.md](02-harness-app-boundary.md) — Harness/App 两层分层、CI 强制隔离。图：[harness-app-boundary.svg](figures/harness-app-boundary.svg)

### 第二步：核心链路

[03-request-flow.md](03-request-flow.md) — 一次请求 14 步完整生命周期。图：[request-flow.svg](figures/request-flow.svg)

[04-middleware-chain.md](04-middleware-chain.md) — ⛔ 已废弃，请用 [middleware/ section](../middleware/README.md) 代替

### 第三步：各模块

| # | 文件 | 图 |
|---|------|----|
| 5 | [05-lead-agent.md](05-lead-agent.md) — Agent 工厂、ThreadState | — |
| 6 | [06-sandbox.md](06-sandbox.md) — Sandbox ABC + 3 种实现 | [SVG](figures/sandbox-architecture.svg) |
| 7 | [07-subagent.md](07-subagent.md) — 双线程池、生命周期 | — |
| 8 | [08-memory.md](08-memory.md) — 提取→队列→持久化 | — |
| 9 | [09-skills-tools.md](09-skills-tools.md) — Skills + Tools + MCP | — |
| 10 | [10-persistence.md](10-persistence.md) — DB/Checkpointer/SSE | — |
| 11 | [11-frontend.md](11-frontend.md) — Next.js 层、流式渲染 | — |

---

## 图一览

| 图 | 内容 |
|---|------|
| [agent-runtime-overview.svg](figures/agent-runtime-overview.svg) | 同心圆分层：Agent Loop → Services → Harness → Gateway → Access |
| [harness-app-boundary.svg](figures/harness-app-boundary.svg) | Harness/App 两层边界 + CI 导入规则 |
| [request-flow.svg](figures/request-flow.svg) | 请求数据流：14 步从 HTTP → SSE |
| [middleware-chain.svg](figures/middleware-chain.svg) | 19 Middlewares：6 种 hook 点 · 触发点 · 职责 |
| [sandbox-architecture.svg](figures/sandbox-architecture.svg) | Sandbox：ABC + 3 实现 + 虚拟路径 |
