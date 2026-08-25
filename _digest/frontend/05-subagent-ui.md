---
title: "Subagent UI：TaskTracker 状态机"
description: "DeerFlow 的 subagent 在前端有独立的 UI 状态追踪——不只是显示 tool call，而是将 subagent 视为一个持续运行的任务，实时显示其内部状态变更。"
topics: [frontend, nextjs, react]
---

# Subagent UI：TaskTracker 状态机

DeerFlow 的 subagent 在前端有独立的 UI 状态追踪——不只是显示 tool call，而是将 subagent 视为一个持续运行的任务，实时显示其内部状态变更。

## Subtask 数据模型

`core/tasks/types.ts`：

```typescript
interface Subtask {
  id: string
  status: "in_progress" | "completed" | "failed"
  subagent_type: string          // "general-purpose", "bash", custom agent name
  description: string            // LLM 生成的任务描述
  latestMessage?: AIMessage      // subagent 最新产出的消息
  prompt: string                 // 发送给 subagent 的初始 prompt
  result?: string                // 完成后的结果文本
  error?: string                 // 失败后的错误信息
}
```

## SubtaskContext

`core/tasks/context.tsx` — `SubtasksProvider` 在 `ChatProviders` 中包裹 ChatPage：

```typescript
// 状态
Record<string, Subtask>

// Hooks
useSubtask(id)          → 读取单个 subtask
useUpdateSubtask()      → merge 部分更新 (用于 streaming 期间)
```

## 生命周期追踪

Subtask 状态通过 SSE 的 `custom` 事件流更新：

```
1. Agent dispatch task tool_call
   → MessageList 检测 assistant:subagent group
   → updateSubtask({ id, status: "in_progress", subagent_type, description, prompt })

2. Subagent 开始工作
   → SSE custom event: "task_running" (含 subagent 内部 tool call 信息)
   → MessageList.onCustomEvent → updateSubtask({ latestMessage })

3. Subagent 完成/失败
   → task tool 返回结果
   → parseSubtaskResult(text) → status: "completed" | "failed"
   → updateSubtask({ status, result/error })
```

## 结果解析

`core/tasks/subtask-result.ts` — `parseSubtaskResult(text)`：

| 前缀匹配 | 状态 |
|---------|------|
| `"Task Succeeded. Result:"` | `completed` |
| `"Task failed."` | `failed` |
| `"Task timed out"` | `failed` |
| `"Task cancelled by user."` | `failed` |
| `"Task polling timed out"` | `failed` |
| 任何以 `"Error:"` 开头 | `failed` |
| 其他 | `in_progress`（默认：不掩盖 contract drift） |

默认 `in_progress` 是防御性设计——如果上游改变了返回格式，宁愿显示为"进行中"也不要把成功标记为失败。

## SubtaskCard 渲染

`components/workspace/messages/subtask-card.tsx` — 每个 subagent 任务渲染为可折叠的 ChainOfThought 面板：

### in_progress 状态

```
┌─ ChainOfThought ──────────────────────────────┐
│ ┌──────────────────────────────────────────┐   │
│ │  🧠 Analyzing repository structure...   │   │  ← Shimmer 动画
│ │  ┌──── ShineBorder (彩虹渐变) ──────┐    │   │
│ │  │  Ambilight 光晕效果               │    │   │
│ │  └────────────────────────────────┘    │   │
│ └──────────────────────────────────────────┘   │
│ ┌─ FlipDisplay ────────────────────────────┐   │
│ │  "Running grep search..."  →  flip  →   │   │  ← motion 垂直翻转文本
│ │  "Reading file..."                       │   │
│ └──────────────────────────────────────────┘   │
├─ 展开后 ──────────────────────────────────────┤
│  ● Prompt (streamdown + word animation)       │
│  ● Current tool: bash("grep -r 'pattern' .")  │
└────────────────────────────────────────────────┘
```

视觉效果：
- **Shimmer** — 文本在描述上播放光泽动画
- **ShineBorder** — 旋转的彩虹渐变边框（表示"活跃中"）
- **Ambilight** — 柔和的光晕脉冲
- **FlipDisplay** — 当前 tool call 活动在文本之间做垂直翻转过渡（motion `AnimatePresence`）

### completed 状态

```
┌─ ChainOfThought ──────────────────────────────┐
│  ✓ Analyzing repository structure...          │  ← 静态文本 + 绿色勾
├─ 展开后 ──────────────────────────────────────┤
│  ● Prompt                                     │
│  ● Result (MarkdownContent)                   │
└────────────────────────────────────────────────┘
```

### failed 状态

```
┌─ ChainOfThought ──────────────────────────────┐
│  ✗ Analyzing repository structure...          │  ← 静态文本 + 红色叉
├─ 展开后 ──────────────────────────────────────┤
│  ● Prompt                                     │
│  ● Error (红色文本)                            │
└────────────────────────────────────────────────┘
```

## 探索流程

在 `MessageList` 中，`assistant:subagent` group type 的处理逻辑：

