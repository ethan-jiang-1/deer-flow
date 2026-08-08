# DeerFlow 全部 35 个 Middleware 一览（2.1.0，sync #4）

## 怎么读这张表

- **#**：在 middleware 链中的位置（也是执行顺序）
- **层**：共享基础层 = lead agent 和 sub agent 都加载；Lead-only = 仅主 agent 加载
- **Hook**：这个 middleware 覆写了哪个 hook（决定它变成哪种 node 或拦截器）
- **可选？**：✅ = 有配置开关/条件触发，可能不在链上；❌ = 始终加载
- **🆕**：2.1.0 新增的 middleware

---

## 共享基础层（lead + sub agent 都加载，13 个）

| # | Middleware | Hook | 一句话 | 可选？ |
|---|-----------|------|--------|--------|
| 1 | **InputSanitizationMiddleware** | `wrap_model_call` | 转义 XML tag + 阻断 forged framework tag，防 prompt injection | ❌ |
| 2 | **ToolOutputBudgetMiddleware** | `wrap_model_call` | 截断过大的 tool 输出，防止撑爆上下文 | ❌ |
| 3 | **ToolResultSanitizationMiddleware** 🆕 | `wrap_model_call` | 中性化远程内容 tool 结果中的 injection 标签（web_fetch/search 等） | ❌ |
| 4 | **ThreadDataMiddleware** | `before_agent` | 创建线程隔离目录（workspace/uploads/outputs） | ❌ |
| 5 | **UploadsMiddleware** | `before_agent` | 检测新上传的文件，注入给 agent（lead only） | ❌ |
| 6 | **SandboxMiddleware** | `before_agent` | 获取 sandbox，存 `sandbox_id` 到 state | ❌ |
| 7 | **DanglingToolCallMiddleware** | `before_agent` | 补充缺失的 ToolMessage + malformed id 恢复 + 无效参数清洗 | ❌ |
| 8 | **LLMErrorHandlingMiddleware** | `before_agent` | LLM API 出错时规范化错误为可恢复的 assistant-facing 错误 | ❌ |
| 9 | **GuardrailMiddleware** | `wrap_tool_call` | 工具执行前授权检查，`fail_closed` 策略。🆕 GuardrailRequest 增强（thread_id、user_id、authz_attributes） | ✅ `guardrails.enabled` |
| 10 | **SandboxAuditMiddleware** | `wrap_tool_call` | 审计沙箱 bash shell/file 操作，记录安全日志 | ❌ |
| 11 | **ReadBeforeWriteMiddleware** | `wrap_tool_call` | 写文件前检查是否读过——sha256 hash "读戳" 防盲目覆盖 | ✅ `read_before_write.enabled` |
| 12 | **ToolProgressMiddleware** | `after_tool` | 检测工具停滞（反复调用无新结果），状态机：ACTIVE→WARNED→BLOCKED | ✅ `tool_progress.enabled` |
| 13 | **ToolErrorHandlingMiddleware** | `after_tool` | **核心**：捕获工具异常 → error ToolMessage + 注入 `deerflow_tool_meta`（status/error_type/recoverable/recommended_action） | ❌ |

> 共享基础层总结：**13 个（🆕 +1：ToolResultSanitizationMiddleware）。sub agent 也加载其中大部分——不含 Uploads 和 DanglingToolCall，额外附加 DurableContextMiddleware + SystemMessageCoalescingMiddleware + guard trio。**

---

## Lead-only 层（仅主 agent 加载，22 个）

