---
title: "Middleware 就是 Loop 的结构"
description: "在 [[00-loop-anatomy]] 里我们说了 loop 本身不自写。那么 DeerFlow 的代码到底"写"了什么？**写了 loop 每一圈的每一个钩子。** middleware 系统就是 DeerFlow agent loo"
topics: [agent-loop, langgraph, execution-model]
---

# Middleware 就是 Loop 的结构

在 [[00-loop-anatomy]] 里我们说了 loop 本身不自写。那么 DeerFlow 的代码到底"写"了什么？**写了 loop 每一圈的每一个钩子。** middleware 系统就是 DeerFlow agent loop 的全部原创代码。

## 为什么 middleware 不是"装饰"而是"结构"

传统 web middleware 是一个 afterthought——先有 request handler，再加 middleware 做 auth/logging/cors。agent middleware 反过来：**先有 middleware 链，链的最内层才是 model 调用**。

```
Web framework 思维（flask/django）:
  request → [auth] → [cors] → [logging] → handler → response
  中间件是"请求前后做点什么"

Agent middleware 思维（deerflow）:
  m1.wrap(m2.wrap(m3.wrap(LLM.call)))
  中间件**就是**调用链本身，LLM call 是链的最内层
```

这个区别解释了为什么 agent middleware 的 hook 点比 web middleware 多得多——因为它不仅要在"前后"做事情，还要**在模型调用内部**做事情。

## 6 种 hook 点 = loop 的 6 个截入位置

```
一个 agent run 的完整生命周期:

  ┌──────────────────────────────────────────────────────────┐
  │  before_agent                                            │
  │  ┌────────────────────────────────────────────────────┐  │
  │  │ 每次 step (以 model 输出无 tool_calls 为结束):      │  │
  │  │                                                     │  │
  │  │  before_model → wrap_model_call → after_model      │  │
  │  │       │                                     │       │  │
  │  │       │  如果有 tool_calls:                  │       │  │
  │  │       │    wrap_tool_call × N                │       │  │
  │  │       │    → 回到 before_model               │       │  │
  │  │       │                                     │       │  │
  │  │       │  如果没有 tool_calls:                │       │  │
  │  │       │    → loop 结束                       │       │  │
  │  └────────────────────────────────────────────────────┘  │
  │  after_agent                                             │
  └──────────────────────────────────────────────────────────┘
```

6 种 hook 点各自做什么？

| Hook | 时机 | 能做什么 | 实际使用案例 |
|------|------|---------|------------|
| `before_agent` | run 开始前 | 初始化 per-run 状态 | LoopDetection 清理上一轮 run 的待注入警告 |
| `before_model` | 每圈 LLM 调用前 | 修改 message list | DynamicContext 注入日期和 memory |
| `wrap_model_call` | LLM 调用的**外层包装** | 修改 request/response，甚至跳过 LLM | Summarization 删除旧消息；LoopDetection 注入 loop 警告 |
| `after_model` | 每圈 LLM 调用后 | 检查 tool_calls，决定是否干预 | LoopDetection 检测重复调用；SubagentLimit 截断超限 task |
| `wrap_tool_call` | 每个 tool 执行**的外层包装** | 修改 tool 输入/输出，甚至跳过执行 | Clarification 拦截 ask_clarification → goto=END；ToolError 转换异常 |
| `after_agent` | run 结束后 | 清理 per-run 状态 | LoopDetection 清空未发出的警告 |

### 为什么 wrap_ 和 before_/after_ 都存在

一个问题：`before_model` 和 `wrap_model_call` 都可以在 LLM 调用前做事情。为什么需要两个？

**before_model 适合"往 state 加东西"，wrap_model_call 适合"控制调用本身"。**

举个例子：如果你想在 LLM 调用前给 message list 加一条 system reminder，你可以用 `before_model` 直接改 state。但如果你想在 LLM 调用**失败**时重试、或者在 context 太长时**裁剪消息**——这些需要控制"要不要调 LLM"和"用哪些消息调"——只能用 `wrap_model_call`，因为它在洋葱的最外层，可以决定调不调 handler。

