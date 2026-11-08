---
title: "成本与容量"
description: "一个配置不当的 agent 加一个复杂请求，就是一次昂贵的账单。"
type: index
topics: [governance]
---

# 成本与容量

一个配置不当的 agent 加一个复杂请求，就是一次昂贵的账单。

v2.2.0 有 per-run 子代理派发上限（`max_total_per_run`）与 `token_budget`，Console 也提供单用户成本视图；但实时成本告警、per-agent 预算、跨用户/集群视图仍是缺口。

> **约束：不修改项目源代码。** 本 `_digested/` 下所有内容仅作研究记录。详见 [根 README](../../README.md)。

## 本篇目

| 文件 | 主题 | 内容 |
|------|------|------|
| [01-cost-attribution.md](01-cost-attribution.md) | **成本归属** | Token 用量、subagent 合并、stream_usage、Console 计价 |
| [02-deployment-and-ops.md](02-deployment-and-ops.md) | **部署与运维** | 热更新、健康检查、迁移、成本视图边界 |
| [03-budgets-and-limits.md](03-budgets-and-limits.md) | **预算与上限** | token_budget、max_total_per_run、执行并发 3 与截断 64 的区别 |
| [04-multi-instance.md](04-multi-instance.md) | **多实例** | 启动闸门的 8 条规则、共享状态要求 |
| [05-concurrency-and-scheduling.md](05-concurrency-and-scheduling.md) | **并发与调度** | 执行并发 3 vs 截断 64、scheduler 旋钮、六条默认「无限制」 |

---

← 返回 [企业 IT 治理总览](../README.md) · 机制细节见 [enterprise-operations/](../../enterprise-operations/README.md)
