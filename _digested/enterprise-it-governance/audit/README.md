---
title: "审计与追责"
description: "「某个时间段内 agent 被拒绝了哪些操作」——能不能不 grep 日志就答出来？"
type: index
topics: [governance]
---

# 审计与追责

「某个时间段内 agent 被拒绝了哪些操作」——能不能不 grep 日志就答出来？

这一域是 v2.2.0 进步最大的地方：guardrail 决策已写入 RunJournal，completed-run evidence 提供只读投影面。但仍需逐项分清哪些决策有结构化证据、哪些只有文本日志。

> **约束：不修改项目源代码。** 本 `_digested/` 下所有内容仅作研究记录。详见 [根 README](../../README.md)。

## 本篇目

| 文件 | 主题 | 内容 |
|------|------|------|
| [01-audit-chain.md](01-audit-chain.md) | **审计链路** | SandboxAudit、RunJournal、completed-run evidence |
| [02-observability.md](02-observability.md) | **可观测** | SSE、心跳、OTEL、单用户 Console 视图 |
| [03-sandbox-audit.md](03-sandbox-audit.md) | **SandboxAudit 细节** | bash 命令分类、结构化 JSON、只写日志不落库 |
| [04-event-coverage.md](04-event-coverage.md) | **事件覆盖矩阵** | 哪些决策有结构化证据、哪些只有日志 |

---

← 返回 [企业 IT 治理总览](../README.md) · 机制细节见 [enterprise-operations/](../../enterprise-operations/README.md)
