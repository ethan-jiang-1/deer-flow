---
title: "Middleware 完整目录"
description: "37 个 middleware，按 hook 点分组。每个条目：文件位置、触发点、位置编号、用途、配置项、非显而易见的细节。"
topics: [middleware, hooks, interceptor-chain]
---

# Middleware 完整目录

> 37 个 middleware，分两阶段组装。来源：`build_lead_runtime_middlewares()`（前 14 个）+ `build_middlewares()`（后 23 个）。

> **"37" 的口径**（v2.1.0 用代码核实）：= **35 个内置 middleware 类** + **2 个通用槽位**（#32 caller 传入的 `custom_middlewares`、#33 config 声明的 `ConfiguredExtensionMiddleware`——`configured_extensions.py` 只提供 `load_configured_extension_middlewares()`，本身不定义类）。35 个内置类 = `agents/middlewares/` 里被 lead 链引用的 33 个类（该目录共 34 个 `class *Middleware` 定义，减去仅 subagent 使用的 `dynamic_context_middleware.py::SubagentDateContextMiddleware`）**+** `sandbox/middleware.py::SandboxMiddleware` **+** `guardrails/middleware.py::GuardrailMiddleware`。
>
> 与 `agents/middlewares/AGENTS.md` 的 **36** 号不冲突：AGENTS.md 不重排编号，只把 `ToolReceiptMiddleware`+`ToolErrorHandlingMiddleware` 合并成同一条 #13；本表把它们拆成 #9/#14（两个 `GuardrailMiddleware` 实例仍合并记作同一行 #10）。因此 **AGENTS.md 的 36 条与本表的 37 条之差只是合并口径差异**，不是能力差异。
>
> 单链**实际实例数**随配置变化（本表列的是"每种可能的条目"，不是某次装配的条数）。按各 Config 类的字段默认值，默认 lead 链 = **25 个实例**（基础层 12：三个 sanitization/budget wrapper + ThreadData/Uploads/Sandbox + Dangling/LLMError/ToolReceipt/SandboxAudit/ReadBeforeWrite/ToolErrorHandling；lead-only 13：9 个无条件 + TokenUsage/Memory/LoopDetection/SafetyFinishReason）——`tool_progress.enabled` / `token_budget.enabled` / `summarization.enabled` / `guardrails.enabled` / `authorization.enabled` 默认关，`verification.receipts_enabled` / `read_before_write.enabled` / `safety_finish_reason.enabled` / `loop_detection.enabled` / `token_usage.enabled` 默认开；模型支持 vision、开 plan mode / subagent / deferred setup / 自定义扩展时再加。两个 guardrail 门与所有可选项都打开时最多 **38 个实例**。

## 共享基础层（1-14，Lead 和 Sub-agent 共用）

