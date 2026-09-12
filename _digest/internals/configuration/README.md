---
title: "配置与扩展系统"
description: "DeerFlow 暴露了哪些挂载点？怎么把自定义的东西挂上去？"
type: index
---

# 配置与扩展系统

DeerFlow 暴露了哪些挂载点？怎么把自定义的东西挂上去？

**回答的核心问题**：两套配置文件（config.yaml + extensions_config.json）的结构、热加载机制、动态模块加载（resolve_variable）、怎么用 class path 挂自定义 tool/model。

> **约束：不修改项目源代码。** 本 `_digest/` 下所有内容仅作研究记录。详见 [根 README](../README.md)。

## 阅读顺序

| 文件 | 内容 |
|------|------|
| **01-config-yaml.md** | AppConfig 深挖：36 section、from_file() 8 步流水线、config_version 升级、🆕 memory 重构、feature gating |
| **02-extensions-json.md** | MCP + Skills 配置：MCP server config、OAuth token、MCP tools 缓存、skills 状态 |
| **03-dynamic-loading.md** | resolve_variable 原理：动态 import + type check、model factory、extra="allow" 透传、thinking 跨 provider |
| **04-config-reference.md** | 完整字段级配置手册：每个 section 的 YAML schema、默认值、🆕 memory.backend_config、authz |
| **05-summarization-deep-dive.md** | 上下文压缩完整机制：触发条件、保留策略、与 DurableContext 协作、🆕 手动 compaction |

## 关键问题

- 修改 config.yaml 后哪些字段实时生效，哪些必须重启？→ `01-config-yaml.md` 热加载分流表
- config.yaml 和 extensions_config.json 的关系？→ `02-extensions-json.md`
- AppConfig 是怎么从 YAML 变成运行时对象的？→ `01-config-yaml.md` 8 步流水线
- MCP server 的 tool 是怎么注入到 Agent Loop 的？→ `02-extensions-json.md` MCP 缓存
- 怎么做到 `config.yaml` 里写个 class path 就能加载自定义 tool/model？→ `03-dynamic-loading.md`
- 🆕 Memory 怎么从平铺配置变成可插拔后端？→ `01-config-yaml.md` + `04-config-reference.md`
- 🆕 手动触发上下文压缩怎么工作？→ `05-summarization-deep-dive.md`
