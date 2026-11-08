---
title: "执行边界"
description: "Agent 真正动手的地方。沙箱、路径、资源、并发——出事的现场都在这一层。"
type: index
topics: [governance]
---

# 执行边界

Agent 真正动手的地方。沙箱、路径、资源、并发——出事的现场都在这一层。

「一个 prompt 能搞出 rm -rf / 吗」的答案全在这里：6 层路径防穿透、硬编码的高危命令正则、per-thread 隔离，以及三种隔离级别完全不同的沙箱模式。

> **约束：不修改项目源代码。** 本 `_digested/` 下所有内容仅作研究记录。详见 [根 README](../../README.md)。

## 本篇目

| 文件 | 主题 | 内容 |
|------|------|------|
| [01-sandbox-modes.md](01-sandbox-modes.md) | **七种沙箱模式** | 从 Local 路径映射到 K8s Provisioner |
| [02-path-containment.md](02-path-containment.md) | **路径防穿透** | 6 层校验 + Bash 子命令审计 |
| [03-resource-limits.md](03-resource-limits.md) | **资源管控与隔离** | CPU/内存/磁盘、per-thread |
| [04-gaps-and-comparison.md](04-gaps-and-comparison.md) | **还担心什么** | 剩余风险、行业对比、Docker 注意 |
| [05-execution-limits.md](05-execution-limits.md) | **执行限制** | 循环检测、并发上限、超时 |

## 规划中

| 文件 | 主题 | 内容 |
|------|------|------|
| 06-extension-execution-lease.md | 扩展执行租约 | extension_execution_leases、MCP durable task |

---

← 返回 [企业 IT 治理总览](../README.md) · 机制细节见 [enterprise-operations/](../../enterprise-operations/README.md)
