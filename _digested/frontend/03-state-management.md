---
title: "状态管理：TanStack Query、ThreadState、localStorage"
description: "DeerFlow 前端使用三层状态架构：服务端状态（TanStack Query）、流式状态（LangGraph SDK）、本地偏好（localStorage + useSyncExternalStore）。"
topics: [frontend, nextjs, react]
---

# 状态管理：TanStack Query、ThreadState、localStorage

DeerFlow 前端使用三层状态架构：服务端状态（TanStack Query）、流式状态（LangGraph SDK）、本地偏好（localStorage + useSyncExternalStore）。

## 第一层：服务端状态 — TanStack Query

`QueryClient` 单例在 `WorkspaceContent` 中通过 `QueryClientProvider` 注入。

### 查询

| Hook | Query Key | 数据来源 |
|------|----------|---------|
| `useThreads(params)` | `["threads", "search", params]` | `client.threads.search()` — 自动分页 |
| `useThreadRuns(threadId)` | `["thread", threadId]` | `client.runs.list(threadId)` |
| `useThreadTokenUsage(threadId)` | `["threadTokenUsage", threadId]` | REST API |
| `useRunDetail(threadId, runId)` | `["run", threadId, runId]` | `client.runs.get()` |
| `useModels()` | `["models"]` | 后端 API |
| `useMemory()` | `["memory"]` | 后端 API |
| `useSkills()` | `["skills"]` | 后端 API |
| `useMCPConfig()` | `["mcp", "config"]` | 后端 API |
| `useSubagentBatches(threadId)` | `["subagent-batches", threadId]` | REST API（活跃时 2s 轮询，否则 15s） |
| `useSubagentBatchItems(...)` | `[..., batchId, "items"]` | REST API 无限分页（页 100，仅首页轮询） |
| `useBackgroundTasks(threadId)` | `["background-tasks", threadId]` | REST API（活跃时 3s 轮询，否则 15s） |
| `useProjects(params)` / `useProject(id)` | `["projects", ...]` | 🆕 项目列表/详情/配置（`core/projects/hooks.ts`） |
| `useInfiniteProjectThreads/Documents` | `["projects", "threads"/"documents", id]` | 🆕 项目详情页双 tab 无限分页 |
| `useInfiniteTrashDocuments()` | `["trash", "documents"]` | 🆕 回收站无限分页（`core/trash/hooks.ts`） |
| `useScheduledTaskRunHistory(taskId)` | `["scheduled-tasks", "runs", taskId, page]` | 🆕 run 历史分页：页大小 50（fetch 51 探测 `hasOlder`），仅第 0 页自动轮询 15s，翻页后停自动刷新 |

### 分支会话树投影（同步 #5）

`useThreads` 返回的线程是平铺分页的；`recent-chat-list.tsx` 通过 `core/threads/thread-branch-tree.ts::flattenThreadBranches()` 把它们投影成**安全的视觉 lineage**，再交给虚拟列表渲染（`└─`/`├─` 缩进 stem + 父标题 aria-label）。投影只信任已加载的、同 pin 分区的 parent——缺失/畸形/跨 pin/自环/成环的 parent 一律保持顶层，所以局部分页或坏 metadata 不会藏起会话。

### 变更

| Mutation | 行为 |
|----------|------|
| `useDeleteThread()` | 删除 thread → 失效 `["threads", "search"]` 查询 |
| `useRenameThread()` | 重命名 → 乐观更新 TanStack Query cache |
| 🆕 `useRestoreDocument()` / `usePurgeDocument()` / `useEmptyTrash()` | 回收站恢复/彻底删除/清空 → 失效 trash + projects 查询；409（内容文件缺失/损坏）时该行留在回收站并提示 |
| 🆕 `useCreateProject/PatchProject/ArchiveProject/RestoreProject/DeleteProject` | 项目生命周期 → 失效 projects + threads 查询 |
| 🆕 `useAttachProjectDocument()` | 项目文档附加到线程 → 配合 `composer-attach.ts` 的跨路由交接（见下） |
| 🆕 `useArchiveThread` / `useThreadArchiveAction` | 会话归档/恢复 → chats 页 Active/Archived 双 tab 切换查询 `useInfiniteThreads({ archived })` |

### 🆕 权限门控（同步 #6，#5294）

`core/auth/permissions.ts`：`GET /api/v1/auth/me` 现在返回 `permissions`（对齐 Gateway `authz.py` Phase 4）。`hasPermission(user, "threads:delete" | "runs:cancel")` 决定 thread-delete-dialog 与 run-cancel 入口是否渲染。语义是**建议性 UI 状态，不是执行点**：`permissions == null`（旧后端或凭据未解析出权限）或用户未加载时一律放行，避免新旧混部时隐藏仍可执行的操作；真正的强制在 Gateway 的 `@require_permission`。

## 第二层：流式状态 — LangGraph SDK useStream

`useStream<AgentThreadState>` 是 LangGraph SDK React 提供的 hook，管理实时 SSE 连接：

### 核心状态

```typescript
thread: {
  messages: Message[]           // 从 values + messages-tuple 事件累积
  values: AgentThreadState      // { title, artifacts[], todos[] }
  isLoading: boolean            // run 是否活跃
  isThreadLoading: boolean      // 初始加载中
  error: Error | null           // 流错误
  submit(messages, config)      // 发送消息 → 启动新 run
  stop()                        // 取消活跃 run
  getMessagesMetadata()         // per-message metadata
}
```

### useThreadStream 增强

`core/threads/hooks.ts:175` 在 useStream 之上添加：

