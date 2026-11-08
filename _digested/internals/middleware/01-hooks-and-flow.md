---
title: "Hook 点与执行流"
description: "Agent 的每一次 step 穿过 6 种 hook 点。理解每种 hook 的触发时机、执行方式、和它适合做什么，是理解整个 middleware 系统的基础。"
topics: [middleware, hooks, interceptor-chain]
---

# Hook 点与执行流

Agent 的每一次 step 穿过 6 种 hook 点。理解每种 hook 的触发时机、执行方式、和它适合做什么，是理解整个 middleware 系统的基础。

> **交叉引用：** Middleware hook 在 Agent loop 中的位置见 [agent-loop/00-loop-anatomy.md](../agent-loop/00-loop-anatomy.md)（三层循环嵌套全景）。

## 6 种 Hook 点

### before_agent

**触发时机：** Agent graph 启动时，在第一个 `before_model` 之前。

**执行方式：** 独立 LangGraph node，按链顺序（0→N）逐个执行。

**返回值：** `dict[str, Any] | None`。返回的 dict 被 LangGraph reducer 合并到 state 中。

**适合做：** 一次性初始化——设置 thread 目录（ThreadDataMiddleware）、处理上传文件（UploadsMiddleware）、获取 sandbox（SandboxMiddleware）、注入系统上下文（DynamicContextMiddleware）。

**不适合做：** 每轮 step 都需要重新计算的事情（应该用 `before_model`）。

```python
# 签名
def before_agent(self, state: State, runtime: Runtime) -> dict | None: ...
async def abefore_agent(self, state: State, runtime: Runtime) -> dict | None: ...
```

### before_model

**触发时机：** 每次 LLM 调用之前（agent loop 的每一轮 step 都会触发）。

**执行方式：** 独立 LangGraph node，按链顺序（0→N）逐个执行。

**返回值：** `dict[str, Any] | None`。典型用法是返回 `{"messages": [HumanMessage(...)]}` 来注入消息。

**适合做：** 注入 vision 内容（ViewImageMiddleware）、触发总结（SummarizationMiddleware）、检测 context loss（TodoMiddleware）。

```python
# 签名
def before_model(self, state: State, runtime: Runtime) -> dict | None: ...
async def abefore_model(self, state: State, runtime: Runtime) -> dict | None: ...
```

### wrap_model_call

**触发时机：** 在 `model_node` **内部**，包裹真正的 LLM 调用。

**执行方式：** 内联洋葱组合——不是 graph node。外层先执行，调 `handler(request)` 进入内层，最内层是 `_execute_model_sync`（真正的 model.invoke）。

**参数：** `ModelRequest` — 包含 `model`, `messages`, `tools`, `system_message`, `tool_choice`, `response_format`, `state`, `runtime`。

**返回值：** `ModelCallResult`（通常是 `AIMessage`）。

**适合做：** 错误重试（LLMErrorHandlingMiddleware）、dangling tool call 修复（DanglingToolCallMiddleware）、延迟警告注入（LoopDetectionMiddleware）、完成提醒注入（TodoMiddleware）。

**关键限制：** 在 model_node 内同步执行。不要在这里做网络请求或耗时操作（除了必要的重试）。

```python
# 签名
def wrap_model_call(self, request: ModelRequest, handler: Callable) -> ModelCallResult: ...
async def awrap_model_call(self, request: ModelRequest, handler: Callable) -> ModelCallResult: ...
```

### after_model

**触发时机：** LLM 调用完成后，在判断是否有 tool_calls 之前。

**执行方式：** 独立 LangGraph node，按**反向**链顺序（N→0）执行。

**返回值：** `dict[str, Any] | None`。可以用来修改 AIMessage（比如清除被 safety filter 污染的 tool_calls）。

**适合做：** 截断过多的 subagent 调用（SubagentLimitMiddleware）、token 统计（TokenUsageMiddleware）、自动标题（TitleMiddleware）、safety 终止检测（SafetyFinishReasonMiddleware）。

