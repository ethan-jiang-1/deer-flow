---
title: "链装配：Middleware 是怎么串起来的"
description: "两阶段组装：共享基础层 12 个 + Lead-only 层 17 个。理解这个才能把自定 middleware 挂到正确位置。"
topics: [middleware, hooks, interceptor-chain]
---

# 链装配：Middleware 是怎么串起来的

## 两阶段组装

Middleware 链在两个函数中按严格顺序构建：

### Phase 1：共享基础层（`build_lead_runtime_middlewares()`）

文件：`deerflow/agents/middlewares/tool_error_handling_middleware.py:259`

```python
def build_lead_runtime_middlewares(*, app_config, lazy_init=True) -> list[AgentMiddleware]:
    return _build_runtime_middlewares(
        app_config=app_config,
        include_uploads=True,              # Lead 需要 UploadsMiddleware
        include_dangling_tool_call_patch=True,  # Lead 需要 Dangling
        lazy_init=lazy_init,
    )
```

内部 `_build_runtime_middlewares()` 返回三个拼接层：

```
outer_wrappers: [InputSanitization, ToolOutputBudget]
    + thread_hooks: [ThreadData, Uploads, Sandbox, Dangling, LLMError, Guardrail(cond), SandboxAudit]
    + tail: [ReadBeforeWrite(cond), ToolProgress(cond), ToolErrorHandling]
```

共 12 个。Sub-agent 通过 `build_subagent_runtime_middlewares()` 使用缩减版（不含 Uploads 和 Dangling）。

### Phase 2：Lead-only 层（`build_middlewares()`）

文件：`deerflow/agents/lead_agent/agent.py:269`

在上面的 12 个之后，依次追加 17 个：

```python
def build_middlewares(config, ...) -> list[AgentMiddleware]:
    middlewares = build_lead_runtime_middlewares(app_config=..., lazy_init=True)

    # 13-15: 上下文管理
    middlewares.append(DynamicContextMiddleware(...))
    middlewares.append(SkillActivationMiddleware(...))
    middlewares.append(DurableContextMiddleware(...))

    # 16-20: 可选 + 始终
    if summarization.enabled: middlewares.append(SummarizationMiddleware(...))
    if is_plan_mode: middlewares.append(TodoListMiddleware(...))
    if token_usage.enabled: middlewares.append(TokenUsageMiddleware(...))
    middlewares.append(TitleMiddleware(...))
    middlewares.append(MemoryMiddleware(...))

    # 21-26: 可选 + 始终
    if model_supports_vision: middlewares.append(ViewImageMiddleware(...))
    if deferred_setup: middlewares.append(DeferredToolFilterMiddleware(...))
    middlewares.append(SystemMessageCoalescingMiddleware(...))
    if subagent_enabled: middlewares.append(SubagentLimitMiddleware(...))
    if loop_detection.enabled: middlewares.append(LoopDetectionMiddleware(...))
    if token_budget.enabled: middlewares.append(TokenBudgetMiddleware(...))

    # 27-29: 尾部
    if custom_middlewares: middlewares.extend(custom_middlewares)
    if safety_finish_reason.enabled: middlewares.append(SafetyFinishReasonMiddleware(...))
    middlewares.append(ClarificationMiddleware(...))  # 必须最后
    return middlewares
```

## 关键顺序约束

| 约束 | 原因 |
|------|------|
| InputSanitization 必须第一个 | 最外层 `wrap_model_call`，所有内层 middleware 看到洗过的输入 |
| ToolProgress 必须在 ToolErrorHandling 外层 | 需要读 `deerflow_tool_meta` 来判断停滞类别 |
| ReadBeforeWrite 必须在 ToolProgress 和 ToolErrorHandling 外面 | 被阻断的 write 直接返回，不消耗 ToolProgress 槽位 |
| SystemMessageCoalescing 在 DeferredToolFilter 之后 | 合并前 deferred tools 的 prompt 注入已完成 |
| Custom middlewares 在 SafetyFinishReason 之前 | 用户 middleware 运行后，安全层做最终检查 |
| ClarificationMiddleware 必须最后一个 | `Command(goto=END)` 中断，后续 middleware 不再执行 |

## Sub-agent 的链

Sub-agent 通过 `build_subagent_runtime_middlewares()` 使用缩减版（不含 Uploads、Dangling）。额外添加 `ViewImageMiddleware`（如果模型支持 vision）和 `SafetyFinishReasonMiddleware`（可选）。Sub-agent 不包含 lead-only 层的任何 middleware（无 summarization、无 plan mode、无 memory、无 title、无 loop detection 等）。

## 与旧版对比

| 维度 | 旧版 (19) | 新版 (29) |
|------|----------|----------|
| 组装函数 | 1 个 (`_build_middlewares`) | 2 个（`build_lead_runtime_middlewares` + `build_middlewares`） |
| Sub-agent 链 | 独立构建 | 复用共享基础层 |
| 前置 middleware | 无 | InputSanitization + ToolOutputBudget |
| 上下文层 | 无 | DynamicContext + SkillActivation + DurableContext |
| 尾部 middleware | Clarification 最后 | Custom → SafetyFinishReason → Clarification |

---
> **See also:** [Agent Loop anatomy](../agent-loop/00-loop-anatomy.md) · [Middleware catalog](03-catalog.md) · [Testing custom middleware](../../testing/04-agent-test-patterns.md)
