# DeerFlow 全部 37 个 Middleware 一览（sync #6，v2.1.0-rc0）

> 本表按 `_digest/internals/middleware/03-catalog.md` 重建（sync #6，v2.1.0-rc0，35 → 37）。
> 权威来源：`build_lead_runtime_middlewares()`（前 14 个共享基础层）+ `build_middlewares()`（后 23 个 lead-only 层）。

## 怎么读这张表

- **#**：在 middleware 链中的位置（也是执行顺序）
- **Hook**：这个 middleware 覆写了哪个 hook（决定它变成哪种 node 或拦截器）
- **可选？**：✅ = 有配置开关/条件触发，可能不在链上；❌ = 始终加载
- **🆕**：2.1.0 新增的 middleware

---

## 共享基础层（lead + sub agent 都加载，14 个）

| # | Middleware | Hook | 一句话 | 可选？ |
|---|-----------|------|--------|--------|
| 1 | **InputSanitizationMiddleware** | `wrap_model_call` | 转义 XML tag + 阻断 forged framework tag，防 prompt injection，包裹 `--- BEGIN USER INPUT ---` 边界 | ❌ |
| 2 | **ToolOutputBudgetMiddleware** | `wrap_model_call` | 超大 tool 结果落盘为 head+tail 预览 + `read_file` 引用。🆕 superseded write elision（`tool_output.elide_superseded_writes` 默认开）：同路径已有更新的成功 read/write 后，旧 `write_file` 的 `content` 在 model-bound request 中替换为占位符 | ❌ |
| 3 | **ToolResultSanitizationMiddleware** 🆕 | `wrap_model_call` | 中性化远程内容 tool 结果中的 injection 标签（web_fetch/search 等，name-based allowlist） | ❌ |
| 4 | **ThreadDataMiddleware** | `before_agent` | 创建线程隔离目录（workspace/uploads/outputs）。顺序：在 Uploads 之前 | ❌ |
| 5 | **UploadsMiddleware** | `before_agent` | 检测新上传的文件，注入给 agent（lead only） | ❌ |
| 6 | **SandboxMiddleware** | `before_agent` | 获取 sandbox，存 `sandbox_id` 到 state | ❌ |
| 7 | **DanglingToolCallMiddleware** | `before_agent` | 补充缺失的 ToolMessage + malformed id 恢复 + 无效参数清洗（用户中断/strict provider 不 400） | ❌ |
| 8 | **LLMErrorHandlingMiddleware** | `wrap_model_call` | LLM API 出错时规范化错误为可恢复的 assistant-facing 错误（重试 + 断路器） | ❌ |
| 9 | **ToolReceiptMiddleware** 🆕 | `wrap_tool_call`（最外层） | 确定性 tool 收据（RFC #4651 layer 1）：每个 tool 结果盖 sha256 收据，模型调用前派生隐藏 ledger（r1..rN）。`receipts_render_mode` 默认 `delegation_only` | ✅ `verification.receipts_enabled`（默认开） |
| 10 | **GuardrailMiddleware** | `wrap_tool_call` | 工具执行前授权检查，`fail_closed` 策略。GuardrailRequest 含 thread_id/user_id/is_subagent/authz_attributes | ✅ `guardrails.enabled` |
| 11 | **SandboxAuditMiddleware** | `wrap_tool_call` | 审计沙箱 bash shell/file 操作，记录安全日志 | ❌ |
| 12 | **ReadBeforeWriteMiddleware** | `wrap_tool_call` | 写文件前检查是否读过——sha256 hash "读戳"，按 (thread, path) 串行化。🆕 `elide_blocked_payloads`（默认开）：被拦截调用的 payload 在 model-bound request 中替换为占位符 | ✅ `read_before_write.enabled` |
| 13 | **ToolProgressMiddleware** | `after_tool` | 检测工具停滞，状态机 ACTIVE→WARNED→BLOCKED。🆕 phase 迁移持久化到 `runtime/events` | ✅ `tool_progress.enabled` |
| 14 | **ToolErrorHandlingMiddleware** | `after_tool` | **核心**：捕获工具异常 → error ToolMessage + 注入 `deerflow_tool_meta`（status/error_type/recoverable/recommended_action/source） | ❌ |

