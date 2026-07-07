---
title: "Concepts — 核心概念"
description: "DeerFlow 的六大核心抽象。理解这些就理解了 DeerFlow。"
type: index
---

# Concepts — 核心概念

DeerFlow 的六大核心抽象。理解这些就理解了 DeerFlow。

## 子目录

| 目录 | 内容 |
|------|------|
| `lead-agent/` | Lead Agent 工厂函数 + ThreadState 结构 |
| `sandbox/` | Sandbox 抽象接口 + 五种实现（Local/Docker/K8s/BoxLite/E2B） |
| `subagent/` | Sub-agent 系统：双线程池 + 完整生命周期 |
| `memory/` | Memory 系统：提取 → 排队 → 持久化 |
| `skills-tools/` | Skills 系统（SKILL.md）+ Tools 组装 |

## 工具清单

| 目录 | 内容 |
|------|------|
| `builtin-tools/` | 17 个内置工具（6 类：运行时控制、沙箱文件、Agent 生命周期、task/tool_search、ACP、Plan Mode） |
| `community-tools/` | 9 个第三方集成（Tavily、Jina、Firecrawl、DuckDuckGo、Exa、Serper、InfoQuest、AIO Sandbox） |
