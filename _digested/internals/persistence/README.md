---
title: "persistence — 持久化内部契约"
description: "数据库 / LangGraph Checkpointer / LangGraph Store 三条持久化线的选型、迁移与 ORM 契约，以及 checkpoint 的 full/delta 存储表示与 delta 历史缓存。"
type: index
topics: [persistence, checkpointer, database, delta-channel]
---

# persistence — 持久化内部契约

> **定位**：回答「三种后端怎么选、checkpoint 在库里长什么样、delta 模式为什么需要历史缓存、迁移链怎么走」；给要改持久化层或排查恢复问题的开发者。
> **边界**：checkpoint 的**运行期**读写（`checkpoint_mode` / `checkpoint_state` / `cached_saver` 的调用方）在 [../runtime/](../runtime/README.md)；内容寻址 blob 存储是另一套东西，见 [../storage/](../storage/README.md)（`checkpoint_blobs` 表与本目录也不是一回事）；`database.*` 配置字段见 [../configuration/04-config-reference.md](../configuration/04-config-reference.md)。

## 阅读路径

1. **先看**：[db-checkpointer-store-backends.md](db-checkpointer-store-backends.md) — 三后端、ORM、迁移与 Store 工厂。
2. **再看**：[checkpoint-dual-mode-and-history-cache.md](checkpoint-dual-mode-and-history-cache.md) — full/delta 双模式与 delta 历史缓存。

## 本篇目

| 文件 | 主题 | 深度 |
|---|---|---|
| [db-checkpointer-store-backends.md](db-checkpointer-store-backends.md) | memory/sqlite/postgres 选型、22 张 ORM 表、Repository、Alembic 链（含 0025 修复型迁移）、Hybrid bootstrap、Postgres schema 与 Store 工厂 | 深入 |
| [checkpoint-dual-mode-and-history-cache.md](checkpoint-dual-mode-and-history-cache.md) | `checkpoint_channel_mode` 双模式、进程冻结、元数据标记、fail-closed 门、`CheckpointStateAccessor`、memory/redis 缓存后端 | 深入 |

## 宪章与约定

- 包内有独立宪章：[backend/packages/harness/deerflow/persistence/AGENTS.md](../../../backend/packages/harness/deerflow/persistence/AGENTS.md)（98 行）；写作纪律沿用 [根 README](../README.md)。checkpoint 保留策略另有上游 draft：[backend/docs/checkpoint-retention-contract.md](../../../backend/docs/checkpoint-retention-contract.md)。

## 相关目录

- [internals 父级](../README.md) — 13 个内部机制子目录的总入口。
- [runtime](../runtime/README.md) — checkpointer 的运行期消费方与 run 生命周期。
- [storage](../storage/README.md) — 内容寻址 blob 存储（与 checkpoint blob 无关）。
- [configuration](../configuration/README.md) — `database.*` 字段与热加载边界。

## 速览

- **三后端同一契约**：`memory` / `sqlite` / `postgres`，由工厂按 `database.backend` 选择；ORM 共 38 张表，Repository 模式隔离 SQL。
- **迁移链**：Alembic 按 `down_revision` 排序而非数字前缀；当前 50 个 revision，head 是 `0048_extension_execution_leases`。0025 是 v2.1.0 的修复型迁移（幂等重放被插队的 `0023_run_change_seq`，并把 `RunChangeClockRow` / `UserPreferenceRow` 补进 ORM 注册表），不是当前 head。
- **两种 checkpoint 表示**：full（整快照 `channel_values`）与 delta（哨兵 blob + 每步 writes）；模式编译进图，运行中不可改，full → delta 单向。
- **delta 的 fail-closed 门**：元数据标记 `deerflow_checkpoint_channel_mode`，不匹配抛 `CheckpointModeMismatchError`；缓存只读、线程级 purge，memory 后端锁外 deepcopy。