| # | Middleware | 文件 | 条件 | 一句话 |
|---|-----------|------|------|--------|
| 1 | **InputSanitizationMiddleware** | `input_sanitization_middleware.py` | 始终 | 转义 `<system>` 等 XML tag 防 prompt injection，包裹 `--- BEGIN USER INPUT ---` 边界，阻断 forged framework tag（`</tool_response>` 等），保留原文到 `ORIGINAL_USER_CONTENT_KEY` |
| 2 | **ToolOutputBudgetMiddleware** | `tool_output_budget_middleware.py` | 始终 | 超大 tool 结果写入磁盘（`externalize_min_chars`），替换为 head+tail 预览 + `read_file` 引用路径。🆕 **superseded write elision**（`tool_output.elide_superseded_writes` 默认开）：成功的 `write_file` 一旦同路径出现更新的成功 read/write/str_replace，其 `content` 参数在 model-bound request 中替换为指向 `read_file` 的占位符（`superseded_write_min_chars` 2000 起、最新 `keep_recent_writes` 1 条始终保留）——磁盘文件才是 source of truth，读前写门强制先读。改写经由共享的 `tool_call_args.py` 在**全部四个 AIMessage 参数面**一致重写（provider 适配器读取面不一致） |
| 3 | **ToolResultSanitizationMiddleware** | `tool_result_sanitization_middleware.py` | 始终 | 🆕 中性化远程内容 tool 结果中的 injection 标签（`web_fetch`/`web_search`/`image_search`/`web_capture`），name-based allowlist |
| 4 | **ThreadDataMiddleware** | `thread_data_middleware.py` | 始终 | 创建 per-thread 目录。**顺序变更**：现在在 Uploads 之前运行 |
| 5 | **UploadsMiddleware** | `uploads_middleware.py` | Lead only | 追踪已上传文件，注入到会话上下文 |
| 6 | **SandboxMiddleware** | `../../sandbox/middleware.py` | 始终 | 获取/释放沙箱，存储 `sandbox_id` |
| 7 | **DanglingToolCallMiddleware** | `dangling_tool_call_middleware.py` | 始终 | 补丁缺失的 ToolMessage + malformed tool-call id 恢复 + 无效参数清洗。用户中断和 strict provider（vLLM/SGLang）不会 400 |
| 8 | **LLMErrorHandlingMiddleware** | `llm_error_handling_middleware.py` | 始终 | 规范化 provider 调用错误为可恢复的 assistant-facing 错误。Subagent 用 marker 区分真实 failure vs 正常完成 |
| 9 | **ToolReceiptMiddleware** | `tool_receipt_middleware.py` | `verification.receipts_enabled`（默认开） | 🆕 确定性 tool 收据（RFC #4651 layer 1）：给每个 tool 结果盖 `deerflow_tool_receipt`（工具名/status/args·output sha256 截断 16 hex/字节数/时间戳），模型调用前从消息流派生隐藏 ledger（r1..rN），超 2000 字符保留最新并标省略。**最外层 `wrap_tool_call`**——在 Guardrail/SandboxAudit/ReadBeforeWrite/ToolProgress 之外，防短路/重建结果漏记账。`verification.receipts_render_mode`（`always`/`delegation_only`，默认 `delegation_only`；subagent 恒 `always`） |
| 10 | **GuardrailMiddleware** | `../../guardrails/middleware.py` | `guardrails.enabled` | Pre-tool-call 鉴权，`fail_closed` 策略。🆕 GuardrailRequest 增强：`thread_id`、`user_id`、`is_subagent`、`authz_attributes` |
| 11 | **SandboxAuditMiddleware** | `sandbox_audit_middleware.py` | 始终 | 审计 bash shell/file 操作的安全日志 |
| 12 | **ReadBeforeWriteMiddleware** | `read_before_write_middleware.py` | `read_before_write.enabled` | 写文件前必须有 `read_file` 记录的 sha256 hash "读戳"，按 `(thread, path)` 串行化。🆕 `elide_blocked_payloads`（默认开）：被拦截调用的 payload（write content / old_str·new_str）在**model-bound request** 中替换为占位符（`elide_min_chars` 2000 起拦）；存储历史/receipts/journal 保留原文 |
| 13 | **ToolProgressMiddleware** | `tool_progress_middleware.py` | `tool_progress.enabled` | 停滞检测状态机：ACTIVE→WARNED→BLOCKED。三个错误类别（可恢复/暂态/停止），Jaccard 去重。🆕 phase 迁移持久化（`runtime/events`，run 重放可见） |
| 14 | **ToolErrorHandlingMiddleware** | `tool_error_handling_middleware.py` | 始终 | 工具异常→错误 ToolMessage。注入 `deerflow_tool_meta`（status/error_type/recoverable/recommended_action/source）。Task tool 结果从同一结构化元数据生成 |

## Lead-only 层（15-37）

