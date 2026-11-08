---
title: "persistence"
description: "数据库 / Checkpointer / Store 三后端的选型、迁移、ORM 契约，以及 checkpoint 的存储表示（full/delta）与 delta 历史缓存。"
type: index
---

# persistence

数据库、LangGraph checkpointer、LangGraph Store 三条持久化线的内部契约。

| 文件 | 内容 |
|------|------|
| **db-checkpointer-store-backends.md** | 三后端（memory/sqlite/postgres）选型与迁移、ORM 22 张表、Repository 模式、Alembic 迁移链（含 0025 修复型迁移）、Hybrid bootstrap、Postgres schema 与 Store 工厂 |
| **checkpoint-dual-mode-and-history-cache.md** | `database.checkpoint_channel_mode` 的 full/delta 双模式：进程冻结、元数据标记、fail-closed 门、`CheckpointStateAccessor`、delta 历史缓存（`CachedHistorySaver` + memory/redis 后端） |

→ Back to [parent README](../README.md)
