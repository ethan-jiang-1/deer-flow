---
title: "Frontend — 前端架构"
description: "Next.js 16 + React 19 + Tailwind CSS 4 的 Agent 工作台：流式渲染、状态管理、工作区布局与 2.2.0 增量。"
type: index
topics: [frontend, nextjs, react, streaming]
---

# Frontend — 前端架构

> **定位**：DeerFlow 的 Web 工作台怎么把一条 SSE 流变成可读的对话界面。核心挑战是流式渲染：SSE 事件 → LangGraph `stream_mode` 映射 → 增量 markdown → React 状态同步。给要改 UI、查渲染 bug、跟同步的人。
> **边界**：不覆盖后端 SSE 的生产端（帧格式、producer lease 见 [observability/05-live-streaming.md](../observability/05-live-streaming.md)），不覆盖 subagent 执行内部（见 [subagent](../concepts/subagent/README.md)），不覆盖构建与部署流水线（见 [enterprise-operations/deployment](../enterprise-operations/deployment/README.md)）。

## 阅读路径

1. **先看**：[00-overview.md](00-overview.md) — 技术栈、目录结构、组件树与数据流总览。
2. **再看**：[01-stream-pipeline.md](01-stream-pipeline.md) — `useThreadStream` 把 SSE 事件转成 React state 的完整管线。
3. **深入**：[03-state-management.md](03-state-management.md) — TanStack Query / ThreadState / localStorage 三层状态与权限门控。

## 本篇目

| 文件 | 主题 | 深度 |
|---|---|---|
| [00-overview.md](00-overview.md) | 技术栈、目录结构、组件树、数据流图与历次同步要点 | 概览 |
| [01-stream-pipeline.md](01-stream-pipeline.md) | SSE → React：`useThreadStream`、stream_mode 映射、增量渲染、重连与 gap 恢复 | 深入 |
| [02-message-rendering.md](02-message-rendering.md) | streamdown、thinking block、tool call 卡片、会话大纲、artifact 预览、知识引用 | 深入 |
| [03-state-management.md](03-state-management.md) | TanStack Query 缓存策略、权限门控、ThreadState context、偏好持久化 | 深入 |
| [04-workspace-layout.md](04-workspace-layout.md) | Drag 面板（artifacts / browser / sidecar / details）、Projects、虚拟化、command palette、Capability Center | 深入 |
| [05-subagent-ui.md](05-subagent-ui.md) | TaskTracker 状态机、批量执行与后台任务 UI、managed subagent 注册表 | 概览 |
| [06-architecture.md](06-architecture.md) | 技术栈全景、core 模块索引、扩展运行时、Pagefind 搜索与已删除面 | 深入 |

## 速览

- **基线**：同步 #8 从 `v2.1.0` 迁到 `v2.2.0`（2026-10-29，两 tag 间 1239 commits / 1068 merged PR）；改动面 `src/core` 142 文件、`src/components` 140、`src/content` 90、`tests/unit` 228、`tests/e2e` 67。
- **流与输入**：`TERMINAL_RUN_STATUSES` 短路、`MAX_STREAM_GAP_RECOVERIES = 5` 与 `stream_replay_gap` 恢复循环、新 tab 接手活跃 run；composer 的 `/` 菜单只剩 `/goal` 与 `/compact`，inline `@` 引用（skill / file / conversation / extension，最多 16 个 skill）配 voice input 与 IME 守卫。
- **界面增量**：知识检索落到 UI（`core/knowledge/`、`[citation:…]` → `knowledge-source-<id>` 锚点、Sources 面板）、定时任务改为列表优先、Capability Center 三 tab（plugins / skills / extensions）与插件页面路由、thread origin / 未读与 15s `thread-activity` 轮询、Pagefind 双语搜索；删除面为 `components/ai-elements/` 14 个模块、`proxy-policy.ts`、`thread-scheduled-tasks-link.tsx`。
- **同步 #6 / v2.1.0**（#6 的逐条增量见各篇 🆕 段）：Capability Center 迁出 Settings 到 `/workspace/capabilities`、Projects / Trash UI、conversation references 与 outline、模型收藏与偏好跨浏览器同步、`message-order.ts` / `stream-state.ts` 排序重构、Artifacts 表格预览（Worker）与 zip 下载；v2.1.0 的两处改动见 [04-workspace-layout.md](04-workspace-layout.md)（侧栏 kebab 裁切 #5681 → #5682）与 [06-architecture.md](06-architecture.md)（`src/content/{en,zh}/harness/` 手册重构：subagents 11 页、extensions 11 页、checkpoints 11 页）。
- **关键路径**：`core/api/api-client.ts`、`core/threads/hooks.ts`、`core/streamdown/`、`components/workspace/workspace-container.tsx` 与 `input-box.tsx`、`core/projects/`、`core/capabilities/`、`core/knowledge/`、`core/extensions/`；完整模块索引见 [06-architecture.md](06-architecture.md)。

## 宪章与约定

- 本目录无独立宪章；研究纪律沿用 [根 README](../README.md)（不修改源码、`main` 只镜像上游、笔记只落在 `ethan`）。
- 每轮同步记录改动面与删除面：被删模块写进正文「已删除」小节，而不是从笔记里静默消失。

## 相关目录

- [overview/](../overview/README.md) — 前端在整个四层架构中的位置。
- [concepts/subagent/](../concepts/subagent/README.md) — TaskTracker 展示的 task 生命周期来源。
- [concepts/projects/](../concepts/projects/README.md) — 项目工作区的后端机制。
- [根 README](../README.md) — 全局阅读地图与关键词检索。
