---
title: "SSE → React 流式管线"
description: "DeerFlow 的流式渲染建立在 LangGraph SDK 的 `useStream` hook 之上，在它上面叠加了消息合并、乐观更新、token 计数、subtask 追踪和历史加载。"
topics: [frontend, nextjs, react]
---

# SSE → React 流式管线

DeerFlow 的流式渲染建立在 LangGraph SDK 的 `useStream` hook 之上，在它上面叠加了消息合并、乐观更新、token 计数、subtask 追踪和历史加载。

## API Client 层

`getAPIClient()` 返回一个 LangGraph SDK `Client` 单例：

- **URL 解析：** `NEXT_PUBLIC_LANGGRAPH_BASE_URL` 或 `{origin}/api/langgraph`
- **CSRF 注入：** 所有变更请求自动从 cookie 读取 `csrf_token` 注入 `X-CSRF-Token` header
- **Stream mode 白名单：** 只允许 `values, messages, messages-tuple, updates, events, debug, tasks, checkpoints, custom`
- **静态 Demo 模式：** 所有 SDK 方法替换为 stub，返回本地 demo 数据

## useThreadStream — 核心 Hook

`core/threads/hooks.ts:175` — 在 `useStream<AgentThreadState>` 上叠加的业务逻辑：

### 生命周期回调

| 回调 | 时机 | 行为 |
|------|------|------|
| `onCreated` | 新 run 被创建 | 调用 `onStart(thread_id, run_id)`，更新 thread metadata |
| `onLangChainEvent` | LangChain 事件 | 监听 `on_tool_end` → 触发 artifact 预览 |
| `onUpdateEvent` | State 更新 | SummarizationMiddleware 处理（移动 summarized 消息到 history）；同步 title 到 TanStack Query cache |
| `onCustomEvent` | 自定义事件 | `task_running` → 更新 subtask context；`llm_retry` → toast 提示 |
| `onError` | 流错误 | 清除 optimistic messages，show toast，失效 token usage cache |
| `onFinish` | Run 完成 | 更新 title，失效 thread search + token usage queries；如果 tab 隐藏则发桌面通知 |

### 消息合并策略

```
history messages (REST API 懒加载)  ← prepend (更旧)
stream messages (useStream 实时)    ← 中间
optimistic messages (本地 React state) ← append (最新)
```

去重按 message ID 或 `tool:{tool_call_id}` identity——保留最后出现的。

### 发送消息流程

```
用户提交 → InputBox.handleSubmit
  → sendMessage(threadId, message)
    1. 防止重复提交 (sendInFlightRef)
    2. 生成乐观 human + AI messages → 本地 state
    3. 如果有文件 → uploadFiles() → 更新乐观状态 ("uploading"→"uploaded")
    4. thread.submit({ messages: [{type: "human", content}] }, {
         threadId, streamSubgraphs: true,
         context: { model_name, thinking_enabled, subagent_enabled, ... }
       })
    5. onCreated → onStart(createdThreadId)
    6. 路由 URL 更新: history.replaceState → /workspace/chats/{newId}
```

## 历史加载：useThreadHistory

Runs 通过 TanStack Query 缓存（`["thread", threadId]`）。每个 run 的消息通过 REST API 获取：
- `GET {backend}/api/threads/{threadId}/runs/{runId}/messages`
- `middleware:*` 来源的消息被过滤（不显示内部消息）
- 按最新到最旧加载，prepend 到已有列表
- `appendMessages` 暴露给 summarization middleware——将被总结的消息从 live stream 移到 history

## Token 用量追踪（流式期间）

`pendingUsageMessages` 追踪自 send 时的基线快照之后到达的新消息：

```
1. sendMessage() → 快照当前 messages IDs → baselineRef
2. 新消息到达 → 过滤 ID 在 baselineRef 之后的消息
3. TokenUsageIndicator 组件 → sum pendingUsageMessages 的 token 值
4. onFinish → 失效 token usage query → TanStack Query 重新从 API 获取最终值
```

后端在每个 AIMessage 的 `additional_kwargs.token_usage_attribution` 中携带详细的 token 归属信息。

## streamdown 渲染管线

`core/streamdown/plugins.ts` 定义了 4 套 remark/rehype 插件组合：

| 预设 | remark | rehype | 用途 |
|------|--------|--------|------|
| `streamdownPlugins` | remark-gfm, remark-math | rehype-raw, rehype-katex | 常规 AI 消息 |
| `streamdownPluginsWithWordAnimation` | remark-gfm, remark-math | rehype-katex, rehypeSplitWordsIntoSpans | 流式动画（subtask 提示） |
| `reasoningPlugins` | remark-gfm, remark-math | rehype-katex | 思考内容（无 rehype-raw：防止 LLM 幻觉 HTML 标签如 `<simd>` 被渲染） |
| `humanMessagePlugins` | remark-math | rehype-katex | 用户消息（无 GFM autolink：防止 URL 渗入相邻文本） |

### 词级动画

`core/rehype/index.ts` — `rehypeSplitWordsIntoSpans`：自定义 rehype 插件，将文本拆分为单独的 `<span class="animate-fade-in">` 词级元素。CJK 文本使用 `Intl.Segmenter("zh", { granularity: "word" })`，非 CJK 按单词边界分割。仅在活跃流式期间启用。

### 思考内容提取

`extractReasoningContentFromMessage()` 从三个来源提取：
1. `additional_kwargs.reasoning_content`（Anthropic 格式）
2. `content[0].thinking`（Anthropic 网关格式）
3. 内联 `<think>...</think>` XML 标签，含流式安全的未闭合标签处理
