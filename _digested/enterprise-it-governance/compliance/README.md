---
title: "合规对照"
description: "把「能不能过我们风控」从主观判断变成可逐条打勾的表。"
type: index
topics: [governance, compliance, gdpr, soc2]
---

# 合规对照

> **定位**：把「能不能过我们风控」从主观判断变成可逐条打勾的表——只陈述「控制项 ↔ DeerFlow 机制」的对应关系与证据位置，缺口如实标出。给内审、法务与外部审计准备材料的人看。
> **边界**：本域**不宣称合规**，结论必须由审计方给出；证据链本身见 [audit/](../audit/README.md)，数据主体权利对应的实现见 [data/](../data/README.md)。

## 阅读路径

1. **先看**：[01-mapping.md](01-mapping.md) — GDPR / SOC2 / ISO27001 / EU AI Act 的逐条映射总表。
2. **再看**：[02-gdpr.md](02-gdpr.md) — 数据主体权利、删除与跨境传输。
3. **深入**：[04-eu-ai-act.md](04-eu-ai-act.md) — 透明度、人类监督、自主性控制与日志留存。

## 本篇目

| 文件 | 主题 | 深度 |
|---|---|---|
| [01-mapping.md](01-mapping.md) | 合规对照总表：四套框架逐条映射 | 概览 |
| [02-gdpr.md](02-gdpr.md) | GDPR：数据主体权利、删除、跨境传输 | 深入 |
| [03-soc2-iso27001.md](03-soc2-iso27001.md) | SOC2 / ISO27001：访问控制、日志留存、变更管理 | 深入 |
| [04-eu-ai-act.md](04-eu-ai-act.md) | EU AI Act：透明度、人类监督、自主性控制 | 深入 |

## 宪章与约定

- 本目录无独立宪章；父级卷宪章为 [../PLAN.md](../PLAN.md)，审计修复记录见 [../AUDIT-FIX-PLAN.md](../AUDIT-FIX-PLAN.md)。
- 写作纪律沿用 [根 README](../../README.md)：判断性段落附 `file:line`，基线 v2.2.0；每页固定免责「本卷不构成合规结论」。
- 阅读约定：缺口按「无 / 有但不覆盖 / 部分闭合」三态标注，每处写明边界条件。

## 相关目录

- [企业 IT 治理总览](../README.md) — 八个治理面向与默认关闭项。
- [数据治理](../data/README.md) — 保留期、PII 与驻留的实际机制。
- [审计与追责](../audit/README.md) — 条款所要求的证据从哪来。
- [执行边界](../execution/README.md) — 隔离与资源限制对应哪些控制项。
- [Enterprise Operations](../../enterprise-operations/README.md) — 条款落成配置时的操作面。
