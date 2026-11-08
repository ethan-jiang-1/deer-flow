---
title: "生命周期与变更控制"
description: "Agent 怎么上线、怎么改、怎么回滚、怎么下架。"
type: index
topics: [governance, lifecycle, change-control]
---

# 生命周期与变更控制

> **定位**：从生到死——agent 怎么上线、怎么改、怎么回滚、怎么下架。变更控制是企业区别于个人的关键：插件授予要重启、skill mutation 走七步流、配置版本只有告警没有闸门。给变更管理与平台负责人看。
> **边界**：全局 kill switch、灰度发布、agent 版本管理仍是缺口，正文逐项标出；扩展能力本身的授权见 [authorization/](../authorization/README.md)，变更留痕见 [audit/](../audit/README.md)。

## 阅读路径

1. **先看**：[01-agent-lifecycle.md](01-agent-lifecycle.md) — 五类 agent 的创建与存储、两条热更新路径、「没有版本管理」的实际含义。
2. **再看**：[02-change-control.md](02-change-control.md) — 插件授予与 skill mutation 七步流。
3. **深入**：[03-agent-sprawl.md](03-agent-sprawl.md) — 四条增殖路径、五项缺失控制，以及「没有 agent 清单」这个根本缺口。

## 本篇目

| 文件 | 主题 | 深度 |
|---|---|---|
| [01-agent-lifecycle.md](01-agent-lifecycle.md) | 五类 agent 的创建、热更新与下架 | 概览 |
| [02-change-control.md](02-change-control.md) | 变更控制：插件授予、skill mutation 七步流 | 深入 |
| [03-agent-sprawl.md](03-agent-sprawl.md) | Agent 蔓延：增殖路径、缺失控制、行业对标 | 深入 |

### 三页合起来回答什么

- **上线**：五类 agent 怎么创建、存在哪，配置热更新的两条路径。
- **变更**：插件授予要重启，skill mutation 走七步流。
- **蔓延**：四条增殖路径里三条不需要运维参与，且没有 agent 清单。

## 宪章与约定

- 本目录无独立宪章；父级卷宪章为 [../PLAN.md](../PLAN.md)，审计修复记录见 [../AUDIT-FIX-PLAN.md](../AUDIT-FIX-PLAN.md)。
- 写作纪律沿用 [根 README](../../README.md)：判断性段落附 `file:line`，基线 v2.2.0。
- 阅读约定：缺口按「无 / 有但不覆盖 / 部分闭合」三态标注，每处写明边界条件。

## 相关目录

- [企业 IT 治理总览](../README.md) — 八个治理面向与默认关闭项。
- [授权模型](../authorization/README.md) — 谁能授予、谁能改。
- [审计与追责](../audit/README.md) — 变更与蔓延能不能被查出来。
- [合规对照](../compliance/README.md) — 变更管理与日志留存对应的条款。
- [Enterprise Operations](../../enterprise-operations/README.md) — 发布、重启与回滚的操作步骤。
