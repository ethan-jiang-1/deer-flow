---
title: "链装配：Middleware 是怎么串起来的"
description: "两阶段组装：共享基础层 14 个 + Lead-only 层 23 个。声明式分层构建器 + 严格顺序约束。理解这个才能把自定义 middleware 挂到正确位置。"
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
outer_wrappers: [InputSanitization, ToolOutputBudget, ToolResultSanitization]
    + thread_hooks: [ThreadData, Uploads, Sandbox, Dangling, LLMError, Guardrail(cond), SandboxAudit]
    + tail: [ToolReceipt(cond), ReadBeforeWrite(cond), ToolProgress(cond), ToolErrorHandling]
```

共 14 个。🆕 `ToolResultSanitization` 位于 `ToolOutputBudget` 之后——先中性化远程内容标签，再做预算截断。🆕 `ToolReceipt`（同步 #5，`verification.receipts_enabled` 默认开）是**最外层 `wrap_tool_call`**，排在 Guardrail/SandboxAudit/ReadBeforeWrite/ToolProgress 之外，防止短路/重建结果漏记账。**顺序变更**：`ThreadData` 移到 `Uploads` 之前运行。使用**声明式分层构建器**。

Sub-agent 通过 `build_subagent_runtime_middlewares()` 使用缩减版（不含 Uploads 和 Dangling）；额外附加 `DurableContextMiddleware` + `SystemMessageCoalescingMiddleware` + guard middlewares（TokenBudget/LoopDetection/SubagentLimit/Summarization）。

### Phase 2：Lead-only 层（`build_middlewares()`）

文件：`deerflow/agents/lead_agent/agent.py:269`

在上面的 14 个之后，依次追加 23 个（同步 #6 新增 `DeferredToolPromotionAuditMiddleware`，插在 SkillActivation 与 SkillToolPolicy 之间）：

```python
def build_middlewares(config, ...) -> list[AgentMiddleware]:
    middlewares = build_lead_runtime_middlewares(app_config=..., lazy_init=True)

    # 15-16, 18-19: 上下文管理
    middlewares.append(DynamicContextMiddleware(...))
    middlewares.append(SkillActivationMiddleware(...))
    if deferred_setup and deferred_setup.deferred_names:
        middlewares.append(DeferredToolPromotionAuditMiddleware(...))  # 🆕 #17 promotion 审计
    middlewares.append(SkillToolPolicyMiddleware(...))       # 🆕 allowed-tools 执行
    middlewares.append(DurableContextMiddleware(...))

    # 20-24: 可选 + 始终
    if summarization.enabled: middlewares.append(SummarizationMiddleware(...))
    if is_plan_mode: middlewares.append(TodoListMiddleware(...))
    if token_usage.enabled: middlewares.append(TokenUsageMiddleware(...))
    middlewares.append(TitleMiddleware(...))
    middlewares.append(MemoryMiddleware(...))

    # 25-31: vision + MCP + guard trio
    if model_supports_vision: middlewares.append(ViewImageMiddleware(...))
    if tool_search.enabled and routing_metadata:
        middlewares.append(McpRoutingMiddleware(...))        # 🆕 auto-promote MCP tools
    if tool_search.enabled:
        middlewares.append(DeferredToolFilterMiddleware(...))
    middlewares.append(SystemMessageCoalescingMiddleware(...))
    if subagent_enabled: middlewares.append(SubagentLimitMiddleware(...))
    if loop_detection.enabled: middlewares.append(LoopDetectionMiddleware(...))
    if token_budget.enabled: middlewares.append(TokenBudgetMiddleware(...))

    # 32-37: 尾部
    if custom_middlewares: middlewares.extend(custom_middlewares)
    middlewares.extend(load_configured_extension_middlewares(...))
    middlewares.append(TerminalResponseMiddleware(...))       # 🆕 空响应恢复
    middlewares.append(ModelLengthFinishReasonMiddleware(...))
    if safety_finish_reason.enabled: middlewares.append(SafetyFinishReasonMiddleware(...))
    middlewares.append(ClarificationMiddleware(...))          # 必须最后

    # 最后才把打包扩展贡献的 middleware（IsolatedMiddleware 包裹）合并进完整栈
    return compose_with_extensions(middlewares, AgentScope.LEAD, ...)