```
1. 扫描 AI messages → 找到有 tool_calls 且 name === "task" 的消息
2. 为每个 task tool_call 注册 subtask:
   updateSubtask({
     id: tool_call.id,
     subagent_type: tool_call.args.subagent_type,
     description: tool_call.args.description,
     prompt: tool_call.args.prompt,
     status: "in_progress"
   })
3. 扫描对应的 ToolMessages → parseSubtaskResult() → 更新 status
4. 渲染:
   - 计数行: "Executing N subtasks..." (i18n: subtasks.executing)
   - SubtaskCard × N (每个 task 一个)
   - MessageGroup (如果同一组中有 reasoning)
```

## 与其他状态系统的交互

- **Token 用量：** Subagent 的 token 消耗在流式结束时通过后端 `SubagentTokenCollector` 合并回父消息的 `token_usage_attribution`
- **Artifact：** Subagent 产出的文件通过 tool call 的 `present_files` 注册到 `ArtifactsContext`
- **Todo：** Subagent 完成可以通过 `write_todos` tool 更新共享的 todo 列表

## Subagent 批量执行 UI（同步 #5）

与上面的单次 `task`（实时 TaskTracker）不同，`batch_task` 是**持久化批量**执行：一次提交大量独立 item，进度走 TanStack Query 轮询而非 SSE。源码 `frontend/src/core/subagent-batches/` + `components/workspace/thread-subagent-batches.tsx`。

### 数据模型（`core/subagent-batches/types.ts`）

```typescript
SubagentBatch   // { id, title, subagent_type, status: queued|running|paused|completed|failed|cancelled,
                //   total_items, max_live_items, max_running_items, max_attempts, counts, ... }
SubagentBatchItem // { id, batch_id, item_key, position, status: pending|queued|leased|running|succeeded|failed|cancelled,
                  //   attempt, model_name, result_preview, result_truncated, error, token_usage, ... }
```

`subagentBatchProgress()` 把 completed item 数归一化成有界百分比（`Math.min(100, ...)`）后才交给 UI 原语。

### Hooks（`core/subagent-batches/hooks.ts`）

| Hook | Query Key | 行为 |
|------|-----------|------|
| `useSubagentBatches(threadId)` | `["subagent-batches", threadId]` | 列表（limit 20）；有活跃 batch 时 2s 轮询，否则 15s |
| `useSubagentBatchItems(threadId, batchId)` | `[...batches, batchId, "items"]` | 无限分页（页大小 100）；**只在已加载 ≤1 页时 3s 轮询**，load-more 后停自动 fan-out |
| `useControlSubagentBatch` | mutation | `pause`/`resume`/`cancel` → 失效列表查询 |
| `useRetrySubagentBatchItem` | mutation | 重试单个失败 item → 失效列表 + items 查询 |

### 能力门控与读模式

`/api/features` 分开报告 **SQL repository 可用性** 与 **startup worker 状态**（`subagent_batches` 相关 capability）：

- 有 worker → 在 default 与 Custom Agent 聊天页都显示触发入口；
- 无 worker 但有 durable 历史 → 线程以**只读模式**展示历史 + JSONL 导出，worker 依赖的变更（pause/resume/cancel/retry）禁用；
- 既无 worker 也无历史 → 隐藏触发入口。

面板渲染有界进度 + 增量分页 item 预览；完整结果仅经 JSONL 导出，**不把完整结果集注入 chat state**，也不从 prompt 文本推断 batch mode。

### API（`core/subagent-batches/api.ts`）

`GET /api/threads/{id}/subagent-batches`、`GET .../{batchId}/items`、`POST .../{batchId}/{pause|resume|cancel}`、`POST .../{batchId}/items/{itemId}/retry`。

## 后台任务 UI（MCP 持久化任务，同步 #5）

与 subagent batch 并列的另一个「线程级后台工作」入口：`frontend/src/core/background-tasks/` + `components/workspace/thread-background-tasks.tsx`。它管理当前线程的 durable MCP 任务（`list_background_tasks` / `cancel_background_task` 的 UI 面）：

- **门控**：header 触发入口对新/mock/static-demo 线程隐藏，且仅在 `/api/features` 报告 startup 作用域的 `mcp_tasks` capability 时才显示；capability 不可用（默认关闭 / memory 后端）时列表查询禁用，绝不轮询一个无法服务的端点。
- **轮询**：列出至多 20 条本地任务；任一任务活跃时 3s 轮询，否则 15s；只在用户展开卡片时才拉取有界详情。
- **展开视图**：展示 result/preview、artifact 元数据、input 请求、最近一次 poll/通知投递/取消错误，**不暴露持久化的远程 handle**。已请求取消的任务在 status 仍活跃时保持 "Cancelling…"；远程取消持续失败时卡片仍可展开并显示尝试次数 + 最近有界错误。
- **通知投递失败**：暴露有界错误与尝试次数；可重试的失败走后端 backoff，永久拒绝或耗尽 5 次预算则显示为 stopped（而非暗示继续重试）。