## 装配逻辑：为什么分散在两处

18 个 middleware 不是在同一个函数里一次性组装的。它们分两段：

```
build_lead_runtime_middlewares(app_config)  ← 基础设施层（不可跳过）
    ├─ ThreadDataMiddleware     # per-thread 目录
    ├─ UploadsMiddleware        # 上传文件追踪
    ├─ SandboxMiddleware        # 沙箱 acquire
    ├─ DanglingToolCallMiddleware
    ├─ LLMErrorHandlingMiddleware
    ├─ GuardrailMiddleware
    ├─ SandboxAuditMiddleware
    └─ ToolErrorHandlingMiddleware

    ↓ append ↓

_build_middlewares(config)  ← 用户功能层（可选/可配置）
    ├─ DynamicContextMiddleware     # 日期 + memory 注入
    ├─ SummarizationMiddleware      # (if enabled)
    ├─ TodoMiddleware               # (if plan_mode)
    ├─ TokenUsageMiddleware          # (if enabled)
    ├─ TitleMiddleware
    ├─ MemoryMiddleware
    ├─ ViewImageMiddleware           # (if model supports vision)
    ├─ DeferredToolFilterMiddleware  # (if tool_search enabled)
    ├─ SubagentLimitMiddleware       # (if subagent_enabled)
    ├─ LoopDetectionMiddleware       # (if enabled)
    ├─ [custom_middlewares]          # user injected
    ├─ SafetyFinishReasonMiddleware  # (if enabled)
    └─ ClarificationMiddleware       # always last
```

**为什么分开？** 基础设施层（前 8 个）是一个 subagent 也需要的——subagent 也要有 Sandbox、Error Handling、DanglingToolCall 修复。用户功能层（后面那些）是 lead agent 特有的——subagent 不需要 Title、Memory、TodoList 这些"人机交互"层的东西。

所以 `build_subagent_runtime_middlewares()` 只拿前 6-7 个基础设施 middleware，不附加功能层。这是一个**复用两层分离**的干净设计。

## 装配顺序 = loop 行为的精确编排

顺序极其重要，因为每个 middleware 假定它后面的 middleware 已经完成了某些工作。几个关键约束：

```
SandboxMiddleware 必须在 ThreadDataMiddleware 之后
  → 因为 sandbox 需要 thread_id 来创建 per-thread workspace

UploadsMiddleware 必须在 SandboxMiddleware 之前
  → 因为上传的文件要在 sandbox acquire 前被追踪

DanglingToolCallMiddleware 必须在 LLMErrorHandlingMiddleware 之前
  → 先修好缺失的 ToolMessage，再做错误归一化

ClarificationMiddleware 必须是最后一个
  → 因为 ask_clarification 要 goto=END，后面的 middleware 的 after hook 才对
  → (after 是反向执行，最后一个 middleware 的 after 最先执行)

LoopDetectionMiddleware 的警告注入为什么在 wrap_model_call 而不是 after_model？
  → after_model 时工具还没执行，没有 ToolMessage 配对
  → OpenAI/Moonshot 要求 AIMessage.tool_calls 紧跟 ToolMessage
  → wrap_model_call 时 ToolMessage 已经在了，注入警告在末尾不破坏配对
```

### ClarificationMiddleware 的 "最后一个" 精妙之处

ClarificationMiddleware 做的事很简单：当 model 调用 `ask_clarification` tool 时，**不执行它，直接返回 `Command(goto=END)`**。为什么它必须是最后一个？

因为 middleware chain 的反向执行。`after_model` 是从最后一个 middleware 开始向前执行的：

```
after_model 执行序:
  ClarificationMiddleware.after_model   ← 第 18 个先执行
  SafetyFinishReasonMiddleware.after_model
  ...
  ThreadDataMiddleware.after_model       ← 第 1 个最后执行
```

