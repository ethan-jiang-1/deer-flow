---
title: "Concepts — 核心概念"
description: "DeerFlow 的核心抽象：Agent、Sandbox、Subagent、Memory、Skills/Tools，外加工具清单与项目工作区。"
type: index
topics: [concepts, architecture, agent, tools]
---

# Concepts — 核心概念

> **定位**：把架构图上的抽象拆成可读专章——Lead Agent 怎么造、代码在哪跑、任务怎么委派、记忆怎么存、技能与工具怎么装配、文件改动怎么审。给读完 overview、准备改代码或写 agent 的人。
> **边界**：不覆盖 middleware 链、运行时与模型层的实现细节（见 [internals](../internals/README.md)）；工具清单只做目录，装配顺序与条件加载在 [builtin-tools](builtin-tools/README.md)。

## 阅读路径

1. **先看**：[lead-agent/](lead-agent/README.md) — 从 `make_lead_agent` 工厂、ThreadState 与 SOUL.md 建立「Agent 是什么」。
2. **再看**：[sandbox/](sandbox/README.md) — 统一执行抽象与七种运行模式（六个 provider 类），回答「代码到底在哪跑、凭什么隔离」。
3. **深入**：[subagent/](subagent/README.md) — 委派、容量准入、durable batch 与报告契约；配套读 [memory/](memory/README.md) 与 [skills-tools/](skills-tools/README.md)。

## 本篇目

| 文件 | 主题 | 深度 |
|---|---|---|
| [lead-agent/](lead-agent/README.md) | Lead Agent 工厂、ThreadState、SOUL.md 与 Node/State 设计 | 深入 |
| [sandbox/](sandbox/README.md) | 统一沙箱抽象 + 七种运行模式（六个 provider 类）：租约、受控出口、隔离记录 | 深入 |
| [subagent/](subagent/README.md) | 子 Agent 委派：容量准入、durable batch、RFC #4651 报告契约 | 深入 |
| [memory/](memory/README.md) | 可插拔 Memory 后端、提取/持久化管线与 Manager 契约 | 深入 |
| [skills-tools/](skills-tools/README.md) | SKILL.md 契约、存储/投影/导出、SkillScan 与 review core | 深入 |
| [projects/](projects/README.md) | 项目工作区：pin-then-render 注入 + document shelf + trash | 概览 |
| [builtin-tools/](builtin-tools/README.md) | 内置工具全量目录：28 个 tool name、A–F 分册、装配顺序 | 概览 |
| [community-tools/](community-tools/README.md) | 25+ 第三方 provider：搜索、抓取、图片、浏览器、知识库 | 概览 |
| [workspace-changes.md](workspace-changes.md) | Agent 对 workspace/outputs 的改动追踪与 diff 审查 | 概览 |

## 宪章与约定

- 本目录无独立宪章；写作纪律沿用 [根 README](../README.md)（不修改源码、`main` 只镜像上游、笔记只落在 `ethan`）。
- 每个子目录的 README 都是独立索引，进入前先读它的「定位 / 边界」，避免在 sandbox 与 community-tools 之间走错门。

## 相关目录

- [overview/](../overview/README.md) — 先看架构图，再回到这里看抽象。
- [internals/](../internals/README.md) — 机制层：Agent Loop、Middleware、模型层、配置、运行时与持久化。
- [frontend/](../frontend/README.md) — 这些概念在 UI 上长什么样（subagent 进度、知识引用、项目工作区）。
- [根 README](../README.md) — 30 / 60 分钟阅读预算与关键词检索表。
