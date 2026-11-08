---
title: "授权模型"
description: "认证回答「你是谁」，授权回答「你能做什么」——agent 替用户执行时，这条链尤其要看清。"
type: index
topics: [governance]
---

# 授权模型

认证回答「你是谁」，授权回答「你能做什么」——agent 替用户执行时，这条链尤其要看清。

DeerFlow 的授权分两层：宿主层的 RBAC（11 个 resource:action）和 agent 层的tool 级门（Guardrail）。两者互不替代，评审时要分开看。

> **约束：不修改项目源代码。** 本 `_digested/` 下所有内容仅作研究记录。详见 [根 README](../../README.md)。

## 本篇目

| 文件 | 主题 | 内容 |
|------|------|------|
| [01-guardrail-layer.md](01-guardrail-layer.md) | **工具级授权：Guardrail 层** | Tool 级授权、可插拔 provider、2.2 三个内置门 |
| [02-bounded-autonomy.md](02-bounded-autonomy.md) | **Bounded Autonomy** | 自动/人工边界在哪里 |
| [03-configurability.md](03-configurability.md) | **策略可配置性总览** | 哪些可配、哪些硬编码，以及为什么 |

## 规划中

| 文件 | 主题 | 内容 |
|------|------|------|
| 04-rbac-permissions.md | RBAC 权限全表 | 11 个 resource:action 权限与装饰器 |
| 05-mcp-scope.md | MCP 作用域 | v2: 作用域键、thread incarnation、personal MCP 归属 |

---

← 返回 [企业 IT 治理总览](../README.md) · 机制细节见 [enterprise-operations/](../../enterprise-operations/README.md)
