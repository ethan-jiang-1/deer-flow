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
