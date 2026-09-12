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
| **00-overview.md** | 全景：技术栈、目录结构、组件树、数据流图、历次同步新功能 |
| **01-stream-pipeline.md** | SSE → React 管线：`useThreadStream` hook、LangGraph stream_mode 映射、增量渲染 |
| **02-message-rendering.md** | streamdown 流式 markdown、thinking block 折叠、tool call 卡片（+ debug 详情面板）、会话大纲导航、artifact 预览（+ CSV/TSV 表格、独立查看窗口） |
| **03-state-management.md** | TanStack Query 缓存策略（projects、分页 run history、归档/项目移动 mutation）、权限门控、ThreadState context、用户偏好 localStorage 持久化 |
| **04-workspace-layout.md** | Drag 面板布局、Projects 项目工作区、thread 列表虚拟化、响应式设计、mobile sidebar 折叠、command palette |
| **05-subagent-ui.md** | TaskTracker context：task_started → task_running → task_completed 的 UI 状态机；+ 持久化 subagent 批量执行 UI、后台任务 UI |
| **06-architecture.md** | 前端技术栈全景：Next.js 16、Tailwind CSS 4、组件树；🆕 Webpack dev 默认（`DEER_FLOW_DEV_BUNDLER` 覆盖）与新 core 模块索引 |

> **同步 #6（431892e1..769589e8，v2.1.0-rc0）**：Capability Center 迁出 Settings（`/workspace/capabilities`）、Projects / Trash UI、conversation references picker、conversation outline、模型收藏、账号偏好跨浏览器同步、`message-order.ts`/`stream-state.ts` 排序重构、Artifacts 表格预览（Worker）/ zip 下载。各文件的 🆕 段落覆盖全部要点。

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
| 项目工作区 | `frontend/src/core/projects/` + `frontend/src/app/workspace/projects/[id]/` |
| 定时任务 | `frontend/src/core/scheduled-tasks/` |
| Artifact 查看器 | `frontend/src/core/artifacts/`（含 delimited-preview、viewer） |
| Subagent 追踪 | `frontend/src/core/tasks/` |
| 设置存储 | `frontend/src/core/settings/store.ts` |
| 国际化 | `frontend/src/core/i18n/` |
| 认证 | `frontend/src/core/auth/` |
| 🆕 消息排序/流状态 | `frontend/src/core/threads/message-order.ts`、`stream-state.ts` |
| 🆕 Projects / Trash 客户端 | `frontend/src/core/projects/`、`core/trash/` |
| 🆕 Capability Center | `frontend/src/app/workspace/capabilities/page.tsx`、`components/workspace/capabilities/` |
| 🆕 会话引用 / 大纲 | `frontend/src/core/conversation-references/`、`core/messages/conversation-outline.ts` |
| 🆕 偏好同步 / 模型收藏 | `frontend/src/core/settings/user-preferences.ts`、`core/models/favorites-store.ts` |
