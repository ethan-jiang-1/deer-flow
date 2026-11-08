---
title: "链装配：Middleware 是怎么串起来的"
description: "两阶段组装：共享基础层 16 + lead-only 23。声明式分层构建器 + `extensions/ordering.py` 的最终顺序校验。理解这个才能把自定义 middleware 挂到正确位置。"
topics: [middleware, hooks, interceptor-chain]
---

# 链装配：Middleware 是怎么串起来的

## 两阶段组装

Middleware 链在两个函数中按严格顺序构建（v2.2.0 口径）：

### Phase 1：共享基础层（`build_lead_runtime_middlewares()`）

文件：`deerflow/agents/middlewares/tool_error_handling_middleware.py:538`（`build_lead_runtime_middlewares`；其内部 `_build_runtime_middlewares` 在 `:347`）

```python
def build_lead_runtime_middlewares(*, app_config, lazy_init=True, authorization_provider=None,
                                   deferred_setup=None, available_skills=None,
                                   owns_agent_skill_projection=True,
                                   skill_authorization=None, user_id=None) -> list[AgentMiddleware]:
    return _build_runtime_middlewares(
        app_config=app_config,
        include_uploads=True,                   # Lead 需要 UploadsMiddleware
        include_dangling_tool_call_patch=True,  # Lead 需要 Dangling
        lazy_init=lazy_init,
        receipts_render_mode=app_config.verification.receipts_render_mode,
        ...
    )
```

内部 `_build_runtime_middlewares()` 返回三个列表顺序拼接（`:379-531`）：

```
outer_wrappers: [InputSanitization, KnowledgeScope, ToolOutputBudget,
                 ToolResultSanitization, PiiRedaction(cond)]          ← Layer 1
    + thread_hooks: [ThreadData, Uploads(仅 lead), Sandbox]           ← Layer 2
    + tail: [Dangling(仅 include_dangling), LLMError,
             ArtifactResolution(cond tool_artifacts.resolve_handles_in_args),
             ToolReceipt(cond), Guardrail(authz, cond), Guardrail(guardrails, cond),
             SandboxAudit, ReadBeforeWrite(cond), ToolProgress(cond),
             ToolErrorHandling, ArtifactCapture(cond tool_artifacts.enabled)]   ← Layer 3
```

（以上即三个列表的拼接顺序；Guardrail 最多两个实例——authorization 与显式 guardrail provider 各一；条目位共 16 个 + `ToolProgress` 与 `ArtifactCapture` 两个条件位，见[目录](03-catalog.md)。）

Layer 1 的排列意图（源码注释 `:370-393`）：`InputSanitization` 在最前 → 是最外层 `wrap_model_call`，内层（含 LLM 重试）看到的都是洗过的消息；`ToolResultSanitization` 排在 `ToolOutputBudget` **之后**，先中性化远程内容标签再做预算截断；`PiiRedaction` 排最后 → 是最内层 wrapper，tool 结果先脱敏、落盘副本才不含 PII。

🆕 v2.2.0 的 `ArtifactResolutionMiddleware` 在 `tail` 里紧跟 `LLMErrorHandling`，并排在 Guardrail/SandboxAudit/ReadBeforeWrite/ToolProgress **之外**（`extensions/ordering.py:113-122` 的 `OrderingConstraint` 硬约束）：handle 必须在"对参数敏感"的授权/审计/写门/progress 策略之前解析成真实引用。`ToolReceiptMiddleware` 仍是最外层 `wrap_tool_call`（`:95-110` 约束它包住 ArtifactResolution/Guardrail/SandboxAudit/ReadBeforeWrite/ToolProgress 全部五个可能短路的环节）。

Sub-agent 通过 `build_subagent_runtime_middlewares()`（`:567`）使用同一基础层：`include_uploads=False`、`include_dangling_tool_call_patch=True`、`receipts_render_mode="always"`（子方上下文不渲染 ledger 就拿不到引用，Layer 1 直接失效）。

🆕 v2.2.0 把 `artifact_resolution_middleware.py` 引入 `extensions/ordering.py::core_ordering_constraints()`，因此**顺序不变量在 extensions 贡献合并之后的最终栈上一次性校验**；违反抛 `RuntimeError` 并点名贡献者——文档称其是这套系统里唯一的硬失败（其余都是可观测性缺口）。

### Phase 2：Lead-only 层（`build_middlewares()`）

文件：`deerflow/agents/lead_agent/agent.py:485`

在共享基础层之后依次追加 23 个：

