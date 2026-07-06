---
title: "Frontend — 前端架构"
description: "Next.js 16 + React 19 + Tailwind CSS 4 构建的 Agent 工作台。核心挑战是**流式渲染**：SSE 事件流 → LangGraph stream_mode 映射 → 增量 markdown 渲染 →"
type: index
---

# Frontend — 前端架构

Next.js 16 + React 19 + Tailwind CSS 4 构建的 Agent 工作台。核心挑战是**流式渲染**：SSE 事件流 → LangGraph stream_mode 映射 → 增量 markdown 渲染 → React 状态同步。

**回答的核心问题**：`useThreadStream` 怎么把 SSE 事件转成 React state？streamdown 怎么做流式 markdown 渲染？workspace 的 drag 面板布局怎么实现的？怎么处理 subagent task 的实时进度展示？

> **约束：不修改项目源代码。** 本 `_digest/` 下所有内容仅作研究记录。详见 [根 README](../README.md)。

## 阅读顺序

| 文件 | 内容 |
|------|------|
| **00-overview.md** | 全景：技术栈、目录结构、组件树、数据流图 |
| **01-stream-pipeline.md** | SSE → React 管线：`useThreadStream` hook、LangGraph stream_mode 映射、增量渲染 |
| **02-message-rendering.md** | streamdown 流式 markdown、thinking block 折叠、tool call 卡片、artifact 预览 |
| **03-state-management.md** | TanStack Query 缓存策略、ThreadState context、用户偏好 localStorage 持久化 |
| **04-workspace-layout.md** | Drag 面板布局、响应式设计、mobile sidebar 折叠、command palette |
| **05-subagent-ui.md** | TaskTracker context：task_started → task_running → task_completed 的 UI 状态机 |
| **06-i18n-and-theming.md** | en-US / zh-CN 国际化、light/dark 主题切换、Tailwind CSS 4 配置 |

## 关键问题

- 前端怎么消费 LangGraph 的 SSE 事件流？→ `01-stream-pipeline.md`
- AI 文本怎么做的逐字流式渲染？→ `02-message-rendering.md`
- ThreadState 怎么在前端多个组件间共享？→ `03-state-management.md`
- 输入框的模型选择/plan mode toggle/file upload 怎么协作？→ `03-state-management.md`
- Subagent 的实时进度怎么展示？→ `05-subagent-ui.md`

## 源文件索引

| 组件 | 路径 |
|------|------|
| API Client 单例 | `frontend/src/core/api/api-client.ts` |
| 核心流式 hook | `frontend/src/core/threads/hooks.ts` |
| 流式 markdown 渲染 | `frontend/src/core/streamdown/` |
| 消息处理 | `frontend/src/core/messages/` |
| 工作区容器 | `frontend/src/components/workspace/workspace-container.tsx` |
| 输入框 | `frontend/src/components/workspace/input-box.tsx` |
| 消息列表 | `frontend/src/components/workspace/messages/` |
| Subagent 追踪 | `frontend/src/core/tasks/` |
| 设置存储 | `frontend/src/core/settings/store.ts` |
| 国际化 | `frontend/src/core/i18n/` |
| 认证 | `frontend/src/core/auth/` |