```

## 关键顺序约束

| 约束 | 原因 |
|------|------|
| InputSanitization 必须第一个 | 最外层 `wrap_model_call`，所有内层 middleware 看到洗过的输入 |
| ToolProgress 必须在 ToolErrorHandling 外层 | 需要读 `deerflow_tool_meta` 来判断停滞类别 |
| ReadBeforeWrite 必须在 ToolProgress 和 ToolErrorHandling 外面 | 被阻断的 write 直接返回，不消耗 ToolProgress 槽位 |
| SystemMessageCoalescing 在 DeferredToolFilter 之后 | 合并前 deferred tools 的 prompt 注入已完成 |
| DeferredToolPromotionAudit 在 SkillToolPolicy 之前（外层） | 只观察 policy 过滤后的 `tool_search` Command——被 policy 拒绝的 schema 不得记为有效 promotion（`extensions/ordering.py` 硬约束） |
| ToolReceipt 最外层 `wrap_tool_call` | Guardrail/SandboxAudit/ReadBeforeWrite/ToolProgress 可短路/重建 ToolMessage，内层收据会漏记账 |
| Custom middlewares 在 SafetyFinishReason 之前 | 用户 middleware 运行后，安全层做最终检查 |
| ClarificationMiddleware 必须最后一个 | `Command(goto=END)` 中断，后续 middleware 不再执行 |

## Sub-agent 的链

Sub-agent 通过 `build_subagent_runtime_middlewares()` 使用缩减版（不含 Uploads；Dangling 保留）。共享 base 之后镜像 lead 链追加：SkillActivation + 🆕 DeferredToolPromotionAudit + SkillToolPolicy 对、ViewImage（vision）、McpRouting + DeferredToolFilter（deferred setup）、LoopDetection + TokenBudget（guard trio）、ConfiguredExtension、SafetyFinishReason，然后是 DurableContext + Summarization（`skip_memory_flush=True`——subagent 内部轮次不得写进父 thread 的 memory）。Sub-agent 不含 lead-only 层的 DynamicContext、TodoList、TokenUsage、Title、Memory、SubagentLimit、TerminalResponse、Clarification。

## 与旧版对比

| 维度 | 旧版 (29) | 新版 (37) |
|------|----------|----------|
| 组装方式 | 命令式 append | 🆕 声明式分层构建器 |
| 组装函数 | 2 个 | 2 个（+ Subagent 使用增强版 shared base） |
| Sub-agent 链 | 缩减版 shared base | 缩减版 + SkillActivation/SkillToolPolicy 对 + PromotionAudit + DurableContext + Summarization + guard trio |
| 前置 middleware | InputSanitization + ToolOutputBudget | + ToolResultSanitization（远程内容中性化） |
| 上下文层 | DynamicContext + SkillActivation + DurableContext | + SkillToolPolicy（allowed-tools 执行）+ 🆕 DeferredToolPromotionAudit（#17，SkillToolPolicy 之前） |
| MCP 层 | DeferredToolFilter | 🆕 McpRouting（auto-promote）+ DeferredToolFilter |
| 尾部 middleware | Custom → SafetyFinishReason → Clarification | Custom → 🆕 TerminalResponse → 🆕 ModelLengthFinishReason → SafetyFinishReason → Clarification |
| Sub-agent 继承 | 无 summarization | 🆕 继承 Summarization + DurableContext + guard trio |

---
> **See also:** [Agent Loop anatomy](../agent-loop/00-loop-anatomy.md) · [Middleware catalog](03-catalog.md) · [Testing custom middleware](../../testing/04-agent-test-patterns.md)