```python
def build_middlewares(config, ...) -> list[AgentMiddleware]:
    middlewares = build_lead_runtime_middlewares(app_config=..., lazy_init=True, ...)

    # 17-19: 上下文管理
    middlewares.append(DynamicContextMiddleware(...))          # 日期 + 可选 memory
    middlewares.append(SkillActivationMiddleware(...))         # slash 激活（不收窄工具）
    if deferred_setup and deferred_setup.deferred_names:
        middlewares.append(DeferredToolPromotionAuditMiddleware(...))
    # （v2.1.0 的 SkillToolPolicyMiddleware 已在 v2.2.0 删除）
    middlewares.append(DurableContextMiddleware(...))

    # 20-24: 可选 + 始终
    if summarization.enabled: middlewares.append(SummarizationMiddleware(...))
    if is_plan_mode:           middlewares.append(TodoListMiddleware(...))
    if token_usage.enabled:    middlewares.append(TokenUsageMiddleware())
    middlewares.append(TitleMiddleware(...))
    if memory_enabled and ...:  middlewares.append(MemoryMiddleware(...))

    # 25-31: vision + MCP + guard trio
    if model_supports_vision: middlewares.append(ViewImageMiddleware())
    if mcp_routing_middleware is not None: middlewares.append(mcp_routing_middleware)
    if tool_search.enabled:
        middlewares.append(DeferredToolFilterMiddleware(...))
        assert_mcp_routing_before_deferred_filter(middlewares)
    middlewares.append(SystemMessageCoalescingMiddleware())
    if subagent_enabled:      middlewares.append(SubagentLimitMiddleware(max_concurrent=..., max_total=...))
    if loop_detection.enabled: middlewares.append(LoopDetectionMiddleware.from_config(...))
    if token_budget.enabled:  middlewares.append(TokenBudgetMiddleware.from_config(...))
    if token_budget.enabled and token_usage.enabled:
        middlewares.append(CompletedSubagentUsageMiddleware())   # 🆕 只回填已完成子方用量

    # 32-37: 尾部
    middlewares.append(ModelContentCompatibilityMiddleware())   # 🆕 请求视图读时清洗
    if custom_middlewares:      middlewares.extend(custom_middlewares)
    middlewares.extend(load_configured_extension_middlewares(...))
    middlewares.append(TerminalResponseMiddleware())
    middlewares.append(ModelLengthFinishReasonMiddleware())
    if safety_finish_reason.enabled: middlewares.append(SafetyFinishReasonMiddleware.from_config(...))
    middlewares.append(ClarificationMiddleware())               # 默认配置下最后

    # 最后才把打包扩展贡献的 middleware（IsolatedMiddleware 包裹）合并进完整栈
    return compose_with_extensions(middlewares, AgentScope.LEAD, AgentBuildContext(...), resolved_extensions)
```

## 关键顺序约束

| 约束 | 原因 | 谁强制 |
|------|------|--------|
| InputSanitization 必须第一个 | 最外层 `wrap_model_call`，所有内层 middleware 看到洗过的输入 | 代码位置（注释 `:370-378`） |
| ToolResultSanitization 在 ToolOutputBudget 内层 | 先中性化原始输出，预算截断落在已中性化文本上 | 代码位置 |
| PiiRedaction 最内层 | 落盘副本（`ToolOutputBudget` externalize）必须是脱敏后的 | 代码位置（#3190） |
| ToolProgress 在 ToolErrorHandling 外层 | 需要读 `deerflow_tool_meta` 判断停滞类别 | `OrderingConstraint`（`extensions/ordering.py:88-92`） |
| ToolReceipt 在最外层 `wrap_tool_call` | Guardrail/SandboxAudit/ReadBeforeWrite/ToolProgress/ArtifactResolution 可短路/重建 ToolMessage，内层收据会漏记账 | `OrderingConstraint`（`:95-114`） |
| ArtifactResolution 在四个策略 middleware 外层 | handle 必须在参数敏感策略检查前解析 | `OrderingConstraint`（`:113-122`） |
| McpRouting 在 DeferredToolFilter 外层 | 自动提升发生在隐藏决策之前 | `assert_mcp_routing_before_deferred_filter()` |
| ReadBeforeWrite 在 ToolProgress/ToolErrorHandling 外层 | 被拦的写立即返回，不消耗 progress 槽位 | 代码位置 |
| ModelContentCompatibility 在所有内置 content 改写之后、custom/extension 注入点之前 | 它要看到"接近最终"的请求；放在 `MODEL_PHYSICAL` anchor 外层才能保住扩展的 final-request 保证 | 代码位置（`agents/factory.py:440-452`） |
| Custom middlewares 在 TerminalResponse/SafetyFinishReason 之前 | 用户 middleware 跑完后尾部安全层做最终检查 | 代码位置 |
| ClarificationMiddleware 在最后 | `Command(goto=END)` 中断，后续 middleware 永远不执行 | 代码位置；`factory.py:453-454` 显式 append 在 `ModelContentCompatibility` 之后，`_insert_extra` 走完后再把 Clarification 弹回尾部（`:458-466`）。**lead 的 `build_middlewares()` 不做这个重排**，`ModelLengthFinishReason` 与 `SafetyFinishReason` 排在它前面 |