| # | Middleware | 文件 | 条件 | 一句话 |
|---|-----------|------|------|--------|
| 15 | **DynamicContextMiddleware** | `dynamic_context_middleware.py` | 始终 | 注入 `<system-reminder>`（日期+memory），保持 system prompt 静态以复用 prefix cache。🆕 v2.1.0-rc0 扩展：组装 model request 时插入 **transient `<project>` 块 + 有界 `<documents>` 索引**（pinned snapshot 纯渲染，latest-only，见 lead-agent digest），记录 `project_context_revision`/`project_shelf_revision`（渲染块 sha256）上下文事件 |
| 16 | **SkillActivationMiddleware** | `skill_activation_middleware.py` | 始终 | 检测 `/skill-name task` 触发语法，注入 SKILL.md body。重算 request-scoped secret 绑定（slash + in-context 双源）。**每个 run 只激活一次** |
| 17 | **DeferredToolPromotionAuditMiddleware** | `tool_promotion_audit_middleware.py` | `tool_search.enabled` | 🆕 v2.1.0-rc0（同步 #6 新增，36→37）：持久化实际生效的 deferred-tool promotion 决策（不含敏感 payload），供可观测性/审计回放。位置：SkillActivation 之后、SkillToolPolicy 之前 |
| 18 | **SkillToolPolicyMiddleware** | `skill_tool_policy_middleware.py` | 始终 | 🆕 应用 `allowed-tools` 只对 slash-activated 或实际 loaded 的 lead-agent skill；passive enabled skill 不限制全局 toolset。`task` 需显式声明 |
| 19 | **DurableContextMiddleware** | `durable_context_middleware.py` | 始终 | 捕获 `task` delegation + skill 引用到 ThreadState，summarization 前保存。每次模型请求前注入 `durable_context_data`。Subagent 也附此 middleware |
| 20 | **SummarizationMiddleware** | `summarization_middleware.py` | `summarization.enabled` | 上下文压缩，防止超出 token 限制。Subagent 继承此 middleware。🆕 `fraction` trigger 的阈值现在从 **summary 模型声明的 `context_window`** 解析（summarization.model_name 优先）；第三方 OpenAI 兼容模型无内置 profile，缺 `context_window` 时 fraction 条款降级丢弃（警告）而非崩溃 |
| 21 | **TodoListMiddleware** | `todo_middleware.py` | `is_plan_mode` | `write_todos` 任务跟踪 |
| 22 | **TokenUsageMiddleware** | `token_usage_middleware.py` | `token_usage.enabled` | Token 用量统计，subagent 用量按消息位置回并 |
| 23 | **TitleMiddleware** | `title_middleware.py` | 始终 | 首次交换完成后自动生成会话标题。🆕 attachment-only 会话用文件名生成标题（#5304）；忽略上传上下文避免标题漂移（#4729） |
| 24 | **MemoryMiddleware** | `memory_middleware.py` | 始终 | 排队异步更新记忆（debounced），捕获 `user_id` 和 `trace_id` |
| 25 | **ViewImageMiddleware** | `view_image_middleware.py` | model `supports_vision` | 注入 base64 图片数据。🆕 字节来源校验：优先从大小+SHA-256 匹配的宿主同步副本读取（sandbox 重建后不失效，`ViewedImageData.sha256/source_sandbox_id`）；provider 错误分类更细 |
| 26 | **McpRoutingMiddleware** | `mcp_routing_middleware.py` | `tool_search.enabled` + routing metadata | 🆕 自动提升匹配的 deferred MCP tool schema。匹配最新 HumanMessage，使用 `auto_promote_top_k`（默认 3），不执行 tool |
| 27 | **DeferredToolFilterMiddleware** | `deferred_tool_filter_middleware.py` | `tool_search.enabled` | 隐藏 deferred MCP tool schema，直到 `tool_search` 或 `McpRoutingMiddleware` promote |
| 28 | **SystemMessageCoalescingMiddleware** | `system_message_coalescing_middleware.py` | 始终 | 合并所有 SystemMessage 为单条（修复 strict backends 拒绝非 leading system message） |
| 29 | **SubagentLimitMiddleware** | `subagent_limit_middleware.py` | `subagent_enabled` | 截断多余 `task` 调用。🆕 同时执行 per-run total delegation cap（default 6），防止无限分批绕过 |
| 30 | **LoopDetectionMiddleware** | `loop_detection_middleware.py` | `loop_detection.enabled` | 检测重复 tool-call 循环。🆕 窗口化 frequency counter——长 run 不误触发；🆕 检测事件持久化到 `runtime/events`（run 重放可审计）。注意 `max_tracked_threads` 是保留的 `(thread_id, run_id)` 历史数，不是整 thread 数 |
| 31 | **TokenBudgetMiddleware** | `token_budget_middleware.py` | `token_budget.enabled` | Per-run token 限制，跨 lead + subagent 共享。warn 注入警告，hard-stop 强制作答 |
| 32 | **Custom middlewares** | (caller-supplied) | 传入 `custom_middlewares=[]` | 用户注入的自定义中间件 |
| 33 | **ConfiguredExtensionMiddleware** | `configured_extensions.py` | `extensions.middlewares` 有配置 | 🆕 从 config 加载零参数 `AgentMiddleware` 类路径（`module.path:ClassName`），经 `reflection.resolve_class` 解析，失败时 loud fail。**可信 operator 配置**——middleware 路径会实例化任意代码 |
| 34 | **TerminalResponseMiddleware** | `terminal_response_middleware.py` | 始终 | 空 terminal AIMessage 恢复：注入 hidden recovery prompt 并重试一次。二次空响应替换为 error fallback |
| 35 | **ModelLengthFinishReasonMiddleware** | `model_length_finish_reason_middleware.py` | 始终 | 🆕 provider 长度截断（`finish_reason=length` / `MAX_TOKENS` / `stop_reason=max_tokens`）的终态 assistant 响应标记 `stop_reason=model_length_capped`。保留原文、不重解析 XML 式 tool call、无视 tool-call intent 或无可见内容的消息 |
| 36 | **SafetyFinishReasonMiddleware** | `safety_finish_reason_middleware.py` | `safety_finish_reason.enabled` | 检测 provider 安全终止（`finish_reason=content_filter`），清除被污染的 tool_calls |
| 37 | **ClarificationMiddleware** | `clarification_middleware.py` | 始终（必须最后） | 拦截 `ask_clarification`，`Command(goto=END)` 中断。RunJournal 做 root-run final reconciliation |