**反向执行的含义：** SafetyFinishReasonMiddleware（位置 18，接近链尾）在 `after_model` 中**最先**执行——它必须第一个看到原始 model 输出，在 LoopDetection 和 SubagentLimit 处理 tool_calls 之前清除被 safety filter 污染的 tool_calls。

```python
# 签名
def after_model(self, state: State, runtime: Runtime) -> dict | None: ...
async def aafter_model(self, state: State, runtime: Runtime) -> dict | None: ...
```

### wrap_tool_call

**触发时机：** 在 `ToolNode` **内部**，包裹每个 tool 的实际执行。

**执行方式：** 内联洋葱组合——不是 graph node。外层先执行，调 `handler(request)` 进入内层，最内层是 `ToolNode._execute_tool_sync`（真正执行 tool）。

**参数：** `ToolCallRequest` — 包含 `tool_call`（dict: name, args, id）、`tool`（BaseTool 实例或 None）、`state`、`runtime`。

**返回值：** `ToolMessage | Command`。

**适合做：** 权限检查（GuardrailMiddleware）、命令审计（SandboxAuditMiddleware）、错误兜底（ToolErrorHandlingMiddleware）、中断 agent（ClarificationMiddleware 返回 `Command(goto=END)`）。

**短路机制：** 不调 `handler(request)` 直接返回 ToolMessage → tool 不执行。让 LLM 看到 "这个 tool 不能调" 的错误消息并选择替代方案。

```python
# 签名
def wrap_tool_call(self, request: ToolCallRequest, handler: Callable) -> ToolMessage | Command: ...
async def awrap_tool_call(self, request: ToolCallRequest, handler: Callable) -> ToolMessage | Command: ...
```

### after_agent

**触发时机：** Agent graph 结束时（没有更多 tool_calls 后）。

**执行方式：** 独立 LangGraph node，按**反向**链顺序（N→0）执行。

**返回值：** `dict[str, Any] | None`。

**适合做：** 释放资源（SandboxMiddleware 释放 sandbox）、持久化（MemoryMiddleware 更新 memory）、清理状态（LoopDetectionMiddleware 清理 `_pending_warnings`）。

```python
# 签名
def after_agent(self, state: State, runtime: Runtime) -> dict | None: ...
async def aafter_agent(self, state: State, runtime: Runtime) -> dict | None: ...
```

## 执行顺序：正向 vs 反向

```
START
  │
  ▼
┌─ before_agent ──────────────────────────────────────┐
│  [0] ThreadData → [1] Uploads → [2] Sandbox → ... → [N] DynamicContext    │  正向 0→N
└─────────────────────────────────────────────────────┘
  │
  ▼
┌─ before_model ──────────────────────────────────────┐
│  [0] Summarization → [1] Todo → [2] ViewImage       │  正向 0→N
└─────────────────────────────────────────────────────┘
  │
  ▼
┌─ wrap_model_call (内联洋葱) ─────────────────────────┐
│  outer(inner(...(_execute_model_sync)...))          │  正向 0→N（外层=索引小）
└─────────────────────────────────────────────────────┘
  │
  ▼
┌─ LLM call ──────────────────────────────────────────┐
│  model.invoke(messages, tools=...)                  │
└─────────────────────────────────────────────────────┘
  │
  ▼
┌─ after_model ───────────────────────────────────────┐
│  [N] Safety → [N-1] Loop → ... → [0] TokenUsage     │  反向 N→0
└─────────────────────────────────────────────────────┘
  │
  ├── 有 tool_calls ──────────────────────────────────┐
  │                                                   │
  │  ┌─ wrap_tool_call (内联洋葱) ──────────────────┐  │
  │  │  outer(inner(...tool执行...))              │  │  正向 0→N
  │  └────────────────────────────────────────────┘  │
  │  │                                               │
  │  └── 循环回到 before_model ──────────────────────┘
  │
  └── 无 tool_calls ──────────────────────────────────┐
     │                                                │
     ▼                                                │
  ┌─ after_agent ───────────────────────────────────┐ │
  │  [N] Memory → ... → [0] Sandbox                 │ │  反向 N→0
  └────────────────────────────────────────────────┘ │
     │                                                │
     ▼                                                │
    END                                               │
```

