---
title: "Middleware 完整目录"
description: "29 个 middleware，按 hook 点分组。每个条目：文件位置、触发点、位置编号、用途、配置项、非显而易见的细节。"
topics: [middleware, hooks, interceptor-chain]
---

# Middleware 完整目录

29 个 middleware，分两阶段组装。来源：`build_lead_runtime_middlewares()`（前 12 个）+ `build_middlewares()`（后 17 个）。

## 共享基础层（1-12，Lead 和 Sub-agent 共用）

| # | Middleware | 文件 | 条件 | 一句话 |
|---|-----------|------|------|--------|
| 1 | **InputSanitizationMiddleware** | `input_sanitization_middleware.py` | 始终 | 🆕 转义 `<system>` 等 XML tag 防 prompt injection，包裹 `--- BEGIN USER INPUT ---` 边界，保留原文到 `ORIGINAL_USER_CONTENT_KEY`。只在 `wrap_model_call` 执行，不修改 checkpoint |
| 2 | **ToolOutputBudgetMiddleware** | `tool_output_budget_middleware.py` | 始终 | 🆕 超大 tool 结果写入磁盘（`externalize_min_chars`），替换为 head+tail 预览 + `read_file` 引用路径。fallback: inline 截断 |
| 3 | **ThreadDataMiddleware** | `thread_data_middleware.py` | 始终 | 创建 per-thread 目录 `users/{uid}/threads/{tid}/user-data/{workspace,uploads,outputs}` |
| 4 | **UploadsMiddleware** | `uploads_middleware.py` | Lead only | 追踪已上传文件，注入到会话上下文 |
| 5 | **SandboxMiddleware** | `../sandbox/middleware.py` | 始终 | 获取/释放沙箱，存储 `sandbox_id` |
| 6 | **DanglingToolCallMiddleware** | `dangling_tool_call_middleware.py` | Lead only | 补丁缺失的 ToolMessage（用户中断也处理 `invalid_tool_calls`） |
| 7 | **LLMErrorHandlingMiddleware** | `llm_error_handling_middleware.py` | 始终 | 规范化 provider 调用错误为可恢复的 assistant-facing 错误 |
| 8 | **GuardrailMiddleware** | `../guardrails/middleware.py` | `guardrails.enabled` | Pre-tool-call 鉴权，`fail_closed` 策略。内置 `AllowlistProvider` |
| 9 | **SandboxAuditMiddleware** | `sandbox_audit_middleware.py` | 始终 | 审计 shell/file 操作的安全日志 |
| 10 | **ReadBeforeWriteMiddleware** | `read_before_write_middleware.py` | `read_before_write.enabled` | 🆕 写文件前必须有 `read_file` 记录。sha256 hash "读戳" 在校验失败时阻断 `write_file`/`str_replace`。按 `(thread, path)` 串行化 |
| 11 | **ToolProgressMiddleware** | `tool_progress_middleware.py` | `tool_progress.enabled` | 🆕 停滞检测状态机：ACTIVE→WARNED→BLOCKED。三个错误类别（可恢复/暂态/停止），Jaccard 去重检测。位于 ToolErrorHandlingMiddleware 外层 |
| 12 | **ToolErrorHandlingMiddleware** | `tool_error_handling_middleware.py` | 始终 | 工具异常→错误 ToolMessage。🔄 重构：注入 `deerflow_tool_meta`（status/error_type/recoverable/recommended_action） |

## Lead-only 层（13-29）

