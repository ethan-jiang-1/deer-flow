---
title: "生命周期与变更控制"
description: "Agent 怎么上线、怎么改、怎么回滚、怎么下架。"
type: index
topics: [governance]
---

# 生命周期与变更控制

Agent 怎么上线、怎么改、怎么回滚、怎么下架。

变更控制是企业区别于个人的关键：插件授予要重启、skill mutation 走七步流、配置版本只有告警没有闸门。但全局 kill switch、灰度发布、agent 版本管理仍是缺口。

> **约束：不修改项目源代码。** 本 `_digested/` 下所有内容仅作研究记录。详见 [根 README](../../README.md)。

## 本篇目

| 文件 | 主题 | 内容 |
|------|------|------|
| [01-agent-lifecycle.md](01-agent-lifecycle.md) | **Agent 生命周期** | 创建、热更新、停用删除 |
| [02-change-control.md](02-change-control.md) | **变更控制** | 插件授予、skill mutation 七步流 |
| [03-agent-sprawl.md](03-agent-sprawl.md) | **Agent 蔓延风险** | 蔓延面、缺失的控制、行业对标 |

## 规划中

| 文件 | 主题 | 内容 |
|------|------|------|
| 04-config-versioning.md | 配置版本与升级 | config_version 63、升级闸门、无 kill switch |

---

← 返回 [企业 IT 治理总览](../README.md) · 机制细节见 [enterprise-operations/](../../enterprise-operations/README.md)