| # | Middleware | Hook | 一句话 | 可选？ |
|---|-----------|------|--------|--------|
| 14 | **DynamicContextMiddleware** | `wrap_model_call` | 注入当前日期 + 可选记忆到首条 HumanMessage | ❌ |
| 15 | **SkillActivationMiddleware** | `wrap_model_call` | 检测 `/skill-name task` 语法，加载 SKILL.md。🆕 每个 run 只激活一次 | ❌ |
| 16 | **SkillToolPolicyMiddleware** 🆕 | `wrap_model_call` | 应用 `allowed-tools` 只对 slash-activated/loaded skill；passive skill 不限制全局 toolset | ❌ |
| 17 | **DurableContextMiddleware** | `wrap_model_call` | 从消息中提取持久上下文（task delegation + skill 引用），防 summarization 丢数据。sub agent 也附加 | ❌ |
| 18 | **SummarizationMiddleware** | `after_agent` | 上下文过长时自动压缩旧消息为摘要。🆕 sub agent 继承此 middleware | ✅ `summarization.enabled` |
| 19 | **TodoListMiddleware** | `after_agent` | Plan mode 的任务追踪，提供 `write_todos` 工具 | ✅ `is_plan_mode` |
| 20 | **TokenUsageMiddleware** | `after_agent` | 记录每轮 token 消耗，子 agent 用量按消息位置回并 | ✅ `token_usage.enabled` |
| 21 | **TitleMiddleware** | `after_agent` | 第一次对话后自动生成线程标题 | ❌ |
| 22 | **MemoryMiddleware** | `after_agent` | 把对话推入记忆队列，后台异步更新用户记忆 | ❌ |
| 23 | **ViewImageMiddleware** | `wrap_model_call` | 把用户上传图片转 base64 注入给模型 | 模型支持 vision 时 |
| 24 | **McpRoutingMiddleware** 🆕 | `wrap_model_call` | 自动提升匹配的 deferred MCP tool schema（基于 routing keywords） | ✅ `tool_search.enabled` |
| 25 | **DeferredToolFilterMiddleware** | `wrap_model_call` | 隐藏 deferred MCP tool schema，直到 `tool_search` 或 McpRouting 提升 | ✅ `tool_search.enabled` |
| 26 | **SystemMessageCoalescingMiddleware** | `wrap_model_call` | 合并多条 SystemMessage 为一条——兼容严格后端（vLLM/SGLang/Anthropic） | ❌ |
| 27 | **SubagentLimitMiddleware** | `after_model` | 截断超量 `task` 调用 + 🆕 per-run total delegation cap（默认 6） | ✅ `subagent_enabled` |
| 28 | **LoopDetectionMiddleware** | `after_model` | 检测重复工具调用模式。🆕 窗口化 frequency counter——长 run 不误触发 | ✅ `loop_detection.enabled` |
| 29 | **TokenBudgetMiddleware** | `after_model` | 强制 token 预算上限，跨 lead + subagent 共享 | ✅ `token_budget.enabled` |
| 30 | **Custom middlewares 槽位** | 任意 | 你的自定义 middleware 插在这里 | ✅ 传了才有 |
| 31 | **ConfiguredExtensionMiddleware** 🆕 | 任意 | config 声明的 `AgentMiddleware` 类路径（`module.path:ClassName`），经 reflection 解析。**可信 operator 配置** | ✅ `extensions.middlewares` 有配置 |
| 32 | **TerminalResponseMiddleware** | `after_model` | 空 terminal AIMessage 恢复：注入 hidden recovery prompt 并重试一次 | ❌ |
| 33 | **ModelLengthFinishReasonMiddleware** 🆕 | `after_model` | provider 长度截断（`finish_reason=length`/`MAX_TOKENS`/`max_tokens`）的终态 assistant 响应标记 `stop_reason=model_length_capped`，保留原文 | ❌ |
| 34 | **SafetyFinishReasonMiddleware** | `after_model` | 检测模型安全拦截（`finish_reason=content_filter`），阻止工具执行 | ✅ `safety_finish_reason.enabled` |
| 35 | **ClarificationMiddleware** | `after_agent` | 拦截 `ask_clarification`，`Command(goto=END)` 中断。RunJournal 做 root-run final reconciliation | ❌ |

---

## 按 Hook 类型归类

### `wrap_model_call`（洋葱拦截器，在 model node 内部）
1, 2, 3, 14, 15, 16, 17, 23, 24, 25, 26（共 11 个）

### `wrap_tool_call`（洋葱拦截器，在 ToolNode 内部）
9, 10, 11（共 3 个）

### `after_tool`
12, 13（共 2 个）

### `before_agent`（图启动时执行一次）
4, 5, 6, 7, 8（共 5 个）

### `after_model`（每次 LLM 调用后执行——反向顺序！）
27, 28, 29, 32, 33, 34（共 6 个）

### `after_agent`（每次 step 结束后执行）
18, 19, 20, 21, 22, 35（共 6 个）

> **after_model 和 after_agent 是两类不同的 hook 点。** `after_model` 在 LangChain 的反向链上执行（后加的 middleware 先执行），`after_agent` 在 step 结束时按正向顺序执行。ClarificationMiddleware（#35，after_agent 的最后）通过 `Command(goto=END)` 中断整个 graph。ConfiguredExtension（#31）是任意 hook 的透明包装，行为取决于被加载的类。

---

## 2.1.0 相比旧版的变化

| 变化 | 详情 |
|------|------|
| **Middleware 总数** | 29 → 33（sync #3）；**33 → 35（sync #4：+ConfiguredExtension, +ModelLengthFinishReason）** |
| **共享基础层** | 12 → 13（+ToolResultSanitizationMiddleware） |
| **Lead-only 层** | 17 → 20（sync #3）；**20 → 22（sync #4：+ConfiguredExtension #31, +ModelLengthFinishReason #33）** |
| **Hook 重构** | `after_model` 拆分：部分移到 `after_agent`（Summarization、Memory、Clarification 等），部分留在 `after_model`（guard trio） |
| **Guardrail 增强** | GuardrailRequest 新增 `thread_id`、`user_id`、`is_subagent`、`authz_attributes` |
| **LoopDetection 增强** | 窗口化 frequency counter——长 run 不误触发 |
| **Dangling 增强** | 新增 malformed tool-call id 恢复 + 无效参数清洗 |
| **SubagentLimit 增强** | 新增 per-run total delegation cap（delegation ledger） |
| **Declarative layered builder** | Middleware 组装改用声明式分层构建器 |