| # | Middleware | 文件 | 条件 | 一句话 |
|---|-----------|------|------|--------|
| 13 | **DynamicContextMiddleware** | `dynamic_context_middleware.py` | 始终 | 🆕 注入 `<system-reminder>`（日期+memory），保持 system prompt 静态以复用 prefix cache。ID-swap 技术：HumanMessage ID 转移给 SystemMessage |
| 14 | **SkillActivationMiddleware** | `skill_activation_middleware.py` | 始终 | 🆕 检测 `/skill-name task` 触发语法，注入 SKILL.md body。重算 request-scoped secret 绑定（slash + in-context 双源） |
| 15 | **DurableContextMiddleware** | `durable_context_middleware.py` | 始终 | 🆕 捕获 `task` delegation + skill 引用到 ThreadState，在 summarization 压缩前保存。每次模型请求前注入 `<durable_context_data>` |
| 16 | **SummarizationMiddleware** | `summarization_middleware.py` | `summarization.enabled` | 上下文压缩，防止超出 token 限制 |
| 17 | **TodoListMiddleware** | `todo_middleware.py` | `is_plan_mode` | `write_todos` 任务跟踪 |
| 18 | **TokenUsageMiddleware** | `token_usage_middleware.py` | `token_usage.enabled` | Token 用量统计，subagent 用量按消息位置回并 |
| 19 | **TitleMiddleware** | `title_middleware.py` | 始终 | 首次交换完成后自动生成会话标题 |
| 20 | **MemoryMiddleware** | `memory_middleware.py` | 始终 | 排队异步更新记忆（30s debounce） |
| 21 | **ViewImageMiddleware** | `view_image_middleware.py` | model `supports_vision` | 注入 base64 图片 |
| 22 | **DeferredToolFilterMiddleware** | `deferred_tool_filter_middleware.py` | `deferred_setup` 有 deferred_names | 隐藏 MCP tool schema，直到 `tool_search` promote。读取 `ThreadState.promoted` |
| 23 | **SystemMessageCoalescingMiddleware** | `system_message_coalescing_middleware.py` | 始终 | 🆕 合并所有 SystemMessage 为单条（修复 vLLM/SGLang/Anthropic 拒绝多条 system message） |
| 24 | **SubagentLimitMiddleware** | `subagent_limit_middleware.py` | `subagent_enabled` | 截断多余 `task` 调用，上限 3（可配 2-4） |
| 25 | **LoopDetectionMiddleware** | `loop_detection_middleware.py` | `loop_detection.enabled` | 检测重复 tool-call 循环，hard-stop 清除后强制作答 |
| 26 | **TokenBudgetMiddleware** | `token_budget_middleware.py` | `token_budget.enabled` | 🆕 Per-run token 限制：warn_threshold 注入警告，hard_stop_threshold 强制作答 |
| 27 | **Custom middlewares** | (caller-supplied) | 传入 `custom_middlewares=[]` | 用户注入的自定义中间件 |
| 28 | **SafetyFinishReasonMiddleware** | `safety_finish_reason_middleware.py` | `safety_finish_reason.enabled` | 检测 provider 安全终止（`finish_reason=content_filter`），抑制 tool 执行 |
| 29 | **ClarificationMiddleware** | `clarification_middleware.py` | 始终（必须最后） | 拦截 `ask_clarification`，`Command(goto=END)` 中断 |

## 相比旧版的变化

| 变化 | 详情 |
|------|------|
| **新增 10 个** | InputSanitization, ToolOutputBudget, ReadBeforeWrite, ToolProgress, DynamicContext, SkillActivation, DurableContext, SystemMessageCoalescing, TokenBudget, Guardrail（原为可选，现正式纳入） |
| **重构 1 个** | ToolErrorHandlingMiddleware 新增 `deerflow_tool_meta` 结构化信号 |
| **顺序重组** | 5 个新 always-on middleware 插入到前面（1-2）和中间（13-15, 23），改变了整体顺序 |
| **ThreadState 扩展** | 新增 `delegations`, `skill_context`, `summary_text`, `promoted` 字段 |

## Hook 点分组

| Hook | 参与 middleware |
|------|---------------|
| `wrap_model_call` (before LLM) | 1, 2, 13, 14, 15, 21, 22, 23 |
| `after_model` | 24, 25, 26, 28 |
| `wrap_tool_call` (before tool) | 8, 10 |
| `after_tool` | 11, 12 |
| `before_agent` | 3, 4, 5, 6, 7, 9 |
| `after_agent` | 16, 17, 18, 19, 20, 29 |
