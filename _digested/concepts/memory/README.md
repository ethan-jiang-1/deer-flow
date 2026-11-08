---
title: "Memory — 可插拔记忆后端"
description: "可插拔 Memory 后端：提取/队列/持久化管线、认知风格与相关性排序，以及 Manager 契约与各后端客户端。"
type: index
topics: [memory, persistence, pluggable-backend]
---

# Memory — 可插拔记忆后端

> **定位**：Agent 的长期记忆怎么提取、排队、落盘、召回，以及怎么换后端。给配置 memory 的人、写自定义 backend 的人、排查「记忆没生效 / 召回不相关」的人。
> **边界**：不覆盖 checkpointer / Store 的持久化后端（见 [internals/persistence](../../internals/persistence/README.md)），不覆盖上下文压缩与 summarization 中间件本身（见 [internals/middleware](../../internals/middleware/README.md)），子 agent 的记忆继承见 [subagent](../subagent/README.md)。

## 阅读路径

1. **先看**：[extract-queue-persist-pipeline.md](extract-queue-persist-pipeline.md) — 管线主体：后端架构、DeerMem storage v2、提取、staleness review、consolidation 与检索配置。
2. **深入**：[manager-contract-and-backend-clients.md](manager-contract-and-backend-clients.md) — `MemoryManager` 契约、5 个 JSON 工具、`summarization_hook`，以及五个后端的初始化与失败模式。

## 本篇目

| 文件 | 主题 | 深度 |
|---|---|---|
| [extract-queue-persist-pipeline.md](extract-queue-persist-pipeline.md) | 提取/队列/持久化管线、storage v2、staleness review、consolidation、hybrid-v1 驱逐 | 深入 |
| [manager-contract-and-backend-clients.md](manager-contract-and-backend-clients.md) | Manager 契约面、工具面、summarization 挂钩、各后端 client 初始化与失败模式 | 深入 |

## 速览

- **双模式**：middleware 把记忆注入上下文；tool 模式经 `get_memory_tools` 暴露 5 个 JSON 工具（含 `memory_get`）。
- **五后端**：deermem / mem0 / noop / openviking / honcho，config 校验与 client 初始化/失败模式各不相同（详见 manager 篇）。
- **2.2.0 增量**：`cognitiveStyle` 摘要段与 10 个 fact 类别、确定性词法相关性排序（IDF + greedy-MMR）、`prescreen/` + `signals/` 两级判定门。
- **隔离**：默认 per-user 隔离；`supports_agent_scoped_management` / `refresh_judge` 是 2.2.0 新增的 host hook。

## 宪章与约定

- 本目录无独立宪章；研究纪律沿用 [根 README](../../README.md)（不修改源码、`main` 只镜像上游、笔记只落在 `ethan`）。
- 记忆与会话恢复是两条独立存储：本目录只讲 memory 后端、提取与召回，checkpoint 与 Store 看 [internals/persistence](../../internals/persistence/README.md)。

## 相关目录

- [concepts/](../README.md) — 概念总览与其它核心抽象。
- [internals/persistence/](../../internals/persistence/README.md) — DB / Checkpointer / Store 三后端，与 Memory 的边界。
- [internals/middleware/](../../internals/middleware/README.md) — 记忆注入在 middleware 链中的位置。
- [observability/](../../observability/README.md) — 记忆提取失败与队列积压怎么观察。
