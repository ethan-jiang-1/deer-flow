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

### 变更

| Mutation | 行为 |
|----------|------|
| `useDeleteThread()` | 删除 thread → 失效 `["threads", "search"]` 查询 |
| `useRenameThread()` | 重命名 → 乐观更新 TanStack Query cache |

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
策略: 保留最后出现的 (新值覆盖旧值)
```

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
