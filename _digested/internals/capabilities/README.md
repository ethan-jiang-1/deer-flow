---
title: "Capabilities — 能力目录"
description: "v2.2.0 的声明式能力目录：一份经校验的 builtin.json（15 条）、把清单派发到既有集成服务的 adapter 注册表、稳定 installation identity，以及把 Agent 的 MCP 选择翻译成工具过滤；它不执行任何东西。"
type: index
topics: [capabilities, catalog, installation-identity, mcp]
---

# Capabilities — 能力目录

> **定位**：把「插件 / MCP server / Lark CLI / skill」从多套管理接口后面收成一份可发现、可校验、可展示、可被 Agent 稳定引用的目录；回答「能力有哪些、怎么装、装完怎么被 Agent 选中」。
> **边界**：**不执行**任何能力——执行归 owning runtime（MCP cache / Lark CLI / skills 存储）；不含会话池、OAuth 与缓存（去 [../mcp/](../mcp/README.md)）；选择不是授权，授权仍在宿主。

## 阅读路径

1. **先看**：[01-catalog-and-adapters.md](01-catalog-and-adapters.md) — 清单 schema、adapter 注册表与发现 API。
2. **再看**：[02-installation-identity-and-agent-selection.md](02-installation-identity-and-agent-selection.md) — 稳定安装身份与 `mcp_plugins` 三态选择。
3. **深入**：[03-bundled-business.md](03-bundled-business.md) — 三个自带 HTTP 客户端的内置 provider。

## 本篇目

| 文件 | 主题 | 深度 |
|---|---|---|
| [01-catalog-and-adapters.md](01-catalog-and-adapters.md) | `PluginManifest` 校验、`load_catalog()` 失败策略、4 个 adapter 的 list/install 分工、`/api/capabilities/*` 权限与失败隔离 | 概览 |
| [02-installation-identity-and-agent-selection.md](02-installation-identity-and-agent-selection.md) | `installation_id()` 两级身份、`ambiguous_installation_ids()` fail-closed、三处写入门、`filter_mcp_plugins()` 与 subagent 传播 | 深入 |
| [03-bundled-business.md](03-bundled-business.md) | dingtalk / wecom / hubspot 的固定 launcher 与凭据白名单、`is_bundled_connection()` 窄例外、HTTP 失败策略 | 深入 |

## 宪章与约定

- 本目录无独立宪章（`deerflow/capabilities/` 下无 `AGENTS.md`）；写作纪律沿用 [根 README](../README.md)。上游权威集成契约是 [docs/capability-center.md](../../../docs/capability-center.md)（257 行），三篇正文是它的源码级展开，冲突以源码为准。

## 相关目录

- [internals 父级](../README.md) — 13 个内部机制子目录的总入口。
- [mcp](../mcp/README.md) — 目录安装最终写进 `extensions_config.json` / 个人 `mcp.json`，由 MCP 缓存与 Session Pool 消费。
- [configuration](../configuration/README.md) — `capability` / `presentation` 是 `extra="allow"` 携带字段，不是 schema 字段。
- [builtin-tools](../../concepts/builtin-tools/README.md) — `filter_mcp_plugins()` 在工具装配处生效。
- [安全 / 信任边界](../../enterprise-operations/security/04-trust-boundary.md) — `is_bundled_connection()` 是 stdio 执行白名单里的唯一窄例外。

## 速览

- **规模与出处**：1000 行 = `builtin.json` 732 + `business.py` 178 + `catalog.py` 51 + `runtime.py` 38 + `__init__.py` 1；上游 commit `42334f26d`，2.1.0 中无对应物。
- **15 条清单的分布**：adapter `mcp` 6 / `guide` 5 / `business` 3 / `lark` 1；kind `mcp` 9 / `native` 5 / `cli` 1；category `office` 3 / `knowledge` 3 / `research` 4 / `business` 2 / `development` 3（无 `custom`）。
- **guide 的 5 条不可安装**：Gateway 侧没有注册对应 adapter，安装请求 422（`app/gateway/capabilities.py:227-231`）。
- **三条不变量**：目录是数据不是代码（`load_catalog()` 只 `json.loads` + pydantic）；目录条目不等于安装；选择不是授权（`runtime.py` docstring 原文）。
- **调用方 5 个文件**：`app/gateway/capabilities.py`、`routers/capabilities.py`、`routers/mcp.py`、`routers/personal_mcp.py`、`tools/tools.py`（含 3 处函数内延迟 import）；测试 3 个文件 + 1 个 blocking-io。

> 未核实：15 条清单的 `setup` 文案未逐条比对 provider 官方文档，只核对了结构化字段。