- **乐观消息：** `[optimisticMessages, setOptimisticMessages]` — 在服务端响应前显示
- **消息合并：** `mergeMessages(history, thread.messages, optimisticMessages)` — history prepend + stream middle + optimistic append
- **Pending usage：** `pendingUsageMessages` — stream 开始后的新消息，用于实时 token 计数
- **文件上传状态：** `[isUploading, setIsUploading]` — 乐观 UI 中的上传进度

### 消息合并细节

```
合并顺序 (从旧到新):
  1. history messages (REST API 懒加载, prepend)
  2. stream messages (useStream 实时, 中间)
  3. optimistic messages (本地 state, append)

去重: 按 message.id 或 tool:{tool_call_id} identity
```

> **同步 #6 重构**：合并顺序不再是简单的 "history prepend / stream middle / optimistic append + 后出现者覆盖"。排序抽成纯函数模块 `core/threads/message-order.ts`，以后端盖在 history/values 消息上的 `deerflow_seq` 为可信骨架（earliest-seq-wins）；`values` 帧合并抽成 `core/threads/stream-state.ts`。完整规则见 [01-stream-pipeline.md](./01-stream-pipeline.md)。

## 第三层：本地偏好 — localStorage + useSyncExternalStore

`core/settings/` 使用 `useSyncExternalStore` 实现跨组件、跨 tab 的响应式本地状态：

### 数据结构

```typescript
interface LocalSettings {
  notification: { enabled: boolean }
  tokenUsage: {
    headerTotal: boolean
    inlineMode: "off" | "per_turn" | "step_debug"
  }
  context: {
    model_name?: string
    mode: "flash" | "thinking" | "pro" | "ultra" | undefined
    reasoning_effort?: "minimal" | "low" | "medium" | "high"
  }
}
```

### 实现细节

- **持久化：** `localStorage["deerflow.local-settings"]` → JSON
- **订阅模式：** `window.addEventListener("storage", ...)` → 跨 tab 同步
- **Per-thread 覆盖：** `localStorage["deerflow.thread-model.{threadId}"]` → 对特定 thread 的 model 覆盖
- **两个 hook：**
  - `useLocalSettings()` — 全局设置
  - `useThreadSettings(threadId)` — 带 per-thread model 覆盖的设置

### 🆕 账号偏好跨浏览器同步（同步 #6，#5397）

`core/settings/user-preferences.ts` + `preferences-sync.ts`：`notification / model_name / mode / reasoning_effort` 四个偏好提升为服务端账号偏好（migration 0023，`GET/PATCH /api/v1/auth/preferences`）：

- **Outbox 式同步**：`PreferencesSync` 类维护 `confirmed` + `pending` 两份，编辑先进 pending 立即本地生效，网络空闲时 flush；pending 存 sessionStorage（按 `userId` 隔离 key），崩溃/刷新后可重试，带指数退避
- **`UserPreferencesBoundary`** 包裹整个 `WorkspaceContent`，网络生命周期挂在已认证的工作区上（不参与渲染）；409/403（cookie 换账号）立即停止，**绝不用旧账号身份重试**
- 解析走 zod 逐字段 safeParse——只保留合法偏好，绝不复制任意运行时上下文

### 🆕 模型收藏（同步 #6，#5441）

`core/models/favorites-store.ts` + `use-model-favorites.ts`：按 `userId` 隔离的 localStorage 收藏列表（`favoritesKey(userId)`），存储不可用时降级 memory；`model-picker-content.tsx` 把收藏置顶（旧 `ai-elements/model-selector.tsx` 已删除）。

## React Context 层

| Context | 数据 | 用途 |
|---------|------|------|
| `ThreadContext` | `{ thread, isMock }` | 将 LangGraph stream 对象注入组件树 |
| `ArtifactsContext` | `{ artifacts[], selectedArtifact, open, select/deselect/setArtifacts }` | Artifact 选择状态 → 右侧面板 |
| `SubtaskContext` | `{ tasks: Record<string, Subtask>, setTasks }` | Subagent 执行状态追踪 |
| `I18nContext` | `{ t: Translations, locale, setLocale }` | 国际化字符串 |
| `PromptInputProvider` | Vercel AI SDK | 输入文本 + 附件管理 |
| `ThemeProvider` | next-themes | Dark/Light/System |
| `SidebarProvider` | shadcn/ui | 侧边栏开合状态 |

## 组件本地状态

| 组件 | 状态 |
|------|------|
| `ChatPage` | `isWelcomeMode: boolean` — 对话模式 vs 欢迎模式 |
| `MessageList` | Sentinels + IntersectionObserver — 无限滚动历史加载 |
| `InputBox` | `displayPrompt` — 当前输入的文本（带 mode/model/reasoning-effort 选择器） |
| `ChatBox` | Panel layout ratio (chat:artifacts) |
| `Reasoning` | `open: boolean` — thinking block 展开/折叠 |

## 状态同步方向

```
Backend                LangGraph SDK         React State           localStorage
   │                        │                     │                     │
   │── SSE ────────────────→│                     │                     │
   │                        │── thread.messages ──→│                     │
   │                        │── thread.values ────→│                     │
   │                        │── thread.isLoading ─→│                     │
   │                        │                     │                     │
   │                        │                     │── user toggle ─────→│ (model, mode)
   │                        │                     │←─ storage event ───│ (cross-tab)
   │                        │                     │                     │
   │←── TanStack Query ─────│←── useQuery ────────│                     │
   │                        │                     │                     │
   │←── submit() ──────────│←── sendMessage() ───│                     │
```
