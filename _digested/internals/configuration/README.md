---
title: "配置与扩展系统"
description: "DeerFlow 暴露了哪些挂载点？两套配置文件（config.yaml + extensions_config.json）的结构、热加载边界、动态模块加载与上下文压缩。"
type: index
topics: [configuration, yaml-config, extensions-json, hot-reload]
---

# 配置与扩展系统

> **定位**：回答「DeerFlow 暴露了哪些挂载点、怎么把自定义 tool/model/sandbox 挂上去、改哪个字段要重启」；给要改部署配置或接自定义组件的读者。
> **边界**：热重载的检测/传播机制在 [../harness-hooks/](../harness-hooks/README.md) 展开；MCP 与 skills 的运行时消费方在 [../mcp/](../mcp/README.md)；模型路由细节在 [../model-layer/](../model-layer/README.md)。

## 阅读路径

1. **先看**：[01-config-yaml.md](01-config-yaml.md) — `AppConfig` 与 8 步加载流水线。
2. **再看**：[02-extensions-json.md](02-extensions-json.md) — MCP server 与 skills 状态。
3. **深入**：[04-config-reference.md](04-config-reference.md) — 每个 section 的字段级手册。

## 本篇目

| 文件 | 主题 | 深度 |
|---|---|---|
| [01-config-yaml.md](01-config-yaml.md) | AppConfig 深挖、`_from_yaml_text()` 流水线、新增 section 速查、8 项 feature gating | 概览 |
| [02-extensions-json.md](02-extensions-json.md) | MCP server 配置、OAuth token、自动 revalidation、工具双层缓存、skills 状态 | 概览 |
| [03-dynamic-loading.md](03-dynamic-loading.md) | `resolve_variable` 原理、tool 装配四道过滤、model factory meta field、reasoning 契约 | 深入 |
| [04-config-reference.md](04-config-reference.md) | 全字段配置手册：YAML schema、默认值、`reload_boundary`、`memory.backend_config` | 深入 |
| [05-summarization-deep-dive.md](05-summarization-deep-dive.md) | 上下文压缩：触发条件、保留策略、DurableContext、手动 compaction | 深入 |

## 宪章与约定

- 本目录无独立宪章；写作纪律沿用 [根 README](../README.md)。

## 相关目录

- [internals 父级](../README.md) — 13 个内部机制子目录的总入口。
- [harness-hooks](../harness-hooks/README.md) — 热重载与单例传播的机制视角。
- [mcp](../mcp/README.md) — `extensions_config.json` 的缓存、OAuth 与配置写回。
- [model-layer](../model-layer/README.md) — `model.use` class path 的另一端。
- [getting-started/02-configuration.md](../../getting-started/02-configuration.md) — 面向使用者的生效规则表。

## 速览

- **两套文件**：`config.yaml`（AppConfig，56 字段 / example 43 个启用键，`config_version` 63）+ `extensions_config.json`（可选，缺失即空配置）。
- **加载 8 步**：读 YAML → 版本检查 → `resolve_env_variables` → 构造 → `_apply_singleton_configs()` 等；未知 key 因 `extra="allow"` 保留而不报错。
- **热/冷边界**：`reload_boundary` 表列出必须重启的 `database.*` / `checkpointer.*` / `sandbox.use` / `log_level` / `channels.*`；其余在下一条消息生效。
- **v2.2.0 新 section**：`blob_storage` / `knowledge_base` / `typesafe` / `deployment`；速查在 01，字段细节在 04。