## 相比旧版的变化

| 变化 | 详情 |
|------|------|
| **新增 4 个（同步 #3）** | ToolResultSanitization（#3）、SkillToolPolicy（#17）、McpRouting（#25）、TerminalResponse |
| **新增 2 个（同步 #4）** | ConfiguredExtension（#33）、ModelLengthFinishReason（#35） |
| **新增 1 个（同步 #5）** | ToolReceiptMiddleware（#9） |
| **新增 1 个（同步 #6，36→37）** | DeferredToolPromotionAudit（#17） |
| **增强（同步 #6）** | DynamicContext（`<project>`/`<documents>` transient 注入）、ToolOutputBudget（superseded write elision + `tool_call_args` 四面一致重写）、ReadBeforeWrite（blocked payload elision）、LoopDetection/ToolProgress（事件持久化）、Title（attachment-only 文件名）、ViewImage（sha256 宿主副本）、Summarization（fraction 从模型 `context_window` 解析）、InputSanitization/TokenBudget/LLMErrorHandling 重构 |
| **增强 5 个** | Guardrail（authz context）、Dangling（malformed id 恢复）、SubagentLimit（delegation ledger + total cap）、LoopDetection（窗口化 counter）、SkillActivation（每 run 只激活一次） |
| **顺序变更** | ThreadData 移到 Uploads 之前（#4→#5）；新增 ToolResultSanitization 插入 #3 位置 |
| **Declarative layered builder** | Middleware 组装改用声明式分层构建器 |

## Hook 点分组

Hook 点共 6 种。下表按 **v2.1.0 源码里各 middleware 类自身定义（AST 扫描 `def`/`async def`）** 统计——数字为本表编号：

| Hook | 参与 middleware |
|------|---------------|
| `before_agent` | 4, 5, 6, 13, 15, 21, 30, 31, 34 |
| `before_model` | 19, 20, 21, 26 |
| `wrap_model_call` (before LLM) | 1, 2, 7, 8, 9, 12, 13, 15, 16, 18, 19, 21, 25, 27, 28, 30, 31, 34 |
| `after_model` | 19, 21, 22, 23, 29, 30, 31, 34, 35, 36, 37 |
| `wrap_tool_call` (before tool) | 2, 3, 6, 9, 10, 11, 12, 13, 14, 17, 18, 27, 37 |
| `after_agent` | 6, 21, 24, 30, 31, 34 |

