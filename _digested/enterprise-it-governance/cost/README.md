---
title: "成本与容量"
description: "一个配置不当的 agent 加一个复杂请求，就是一次昂贵的账单。"
type: index
topics: [governance]
---

# 成本与容量

一个配置不当的 agent 加一个复杂请求，就是一次昂贵的账单。

v2.2.0 已补上 per-run 预算（max_total_per_run + token_budget），但实时成本仪表盘、per-agent 预算、agent 级 SLO 仍是缺口。

> **约束：不修改项目源代码。** 本 `_digested/` 下所有内容仅作研究记录。详见 [根 README](../../README.md)。

## 本篇目

| 文件 | 主题 | 内容 |
|------|------|------|
| [01-cost-attribution.md](01-cost-attribution.md) | **成本归属** | Token 用量、subagent 合并、stream_usage |
| [02-deployment-and-ops.md](02-deployment-and-ops.md) | **部署与运维** | 热更新、健康检查、迁移 |

## 规划中

| 文件 | 主题 | 内容 |
|------|------|------|
| 03-budgets-and-limits.md | 预算与上限 | token_budget、max_total_per_run、并发 64 |
| 04-multi-instance.md | 多实例 | multi_instance 的 8 条拒绝规则、共享状态要求 |

---

← 返回 [企业 IT 治理总览](../README.md) · 机制细节见 [enterprise-operations/](../../enterprise-operations/README.md)
