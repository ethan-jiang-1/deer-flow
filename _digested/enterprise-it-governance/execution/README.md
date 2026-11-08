---
title: "执行边界"
description: "Agent 真正动手的地方。沙箱、路径、资源、并发——出事的现场都在这一层。"
type: index
topics: [governance, sandbox, execution, isolation]
---

# 执行边界

> **定位**：Agent 真正动手的地方——七种沙箱模式、6 层路径防穿透、硬编码的高危命令正则、per-thread 隔离、资源与并发上限。「一个 prompt 能搞出 `rm -rf /` 吗」的答案全在这里。给安全评审与沙箱选型的工程师看。
> **边界**：授权门（谁能触发）见 [authorization/](../authorization/README.md)；执行留下的审计证据见 [audit/](../audit/README.md)；容器与镜像部署见 [enterprise-operations/deployment/](../../enterprise-operations/deployment/README.md)。

## 阅读路径

1. **先看**：[01-sandbox-modes.md](01-sandbox-modes.md) — 从 Local 路径映射到 K8s Provisioner 的七种模式与三种隔离级别。
2. **再看**：[02-path-containment.md](02-path-containment.md) — 6 层校验加 Bash 子命令审计，路径怎么被关住。
3. **深入**：[05-execution-limits.md](05-execution-limits.md) — 循环检测、并发上限与超时，跑飞之前在哪刹车。

## 本篇目

| 文件 | 主题 | 深度 |
|---|---|---|
| [01-sandbox-modes.md](01-sandbox-modes.md) | 七种沙箱模式与三种隔离级别 | 概览 |
| [02-path-containment.md](02-path-containment.md) | 路径防穿透：6 层校验 + Bash 子命令审计 | 深入 |
| [03-resource-limits.md](03-resource-limits.md) | 资源管控：输出截断、并发、磁盘与 cgroup 边界 | 深入 |
| [04-gaps-and-comparison.md](04-gaps-and-comparison.md) | 剩余风险：出站网络、资源配额边界 | 概览 |
| [05-execution-limits.md](05-execution-limits.md) | 执行限制：循环检测、并发上限、超时 | 深入 |

## 宪章与约定

- 本目录无独立宪章；父级卷宪章为 [../PLAN.md](../PLAN.md)。
- 写作纪律沿用 [根 README](../../README.md)：判断性段落附 `file:line`，基线 v2.2.0。
- 阅读约定：缺口按「无 / 有但不覆盖 / 部分闭合」三态标注，每处写明边界条件。

## 相关目录

- [企业 IT 治理总览](../README.md) — 八个治理面向与默认关闭项。
- [授权模型](../authorization/README.md) — 执行之前先过哪几道授权门。
- [数据治理](../data/README.md) — 执行过程会碰到哪些数据与凭据。
- [Enterprise Operations](../../enterprise-operations/README.md) — 沙箱模式在部署侧的选型与配置。
