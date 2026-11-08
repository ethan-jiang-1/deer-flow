# DeerFlow 全部 39 个 Middleware 条目位一览（sync #8，v2.2.0）

> 本表按 `_digested/internals/middleware/03-catalog.md` 重建（sync #8，v2.2.0，37 → 39 条目位）。
> 权威来源：`_build_runtime_middlewares()`（`tool_error_handling_middleware.py:347`，经 `build_lead_runtime_middlewares()` `:538` 导出）产出前 **16** 条共享基础层 + `build_middlewares()`（`lead_agent/agent.py:485`）再追加 **23** 条 lead-only 层。

## 怎么读这张表

- **#**：在 middleware 链中的位置（也是 before_* 的执行顺序；after_* 反向执行）
- **Hook**：这个 middleware 覆写哪个 hook → 决定它变成哪种 node 或拦截器（本表已把每个条目的主 hook 写准；纯 `wrap_*` 的条目不会产生任何 node）
- **可选？**：✅ = 有配置开关/条件触发，可能不在链上；❌ = 始终加载
- **🆕**：2.2.0 新增；**~~删除线~~**：2.1 有、2.2 已下线

> **"39" 的口径**（v2.2.0 用代码核实）：36 个内置 middleware 类型 + 2 个通用槽位（#34 caller 传入的 `custom_middlewares`、#35 config 声明的 `load_configured_extension_middlewares()`），再加 2 个条件性同族条目（`CompletedSubagentUsageMiddleware` `token_usage_middleware.py:382`、`SubagentDateContextMiddleware` `dynamic_context_middleware.py`，后两者只在 subagent 链）。**单链实际实例数随配置变化**，本表列的是"每种可能的条目"。

---

## 共享基础层（lead + sub agent 都加载，16 个）

