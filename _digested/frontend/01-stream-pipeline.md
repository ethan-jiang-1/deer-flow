---



title: "SSE → React 流式管线"
description: 'DeerFlow 的流式渲染建立在 LangGraph SDK 的 `useStream` hook 之上，在它上面叠加了消息合并、乐观更新、token 计数、subtask 追踪和历史加载。'
topics: [frontend, nextjs, react]
verified_against: v2.2.0
last_verified: 2026-11-08
---

# SSE → React 流式管线

DeerFlow 的流式渲染建立在 LangGraph SDK 的 `useStream` hook 之上，在它上面叠加了消息合并、乐观更新、token 计数、subtask 追踪和历史加载。

## API Client 层

`core/api/api-client.ts` 的 `getAPIClient(isMock?)` 按 `"mock"` / `"default"` 两个 key 缓存在模块级 `Map` 里（每进程各一份，不随用户切换重建）：

- **URL 解析：** `getLangGraphBaseURL(isMock)`——`NEXT_PUBLIC_LANGGRAPH_BASE_URL` 或 `{origin}/api/langgraph`
- **CSRF 注入：** SDK 的 `onRequest: injectCsrfHeader` 在每个出站请求前从 cookie 读 `csrf_token` 注入 `X-CSRF-Token`；`readCsrfCookie` / `isStateChangingMethod` 与直连 REST 的 `fetcher.ts` 共用，避免两套契约漂移（每次读 cookie 而不是构造时写死 header，登入/登出/改密的轮转自动生效）
- **Stream mode 白名单：** `core/api/stream-mode.ts` 的 `SUPPORTED_RUN_STREAM_MODES` = `values, messages-tuple, updates, debug, tasks, checkpoints, custom`（**没有** `messages`、`events`）。`sanitizeRunStreamOptions()` 丢弃不支持的 `streamResumable`、遇到不支持的模式直接抛错并 `console.warn`（每种模式只警告一次）
- **聊天强制增量流：** `forceChatRunStreamOptions()` 把 `streamMode` 收敛为 `CHAT_RUN_STREAM_MODES = ["messages-tuple", "updates", "custom"]` ∪ 调用方显式请求的模式，且**删掉 `values`**——否则 SDK 的惰性 message tracking 会顺带请求 `values`，每个 graph step 后重传整份 thread state（含全部历史消息）
- **创建 run 不重试：** `runCreationClient` 的 `maxRetries: 0`（非幂等，重试可能重复建 run）；恢复用的 GET 走 `StreamRecoveryClient` 保留 SDK 的重试/退避
- **静态 Demo 模式：** `isStaticWebsiteOnly()` 时改用 `createStaticClient()`，所有 SDK 方法替换为 stub，返回本地 demo 数据（`core/threads/static-demo.ts`）；`core/api/static-response.ts` 统一 stub 响应构造（#5302 支持独立 demo API + 运行时 GitHub stars，`app/github-stars/route.ts` + landing `star-counter.tsx`）

### 🆕 2.2.0：流重连与 replay gap 恢复

2.1.0 的重连是"重连一次，失败就报错"；2.2.0 在 `api-client.ts` 里包了一层带预算的恢复循环：