> 口径说明：① 只统计 DeerFlow 侧类**自身**定义的 hook；从 LangChain 基类继承的（如 `DeerFlowSummarizationMiddleware` ← `SummarizationMiddleware`、`TodoMiddleware` ← `TodoListMiddleware` 的基类实现）不在此列，第 20/21 条因此偏低。② `AgentMiddleware` 没有 `after_tool` hook——旧表的 `after_tool` 行是过期条目，已删除（工具结果处理走 #13/#14 的 `wrap_tool_call`）。
>
> ConfiguredExtension（#33）是任意 hook 的透明包装——它实例化 config 声明的 middleware，钩子行为取决于被加载的类。Custom middlewares（#32）同理。

## 辅助模块（非 middleware，但被 middleware 使用）

| 模块 | 用途 |
|------|------|
| `delegation_ledger.py` | SubagentLimit 使用的委托账本（去重 + total cap） |
| `skill_context.py` | SkillToolPolicy 使用的 skill 上下文管理 |
| `tool_result_meta.py` | ToolErrorHandling 使用的结构化 tool result 元数据 |
| `tool_receipt.py` | 🆕 ToolReceipt 的确定性收据核心（`make_tool_receipt`/`extract_tool_receipts`/`render_tool_receipts`，ledger 派生与渲染、2000 字符预算） |
| `receipt_verification.py` | 🆕 v2.1.0-rc0：父方核查 subagent 报告的 receipt 引用（`[rN]`/`[rN tool_name]`）vs 子方消息流的执行记录。纯函数无 IO（RFC #4651 PR2） |
| `tool_call_args.py` | 🆕 v2.1.0-rc0：elision 类中间件共享的 tool-call 参数重写——在 AIMessage 的全部四个参数面一次改写（provider 适配器读取面不一致） |
| `tool_output_synopsis.py` | 🆕 超大 tool output 的结构化摘要生成 |
| `_bounded_dict.py` | LoopDetection 窗口化 counter 的有界字典 |
| `safety_termination_detectors.py` | SafetyFinishReason 的终止检测器 |
| `model_length_termination_detectors.py` | 🆕 ModelLengthFinishReason 的 provider 终止检测器（`default_detectors()`） |
| `tool_transform_meta.py` | 结果改写中间件的**声明式变换轨迹**：`append_tool_transform(additional_kwargs, kind, *, by, version="1")` 往 `deerflow_tool_transforms` 追加条目，`read_tool_transforms(message)` 读出元组。按**应用顺序**排列（最后一条产出最终可见字节），让观察者从事实而不是"嗅探输出措辞"来分类 raw→visible 变换 |
| `audit_context.py` | 审计 recorder 的**窄作用域解析**：`resolve_audit_recorder(context, recorder_key=...)` 返回 `(recorder, is_subagent, agent_id)`。普通 lead run 拥有 `__run_journal`；task 子 agent 只拿到服务端安装的窄 recorder，**它的存在本身就是子 agent 归属的凭据**——调用方自报的 `is_subagent` 永不被采信。三个键：`__run_loop_detection_recorder` / `__run_tool_promotion_recorder` / `__run_tool_progress_recorder` |
| `message_utils.py` | 消息列表共享助手：`is_genuine_user_message`（排除系统注入的 HumanMessage）、`requires_input_sanitization`、`insert_after_leading_system_messages`（保持 system 块在前的插入位置） |
| `../../agents/human_input.py` | ClarificationMiddleware 的**回执读侧契约**：`HUMAN_INPUT_RESPONSE_KEY = "human_input_response"`，`read_human_input_response(additional_kwargs)` 严格校验 `version==1` + `kind=="human_input_response"` + 非空 `source`/`request_id`/`value`，再分派 `text` / `option`（后者额外要求非空 `option_id`）；任何不合规一律返回 `None`（不抛异常） |
| `../../authz/outcome.py` | Guardrail → observer 的**中立授权结果契约**：`put_authorization_outcome(context, tool_call_id, outcome)` / `pop_authorization_outcome(...)`，键 `__authorization_outcome`（`__` 前缀 → Gateway `build_run_config` 会剥掉调用方伪造的同名值）。发布方与消费方**互不 import**，只依赖这个模块。`AuthorizationOutcome(decision, policy_id, policy_version, reason_codes)`；无 observer 时没人 pop，所以 store 有 `_MAX_TRACKED_OUTCOMES = 500` 上界（最旧的先淘汰），把"授权开启的部署按 run 生命周期无限增长"这一隐患钉死 |
