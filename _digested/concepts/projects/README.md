---
title: "Projects — 项目工作区"
description: "v2.1.0-rc0 子系统：把 threads 组织进项目，以 pin-then-render 注入 instructions 与 document shelf。"
type: index
topics: [projects, threads, context]
---

# Projects — 项目工作区

> **定位**：v2.1.0-rc0（同步 #6）新增的子系统。回答「项目怎么把多个 thread 分组、项目级 instructions 与 document shelf 怎么进入每一轮上下文、trash 为什么还需要保留期清扫与 purge」。给用项目组织多轮工作、或排查上下文注入的人。
> **边界**：不覆盖 thread 生命周期与 run 状态机（见 [internals/runtime](../../internals/runtime/README.md)），不覆盖前端项目页的交互实现（见 [frontend/04-workspace-layout.md](../../frontend/04-workspace-layout.md)），也不覆盖 workspace 文件改动追踪（见 [workspace-changes.md](../workspace-changes.md)）。

## 阅读路径

1. **先看**：[project-workspaces.md](project-workspaces.md) — 「核心机制：pin-then-render」与「上下文注入边界」两节。
2. **深入**：同篇「Document Shelf 与 Trash」「配置」两节 — trash 清扫 / purge / 恢复、shelf 落盘分类，以及 `config.yaml -> projects:`。

## 本篇目

| 文件 | 主题 | 深度 |
|---|---|---|
| [project-workspaces.md](project-workspaces.md) | pin-then-render 上下文注入、shelf 工具、trash/promotion、配置 | 深入 |

## 速览

- **注入是快照**：项目 instructions 与 shelf 文档先 pin 成快照、再 render 进上下文，渲染边界是显式的（见正文「渲染边界」）。
- **shelf 有类型**：文档落盘与转换按类型分类，工具返回有固定契约，不是任意文件透传。
- **trash 是回收站**：删除先进 trash，保留期清扫与 purge 钩子是两条回收路径；trash 与 promotion 是配套的一对机制（语义见正文）。

## 宪章与约定

- 本目录无独立宪章；研究纪律沿用 [根 README](../../README.md)（不修改源码、`main` 只镜像上游、笔记只落在 `ethan`）。
- 本子系统仍标注 rc 基线（v2.1.0-rc0），字段与路由以正文记录的同步点为界。

## 相关目录

- [lead-agent/](../lead-agent/README.md) — ThreadState 侧的结构与工厂装配。
- [concepts/](../README.md) — 概念总览与其它核心抽象。
- [enterprise-operations/app-layer/](../../enterprise-operations/app-layer/README.md) — 项目相关 REST 路由与认证。
- [frontend/](../../frontend/README.md) — 项目工作区在 UI 上的布局与状态管理。