| 机制 | 源码 | 语义 |
|------|------|------|
| 终止态短路 | `TERMINAL_RUN_STATUSES = {success, error, timeout, interrupted}`（`joinStream` 包装） | 重连前先 `runs.get()`；已完成 run 直接返回，不去 join 已被回收（秒级 `publish_end` 后 ~60s reap）的 stream bridge——否则会永远阻塞在 drained condition variable 上，把 `isLoading` 钉成 true、首条消息被路由成 stop |
| 恢复预算 | `MAX_STREAM_GAP_RECOVERIES = 5` | 原始 stream 不计入，耗完 5 次恢复最多消耗 6 条流；超限抛 `StreamReplayGapError` |
| gap 帧 | `StreamReplayGapData`，`code: "stream_replay_gap"` | 服务端 `event: "gap"` 载荷含 `run_id` / `requested_event_id` / `earliest_available_event_id` / `latest_available_event_id` / `recovery: "reload_durable_state"`；run_id 必须等于当前活跃 run，否则报错 |
| 恢复动作 | `recoverStreamReplayGaps()` | 先向 hook 发 `custom` 帧 `{type:"stream_replay_gap"}` → `threads.getState()` 重拉 durable values → 用 `submittedInput`/`kwargs.input` 合成一份 snapshot 再 `joinStream(lastEventId = latest_available_event_id)`（缓冲为空则无游标重连） |
| 乐观 human 保底 | `loadReconnectInputSnapshot()` | 增量 chat 流不含 `values`，刷新后可能先收到 AI/tool chunk 而 human 消息还没进 durable feed；用 run 输入补一条合成 snapshot，按 message id 去重后合并进 durable values |
| 重连指针 | `rememberReconnectRun` / `clearReconnectRun` | `sessionStorage["lg:stream:{threadId}"] = runId`，只有当指针仍指向该 run 时才清除，避免误删新 run 的指针 |
| 停不存在的 run | `isRunNotCancellableError`（409 `"is not cancellable"`） | 终止态 cancel 视为 no-op 吞掉；另一分支 `"not active on this worker and cannot be cancelled"` 故意不吞——那是活 run 的真实取消失败 |
| 不可流存的 run | `isInactiveRunStreamError`（409 `"not active on this worker"` + `"cannot be streamed"`） | store-only run 无 bridge，重连即静默结束而不是抛错 |

## useThreadStream — 核心 Hook

`core/threads/hooks.ts:1956` 的 `useThreadStream({ threadId, displayThreadId, assistantId = "lead_agent", context, isMock, onSend, onStart, onFinish })` — 在 `useStream<AgentThreadState>` 上叠加的业务逻辑。`threadId` 与 `displayThreadId` 分离：新会话页 `threadId` 还是 undefined 而 `displayThreadId` 已经是 URL 上的新 id，`currentViewThreadId = displayThreadId ?? threadId` 决定乐观消息归属哪个视图。

`useStream` 选项里三处非默认值：`reconnectOnMount: true`、`fetchStateHistory: { limit: 1 }`、`throttle: true`（只取布尔档——同 tick 内合并成一次 React 通知；SDK 的**数值档是 trailing debounce**，chunk 持续快于窗口时会把 UI 饿死）。

### 生命周期回调

| 回调 | 时机 | 行为 |
|------|------|------|
| `onCreated` | 新 run 被创建 | `handleStreamStart(thread_id, run_id)` → `onStart`；同时往 thread search 缓存和 infinite 列表缓存各 upsert 一条 `status: "busy"` 的占位 thread；带 `context.agent_name` 时再 `threads.update({metadata:{agent_name}})` |
| `onLangChainEvent` | LangChain 事件 | 监听 `on_tool_end` → 触发 artifact 预览 |
| `onUpdateEvent` | State 更新 | 先过 `hasRenderedThreadStateUpdate()` + `reduceThreadStateUpdates()` 做渲染态 patch（见 stream-state.ts）；SummarizationMiddleware 的 `messages` 补丁 ≥2 条时算 transient history（旧的 `HumanMessage(name="summary")` 只按 id 记入 `summarizedRef`）；收集 `title` 并写进 thread 缓存 |
| `onCustomEvent` | 自定义事件 | 🆕 `stream_replay_gap` → 清空乐观消息/transient bridge/usage 基线/subtask、失效停止线程缓存并 `toast.warning`；`task_*` → `taskEventToSubtaskUpdate`，`task_running` **追加** step 而不是覆盖（#3779）；`llm_retry` → toast |
| `onError` | 流错误 | `scheduleActiveRunRejoinRetry(run)` → 清乐观消息、重置 usage 基线、toast，失效 `threadHistoryQueryKey` + `threadTokenUsageQueryKey` |
| `onFinish` | Run 完成 | 记 completed run、settle rejoin、回调 `onFinish`、重置 usage 基线、`invalidateStoppedThreadCaches()` |

### 🆕 2.2.0：新标签页/新浏览器接手活跃 run

SDK 的 `reconnectOnMount` 只认本 tab `sessionStorage` 里的 run 指针。2.2.0 在 `useThreadStream` 里补了服务端侧恢复：

