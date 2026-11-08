---
title: "Lead Agent 系统"
description: "make_lead_agent 工厂、ThreadState、SOUL.md 编写与 LangGraph node/state 设计。"
type: index
topics: [agent, factory, threadstate, langgraph]
---

# Lead Agent 系统

> **定位**：DeerFlow 的核心对象。回答「Lead Agent 是怎么被造出来的、状态里装什么、行为怎么定义、图怎么设计」——给要改 agent 装配或写自定义 agent 的人。
> **边界**：不覆盖 middleware 链的逐项组装与顺序（见 [internals/middleware](../../internals/middleware/README.md)），不覆盖 subagent 的执行与报告契约（见 [subagent](../subagent/README.md)），工具清单与加载条件见 [builtin-tools](../builtin-tools/README.md)。

## 阅读路径

1. **先看**：[factory-and-threadstate.md](factory-and-threadstate.md) — `make_lead_agent` 工厂、ThreadState schema 与 7 步装配。
2. **再看**：[02-soul-md-guide.md](02-soul-md-guide.md) — 给自定义 Agent 写 SOUL.md：模板、示例与常见错误。
3. **深入**：[03-graph-nodes-and-state-design.md](03-graph-nodes-and-state-design.md) — 两个固定 node、middleware 即 node、state 扩展与 `jump_to`。

## 本篇目

| 文件 | 主题 | 深度 |
|---|---|---|
| [factory-and-threadstate.md](factory-and-threadstate.md) | 工厂函数、ThreadState schema、7 步装配 | 深入 |
| [02-soul-md-guide.md](02-soul-md-guide.md) | SOUL.md 编写：模板、最佳实践、示例、常见错误 | 概览 |
| [03-graph-nodes-and-state-design.md](03-graph-nodes-and-state-design.md) | LangGraph Node/State 设计：固定 node、state 扩展、sub-agent 独立图 | 深入 |

## 速览

- **三篇分工**：工厂篇回答「怎么装」，SOUL 篇回答「行为怎么定义」，Node/State 篇回答「图怎么设计」。
- **ThreadState 是契约面**：工具的第一个参数 `runtime: Runtime` 就注入 thread state / sandbox 引用；扩展 state 要同时对照工厂篇与 Node/State 篇。

## 宪章与约定

- 本目录无独立宪章；研究纪律沿用 [根 README](../../README.md)（不修改源码、`main` 只镜像上游、笔记只落在 `ethan`）。
- 装配序列与源码行号随上游同步发生位移，引用以各篇开头标注的基线为准；对不上时按 [_upstream-sync/SYNC.md](../../_upstream-sync/SYNC.md) 复核。

## 相关目录

- [concepts/](../README.md) — 回到概念总览：Sandbox / Memory / Skills 与 Agent 的关系。
- [internals/agent-loop/](../../internals/agent-loop/README.md) — Agent Loop 的三层嵌套与扩展点。
- [internals/middleware/](../../internals/middleware/README.md) — 中间件即 node：hook 点与链组装。
- [subagent/](../subagent/README.md) — 子 Agent 的发现、执行与验收。
