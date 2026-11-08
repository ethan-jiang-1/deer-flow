---
title: "审计与追责"
description: "「某个时间段内 agent 被拒绝了哪些操作」——能不能不 grep 日志就答出来？"
type: index
topics: [governance, audit, observability, evidence]
---

# 审计与追责

> **定位**：事后能否还原——guardrail 决策、SandboxAudit、RunJournal 与 completed-run evidence 各自留下什么证据。给做审计取证、事故复盘与监管应答的人看。
> **边界**：日志与事件流的实现细节见 [enterprise-operations/tracing/](../../enterprise-operations/tracing/README.md)；哪些条款需要这些证据见 [compliance/](../compliance/README.md)。本域不承诺「审计完备」，只标出覆盖与空白。

## 阅读路径

1. **先看**：[01-audit-chain.md](01-audit-chain.md) — SandboxAudit、RunJournal、completed-run evidence 三条链路怎么接。
2. **再看**：[04-event-coverage.md](04-event-coverage.md) — 事件覆盖矩阵：哪些决策有结构化证据、哪些只有日志。
3. **深入**：[03-sandbox-audit.md](03-sandbox-audit.md) — bash 命令分类、结构化 JSON，以及「只写日志不落库」的边界。

## 本篇目

| 文件 | 主题 | 深度 |
|---|---|---|
| [01-audit-chain.md](01-audit-chain.md) | 审计链路：SandboxAudit、RunJournal、evidence | 概览 |
| [02-observability.md](02-observability.md) | 可观测：SSE、心跳、OTEL、单用户 Console 视图 | 深入 |
| [03-sandbox-audit.md](03-sandbox-audit.md) | SandboxAudit：命令分类与只写日志的边界 | 深入 |
| [04-event-coverage.md](04-event-coverage.md) | 事件覆盖矩阵：结构化证据 vs 文本日志 | 概览 |

## 宪章与约定

- 本目录无独立宪章；父级卷宪章为 [../PLAN.md](../PLAN.md)，审计修复记录见 [../AUDIT-FIX-PLAN.md](../AUDIT-FIX-PLAN.md)。
- 写作纪律沿用 [根 README](../../README.md)：判断性段落附 `file:line`，基线 v2.2.0。
- 阅读约定：缺口按「无 / 有但不覆盖 / 部分闭合」三态标注，每处写明边界条件。

## 相关目录

- [企业 IT 治理总览](../README.md) — 八个治理面向与默认关闭项。
- [合规对照](../compliance/README.md) — 哪些条款要求这类证据。
- [身份与接入](../identity/README.md) — 登录、PAT 等身份事件的来源。
- [执行边界](../execution/README.md) — SandboxAudit 记录的命令从哪来。
- [Enterprise Operations](../../enterprise-operations/README.md) — 日志与追踪后端的接法。