- `activeRunId` 来自 thread 查询，`ACTIVE_RUN_STATUSES = {pending, running}` 才算活跃
- 没有指针时自己 `joinStream(runId)`；`ACTIVE_RUN_REJOIN_RETRY_DELAYS_MS = [1000, 2000]`，`MAX_ACTIVE_RUN_REJOIN_ATTEMPTS = 3`
- 若指针已指向该 run，说明 SDK 原生重连已经拥有这条流，**不**创建第二个 SSE 消费者；SDK 重连失败时 `scheduleActiveRunRejoinRetry()` 释放指针并让恢复循环接手
- 线程切换/卸载时清理定时器并 `clearReconnectRun()`

### 消息合并策略

```
history messages (REST 分页懒加载)  ← prepend (更旧)
transient history (压缩中间态桥接)  ← 中间
stream messages (useStream 实时)    ← 中间
optimistic messages (本地 React state) ← append (最新)
```

去重按 `messageIdentity()`——message ID 或 `tool:{tool_call_id}`；human 消息带 `__user` 后缀的 id 归一成 `message:{id}`。同一身份保留最后出现的那份。乐观 human 用客户端生成的 `local-human-{uuid}` 作为 id，`localTurnAnchorRef` 记住它，渲染快照到达时按这个精确身份确认，而不是靠"基线之后的人类消息"猜测（否则 checkpoint 被压缩裁剪后会把更早的纯历史 human 提升成这轮的锚点）。

### 发送消息流程

```
用户提交 → InputBox.handleSubmit
  → sendMessage(threadId, message, extraContext?, options?)
    1. 防重入 sendInFlightRef；记录 usage 基线（persistedMessages 的身份集合）
    2. 生成乐观 human（id = local-human-{uuid}，hide_from_ui 时不生成）+ 上传中占位 AI
    3. 有文件 → uploadFiles() → 乐观 human 的 additional_kwargs.files 从 "uploading" 改成 "uploaded" + path
    4. options.onSent()（附件上传成功才算真正派出）
    5. thread.submit({ messages: buildThreadSubmitMessages(...) }, {
         threadId,
         streamResumable: true,
         config: { recursion_limit: 1000 },
         context: buildRunContext({...})
       })
    6. onCreated → onStart；失效 ["threads","search"] 与 INFINITE_THREADS_QUERY_KEY_PREFIX
```

- **不发 `streamSubgraphs`**：subtask 进度走 root namespace 的 custom 事件；开 subgraph 帧会把被委派 subagent 的 values/messages 漏进主线程视图（#4399）
- **`buildRunContext()`（`hooks.ts:267`）** 是 run context 的唯一装配点：`mode` → `thinking_enabled`（`mode !== "flash"`）、`is_plan_mode`（pro/ultra）、`subagent_enabled`（ultra）、`reasoning_effort`（显式设置优先，否则 ultra→high / pro→medium / thinking→low）；再加 `thread_id`、`locale`、`client_timezone`（浏览器 IANA 时区，只用于聊天创建定时任务时的默认时区，不进模型上下文）与 `conversation_references`（settings 里的同名 key 会被剔除，只认参数传入的）

## 历史加载：useThreadHistory（`hooks.ts:3295`）

历史消息走 Gateway 自己的分页接口，而不是 SDK 的 `runs/{runId}/messages`：

