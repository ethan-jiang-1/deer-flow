---
title: "Middleware 完整目录"
description: "35 个 middleware，按 hook 点分组。每个条目：文件位置、触发点、位置编号、用途、配置项、非显而易见的细节。"
topics: [middleware, hooks, interceptor-chain]
---

# Middleware 完整目录

35 个 middleware，分两阶段组装。来源：`build_lead_runtime_middlewares()`（前 13 个）+ `build_middlewares()`（后 22 个）。

## 共享基础层（1-13，Lead 和 Sub-agent 共用）

| # | Middleware | 文件 | 条件 | 一句话 |
|---|-----------|------|------|--------|
| 1 | **InputSanitizationMiddleware** | `input_sanitization_middleware.py` | 始终 | 转义 `<system>` 等 XML tag 防 prompt injection，包裹 `--- BEGIN USER INPUT ---` 边界，阻断 forged framework tag（`</tool_response>` 等），保留原文到 `ORIGINAL_USER_CONTENT_KEY` |
| 2 | **ToolOutputBudgetMiddleware** | `tool_output_budget_middleware.py` | 始终 | 超大 tool 结果写入磁盘（`externalize_min_chars`），替换为 head+tail 预览 + `read_file` 引用路径 |
| 3 | **ToolResultSanitizationMiddleware** | `tool_result_sanitization_middleware.py` | 始终 | 🆕 中性化远程内容 tool 结果中的 injection 标签（`web_fetch`/`web_search`/`image_search`/`web_capture`），name-based allowlist |
| 4 | **ThreadDataMiddleware** | `thread_data_middleware.py` | 始终 | 创建 per-thread 目录。**顺序变更**：现在在 Uploads 之前运行 |
| 5 | **UploadsMiddleware** | `uploads_middleware.py` | Lead only | 追踪已上传文件，注入到会话上下文 |
| 6 | **SandboxMiddleware** | `../../sandbox/middleware.py` | 始终 | 获取/释放沙箱，存储 `sandbox_id` |
| 7 | **DanglingToolCallMiddleware** | `dangling_tool_call_middleware.py` | 始终 | 补丁缺失的 ToolMessage + malformed tool-call id 恢复 + 无效参数清洗。用户中断和 strict provider（vLLM/SGLang）不会 400 |
| 8 | **LLMErrorHandlingMiddleware** | `llm_error_handling_middleware.py` | 始终 | 规范化 provider 调用错误为可恢复的 assistant-facing 错误。Subagent 用 marker 区分真实 failure vs 正常完成 |
| 9 | **GuardrailMiddleware** | `../../guardrails/middleware.py` | `guardrails.enabled` | Pre-tool-call 鉴权，`fail_closed` 策略。🆕 GuardrailRequest 增强：`thread_id`、`user_id`、`is_subagent`、`authz_attributes` |
| 10 | **SandboxAuditMiddleware** | `sandbox_audit_middleware.py` | 始终 | 审计 bash shell/file 操作的安全日志 |
| 11 | **ReadBeforeWriteMiddleware** | `read_before_write_middleware.py` | `read_before_write.enabled` | 写文件前必须有 `read_file` 记录的 sha256 hash "读戳"，按 `(thread, path)` 串行化 |
| 12 | **ToolProgressMiddleware** | `tool_progress_middleware.py` | `tool_progress.enabled` | 停滞检测状态机：ACTIVE→WARNED→BLOCKED。三个错误类别（可恢复/暂态/停止），Jaccard 去重 |
| 13 | **ToolErrorHandlingMiddleware** | `tool_error_handling_middleware.py` | 始终 | 工具异常→错误 ToolMessage。注入 `deerflow_tool_meta`（status/error_type/recoverable/recommended_action/source）。Task tool 结果从同一结构化元数据生成 |

## Lead-only 层（14-33）

