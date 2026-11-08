---
title: "授权模型"
description: "认证回答「你是谁」，授权回答「你能做什么」——agent 替用户执行时，这条链尤其要看清。"
type: index
topics: [governance, authorization, rbac, guardrail]
---

# 授权模型

> **定位**：本域拆开 DeerFlow 的两层授权——宿主层 RBAC（13 个 `resource:action`）与 agent 层 tool 级门（Guardrail），回答「怎么限制 agent 只能调某些 tool」「名单门不够用怎么办」。给权限模型设计与工具接入评审者看。
> **边界**：认证与账号生命周期见 [identity/](../identity/README.md)；授权通过之后命令怎么被限制在沙箱里见 [execution/](../execution/README.md)。两层互不替代，评审时要分开看。

## 阅读路径

1. **先看**：[03-configurability.md](03-configurability.md) — 策略全景：哪些可配、哪些硬编码、以及为什么。
2. **再看**：[04-rbac-permissions.md](04-rbac-permissions.md) — 13 个 `resource:action` 全表、默认关闭的开关、条件下权限。
3. **深入**：[01-guardrail-layer.md](01-guardrail-layer.md) — tool 级授权、可插拔 provider 与 v2.2 的三个内置门。

## 本篇目

| 文件 | 主题 | 深度 |
|---|---|---|
| [01-guardrail-layer.md](01-guardrail-layer.md) | 工具级授权：Guardrail 层与三个内置风险门 | 深入 |
| [02-bounded-autonomy.md](02-bounded-autonomy.md) | Bounded Autonomy：自动/人工边界在哪里 | 概览 |
| [03-configurability.md](03-configurability.md) | 策略可配置性总览 | 概览 |
| [04-rbac-permissions.md](04-rbac-permissions.md) | RBAC 权限全表：13 个 `resource:action` | 深入 |
| [05-mcp-scope.md](05-mcp-scope.md) | MCP 作用域：作用域键、thread incarnation、personal MCP 归属 | 深入 |

## 宪章与约定

- 本目录无独立宪章；父级卷宪章为 [../PLAN.md](../PLAN.md)，审计修复记录见 [../AUDIT-FIX-PLAN.md](../AUDIT-FIX-PLAN.md)。
- 写作纪律沿用 [根 README](../../README.md)：判断性段落附 `file:line`，基线 v2.2.0。
- 阅读约定：缺口按「无 / 有但不覆盖 / 部分闭合」三态标注，每处写明边界条件。

## 相关目录

- [企业 IT 治理总览](../README.md) — 八个治理面向与默认关闭项。
- [身份与接入](../identity/README.md) — 授权的前提：谁在操作。
- [执行边界](../execution/README.md) — 授权之后，操作怎么被执行。
- [Enterprise Operations](../../enterprise-operations/README.md) — 这些授权项在配置与运维侧的落点。
