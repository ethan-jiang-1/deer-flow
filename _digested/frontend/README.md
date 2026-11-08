---
title: "Frontend — 前端架构"
description: "Next.js 16 + React 19 + Tailwind CSS 4 构建的 Agent 工作台。核心挑战是**流式渲染**：SSE 事件流 → LangGraph stream_mode 映射 → 增量 markdown 渲染 →"
type: index
---

# Frontend — 前端架构

Next.js 16 + React 19 + Tailwind CSS 4 构建的 Agent 工作台。核心挑战是**流式渲染**：SSE 事件流 → LangGraph stream_mode 映射 → 增量 markdown 渲染 → React 状态同步。

**回答的核心问题**：`useThreadStream` 怎么把 SSE 事件转成 React state？streamdown 怎么做流式 markdown 渲染？workspace 的 drag 面板布局怎么实现的？怎么处理 subagent task 的实时进度展示？

> **约束：不修改项目源代码。** 本 `_digested/` 下所有内容仅作研究记录。详见 [根 README](../README.md)。

## 阅读顺序

| 文件 | 内容 |
|------|------|
| **00-overview.md** | 全景：技术栈、目录结构、组件树、数据流图、历次同步新功能 |
| **01-stream-pipeline.md** | SSE → React 管线：`useThreadStream` hook、LangGraph stream_mode 映射、增量渲染 |
| **02-message-rendering.md** | streamdown 流式 markdown、thinking block 折叠、tool call 卡片（+ debug 详情面板）、会话大纲导航、artifact 预览（+ CSV/TSV 表格、独立查看窗口）；🆕 知识引用（knowledge citations）与 workspace-changes 徽章 |
| **03-state-management.md** | TanStack Query 缓存策略（projects、分页 run history、归档/项目移动 mutation、🆕 thread activity 轮询、capability catalog/installations、knowledge catalog）、权限门控、ThreadState context、用户偏好 localStorage 持久化 |
| **04-workspace-layout.md** | Drag 面板布局（🆕 sidecar/browser/details 四种右面板）、Projects 项目工作区、thread 列表虚拟化、响应式设计、mobile sidebar 折叠、command palette、🆕 Capability Center 三 tab 与插件页面路由 |
| **05-subagent-ui.md** | TaskTracker context：task_started → task_running → task_completed 的 UI 状态机；+ 持久化 subagent 批量执行 UI、后台任务 UI；🆕 managed subagent 注册表（`core/subagents`） |
| **06-architecture.md** | 前端技术栈全景：Next.js 16、Tailwind CSS 4、组件树；Webpack dev 默认（`DEER_FLOW_DEV_BUNDLER` 覆盖）、core 模块索引、🆕 2.2.0 新增 core 模块与扩展运行时（`core/extensions`、`core/capabilities`、`core/knowledge`、`core/channels`…） |

## 🆕 同步 #8（v2.1.0 → v2.2.0）

基线从 tag `v2.1.0` 迁到 `v2.2.0`（2026-10-29 发布，两 tag 之间 1239 commits / 1068 merged PR）。前端域改动面：`src/core` 142 文件、`src/components` 140 文件、`src/content` 90 文件、`tests/unit` 228 文件、`tests/e2e` 67 文件。本轮主题：

- **知识检索落地到 UI**：`core/knowledge/`（scope 快照 + ragflow 证据）与 `knowledge-scope-selector`、`knowledge_scope` run context、`[citation:…]` 指向 `knowledge-source-<id>` 片段锚点的引用徽章与 Sources 面板 → 01 / 02
- **流重连更硬**：`TERMINAL_RUN_STATUSES` 短路、`MAX_STREAM_GAP_RECOVERIES = 5`、`stream_replay_gap` 恢复循环、新 tab 接手活跃 run → 01
- **Composer 语义收敛**：`/` 菜单只剩 `/goal` 与 `/compact`、inline `@` 引用（skill/file/conversation/extension，最多 16 个 skill）、voice input + IME 守卫 → 01 / 03
- **定时任务从"表单页"变成"列表优先"**：任务详情/运行历史/停止条件/上限、聊天内任务卡与生命周期事件行、`scheduled-task-events` → 03 / 04
- **Capability Center 三 tab**（plugins / skills / extensions）+ 插件清单（`PluginManifest` v1）+ 扩展插件页面路由 → 04 / 06
- **会话可见性**：thread origin（`deerflow_origin`）、未读标记与 15s `thread-activity` 轮询、goal 状态条、message-details 右面板 → 02 / 03 / 04
- **文档站搜索**：Pagefind 双语索引（`scripts/build-search-index.mjs`）+ `DocsHtmlLang` → 06
- **删除面**：`components/ai-elements/` 14 个模块、认证代理策略模块 `proxy-policy.ts` 与 `thread-scheduled-tasks-link.tsx` 已删除（见 06）

> **同步 #6（431892e1..769589e8，v2.1.0-rc0）**：Capability Center 迁出 Settings（`/workspace/capabilities`）、Projects / Trash UI、conversation references picker、conversation outline、模型收藏、账号偏好跨浏览器同步、`message-order.ts`/`stream-state.ts` 排序重构、Artifacts 表格预览（Worker）/ zip 下载。各文件的 🆕 段落覆盖全部要点。

> **同步 v2.1.0（769589e8..345f08be）**：本轮 10 个上游 commit 中与 frontend 相关的实质变更只有两处 —— ① Projects 侧栏分组模式下嵌套 `SidebarMenu` 的 kebab 裁切修复（#5681 → #5682）；② `src/content/{en,zh}/harness/` 的 `subagents/`（11 页）与 `extensions/`（10 页）双语手册重构与新增（2.2.0 起 `extensions/` 为 11 页、另新增 `checkpoints/` 11 页）。分别见 [04-workspace-layout.md](./04-workspace-layout.md)、[06-architecture.md](./06-architecture.md)。（另：`frontend/package.json` 的 `version` 在 `345f08be` 由 `2.1.0-rc0` bump 到 `2.1.0`，依赖与 scripts 无变动。）

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
| Harness 内容手册 | `frontend/src/content/{en,zh}/harness/`（`subagents/` 11 页、`extensions/` 11 页、`checkpoints/` 11 页） |
| 🆕 知识库 scope | `frontend/src/core/knowledge/`、`frontend/src/components/workspace/knowledge-scope-selector.tsx` |
| 🆕 知识/普通引用 | `frontend/src/core/citations/sources.ts`、`frontend/src/components/workspace/citations/` |
| 🆕 Capability 目录 | `frontend/src/core/capabilities/`、`frontend/src/components/workspace/capabilities/plugin-catalog.ts` |
| 🆕 扩展插件运行时 | `frontend/src/core/extensions/`、`frontend/src/components/workspace/plugin-page.tsx` |
| 🆕 流模式与重连 | `frontend/src/core/api/stream-mode.ts`、`frontend/src/core/api/api-client.ts` |
| 🆕 会话未读/来源 | `frontend/src/core/threads/activity.ts`、`origin.ts` |
| 🆕 workspace 变更徽章 | `frontend/src/core/workspace-changes/`、`frontend/src/components/workspace/changes/` |
| 🆕 右面板四态 | `frontend/src/components/workspace/chats/chat-box.tsx`（artifacts / browser / sidecar / details） |
