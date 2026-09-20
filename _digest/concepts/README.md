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
| `sandbox/` | Sandbox 抽象接口 + 七种实现（Local/Docker/K8s/BoxLite/E2B/Tenki/OpenSandbox） |
| `subagent/` | Sub-agent 系统：双线程池 + 完整生命周期 |
| `memory/` | 🆕 Memory 系统：可插拔后端（deermem/mem0/noop/openviking）+ consolidation + staleness review |
| `skills-tools/` | 🆕 Skills 系统（SKILL.md）+ SkillScan + deferred discovery + review gate |
| `workspace-changes.md` | 🆕 Agent 文件改动追踪（pre/post run 快照 + diff 审查） |
| `projects/` | 🆕 v2.1.0-rc0 项目工作区：pin-then-render 上下文注入 + document shelf + trash |

## 工具清单

| 目录 | 内容 |
|------|------|
| `builtin-tools/` | 18 个内置工具（6 类：运行时控制、沙箱文件、Agent 生命周期、task/tool_search、ACP、Plan Mode） |
| `community-tools/` | 15+ 个第三方集成（搜索、抓取、图片搜索、浏览器自动化、截图、沙箱） |