| # | Middleware | Hook | 一句话 | 可选？ |
|---|-----------|------|--------|--------|
| 1 | **InputSanitizationMiddleware** | `wrap_model_call` | 转义 XML tag + 阻断 forged framework tag，防 prompt injection，包裹 `--- BEGIN USER INPUT ---` 边界。🆕 2.2：`original_user_content` 变为 **server-owned provenance**——Gateway 剥掉调用方自带值，非 internal run 不可信；调用方 marker 打 `untrusted_input`（`utils/messages.py:19`），**从不**被剥 | ❌ |
| 2 | **KnowledgeScopeMiddleware** 🆕 | `before_agent` | 把 run 的 canonical 知识作用域投影成请求级约束：`disabled` 时移除知识检索类工具与提示，非法/畸形 scope **fail-closed**；模型输入永远不能设置或放宽作用域 | ❌ |
| 3 | **ToolOutputBudgetMiddleware** | `wrap_model_call` | 超大 tool 结果落盘为 head+tail 预览 + `read_file` 引用。superseded write elision（`tool_output.elide_superseded_writes` 默认开）：同路径已有更新的成功 read/write 后，旧 `write_file` 的 `content` 在 model-bound request 中替换为占位符（2000 字符起、最新 1 条始终保留）；改写经共享 `tool_call_args.py` 在全部四个 AIMessage 参数面一致重写 | ❌ |
| 4 | **ToolResultSanitizationMiddleware** | `wrap_model_call` | 中性化远程内容 tool 结果中的 injection 标签（`web_fetch`/`web_search`/`image_search`/`web_capture`，name-based allowlist）。位于 #3 **之后**（更内层）：先中性化原始输出再做预算截断 | ❌ |
| 5 | **PiiRedactionMiddleware** 🆕 | `wrap_model_call` | 列在 Layer-1 最末 → 最内层 wrapper：tool 结果先脱敏，`ToolOutputBudget` 落盘的副本才不含 PII | ✅ `pii_redaction.enabled`（默认关） |
| 6 | **ThreadDataMiddleware** | `before_agent` | 创建线程隔离目录（workspace/uploads/outputs）。顺序：在 Uploads 之前 | ❌ |
| 7 | **UploadsMiddleware** | `before_agent` | 检测新上传的文件，注入给 agent | ❌（sub agent 链 `include_uploads=False`） |
| 8 | **SandboxMiddleware** | `before_agent`、`before_model`、`after_agent` | 获取 sandbox，存 `sandbox_id` 到 state；`before_model` 二次校验、`after_agent` 对称释放（栈语义） | ❌ |
| 9 | **DanglingToolCallMiddleware** | `wrap_model_call` | 补充缺失的 ToolMessage + malformed id 恢复 + 无效参数清洗（用户中断/strict provider 不 400） | ❌ |
| 10 | **LLMErrorHandlingMiddleware** | `wrap_model_call` | LLM API 出错时规范化错误为可恢复的 assistant-facing 错误（重试 + 断路器）。🆕 2.2：true empty stop 额外给一次 model-boundary 重试 | ❌ |
| 11 | **ArtifactResolutionMiddleware** 🆕 | `wrap_tool_call` | 把 tool artifact handle 在**任何参数敏感策略之前**解析成真实引用（`tool_artifacts.resolve_handles_in_args`）。`extensions/ordering.py:113-120` 硬约束它包住 Guardrail/SandboxAudit/ReadBeforeWrite/ToolProgress | ✅ `tool_artifacts.enabled` |
| 12 | **ToolReceiptMiddleware** | `wrap_tool_call`（最外层） | 确定性 tool 收据（RFC #4651 layer 1）：每个 tool 结果盖 sha256 收据，模型调用前派生隐藏 ledger（r1..rN）。lead 默认 `delegation_only`、subagent 恒 `always` | ✅ `verification.receipts_enabled`（默认开） |
| 13 | **GuardrailMiddleware**（authorization 实例） | `wrap_tool_call` | Layer 2 执行前授权检查：`GuardrailAuthorizationAdapter` 包 `AuthorizationProvider`，`fail_closed` 策略。**这是 2.2 之后 `allowed-tools` 权限上限的真正归属之一** | ✅ `authorization.enabled` |
| 14 | **GuardrailMiddleware**（显式 provider 实例） | `wrap_tool_call` | 显式 guardrails provider（如内置 `AllowlistProvider(allowed_tools=..., denied_tools=...)`）。`allowed_tools=[]` = 全拒，`None` = 全放 | ✅ `guardrails.enabled` + `guardrails.provider` |
| 15 | **SandboxAuditMiddleware** | `wrap_tool_call` | 审计沙箱 bash shell/file 操作，记录安全日志 | ❌ |
| 16 | **ReadBeforeWriteMiddleware** | `wrap_tool_call` | 写文件前检查是否读过——sha256 hash "读戳"，按 (thread, path) 串行化。`elide_blocked_payloads`（默认开）：被拦截调用的 payload 在 model-bound request 中替换为占位符 | ✅ `read_before_write.enabled`（默认开） |
| 17 | **ToolProgressMiddleware** | `before_agent`、`wrap_tool_call` | 检测工具停滞，状态机 ACTIVE→WARNED→BLOCKED；phase 迁移持久化到 `runtime/events` | ✅ `tool_progress.enabled`（默认关） |
| 18 | **ToolErrorHandlingMiddleware** | `wrap_tool_call`（内层） | **核心**：捕获工具异常 → error ToolMessage + 注入 `deerflow_tool_meta`（status/error_type/recoverable/recommended_action/source） | ❌ |
| 19 | **ArtifactCaptureMiddleware** 🆕 | `before_model` | 从 state 里已是归一化结果的 messages 提取轻量 artifact 元数据（error 结果跳过；`max_entries` 在 emit 时执行）。因为是 `before_model`，放在工具 wrap 链的哪个位置都无所谓 | ✅ `tool_artifacts.enabled`（默认开） |

> **顺序要点**：`_build_runtime_middlewares()` 返回 `[*outer_wrappers, *thread_hooks, *tail]`（`:529`）。`outer_wrappers` = Layer 1（#1-#5），`thread_hooks` = Layer 2（#6-#8），`tail` = Layer 3（#9-#19，按上表顺序）。**`wrap_tool_call` 的最外层是 #12 ToolReceipt**（Guardrail/SandboxAudit/ReadBeforeWrite/ToolProgress/ArtifactResolution 都可能短路或重建 ToolMessage，内层收据会漏记账）。

> 共享基础层总结：**16 条（sync #6 前为 14 条）**。sub agent 走 `build_subagent_runtime_middlewares()`（`tool_error_handling_middleware.py:567`）——同一基础层、`include_uploads=False`、receipts 恒 `always`，另外附加 DurableContext + SystemMessageCoalescing + guard trio（见文末）。

---

## Lead-only 层（仅主 agent 加载，23 个）