**为什么正向 setup / 反向 teardown？** 这是经典的栈语义。如果一个 middleware 在 `before_agent` 中分配了资源（比如 SandboxMiddleware acquire sandbox），它应该是**最后一个**释放资源的（`after_agent` 最后执行）。这保证了资源在整个 agent 生命周期中可用。

## Graph Node vs Inline 执行

关键区别：

| | Graph Node (`before_*` / `after_*`) | Inline (`wrap_*`) |
|---|---|---|
| **执行位置** | 独立的 LangGraph node | 在 model_node 或 ToolNode 内部 |
| **调度方式** | LangGraph edge 连接 | 直接函数调用（嵌套 callable） |
| **异步** | node 可以是 async | `awrap_*` 变体由 ToolNode 的 async 路径调用 |
| **状态修改** | 返回 dict，被 LangGraph reducer 合并 | 返回替代值（AIMessage / ToolMessage） |
| **短路** | 返回 `Command(goto=...)` 跳转 | 不调 `handler()` 即短路 |
| **执行顺序** | `before_*` 正向 / `after_*` 反向 | 正向（外层=索引小） |

`wrap_*` 之所以设计为内联而非 graph node，是因为它们需要**看到返回值**——graph node 只能往 state 里写 dict，看不到后续节点的输出。只有嵌套 callable 才能实现 "外层看到内层的返回值" 这个模式。

## 状态修改的 3 种机制

### 1. 返回 dict（before_* / after_*）

```python
def after_model(self, state, runtime):
    # 修改最后一个 AIMessage
    last_msg = state["messages"][-1]
    last_msg.tool_calls = []  # 清除 tool_calls
    return {"messages": [last_msg]}  # 同 id → add_messages reducer 替换
```

### 2. request.override() + handler()（wrap_*）

```python
def wrap_tool_call(self, request, handler):
    # 修改 tool 参数
    modified = request.override(tool_call={**request.tool_call, "args": sanitized_args})
    return handler(modified)  # 传递给内层
```

### 3. Command(goto=...)（任意 hook）

```python
def wrap_tool_call(self, request, handler):
    if request.tool_call["name"] == "ask_clarification":
        return Command(update={"messages": [clarification_msg]}, goto="__end__")
    return handler(request)
```

LangGraph 的 `Command(goto=...)` 是 graph 中断的标准方式。`goto="__end__"` 直接跳转到 END 节点，agent 停止执行。

## 错误传播

**没有集中式的 try/except 包裹每个 middleware。** 异常传播取决于 hook 类型：

- **Graph node (before_* / after_*):** 异常直接传播给 LangGraph node runner → agent run 失败。同一阶段的后续 middleware 全部跳过。
- **wrap_model_call (内联):** 如果 LLMErrorHandlingMiddleware（位置 4，最外层之一）捕获了异常并做了重试/降级，内层 middleware 完全不感知。但如果异常来自内层 middleware 且没有被外层捕获 → 传播到 model_node → agent run 失败。
- **wrap_tool_call (内联):** ToolErrorHandlingMiddleware（位置 7）作为外层之一，try/except 包裹 handler()。tool 执行异常被它捕获并转换为 error ToolMessage。但如果 ToolErrorHandlingMiddleware **自己**抛了异常（不太可能，但可能），它之后的 middleware（DeferredToolFilter、Clarification）就跳过了。

**实际影响：** 一个 third-party middleware 的 bug 可以导致整个 agent run 崩溃。没有 "跳过出错的 middleware 继续执行" 的机制。这是信任模型——框架信任所有 middleware 不会抛未预期的异常。