- **无限查询**：`threadHistoryQueryKey = ["thread-messages", threadId]`（`hooks.ts:654`）+ `getThreadHistoryNextPageParam`（`hooks.ts:635`）读 `next_before_seq`；`buildThreadMessagesPageUrl`（`hooks.ts:653`）构造 `GET /api/threads/{threadId}/messages/page?before_seq=&limit=`
- **响应形状**：`{ data, has_more, next_before_seq }`；`flattenThreadHistoryPages`（`hooks.ts:672`）压平，`reconcileThreadHistoryRows`（`hooks.ts:727`）把新页与已有行按身份对齐（重复/乱序/seq 缺口都在这层收敛）
- **待失效的 superseded run**：`useThreadHistory({ enabled, pendingSupersededRunIds })`，被新 run 顶掉的 run 的乐观/流副本在这里被替换掉
- **导出**：`fetchThreadExportMessages()` 用 limit 200 翻页拉全量，导出路径另外用 `stripInternalMarkers()` 清掉后端注入标记（见 02-message-rendering.md）
- **isHiddenFromUIMessage()**（`core/messages/utils.ts:1128`）过滤不显示的消息：`additional_kwargs.hide_from_ui === true`、`HIDDEN_CONTROL_MESSAGE_NAMES`（`summary / loop_warning / todo_reminder / todo_completion_reminder`）、以及"只有 `<slash_skill_activation>` 标记、去掉上传标签后内容为空"的 human 消息
- `appendMessages` 暴露给 summarization middleware——将被总结的消息从 live stream 移到 history
- 🆕 2.2.0 的乐观/流/历史合并顺序由 `core/threads/message-order.ts` 统一裁决（见「同步 #6」），不再靠"prepend / middle / append"三段拼接

## Token 用量追踪（流式期间）

`pendingUsageBaselineMessageIdsRef` 追踪自 send 时的基线快照之后到达的新消息：

```
1. sendMessage() → 基线 = persistedMessages 的身份集合（messageIdentity）
2. 新消息到达 → pendingUsageMessages 只取基线之后到达的消息
3. TokenUsageIndicator（chat-page.tsx:631）→ sum pendingUsageMessages 的 token 值
4. onFinish / onError → 重置基线 + 失效 ["thread-token-usage", threadId] → TanStack Query 重新从 API 获取最终值
```

后端在每个 AIMessage 的 `additional_kwargs.token_usage_attribution` 中携带详细的 token 归属信息；thread 级汇总在 `ThreadTokenUsageResponse`（`total_tokens / total_input_tokens / total_output_tokens` + `ThreadContextUsage {token_count, max_context_tokens, percentage}`）。🆕 2.2.0 的 `ContextUsageBadge`（`context-usage-badge.tsx`，chat 头部）用 `selectContextUsage()` 读 `context_usage`，无数据时渲染带 `data-context-usage-placeholder` 的骨架占位而不是直接消失。

## streamdown 渲染管线

`core/streamdown/plugins.ts` 是 remark/rehype 的唯一落点（**没有** `core/rehype/` 目录），导出 3 个可复用预设 + 2 个渲染插件集 + 动画配置：

| 预设 | remark | rehype | 用途 |
|------|--------|--------|------|
| `streamdownPlugins`（:190） | remark-gfm (`singleTilde:false`), remark-math (`singleDollarTextMath:true`) | rehype-raw → `rehypeSanitizeStep` → `rehypeClobberFragments` → rehype-katex；`plugins: streamdownRenderingPlugins` | 常规 AI 消息、memory 摘要 |
| `streamdownPluginsWithoutRawHtml`（:259） | 同上 | 同上但**去掉 rehype-raw**（原始 HTML 保持惰性文本） | `MarkdownContent` / `SubtaskCard` 默认链 |
| `reasoningPlugins`（:269） | 同上 | 与 `streamdownPluginsWithoutRawHtml` 是同一个对象 | 思考内容（无 rehype-raw：防止 LLM 幻觉 HTML 标签如 `<simd>` 被渲染） |

关键约束：一旦传入 `rehypePlugins`，streamdown@2.5 会**整链替换**掉自带的 `[rehype-raw, rehype-sanitize, rehype-harden]`，所以每条自定义链都必须在 `rehypeRaw` 之后、`rehype-katex` 之前重新插入 `rehypeSanitizeStep`（基于 sanitize `defaultSchema` 放宽 `tel:`、math className、`metastring`）。artifact 预览链（`markdown-preview-plugins.ts`）另加 `rehypeScopedSlug`，并靠 `rehypeClobberFragments` 修正 sanitize `user-content-` 前缀带来的脚注/片段链接问题。

`streamdownRenderingPlugins = { code, mermaid }`（`:185`）是 streamdown 的 `plugins` 字段——代码高亮与 mermaid 渲染器从 rehype 链里单列出来；`toStreamdownComponents` / `SafeStreamdown` / `SafeMessageResponse` / `SafeReasoningContent`（`core/streamdown/components.tsx`）全部默认沿用它。