| # | Middleware | Hook | 一句话 | 可选？ |
|---|-----------|------|--------|--------|
| 20 | **DynamicContextMiddleware** | `before_agent` | 注入 `<system-reminder>`（日期+memory），保持 system prompt 静态以复用 prefix cache。🆕 v2.1.0-rc0：插入 transient `<project>` 块 + 有界 `<documents>` 索引 | ❌ |
| 21 | **SkillActivationMiddleware** | `wrap_model_call`（`skill_activation_middleware.py:921`） | 检测 `/skill-name task` 语法，加载 SKILL.md，每个 run 只激活一次，记 `middleware:skill_activation` 审计事件。⚠️ 2.2：**激活本身不再改变工具集** | ❌ |
| 22 | **DeferredToolPromotionAuditMiddleware** | `wrap_tool_call`（纯观察） | 在 inner 结果转换全部跑完后观察 `tool_search` 的 `Command`，持久化实际生效的 promotion 决策（不含敏感 payload），供可观测性/审计回放。`_record()` 只读不写结果——但它是**真实在外层的包装**，所以必须排在 DeferredToolFilter 之前 | ✅ `tool_search.enabled` + 有 deferred names |
| ~~—~~ | ~~**SkillToolPolicyMiddleware**~~ | ~~`wrap_model_call`~~ | ⚠️ **2.2 已删除**：`agents/middlewares/skill_tool_policy_middleware.py`（529 行）整文件已删除，#6935；配套 `skills/tool_policy.py`（65 行）同样已删除。`allowed-tools` 降级为兼容元数据，权限上限移交「agent 组装 + 执行授权」（#13/#14）。 | ~~❌~~ |
| 23 | **DurableContextMiddleware** | `before_model`、`after_model` | 捕获 task delegation + skill 引用到 ThreadState，summarization 前保存；再注入 summary + ledger + skills 通道 | ❌ |
| 24 | **SummarizationMiddleware**（`DeerFlowSummarizationMiddleware`） | `before_model` | 超过 token 阈值时压缩旧消息。🆕 2.2：`fraction` 的分母来自模型声明的 `context_window`，缺失时降级并告警 | ✅ `summarization.enabled` |
| 25 | **TodoListMiddleware**（`TodoMiddleware`） | 全部 6 个 hook | plan mode 下的 todo 管理。🆕 唯一实际使用 `jump_to: model` 的条目（`todo_middleware.py:313, 372`）：还有未完成 todo 却想收尾时把 agent 拽回 loop；见到 `model_length_termination` 标记就不再重入 | ✅ plan mode |
| 26 | **TokenUsageMiddleware** | `after_model` | 累计 token 用量 | ✅ `token_usage.enabled` |
| 27 | **TitleMiddleware** | `after_model` | 第一轮对话后自动生成线程标题（只读 state + 写 state，不设 `jump_to`） | ❌ |
| 28 | **MemoryMiddleware** | `after_agent` | 读写 durable memory（每 agent 存储） | ✅ `memory_enabled` |
| 29 | **ViewImageMiddleware** | `wrap_model_call` | 模型支持 vision 时注入图片细节（sha256 宿主副本） | ✅ 模型 `supports_vision` |
| 30 | **McpRoutingMiddleware** | `before_model` | 🆕 按 MCP routing hints 在 model 调用前自动 promote 匹配的 deferred 工具——**必须在 DeferredToolFilter 外层**（`assert_mcp_routing_before_deferred_filter()` 强制） | ✅ `tool_search.enabled` + 有 `mode:"prefer"` 的 routing hint，否则 builder 返回 `None` 不上链 |
| 31 | **DeferredToolFilterMiddleware** | `wrap_model_call`（+ `wrap_tool_call` 安全网） | 从 `request.tools` 移除未 promote 的 deferred MCP 工具；幻觉直调时返回错误 ToolMessage 指示先 `tool_search` | ✅ `tool_search.enabled` |
| 32 | **SystemMessageCoalescingMiddleware** | `wrap_model_call` | 合并多个 leading system 块，兼容 strict backend | ❌ |
| 33 | **SubagentLimitMiddleware** | `after_model` | 限制并发/总子 agent 数（delegation ledger + total cap） | ✅ `subagent_enabled` |
| 34 | **LoopDetectionMiddleware** | `before_agent`、`after_model`、`after_agent` | 比较连续几轮 `tool_calls`，发现重复模式就清掉 tool_calls 让模型出文本；事件持久化到 `runtime/events`，警告延后到下一圈 `wrap_model_call` 注入以保 tool-call 配对 | ✅ `loop_detection.enabled`（默认开） |
| 35 | **TokenBudgetMiddleware** | `before_agent`、`after_model`、`after_agent` | 按 run 的 token 预算止损 | ✅ `token_budget.enabled`（默认关） |
| 36 | **CompletedSubagentUsageMiddleware** | `after_model` | 只回填已完成子方的用量（`token_usage_middleware.py:382`） | ✅ `token_budget.enabled` 且 `token_usage.enabled` |
| 37 | **ModelContentCompatibilityMiddleware** 🆕 | `wrap_model_call` | 读时清洗持久化的 URL 来源 file/image 块（Chat Completions 序列化器拒收），只改请求视图、**不写 state/checkpoint**；追加在所有内置 content 改写之后、`MODEL_PHYSICAL` anchor 外层 | ❌ |
| 38 | **〔custom_middlewares〕槽位** | 取决于调用方 | `build_middlewares(custom_middlewares=[...])` 注入的用户 middleware（`agent.py:750-751`） | ✅ 调用方传 |
| 39 | **〔configured extensions〕槽位** | 取决于扩展 | `load_configured_extension_middlewares()`（`agents/middlewares/configured_extensions.py`，`agent.py:753-755`）；之后 `compose_with_extensions()`（`deerflow/extensions/stack.py`，`agent.py:786-800`）再合并打包扩展贡献 | ✅ `config.yaml` 声明 |
| 40 | **TerminalResponseMiddleware** 🆕 | `after_model` | 空 terminal AIMessage 恢复：post-tool 响应仍无可见文本时补 hidden recovery 提示并重试一次，二次仍空则换成 error fallback。**不新增 graph 级恢复轮次** | ❌ |
| 41 | **ModelLengthFinishReasonMiddleware** 🆕 | `after_model` | provider 长度截断时标 `stop_reason=model_length_capped`、**抑制该响应的 tool_calls**，无可见文本时追加长度提示 | ❌ |
| 42 | **SafetyFinishReasonMiddleware** 🆕 | `after_model` | provider 安全终止（`finish_reason=content_filter` 等）时清掉被污染的 `tool_calls`，发 termination 事件 + 审计。注册在 Clarification **之前** → 反向分发时第 2 个执行 | ✅ `safety_finish_reason.enabled`（默认开） |
| 43 | **ClarificationMiddleware** | `after_model`、`wrap_tool_call` | 列表最后一条。`wrap_tool_call` 拦截 `ask_clarification` 返回 `Command(goto=END)`；`after_model` 丢弃同轮兄弟 tool_calls（`clarification_middleware.py:395-445, 518-521, 574`）。反向分发时**最先执行** | ❌ |

