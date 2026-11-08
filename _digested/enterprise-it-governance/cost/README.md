---
title: "成本与容量"
description: "一个配置不当的 agent 加一个复杂请求，就是一次昂贵的账单。"
type: index
topics: [governance, cost, budget, concurrency]
---

# 成本与容量

> **定位**：花多少、怎么控。v2.2.0 已有 per-run 子代理派发上限（`max_total_per_run`）、`token_budget` 与单用户 Console 成本视图；本域把成本归属、限额维度、多实例与并发调度放在一起看。给平台预算负责人与容量规划者看。
> **边界**：实时成本告警、per-agent 预算、跨用户/集群视图仍是缺口，逐项结论在正文；token 用量如何进入 tracing 见 [enterprise-operations/tracing/](../../enterprise-operations/tracing/README.md)。

## 阅读路径

1. **先看**：[01-cost-attribution.md](01-cost-attribution.md) — token 用量、subagent 合并、`stream_usage` 与 Console 计价怎么对上。
2. **再看**：[03-budgets-and-limits.md](03-budgets-and-limits.md) — `token_budget`、`max_total_per_run`，以及「执行并发 3」与「截断 64」的区别。
3. **深入**：[05-concurrency-and-scheduling.md](05-concurrency-and-scheduling.md) — scheduler 旋钮与六条默认「无限制」。

## 本篇目

| 文件 | 主题 | 深度 |
|---|---|---|
| [01-cost-attribution.md](01-cost-attribution.md) | 成本归属：用量、subagent 合并、Console 计价 | 概览 |
| [02-deployment-and-ops.md](02-deployment-and-ops.md) | 部署与运维：热更新、健康检查、成本视图边界 | 深入 |
| [03-budgets-and-limits.md](03-budgets-and-limits.md) | 预算与上限：token_budget、max_total_per_run | 深入 |
| [04-multi-instance.md](04-multi-instance.md) | 多实例：启动闸门 8 条规则与共享状态要求 | 深入 |
| [05-concurrency-and-scheduling.md](05-concurrency-and-scheduling.md) | 并发与调度：执行 3 vs 截断 64、scheduler 旋钮 | 深入 |

## 宪章与约定

- 本目录无独立宪章；父级卷宪章为 [../PLAN.md](../PLAN.md)，审计修复记录见 [../AUDIT-FIX-PLAN.md](../AUDIT-FIX-PLAN.md)。
- 写作纪律沿用 [根 README](../../README.md)：判断性段落附 `file:line`，基线 v2.2.0。
- 阅读约定：缺口按「无 / 有但不覆盖 / 部分闭合」三态标注，每处写明边界条件。

## 相关目录

- [企业 IT 治理总览](../README.md) — 八个治理面向与默认关闭项。
- [执行边界](../execution/README.md) — 并发与超时在执行层的边界。
- [生命周期与变更控制](../lifecycle/README.md) — 配置改动如何影响容量。
- [Enterprise Operations](../../enterprise-operations/README.md) — 多实例与调度在部署侧的旋钮。