| # | Middleware | 文件 | 条件 | 一句话 |
|---|-----------|------|------|--------|
| 14 | **DynamicContextMiddleware** | `dynamic_context_middleware.py` | 始终 | 注入 `<system-reminder>`（日期+memory），保持 system prompt 静态以复用 prefix cache |
| 15 | **SkillActivationMiddleware** | `skill_activation_middleware.py` | 始终 | 检测 `/skill-name task` 触发语法，注入 SKILL.md body。重算 request-scoped secret 绑定（slash + in-context 双源）。**每个 run 只激活一次** |
| 16 | **SkillToolPolicyMiddleware** | `skill_tool_policy_middleware.py` | 始终 | 🆕 应用 `allowed-tools` 只对 slash-activated 或实际 loaded 的 lead-agent skill；passive enabled skill 不限制全局 toolset。`task` 需显式声明 |
| 17 | **DurableContextMiddleware** | `durable_context_middleware.py` | 始终 | 捕获 `task` delegation + skill 引用到 ThreadState，summarization 前保存。每次模型请求前注入 `durable_context_data`。Subagent 也附此 middleware |
| 18 | **SummarizationMiddleware** | `summarization_middleware.py` | `summarization.enabled` | 上下文压缩，防止超出 token 限制。Subagent 继承此 middleware |
| 19 | **TodoListMiddleware** | `todo_middleware.py` | `is_plan_mode` | `write_todos` 任务跟踪 |
| 20 | **TokenUsageMiddleware** | `token_usage_middleware.py` | `token_usage.enabled` | Token 用量统计，subagent 用量按消息位置回并 |
| 21 | **TitleMiddleware** | `title_middleware.py` | 始终 | 首次交换完成后自动生成会话标题 |
| 22 | **MemoryMiddleware** | `memory_middleware.py` | 始终 | 排队异步更新记忆（debounced），捕获 `user_id` 和 `trace_id` |
| 23 | **ViewImageMiddleware** | `view_image_middleware.py` | model `supports_vision` | 注入 base64 图片数据 |
| 24 | **McpRoutingMiddleware** | `mcp_routing_middleware.py` | `tool_search.enabled` + routing metadata | 🆕 自动提升匹配的 deferred MCP tool schema。匹配最新 HumanMessage，使用 `auto_promote_top_k`（默认 3），不执行 tool |
| 25 | **DeferredToolFilterMiddleware** | `deferred_tool_filter_middleware.py` | `tool_search.enabled` | 隐藏 deferred MCP tool schema，直到 `tool_search` 或 `McpRoutingMiddleware` promote |
| 26 | **SystemMessageCoalescingMiddleware** | `system_message_coalescing_middleware.py` | 始终 | 合并所有 SystemMessage 为单条（修复 strict backends 拒绝非 leading system message） |
| 27 | **SubagentLimitMiddleware** | `subagent_limit_middleware.py` | `subagent_enabled` | 截断多余 `task` 调用。🆕 同时执行 per-run total delegation cap（default 6），防止无限分批绕过 |
| 28 | **LoopDetectionMiddleware** | `loop_detection_middleware.py` | `loop_detection.enabled` | 检测重复 tool-call 循环。🆕 窗口化 frequency counter——长 run 不误触发 |
| 29 | **TokenBudgetMiddleware** | `token_budget_middleware.py` | `token_budget.enabled` | Per-run token 限制，跨 lead + subagent 共享。warn 注入警告，hard-stop 强制作答 |
| 30 | **Custom middlewares** | (caller-supplied) | 传入 `custom_middlewares=[]` | 用户注入的自定义中间件 |
| 31 | **ConfiguredExtensionMiddleware** | `configured_extensions.py` | `extensions.middlewares` 有配置 | 🆕 从 config 加载零参数 `AgentMiddleware` 类路径（`module.path:ClassName`），经 `reflection.resolve_class` 解析，失败时 loud fail。**可信 operator 配置**——middleware 路径会实例化任意代码 |
| 32 | **TerminalResponseMiddleware** | `terminal_response_middleware.py` | 始终 | 空 terminal AIMessage 恢复：注入 hidden recovery prompt 并重试一次。二次空响应替换为 error fallback |
| 33 | **ModelLengthFinishReasonMiddleware** | `model_length_finish_reason_middleware.py` | 始终 | 🆕 provider 长度截断（`finish_reason=length` / `MAX_TOKENS` / `stop_reason=max_tokens`）的终态 assistant 响应标记 `stop_reason=model_length_capped`。保留原文、不重解析 XML 式 tool call、无视 tool-call intent 或无可见内容的消息 |
| 34 | **SafetyFinishReasonMiddleware** | `safety_finish_reason_middleware.py` | `safety_finish_reason.enabled` | 检测 provider 安全终止（`finish_reason=content_filter`），清除被污染的 tool_calls |
| 35 | **ClarificationMiddleware** | `clarification_middleware.py` | 始终（必须最后） | 拦截 `ask_clarification`，`Command(goto=END)` 中断。RunJournal 做 root-run final reconciliation |

## 相比旧版的变化

| 变化 | 详情 |
|------|------|
| **新增 4 个（同步 #3）** | ToolResultSanitization（#3）、SkillToolPolicy（#16）、McpRouting（#24）、TerminalResponse |
| **新增 2 个（同步 #4）** | ConfiguredExtension（#31）、ModelLengthFinishReason（#33） |
| **增强 5 个** | Guardrail（authz context）、Dangling（malformed id 恢复）、SubagentLimit（delegation ledger + total cap）、LoopDetection（窗口化 counter）、SkillActivation（每 run 只激活一次） |
| **顺序变更** | ThreadData 移到 Uploads 之前（#4→#5）；新增 ToolResultSanitization 插入 #3 位置 |
| **Declarative layered builder** | Middleware 组装改用声明式分层构建器 |

## Hook 点分组

| Hook | 参与 middleware |
|------|---------------|
| `wrap_model_call` (before LLM) | 1, 2, 3, 14, 15, 16, 17, 23, 24, 25, 26 |
| `after_model` | 27, 28, 29, 32, 33, 34 |
| `wrap_tool_call` (before tool) | 9, 10, 11 |
| `after_tool` | 12, 13 |
| `before_agent` | 4, 5, 6, 7, 8 |
| `after_agent` | 18, 19, 20, 21, 22, 35 |

> ConfiguredExtension（#31）是任意 hook 的透明包装——它实例化 config 声明的 middleware，钩子行为取决于被加载的类。

## 辅助模块（非 middleware，但被 middleware 使用）

| 模块 | 用途 |
|------|------|
| `delegation_ledger.py` | SubagentLimit 使用的委托账本（去重 + total cap） |
| `skill_context.py` | SkillToolPolicy 使用的 skill 上下文管理 |
| `tool_result_meta.py` | ToolErrorHandling 使用的结构化 tool result 元数据 |
| `tool_output_synopsis.py` | 🆕 超大 tool output 的结构化摘要生成 |
| `_bounded_dict.py` | LoopDetection 窗口化 counter 的有界字典 |
| `safety_termination_detectors.py` | SafetyFinishReason 的终止检测器 |
| `model_length_termination_detectors.py` | 🆕 ModelLengthFinishReason 的 provider 终止检测器（`default_detectors()`） |