> 共享基础层总结：**14 个（sync #6 前为 13 个，+ToolReceiptMiddleware）。sub agent 也加载其中大部分——不含 Uploads，额外附加 DurableContextMiddleware + SystemMessageCoalescingMiddleware + guard trio。**

---

## Lead-only 层（仅主 agent 加载，23 个）

| # | Middleware | Hook | 一句话 | 可选？ |
|---|-----------|------|--------|--------|
| 15 | **DynamicContextMiddleware** | `wrap_model_call` | 注入 `<system-reminder>`（日期+memory），保持 system prompt 静态以复用 prefix cache。🆕 v2.1.0-rc0：插入 transient `<project>` 块 + 有界 `<documents>` 索引 | ❌ |
| 16 | **SkillActivationMiddleware** | `wrap_model_call` | 检测 `/skill-name task` 语法，加载 SKILL.md。每个 run 只激活一次 | ❌ |
| 17 | **DeferredToolPromotionAuditMiddleware** 🆕 | — | 🆕 sync #6（36→37）：持久化实际生效的 deferred-tool promotion 决策（不含敏感 payload），供可观测性/审计回放。位置：SkillActivation 之后、SkillToolPolicy 之前 | ✅ `tool_search.enabled` |
| 18 | **SkillToolPolicyMiddleware** 🆕 | `wrap_model_call` | 应用 `allowed-tools` 只对 slash-activated/loaded skill；passive skill 不限制全局 toolset | ❌ |
| 19 | **DurableContextMiddleware** | `wrap_model_call` | 捕获 task delegation + skill 引用到 ThreadState，summarization 前保存。sub agent 也附加 | ❌ |
| 20 | **SummarizationMiddleware** | `after_agent` | 上下文过长时自动压缩旧消息为摘要。🆕 `fraction` 阈值从 summary 模型声明的 `context_window` 解析 | ✅ `summarization.enabled` |
| 21 | **TodoListMiddleware** | `after_agent` | Plan mode 的任务追踪，提供 `write_todos` 工具 | ✅ `is_plan_mode` |
| 22 | **TokenUsageMiddleware** | `after_agent` | 记录每轮 token 消耗，子 agent 用量按消息位置回并 | ✅ `token_usage.enabled` |
| 23 | **TitleMiddleware** | `after_agent` | 第一次对话后自动生成线程标题。🆕 attachment-only 会话用文件名生成标题 | ❌ |
| 24 | **MemoryMiddleware** | `after_agent` | 把对话推入记忆队列，后台异步更新用户记忆 | ❌ |
| 25 | **ViewImageMiddleware** | `wrap_model_call` | 把用户上传图片转 base64 注入给模型。🆕 字节来源校验：优先从大小+SHA-256 匹配的宿主同步副本读取 | 模型支持 vision 时 |
| 26 | **McpRoutingMiddleware** 🆕 | `wrap_model_call` | 自动提升匹配的 deferred MCP tool schema（`auto_promote_top_k` 默认 3，不执行 tool） | ✅ `tool_search.enabled` |
| 27 | **DeferredToolFilterMiddleware** | `wrap_model_call` | 隐藏 deferred MCP tool schema，直到 `tool_search` 或 McpRouting 提升 | ✅ `tool_search.enabled` |
| 28 | **SystemMessageCoalescingMiddleware** | `wrap_model_call` | 合并多条 SystemMessage 为一条——兼容严格后端（vLLM/SGLang/Anthropic） | ❌ |
| 29 | **SubagentLimitMiddleware** | `after_model` | 截断超量 `task` 调用 + per-run total delegation cap（默认 6） | ✅ `subagent_enabled` |
| 30 | **LoopDetectionMiddleware** | `after_model` | 检测重复工具调用模式（窗口化 frequency counter）。🆕 检测事件持久化到 `runtime/events` | ✅ `loop_detection.enabled` |
| 31 | **TokenBudgetMiddleware** | `after_model` | 强制 token 预算上限，跨 lead + subagent 共享（warn 注入警告，hard-stop 强制作答） | ✅ `token_budget.enabled` |
| 32 | **Custom middlewares 槽位** | 任意 | 你的自定义 middleware 插在这里 | ✅ 传了才有 |
| 33 | **ConfiguredExtensionMiddleware** 🆕 | 任意 | config 声明的 `AgentMiddleware` 类路径（`module.path:ClassName`），经 reflection 解析。**可信 operator 配置** | ✅ `extensions.middlewares` 有配置 |
| 34 | **TerminalResponseMiddleware** | `after_model` | 空 terminal AIMessage 恢复：注入 hidden recovery prompt 并重试一次 | ❌ |
| 35 | **ModelLengthFinishReasonMiddleware** 🆕 | `after_model` | provider 长度截断（`finish_reason=length`/`MAX_TOKENS`）标记 `stop_reason=model_length_capped`，保留原文 | ❌ |
| 36 | **SafetyFinishReasonMiddleware** | `after_model` | 检测模型安全拦截（`finish_reason=content_filter`），清除被污染的 tool_calls | ✅ `safety_finish_reason.enabled` |
| 37 | **ClarificationMiddleware** | `after_model` | 拦截 `ask_clarification`，`Command(goto=END)` 中断。RunJournal 做 root-run final reconciliation。**必须最后** | ❌ |