> 说明：lead-only 表里按"每条可能的条目"列出，编号 20-43 是展开后的实际条目数（23 个内置位 + 2 个槽位已含其中；`CompletedSubagentUsageMiddleware` 是条件同族条目）。与 `_digested/internals/middleware/03-catalog.md` 的全局 1-39 编号口径不同，本表分两段编号以便和 `build_middlewares()` 的追加顺序对齐。

---

## Sub-agent 链（`build_subagent_runtime_middlewares()`，`tool_error_handling_middleware.py:567`）

```
共享基础层（不含 #7 Uploads、Dangling 保留、receipts 恒 always）
  → SkillActivation → DeferredToolPromotionAudit(cond) → ViewImage(vision) → McpRouting(cond)
  → DeferredToolFilter(cond) + assert → LoopDetection(cond) → TokenBudget(cond)
  → SafetyFinishReason(cond) → DurableContext → Summarization(skip_memory_flush=True)
  → ModelContentCompatibility → SubagentDateContextMiddleware → SystemMessageCoalescing
  → compose_with_extensions(..., AgentScope.SUBAGENT, ...)
```

`SubagentDateContextMiddleware`（`dynamic_context_middleware.py`，`before_agent`）一次性注入隐藏 `<current_date>`。sub agent **不含** lead-only 的 DynamicContext、TodoList、TokenUsage/CompletedSubagentUsage、Title、Memory、SubagentLimit、TerminalResponse、ModelLengthFinishReason、Clarification。