### 🆕 2.2.0：闭合 fence 的判定（`core/streamdown/fences.ts`）

`isClosingFence()` 从 mermaid 模块提到独立文件，规则收紧为「**带 info string 的 fence 行不算闭合**」，mermaid 与 `stripLeakedSystemTags()` 共用同一判定：

- 外层围栏里贴一段三反引号 + `python` 的代码块（讲 markdown 的常见情形）时，那一行不会被当成"关闭当前围栏"，外层围栏继续、内容仍是代码而不是交给 rehype 链渲染
- 旧判定在这里会提前闭合，属于渲染正确性问题（CHANGELOG 前端条目见 #8011 附近）
- 未闭合围栏一律视为"后面全是代码"，与 `core/messages/utils.ts::protectedCodeRanges()` 的导出侧保护同语义

### 词级动画

源码中**不存在**自定义拆词 rehype 插件（`core/rehype/`、`rehypeSplitWordsIntoSpans` 均已在 #4266 `bb008812` 移除）。词级渐显改由 streamdown 自身的 `animated` 能力完成：

- `streamdownWordAnimation`（`:205`）= `{ animation: "fadeIn", duration: 200, sep: "word" }`（subtask card 用）
- `streamdownSmoothStreamingAnimation`（`:211`）= 上一项 + `stagger: 0`（`MarkdownContent` 用，让每个新词与周围 marker 同时开始渐显，避免大 chunk 下后续文字延迟数秒）
- `rehypeStreamingListItems`（`:228`）仅在流式渲染时挂载：隐藏尾部空 `<li>`，给其余列表项打 `data-streaming-list-item`，让原生 marker 与文字同步

CSS 侧对应 `globals.css` 的 `--animate-fade-in: fade-in 1.1s`。

### 思考内容提取

`extractReasoningContentFromMessage()`（`core/messages/utils.ts:978`）从三个来源提取：
1. `additional_kwargs.reasoning_content`（Anthropic 格式）
2. `content[0].thinking`（Anthropic 网关格式）
3. 内联 `<think>...</think>` XML 标签，含流式安全的未闭合标签处理

第 3 条走 `splitInlineReasoningFromAIMessage()`——结果按 message 对象缓存在 `WeakMap`、以**内容字符串**为校验键（content 被重写就重算）：`hasContent` / `hasReasoning` / `extractContentFromMessage` / `extractReasoningContentFromMessage` 每收到一个 stream chunk 都会扫一遍全量消息列表，不缓存就是 O(总内容)²。渲染侧由 `MessageReasoning`（`messages/message-reasoning.tsx`）消费：流式期间展开，**只在真正流过式之后**才在结束 1 秒后自动折叠——历史消息挂载时 `isLoading` 恒为 false，不会自动收起。

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

`values` 帧的合并抽成独立模块（`core/threads/stream-state.ts`）：

- `RENDERED_THREAD_STATE_KEYS = ["title", "artifacts", "tool_artifacts", "todos", "goal"]`——**五个**渲染键，只有这些字段的 patch 才触发渲染态更新；`hasRenderedThreadStateUpdate()` 判定，`reduceThreadStateUpdates()` 施加
- `mergeArtifacts()` 按路径合并 artifacts 列表；`mergeToolArtifacts()` 以 tool 调用为 handle 合并流式工具产物，支持 `op: "trim_to"` 截断（默认保留上限 1000 条，防止长跑 run 把内存吃穿）
- `GoalState`（objective + status + 时间戳，`isGoalState()` 要求 `status === "active"`）是一等渲染状态：`goal` 为 active、或本轮留下 `goal_outcome`（`ThreadGoalOutcome`，如"目标已达成"）时，composer 上方的 **goal 状态条**（`components/workspace/goal-status.tsx`）出现，显示目标与"为什么停下"——`GoalStopKey` 区分 `limit / autoOff / noProgress / tokenCapped / loopCapped / recursionCapped / missingEvidence / runFailed / needsInputCard / needsInputReply / external / unchecked`；需要用户补充信息时用"需要你补充信息"的 primary 色芯片。两者都没有时整条不渲染

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
