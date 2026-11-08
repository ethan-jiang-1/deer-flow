---
title: "storage — 内容寻址 blob 存储（v2.2.0）"
description: "v2.2.0 新增的内容寻址 blob 存储（#4189 item 2）：sha256 做地址、写入幂等、去重免费、读时校验；默认 blob_storage.enabled: false，关闭时没有任何 producer 写入。"
type: index
topics: [storage, blob-store, content-addressed, multi-instance]
---

# storage — 内容寻址 blob 存储

> **定位**：把「文件在哪台机器的哪个路径」换成「这份字节的 sha256 是什么」；回答「多 Gateway 部署下 blob 怎么跨实例解析、后端怎么插、哪些 producer 已经迁移」。
> **边界**：本目录只讲 blob 存储契约、`local_fs` 后端与 producer；`blob_storage` 配置字段在 [../configuration/04-config-reference.md](../configuration/04-config-reference.md)；checkpoint 自己的 `checkpoint_blobs` 是另一套（去 [../persistence/](../persistence/README.md)）；`ToolOutputBudgetMiddleware` 的完整条目在 [../middleware/03-catalog.md](../middleware/03-catalog.md)。

## 阅读路径

1. **先看**：[01-contract-and-factory.md](01-contract-and-factory.md) — `BlobRef` / `BlobStore` 契约与进程单例工厂。
2. **再看**：[02-local-fs.md](02-local-fs.md) — 分片布局、原子发布与 sidecar 规则。
3. **深入**：[03-producers.md](03-producers.md) — 两个写入点、三条读路径与失败策略总表。

## 本篇目

| 文件 | 主题 | 深度 |
|---|---|---|
| [01-contract-and-factory.md](01-contract-and-factory.md) | `BlobRef` 四元组、`kind` 语法、6 条契约级失败策略、后端解析与热重载单例、新后端检查单 | 概览 |
| [02-local-fs.md](02-local-fs.md) | `<root>/<kind>/<sha[:2]>/<sha>` 布局、临时文件 + `os.replace`、并发写者、sidecar 三条「不是」、64 MiB 上限 | 深入 |
| [03-producers.md](03-producers.md) | `viewed-image` / `tool-output` 两个写入点、中间件注入 / artifact GET / tool-output 还原三个消费点、失败策略表 | 深入 |

## 宪章与约定

- 包内有独立宪章：[backend/packages/harness/deerflow/storage/AGENTS.md](../../../backend/packages/harness/deerflow/storage/AGENTS.md)（109 行，新后端/新 producer 的硬要求）；写作纪律沿用 [根 README](../README.md)。运维面见上游 [backend/docs/blob-storage.md](../../../backend/docs/blob-storage.md)（138 行，producer 白名单与 GC 规则）。

## 相关目录

- [internals 父级](../README.md) — 13 个内部机制子目录的总入口。
- [configuration](../configuration/README.md) — `blob_storage.enabled / backend / backend_config` 与热加载。
- [middleware](../middleware/README.md) — `ToolOutputBudgetMiddleware` 的中间件条目。
- [persistence](../persistence/README.md) — checkpoint channel blob（与本目录的 `BlobRef` 无关）。
- [安全 / 信任边界](../../enterprise-operations/security/04-trust-boundary.md) — artifact GET 的权限与日志规则。

## 速览

- **默认关闭是设计**：`enabled: false` 时 `get_blob_store_if_enabled()` 返回 `None`，**没有任何 producer 写入**；这是「先落契约、再逐个 producer 迁移」的白名单式落地。
- **规模 851 行 / 7 个文件**：`local_fs_store.py` 260、`manager.py` 224、`contract.py` 198、`AGENTS.md` 109、`__init__.py` 34，其余两个目录 `__init__` 各 13。
- **唯一后端** `LocalFsBlobStore`：内容 `fsync` 但目录项没有；sidecar **不是读依赖、不是引用计数、失败不毁 put**（内容寻址会把相同字节塌缩，sidecar 只能记录先到的写者）。
- **失败方向不对称**：写 `view_image` 失败 = fail-loud（工具调用失败），其余写入与所有读取 fail-soft；checkpoint 里只有引用，字节不过界。
- **`get_blob_store()` 目前没有生产调用方**：producer 一律走 `get_blob_store_if_enabled()`（全仓 grep 只有测试用前者）。
- **测试**：`backend/tests/test_blob_store.py`（485 行，契约 + local_fs + 工厂）；producer 侧见 `test_view_image_tool.py`、`test_view_image_middleware.py`、`test_tool_output_budget_middleware.py`、`test_artifacts_router.py`；热加载端到端在 `test_app_config_reload.py:879`。