---

## 按 Hook 类型归类

### `wrap_model_call`（洋葱拦截器，在 model node 内部）
1, 2, 3, 8, 15, 16, 18, 19, 25, 26, 27, 28

### `wrap_tool_call`（洋葱拦截器，在 ToolNode 内部）
9, 10, 11, 12

### `after_tool`
13, 14

### `before_agent`（图启动时执行一次）
4, 5, 6, 7

### `after_model`（每次 LLM 调用后执行——反向顺序！）
29, 30, 31, 34, 35, 36

### `after_agent`（每次 step 结束后执行）
20, 21, 22, 23, 24

### 条件/任意 hook
17（`tool_search.enabled` 时）、32（自定义）、33（任意 hook 的透明包装）、37（`after_model` 洋葱链 + `Command(goto=END)`）

> **after_model 和 after_agent 是两类不同的 hook 点。** `after_model` 在 LangChain 的反向链上执行（后加的 middleware 先执行），`after_agent` 在 step 结束时按正向顺序执行。ClarificationMiddleware（#37，链上最后一个）在 after_model 反向链上第一个检查模型输出，发现 `ask_clarification` 即 `Command(goto=END)` 中断整个 graph。ConfiguredExtension（#33）是任意 hook 的透明包装，行为取决于被加载的类。

---

## sync #6（v2.1.0-rc0）相比旧版的变化

| 变化 | 详情 |
|------|------|
| **Middleware 总数** | 29 → 33（sync #3）；33 → 35（sync #4）；35 → 37（**sync #5：+ToolReceiptMiddleware #9；sync #6：+DeferredToolPromotionAuditMiddleware #17，36→37**） |
| **共享基础层** | 12 → 13（+ToolResultSanitization）；**13 → 14（sync #5：+ToolReceipt #9）** |
| **Lead-only 层** | 20 → 22（sync #4）；**22 → 23（sync #6：+DeferredToolPromotionAudit #17）** |
| **🆕 ToolReceipt（#9）** | 确定性 tool 收据 + 隐藏 ledger，最外层 `wrap_tool_call`，防短路漏记账 |
| **🆕 DeferredToolPromotionAudit（#17）** | 持久化实际生效的 deferred-tool promotion 决策，供审计回放 |
| **DynamicContext 增强** | transient `<project>` 块 + 有界 `<documents>` 索引注入，`project_context_revision` 上下文事件 |
| **ToolOutputBudget 增强** | superseded write elision；改写经共享 `tool_call_args.py` 在全部四个 AIMessage 参数面一致重写 |
| **ReadBeforeWrite 增强** | `elide_blocked_payloads`：被拦截调用 payload 在 model-bound request 中占位符化 |
| **LoopDetection/ToolProgress 增强** | 检测/phase 迁移事件持久化到 `runtime/events`（run 重放可审计） |
| **其他增强** | Title（attachment-only 文件名标题）、ViewImage（sha256 宿主副本）、Summarization（fraction 从模型 `context_window` 解析）、Guardrail（authz context）、Dangling（malformed id 恢复）、SubagentLimit（delegation ledger + total cap）、SkillActivation（每 run 只激活一次） |
| **Declarative layered builder** | Middleware 组装改用声明式分层构建器 |