---

## 按 hook 类型分类（lead 链，v2.2.0 AST 实测）

| hook → node | 定义它的类 |
|---|---|
| `before_agent` | ThreadData、Uploads、Sandbox、KnowledgeScope、ToolProgress、DynamicContext、Todo(cond)、LoopDetection(cond)、TokenBudget(cond) |
| `before_model` | ArtifactCapture、Sandbox、DeferredToolFilter、McpRouting、DurableContext、Summarization(cond)、Todo(cond) |
| `after_model` | DurableContext、Title、TokenUsage(cond)、SubagentLimit(cond)、LoopDetection(cond)、TokenBudget(cond)、CompletedSubagentUsage(cond)、TerminalResponse、ModelLengthFinishReason、SafetyFinishReason(cond)、Clarification |
| `after_agent` | Sandbox、Memory、LoopDetection(cond)、TokenBudget(cond) |
| **只做 `wrap_model_call`**（无 node） | InputSanitization、ToolOutputBudget、ToolResultSanitization、PiiRedaction、LLMErrorHandling、DanglingToolCall、SkillActivation、ViewImage、SystemMessageCoalescing、ModelContentCompatibility |
| **只做 `wrap_tool_call`**（无 node） | ToolReceipt、ArtifactResolution、Guardrail(×2)、SandboxAudit、ReadBeforeWrite、ToolErrorHandling、DeferredToolPromotionAudit（纯观察） |

---

## v2.1.0 → v2.2.0 变更速览

| 变化 | 说明 |
|------|------|
| **条目位** | 37 → **39**（共享基础层 14 → 16，lead-only 23 不变） |
| **⚠️ 删除 SkillToolPolicyMiddleware** | `skill_tool_policy_middleware.py`（529 行）已删除、`skills/tool_policy.py`（65 行）已删除，#6935 `0d73798be`；`allowed-tools` 降级为**兼容元数据**，权限上限移交 agent 组装 + 执行授权（#13/#14）。对文档/测试的影响：任何「skill 声明 allowed-tools 就看不到某工具」式断言在 2.2 **已不成立** |
| **🆕 KnowledgeScope（#2）** | canonical 知识作用域 → 请求级约束，fail-closed |
| **🆕 PiiRedaction（#5）** | Layer-1 最内层脱敏，落盘副本无 PII |
| **🆕 ArtifactResolution（#11）** | handle 解析在参数敏感策略之前（ordering 硬约束） |
| **🆕 ArtifactCapture（#19）** | `before_model` 提取 artifact 元数据 |
| **🆕 ModelContentCompatibility（#37）** | 请求视图读时清洗 URL/file 块，不写 state |
| **🆕 TerminalResponse（#40）** | 空 terminal 响应兜底，不新增恢复轮次 |
| **🆕 ModelLengthFinishReason（#41）** | 长度截断标记 + 抑制 tool_calls |
| **🆕 SafetyFinishReason（#42）** | 安全终止清 tool_calls，reversed 分发里优先级仅次于 Clarification |
| **ToolReceipt 增强** | 确定性 tool 收据 + 隐藏 ledger，最外层 `wrap_tool_call`，防短路漏记账 |
| **DynamicContext 增强** | transient `<project>` 块 + 有界 `<documents>` 索引注入，`project_context_revision` 上下文事件 |
| **ToolOutputBudget 增强** | superseded write elision；改写经共享 `tool_call_args.py` 在全部四个 AIMessage 参数面一致重写 |
| **ReadBeforeWrite 增强** | `elide_blocked_payloads`：被拦截调用 payload 在 model-bound request 中占位符化 |
| **LoopDetection/ToolProgress 增强** | 检测/phase 迁移事件持久化到 `runtime/events`（run 重放可审计） |
| **其他增强** | Title（attachment-only 文件名标题）、ViewImage（sha256 宿主副本）、Summarization（fraction 从模型 `context_window` 解析）、Guardrail（authz context）、Dangling（malformed id 恢复）、SubagentLimit（delegation ledger + total cap）、SkillActivation（每 run 只激活一次、且**不收窄工具**） |
| **Declarative layered builder** | 组装改声明式分层构建器；`extensions/ordering.py::core_ordering_constraints()` 在 `compose_with_extensions()` 合并扩展贡献之后**一次性校验**顺序不变量，违反抛 `RuntimeError` 并点名贡献者 |
