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
- **静态 Demo 模式：** 所有 SDK 方法替换为 stub，返回本地 demo 数据；🆕 `core/api/static-response.ts` 统一 stub 响应构造（#5302 支持独立 demo API + 运行时 GitHub stars，`app/github-stars/route.ts` + landing `star-counter.tsx`）

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

`core/streamdown/plugins.ts` 是 remark/rehype 的唯一落点（**没有** `core/rehype/` 目录），导出 3 个可复用预设 + 动画配置：

| 预设 | remark | rehype | 用途 |
|------|--------|--------|------|
| `streamdownPlugins` | remark-gfm (`singleTilde:false`), remark-math (`singleDollarTextMath:true`) | rehype-raw → `rehypeSanitizeStep` → `rehypeClobberFragments` → rehype-katex；streamdown `plugins: { code, mermaid }` | 常规 AI 消息、memory 摘要 |
| `streamdownPluginsWithoutRawHtml` | 同上 | 同上但**去掉 rehype-raw**（原始 HTML 保持惰性文本） | `MarkdownContent` / `SubtaskCard` 默认链 |
| `reasoningPlugins` | 同上 | 与 `streamdownPluginsWithoutRawHtml` 是同一个对象 | 思考内容（无 rehype-raw：防止 LLM 幻觉 HTML 标签如 `<simd>` 被渲染） |

关键约束：一旦传入 `rehypePlugins`，streamdown@2.5 会**整链替换**掉自带的 `[rehype-raw, rehype-sanitize, rehype-harden]`，所以每条自定义链都必须在 `rehypeRaw` 之后、`rehype-katex` 之前重新插入 `rehypeSanitizeStep`（基于 sanitize `defaultSchema` 放宽 `tel:`、math className、`metastring`）。artifact 预览链（`markdown-preview-plugins.ts`）另加 `rehypeScopedSlug`，并靠 `rehypeClobberFragments` 修正 sanitize `user-content-` 前缀带来的脚注/片段链接问题。

### 词级动画

源码中**不存在**自定义拆词 rehype 插件（`core/rehype/`、`rehypeSplitWordsIntoSpans` 均已在 #4266 `bb008812` 移除）。词级渐显改由 streamdown 自身的 `animated` 能力完成：

- `streamdownWordAnimation` = `{ animation: "fadeIn", duration: 200, sep: "word" }`（subtask card 用）
- `streamdownSmoothStreamingAnimation` = 上一项 + `stagger: 0`（`MarkdownContent` 用，让每个新词与周围 marker 同时开始渐显，避免大 chunk 下后续文字延迟数秒）
- `rehypeStreamingListItems` 仅在流式渲染时挂载：隐藏尾部空 `<li>`，给其余列表项打 `data-streaming-list-item`，让原生 marker 与文字同步

CSS 侧对应 `globals.css` 的 `--animate-fade-in: fade-in 1.1s`。

### 思考内容提取

`extractReasoningContentFromMessage()` 从三个来源提取：
1. `additional_kwargs.reasoning_content`（Anthropic 格式）
2. `content[0].thinking`（Anthropic 网关格式）
3. 内联 `<think>...</think>` XML 标签，含流式安全的未闭合标签处理

## 🆕 流前预处理：Input Polish

在消息进入 agent loop 之前，composer 提供可选的 LLM 润色：

`POST /api/input-polish` → 一次性 LLM 调用（不创建 LangGraph run、不持久化消息）

- **独立 LLM 路径**：使用 `deerflow.utils.oneshot_llm.run_oneshot_llm`（与 suggestions route 共享），model build + Langfuse metadata + invoke 统一在一处
- **不修改 thread state**：润色结果只在 composer 中展示，用户可以选择发送原文或润色后的版本
- **安全**：验证 stripped view of draft（发送给模型的版本与展示的版本一致），保留字面 `<think>` 子串

## 🆕 同步 #6：合并排序与流状态重构

`core/threads/hooks.ts` 本轮大改（净 +1225 行），核心逻辑拆成两个纯模块：

### 消息排序：`core/threads/message-order.ts`

合并后的展示顺序不再依赖简单的"history prepend / stream middle / optimistic append"，而是一个纯函数排序模块（无 React、无缓存、无线程态）：

- **身份归一化**：`messageIdentity()` 按 message ID 或 `tool:{tool_call_id}` 识别同一条消息的多个副本
- **可信位置**：后端在 history 行和已持久化的 `values` 帧消息上盖 `deerflow_seq`（`MESSAGE_SEQ_KEY`，镜像后端 `deerflow/runtime/events/message_identity.py::MESSAGE_SEQ_KEY`）。只有正的安全整数才算数；缺失/非法值绝不覆盖已知位置；同一身份的多个可信值收敛到最早 feed 位置（对齐后端 `get_message_seqs` 的 earliest-seq-wins）
- **骨架编织**：以所有带可信 seq 的身份为骨架排序，无 seq 的分段围绕共享身份锚点按原内部顺序编织（分段落在下一个锚点之前）
- **防覆盖规则**：可见内容上 live 副本刷新 history 副本，但隐藏的 checkpoint 控制消息永远不覆盖可见的 user turn；`deerflow_seq` 是 server 拥有的展示元数据，客户端绝不写回 checkpoint
- 相关修复：#5293（content merge 时保住可信位置）、#4834（中断的 uniform run 保序）、#4696（分页与上下文压缩重叠时早期 user 消息消失/跳动）

### 流状态 patch：`core/threads/stream-state.ts`

`values` 帧的合并抽成独立模块：`hasRenderedThreadStateUpdate()` 只认 `title / artifacts / todos / goal` 四个渲染键的 patch，`mergeArtifacts()` 做列表合并；`GoalState`（objective + status + 时间戳，`active` 才有效）是新的一等渲染状态。

### Composer 恢复

#5428：流重连（stream reconnect）后恢复用户输入——`onError` 清理乐观消息时不再丢掉正在编辑的 composer 草稿。

## 🆕 同步 #6：Conversation References（composer 引用会话）

#5465：composer 新增「引用会话」能力，把其他会话作为下一轮消息的参考材料：

- `components/workspace/conversation-references/`：`reference-conversations-button`（入口）+ `conversation-reference-picker`（选择器）+ `conversation-reference-chip`（composer 上的已选 chip）
- 选择的 thread ID 以 `conversationReferences?: string[]` 作为 run context 发送（`input-box.tsx`），由 Gateway 在 admission 时消费并授予读取权限
- `core/conversation-references/metadata.ts` 在可见 human 消息上写 display-only metadata（`CONVERSATION_REFERENCES_KWARG = "conversation_references"`），**它不授予权限**——读取权只来自 run request context，且 Gateway 不把它持久化进聊天历史

## 🆕 同步 #6：虚拟消息列表与大纲

- `messages/virtual-message-list.tsx` 本轮扩展约 +200 行，为大纲导航提供可滚动锚点；配合 `message-list.tsx` 的 IntersectionObserver 历史加载
- 长对话时 `ConversationOutline`（见 02-message-rendering.md）按章节跳转，#5025 还包含"跳转前先解除 bottom lock"（escape bottom lock）的修正