> ⚠️ 与 `AGENTS.md` 的差异：AGENTS.md 称 `SafetyFinishReason` 注册在 TerminalResponse/custom/configured 之后以便 after_model 反向分发时最先执行——这依赖 Clarification 之后是否还有条目。v2.2.0 的 `build_middlewares()` 末尾顺序是 `... TerminalResponse → ModelLengthFinishReason → SafetyFinishReason(cond) → Clarification`，因此 after_model 里最先执行的是 **Clarification**（`clarification_middleware.py` 自己也定义 `after_model`），Safety 排第二。这一点以源码为准。

## Sub-agent 的链

Sub-agent 通过 `build_subagent_runtime_middlewares()`（`tool_error_handling_middleware.py:567`）使用同一共享基础层（不含 Uploads；Dangling 保留；receipts 恒 `always`）。之后依次追加：

```
SkillActivation → DeferredToolPromotionAudit(cond) → ViewImage(vision) → McpRouting(cond)
  → DeferredToolFilter(cond) + assert → LoopDetection(cond) → TokenBudget(cond)
  → SafetyFinishReason(cond) → DurableContext → Summarization(skip_memory_flush=True)
  → ModelContentCompatibility → SubagentDateContextMiddleware → SystemMessageCoalescing
  → compose_with_extensions(..., AgentScope.SUBAGENT, ...)
```

🆕 v2.2.0 的三处变化：① **Summarization 追加在 guard trio 之后**（lead 链在之前；作者注明这是良性的——压缩在 `before_model`、记账在 `after_model` 互不干扰），且 `skip_memory_flush=True`（子 agent 共享父 `thread_id`，否则子方轮次会写进父 thread 的 durable memory，#3875 Phase 3 review）；② subagent 也注册 `ModelContentCompatibilityMiddleware`；③ 末尾补 `SubagentDateContextMiddleware`（#4781，一次性注入隐藏 `<current_date>`）与 `SystemMessageCoalescingMiddleware`（#4040/#4781），保证 strict backend 只收到一个 leading system 块。

Sub-agent 不含 lead-only 的 DynamicContext、TodoList、TokenUsage（及 `CompletedSubagentUsageMiddleware`）、Title、Memory、SubagentLimit、TerminalResponse、ModelLengthFinishReason、Clarification。

## 与旧版对比

| 维度 | v2.1.0（37 条目位） | v2.2.0（39 条目位） |
|------|----------|----------|
| 组装方式 | 声明式分层构建器 | 同左，最终 `compose_with_extensions()` |
| Layer 1 wrapper | InputSanitization / ToolOutputBudget / ToolResultSanitization | + KnowledgeScope、+ PiiRedaction（条件） |
| `wrap_tool_call` 最外层 | ToolReceipt | ToolReceipt（内层新增 ArtifactResolution） |
| 上下文层 | DynamicContext + SkillActivation + SkillToolPolicy + DurableContext | DynamicContext + SkillActivation + DurableContext（SkillToolPolicy 已删除，`allowed-tools` 降级为兼容元数据） |
| 新机制 | — | tool artifact（capture + resolve，`ThreadState.tool_artifacts`）、`tool_declarations.py` 的中间件声明工具 Layer-1 授权、`CompletedSubagentUsageMiddleware` |
| 尾部 middleware | Custom → TerminalResponse → ModelLength → Safety → Clarification | ModelContentCompatibility → Custom → Configured(ext) → TerminalResponse → ModelLength → Safety → Clarification |
| Sub-agent 继承 | Summarization + DurableContext + guard trio | 同左，另加 ModelContentCompatibility + DateContext + Coalescing |

---
> **See also:** [Agent Loop anatomy](../agent-loop/00-loop-anatomy.md) · [Middleware catalog](03-catalog.md) · [Hook 点与执行流](01-hooks-and-flow.md)