ClarificationMiddleware 的 `wrap_tool_call` 拦截 tool 执行并 goto=END。如果它不是最后一个，前面注册的 middleware 的 `after_model` 还会继续执行，可能会产生副作用。排在最后，它的 hook 最先触发，后面的 middleware 就不会对 clarification 请求做额外处理。

## Loop Detection 双层安全网：为什么需要第二层

`LoopDetectionMiddleware` 有两层检测：

**Layer 1 — Hash-based**：每次 model 输出 tool_calls 时，对 `name + args` 做 hash。同一个 hash 在滑动窗口里出现 3 次→警告，5 次→强制 strip 所有 tool_calls。

这能抓到"反复读同一个文件同一个范围"的死循环。但抓不到"读 40 个不同文件"的循环——每次都不同 hash。

**Layer 2 — Frequency-based**：不计 args，只计 tool 类型被调用的次数。`read_file` 被调 30 次→警告，50 次→强制停止。

Layer 2 有一个重要扩展点：`tool_freq_overrides`。某些 tool（如 `bash`）在批量 pipeline 场景下可能合法地被调用很多次。可以配置：

```yaml
loop_detection:
  enabled: true
  tool_freq_overrides:
    bash:
      warn: 100
      hard_limit: 150
```

### 更精妙的是：警告注入的时机选择

LoopDetection 的警告不直接 console.log——它要作为一条 human message 注入下一轮 LLM 调用。但注入时机不是 `after_model`，而是**下一圈的 `wrap_model_call`**：

```
为什么不行（在 after_model 注入）:
  1. model 输出 AIMessage(tool_calls=[tool_a])
  2. after_model 检测到重复 → 想注入 "stop looping" 警告
  3. 但如果现在插入 HumanMessage("stop looping")，消息序列变成:
     ... AIMessage(tool_calls=[tool_a]) HumanMessage(...)
  4. tools node 还没执行 tool_a 呢！tool_a 的 ToolMessage 还没产生
  5. OpenAI/Moonshot 校验: "tool_call_ids did not have response messages" → 400

为什么行（在下一圈 wrap_model_call 注入）:
  1. model 输出 AIMessage(tool_calls=[tool_a])
  2. after_model 检测到重复 → queue_pending_warning("stop looping")  ← 只排队
  3. tools node 执行 tool_a
  4. 消息序列: ... AIMessage(tool_calls=[tool_a]) ToolMessage(result=...) ← 配对完整
  5. 下一圈 wrap_model_call 触发 → drain_pending_warnings()
  6. 在消息列表末尾追加 HumanMessage("stop looping") ← 不破坏配对
```

这是一个**为了兼容三个 provider 的 tool-call pairing 校验而做出的设计方案**。它的代价是：警告要到下一圈才生效，如果下一圈 model 直接输出文本（不调 tools），警告可能永远发不出来。但 `after_agent` 里有清理逻辑，不会把警告泄露到下一个 run。

## Middleware 和 run_agent() 的关系

最后要理解一点：`run_agent()` 不是 middleware 的一部分——它是在 middleware 外面的一层：

```
run_agent() 做的事:
  ├─ 快照 checkpoint (rollback 用)
  ├─ 构建 runtime context
  ├─ 注入 __pregel_runtime
  ├─ agent_factory(config) → 触发 middleware 装配
  ├─ agent.astream() → middleware 链开始工作
  ├─ abort 检查
  ├─ journal flush, token persist
  └─ bridge cleanup
```

`run_agent()` 提供一个**受控的运行环境**——checkpoint、abort、journal——middleware 不关心这些。这也是分层：middleware 只关心 agent loop 内部的行为，`run_agent()` 管理"一个 run"作为一个整体的生命周期。

下一步：[[02-extension-points]] 从三个维度讲怎么往外扩——加 tool、加 middleware、加 subagent。
