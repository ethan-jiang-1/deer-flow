---
title: "Middleware 完整目录"
description: "39 个 middleware，按 hook 点分组。每个条目：文件位置、触发点、位置编号、用途、配置项、非显而易见的细节。"
topics: [middleware, hooks, interceptor-chain]
---

# Middleware 完整目录

> **39 个条目位，分两阶段组装**（v2.2.0 口径）。来源：`_build_runtime_middlewares()`（`tool_error_handling_middleware.py:347`，经 `build_lead_runtime_middlewares` 导出）产出前 16 条，`build_middlewares()`（`lead_agent/agent.py:485`）再追加 23 条。这与 `agents/middlewares/AGENTS.md` 的 39 条编号（`AGENTS.md:60-176`）一一对应。

> **"39" 的口径**（v2.2.0 用代码核实）：= **36 个内置 middleware 类型** + **2 个通用槽位**（#34 caller 传入的 `custom_middlewares`、#35 config 声明的 `load_configured_extension_middlewares()`——`configured_extensions.py` 只提供加载函数，本身不定义类）；外加 2 个条件性同族条目：`CompletedSubagentUsageMiddleware`（`token_usage_middleware.py:382`，仅当 token budget + usage 都开，见 #32）与 `SubagentDateContextMiddleware`（`dynamic_context_middleware.py`，仅 subagent 链，见文末）。
> 36 个内置类型 = `agents/middlewares/` 目录下 **35 个被 lead 链引用的 `class *Middleware`**（该目录共 39 个定义，减去仅 subagent 用的 `SubagentDateContextMiddleware`、仅 subagent 链注册的 `CompletedSubagentUsageMiddleware`、`memory_middleware.py::MemoryMiddlewareState` 与 `clarification_middleware.py::ClarificationMiddlewareState` 两个 state 子类）**+** `sandbox/middleware.py::SandboxMiddleware` **+** `guardrails/middleware.py::GuardrailMiddleware`。
> **v2.1.0 → v2.2.0 的增减**：`SkillToolPolicyMiddleware` 已在 v2.2.0 删除（`skill_tool_policy_middleware.py` 已删除，#6935；`allowed-tools` 降级为兼容元数据）；新增 `KnowledgeScopeMiddleware`、`ArtifactResolutionMiddleware`、`ArtifactCaptureMiddleware`、`PiiRedactionMiddleware`、`ModelContentCompatibilityMiddleware` 五个实例位。AGENTS.md 仍把 `ToolReceiptMiddleware`+`ToolErrorHandlingMiddleware` 合并成同一条 #15、把两个 guardrail 实例合并成 #11 规律条目，而本表拆开计行，故两边编号不能逐条对齐。
>
> 单链**实际实例数**随配置变化（本表列的是"每种可能的条目"，不是某次装配的条数）。`tool_progress.enabled` / `token_budget.enabled` / `summarization.enabled` / `guardrails.enabled` / `authorization.enabled` / `pii_redaction.enabled` 默认关，`verification.receipts_enabled` / `read_before_write.enabled` / `safety_finish_reason.enabled` / `loop_detection.enabled` / `token_usage.enabled` / `tool_artifacts.enabled` 默认开；模型支持 vision、开 plan mode / subagent / deferred setup / 自定义扩展时再加。

## 共享基础层（1-16，Lead 和 Sub-agent 共用）

| # | Middleware | 文件 | 条件 | 一句话 |
|---|-----------|------|------|--------|
| 1 | **InputSanitizationMiddleware** | `input_sanitization_middleware.py` | 始终 | 转义 `<system>` 等 XML tag 防 prompt injection，包裹 `--- BEGIN USER INPUT ---` 边界，阻断 forged framework tag（`</tool_response>` 等），保留原文到 `ORIGINAL_USER_CONTENT_KEY`。🆕 v2.2.0：`additional_kwargs.original_user_content` 变成 **server-owned provenance**——Gateway 对非 internal 的 run 请求剥掉调用方自带值，可信 IM 调用可带它在加传输/文件上下文前的原始串；非字符串值一律被替换。调用方 marker 打 `untrusted_input`（`utils/messages.py:19`），**从不**被剥掉 |
| 2 | **KnowledgeScopeMiddleware** | `knowledge_scope_middleware.py` | 始终 | 🆕 v2.2.0 新增。把 run 的 canonical 知识作用域（`KNOWLEDGE_SCOPE_RUNTIME_KEY`）投影成请求级约束：`disabled` 时移除知识检索类工具与相关提示，非法/畸形 scope 按 fail-closed 处理；模型输入永远不能设置或放宽作用域。位于 `InputSanitization` 之后、`ToolOutputBudget` 之前（`tool_error_handling_middleware.py:379-384`） |
| 3 | **ToolOutputBudgetMiddleware** | `tool_output_budget_middleware.py` | 始终 | 超大 tool 结果写入磁盘（`externalize_min_chars`），替换为 head+tail 预览 + `read_file` 引用路径。**superseded write elision**（`tool_output.elide_superseded_writes` 默认开）：成功的 `write_file` 一旦同路径出现更新的成功 read/write/str_replace，其 `content` 参数在 model-bound request 中替换为指向 `read_file` 的占位符（`superseded_write_min_chars` 2000 起、最新 `keep_recent_writes` 1 条始终保留）。改写经由共享的 `tool_call_args.py` 在**全部四个 AIMessage 参数面**一致重写 |
| 4 | **ToolResultSanitizationMiddleware** | `tool_result_sanitization_middleware.py` | 始终 | 中性化远程内容 tool 结果中的 injection 标签（`web_fetch`/`web_search`/`image_search`/`web_capture`），name-based allowlist。位于 `ToolOutputBudget` **之后**（更内层），先中性化原始输出、再做预算截断 |
| 5 | **PiiRedactionMiddleware** | `pii_redaction_middleware.py` | `pii_redaction.enabled`（默认关） | 🆕 v2.2.0 新增。列在 Layer-1 最末 → 最内层 wrapper：tool 结果先被 PII 脱敏，`ToolResultSanitization` 再中性化标签、`ToolOutputBudget` 才把副本落盘（落盘副本因此已是脱敏文本）；user message 也在其他请求改写之后才到达（#3190） |
| 6 | **ThreadDataMiddleware** | `thread_data_middleware.py` | 始终 | 创建 per-thread 目录（`before_agent`）。位于 Uploads 之前 |
| 7 | **UploadsMiddleware** | `uploads_middleware.py` | Lead only | 追踪本次 run 的上传文件，注入会话上下文 |
| 8 | **SandboxMiddleware** | `../../sandbox/middleware.py` | 始终 | 获取/释放沙箱，存储 `sandbox_id`；接收 `available_skills` / `owns_agent_skill_projection` 决定是否投影 agent 技能 |
| 9 | **DanglingToolCallMiddleware** | `dangling_tool_call_middleware.py` | 始终 | 补丁缺失的 ToolMessage + malformed tool-call id 恢复 + 无效参数清洗。用户中断和 strict provider（vLLM/SGLang）不会 400 |
| 10 | **LLMErrorHandlingMiddleware** | `llm_error_handling_middleware.py` | 始终 | 规范化 provider 调用错误为可恢复的 assistant-facing 错误。🆕 v2.2.0：对"真空 stop"给一次 model-boundary 重试；响应分类共用 `model_response.py`（`last_ai_message`/`has_tool_call_intent`/`has_visible_content`/`append_visible_text`/`finish_reason`），`has_visible_content` 用等值而非集合成员判断 block `type`（`type: []` / `{}` 是合法 JSON，哈希会抛 TypeError） |
| 11 | **ArtifactResolutionMiddleware** | `artifact_resolution_middleware.py` | `tool_artifacts.enabled && tool_artifacts.resolve_handles_in_args`（默认开） | 🆕 v2.2.0 新增。tool 执行前把 tool-call 参数里的 `art_xxxxxxxx` handle 解析为 `ThreadState.tool_artifacts[].real_ref`（#4676）。位于收据层内、授权/审计/写门/progress 策略外；未知或过期 handle 直接返回错误 ToolMessage（列缺失 handle + 最多 10 个现存 handle），不执行 tool。只改请求参数，从不改消息历史。见 `TOOL_ARTIFACTS.md` |
| 12 | **ToolReceiptMiddleware** | `tool_receipt_middleware.py` | `verification.receipts_enabled`（默认开） | 确定性 tool 收据（RFC #4651 layer 1）：给每个 tool 结果盖 `deerflow_tool_receipt`（工具名/status/args·output sha256 截断 16 hex/字节数/时间戳），模型调用前从消息流派生隐藏 ledger（r1..rN），超 2000 字符保留最新并标省略。**最外层 `wrap_tool_call`**——在 ArtifactResolution/Guardrail/SandboxAudit/ReadBeforeWrite/ToolProgress 之外（`extensions/ordering.py:94-120` 声明约束）。`verification.receipts_render_mode`（`always`/`delegation_only`，默认 `delegation_only`；subagent 恒 `always`） |
| 13 | **GuardrailMiddleware**（authorization） | `../../guardrails/middleware.py` | `authorization.enabled` | Layer-2 执行检查：复用 Layer-1 能力过滤用的同一 provider 实例（包在 `GuardrailAuthorizationAdapter` 里）；当前 build 有具体 deferred setup 时生成的 `tool_search` 可跳过第二次 provider 调用。失败即 fail-closed，产出错误 ToolMessage |
| 14 | **GuardrailMiddleware**（显式 provider） | `../../guardrails/middleware.py` | `guardrails.enabled` + `guardrails.provider` | 追加在 authorization 之后（更内层），仍然评估每一次调用（含 `tool_search`）。provider 由 `resolve_variable(provider.use)` 解析，构造器接受 `framework` 或 `**kwargs` 时自动注入 `framework="deerflow"`（`tool_error_handling_middleware.py:466-488`） |
| 15 | **SandboxAuditMiddleware** | `sandbox_audit_middleware.py` | 始终 | 审计 bash shell/file 操作的安全日志。命令分类是防御纵深与审计，**不是**安全边界。v2.1.0 起按**位置**判定命令替换（命令位 `$(curl u)` 拦截 / 值位 `x=$(curl u)` 放行，#4611） |
| 16 | **ReadBeforeWriteMiddleware** | `read_before_write_middleware.py` | `read_before_write.enabled`（默认开） | 写文件前必须有 `read_file` 记录的 sha256 "读戳"，按 `(scope, path)` 串行化；读戳在 ToolMessage 上，丢失读戳即丢失标记。`elide_blocked_payloads`（默认开）：被拦 payload 在 model-bound request 中换成占位符（`elide_min_chars` 2000 起拦）。位于 ToolProgress/ToolErrorHandling 外层，被拦写不消耗 progress 槽位 |

（该链的三层拼接见 `_build_runtime_middlewares()`：`outer_wrappers`（1-5）→ `thread_hooks`（6-8）→ `tail`（9-16 + `ToolProgress` + `ToolErrorHandling` + `ArtifactCapture`）。条目位 18 个，其中 Guardrail 最多两个实例。）

## Lead-only 层（17-39）

| # | Middleware | 文件 | 条件 | 一句话 |
|---|-----------|------|------|--------|
| 17 | **ToolProgressMiddleware** | `tool_progress_middleware.py` | `tool_progress.enabled` | 停滞检测状态机：ACTIVE→WARNED→BLOCKED（RFC #3177）。在共享基础层 `tail` 中位于 `ToolErrorHandling` 外层以便读 `deerflow_tool_meta`。phase 迁移持久化到 `runtime/events`（`middleware:tool_progress`，run 重放可见，含 goal continuation 触发的 `reset`） |
| 18 | **ToolErrorHandlingMiddleware** | `tool_error_handling_middleware.py` | 始终 | 工具异常→错误 ToolMessage。注入 `deerflow_tool_meta`（status/error_type/recoverable/recommended_action/source）。`task` 工具的异常包装也从同一结构化元数据生成 |
| 19 | **ArtifactCaptureMiddleware** | `artifact_capture_middleware.py` | `tool_artifacts.enabled`（默认开） | 🆕 v2.2.0 新增。`before_model` hook（不是 `wrap_tool_call`，避免把 ToolMessage 包进 `Command`）：扫描消息尾部未捕获的 tool artifact，抽成 `ArtifactEntry` 写入 `ThreadState.tool_artifacts`；`tool_artifact_processed` 记录已处理条目 hash（防重启后重复扫描）。handle = `art_` + 8 hex，由 (thread_id, ToolMessage.id, tool_call_id, ordinal) 确定性派生——**是标识符不是所有权凭证**。见 `TOOL_ARTIFACTS.md` |
| 20 | **DynamicContextMiddleware** | `dynamic_context_middleware.py` | 始终 | 注入 `<system-reminder>`（日期 + 可选 memory），保持 system prompt 静态以复用 prefix cache。组装 model request 时插入 transient `<project>` 块 + 有界 `<documents>` 索引，记录 `project_context_revision`/`project_shelf_revision` 上下文事件。🆕 v2.2.0：`context.locale`（`en-US`/`zh-CN`）作为**仅请求内**的语言偏好投影为人数据，静态 system prompt 与 locale 无关 |
| 21 | **SkillActivationMiddleware** | `skill_activation_middleware.py` | 始终 | 检测 `/skill-name task` 触发语法，注入 SKILL.md body；重算 request-scoped secret 绑定（slash + in-context 双源）。每个 run 只激活一次。🆕 v2.2.0：**不再收窄 toolset**——enabled/configured skills 只是可发现的元数据，不再约束工具集（#6935） |
| 22 | **DeferredToolPromotionAuditMiddleware** | `tool_promotion_audit_middleware.py` | `deferred_setup.deferred_names` 非空 | 持久化实际生效的 deferred-tool promotion 决策（工具名 + catalog hash，不含敏感 payload），供可观测性/审计回放。位于 SkillActivation 之后 |
| 23 | **DurableContextMiddleware** | `durable_context_middleware.py` | 始终 | 捕获 `task` delegation + skill 引用到 ThreadState，summarization 前保存；每次模型请求前注入 `durable_context_data`。🆕 v2.2.0：新 user turn 到来时**取消此前 run 仍未回复的 delegation**（保留 resume、同 run 续跑、无 `run_id` 的条目；pre-turn 已有回复则不取消） |
| 24 | **SummarizationMiddleware** | `summarization_middleware.py` | `summarization.enabled` | 上下文压缩。`fraction` trigger 的阈值从 **summary 模型声明的 `context_window`** 解析（`summarization.model_name` 优先）；缺 `context_window` 时降级丢弃该条款并警告。`trim_tokens_to_summarize=None` 表示单步无界折叠 |
| 25 | **TodoListMiddleware** | `todo_middleware.py` | `is_plan_mode` | `write_todos` 任务跟踪；压缩契约见 `docs/summarization.md#todo-reminders` |
| 26 | **TokenUsageMiddleware** | `token_usage_middleware.py` | `token_usage.enabled` | Token 用量统计，subagent 用量按消息位置回并 |
| 27 | **TitleMiddleware** | `title_middleware.py` | 始终 | 首次交换完成后自动生成会话标题。attachment-only 会话用文件名生成标题（#5304），忽略上传上下文避免标题漂移（#4729）；标 `SystemOperationKind.TITLE` provenance |
| 28 | **MemoryMiddleware** | `memory_middleware.py` | 始终 | 排队异步更新记忆（debounced），捕获 `user_id`/`trace_id`；**只排队抽取**，不做注入 |
| 29 | **ViewImageMiddleware** | `view_image_middleware.py` | model `supports_vision` | 注入 base64 图片数据。字节来源优先取大小+SHA-256 匹配的宿主同步副本（sandbox 重建后不失效，`ViewedImageData.sha256/source_sandbox_id`） |
| 30 | **McpRoutingMiddleware** | `mcp_routing_middleware.py` | `tool_search.enabled` + routing metadata | 自动提升匹配的 deferred MCP tool schema（匹配最新 HumanMessage，`auto_promote_top_k` 默认 3），不执行 tool。必须在 `DeferredToolFilter` 外层（`assert_mcp_routing_before_deferred_filter` 断言） |
| 31 | **DeferredToolFilterMiddleware** | `deferred_tool_filter_middleware.py` | `deferred_setup.deferred_names` 非空 | 隐藏 deferred MCP tool schema，直到 `tool_search` 或 `McpRoutingMiddleware` promote |
| 32 | **SystemMessageCoalescingMiddleware** | `system_message_coalescing_middleware.py` | 始终 | 合并所有 SystemMessage 为单条 leading `system_message`（strict backends vLLM/SGLang/Qwen/Anthropic 拒绝多条或非 leading system）。🆕 v2.2.0：subagent 链也注册（#4040/#4781），并打 `deerflow_producer_kind` provenance |
| 33 | **SubagentLimitMiddleware** | `subagent_limit_middleware.py` | `subagent_enabled` | 截断多余 `task` 调用（并发上限 `max_concurrent_subagents`，被 `effective_subagent_concurrency` 夹到启动冻结的 `subagent_runtime.max_running` 与 schema 上限 64 的最小值）；同时执行 per-run total delegation cap（默认 `subagents.max_total_per_run=6`，schema 1-50，run 级覆盖 `max_total_subagents`） |
| 34 | **LoopDetectionMiddleware** | `loop_detection_middleware.py` | `loop_detection.enabled` | 检测重复 tool-call 循环：hash 集合 + per-tool 频率两层；警告延后到下一圈 `wrap_model_call` 注入（保 tool-call 配对）。🆕 v2.2.0：subagent 链也注册（#3875 Phase 1） |
| 35 | **TokenBudgetMiddleware** | `token_budget_middleware.py` | `token_budget.enabled` | Per-run token 限制。🆕 v2.2.0：subagent 链也注册（`subagents.token_budget` 默认开，per-agent 覆盖 `subagents.agents.<name>.token_budget`）；hard-stop 不抛异常，只剥 tool_calls 让 run 以最终答案收尾，并把 `consume_stop_reason` 交给 executor |
| 36 | **ModelContentCompatibilityMiddleware** | `model_content_compatibility_middleware.py` | 始终（lead + subagent） | 🆕 v2.2.0 新增。只改**请求视图**的读时清洗：把 list-form content 里 URL 来源的 file/image block 改写为文本占位符，让转换层修复前已被污染的 thread 在下次模型调用时自愈。状态与 checkpoint 从不写入 |
| 37 | **Custom middlewares** | (caller-supplied) | 传入 `custom_middlewares=[]` | 用户注入的自定义中间件，直接 `extend` 在内置栈之后 |
| 38 | **ConfiguredExtensionMiddleware** | `configured_extensions.py` | `extensions.middlewares` 有配置 | 从 config 加载零参数 `AgentMiddleware` 类路径（`module.path:ClassName`），经 `reflection.resolve_class` 解析，失败 loud fail。**可信 operator 配置**——路径会实例化任意代码 |
| 39 | **TerminalResponseMiddleware** | `terminal_response_middleware.py` | 始终 | 空 terminal AIMessage 恢复：post-tool 响应仍无用户可见文本时，补一条 hidden recovery 提示并重试一次；二次空响应替换为 error fallback。不新增 graph 级恢复轮次 |
| — | **ModelLengthFinishReasonMiddleware** | `model_length_finish_reason_middleware.py` | 始终 | provider 长度截断（`finish_reason=length` / `MAX_TOKENS` / `stop_reason=max_tokens`）的响应标记 `stop_reason=model_length_capped`，抑制该响应的 tool_calls，无可见文本时补长度提示。与下一条一起夹在 TerminalResponse 之后 |
| — | **SafetyFinishReasonMiddleware** | `safety_finish_reason_middleware.py` | `safety_finish_reason.enabled`（默认开） | 检测 provider 安全终止（`finish_reason=content_filter`），清除被污染的 tool_calls。注册在 TerminalResponse/custom/configured **之后**，借 LangChain 的 after_model 反向分发在 after_model 中最先执行 |
| — | **ClarificationMiddleware** | `clarification_middleware.py` | 始终（必须最后） | 拦截 `ask_clarification`，`Command(goto=END)` 中断；RunJournal 做 root-run final reconciliation。默认配置下它确实是最后一条，但 `ModelLengthFinishReason` 与 `SafetyFinishReason` 在 list 尾部排在其前 |

> **编号口径**：37-39 号在 `AGENTS.md` 里是 #34/#35/#33（"custom / configured / TerminalResponse"顺序），本表按 `build_middlewares()` 的真实 append 顺序排（custom → configured → TerminalResponse）。`ModelLengthFinishReason` / `SafetyFinishReason` / `Clarification` 三条用"—"标注，因为 AGENTS.md 把它们与 TerminalResponse 列为同一尾部区段。

## v2.1.0 → v2.2.0 的变化

| 变化 | 详情 |
|------|------|
| **新增（v2.2.0）** | `KnowledgeScopeMiddleware`（#2）、`PiiRedactionMiddleware`（#5）、`ArtifactResolutionMiddleware`（#11）、`ArtifactCaptureMiddleware`（#19）、`ModelContentCompatibilityMiddleware`（#36）；辅助模块新增 `tool_declarations.py`、`model_response.py`、`skill_usage.py`、`TOOL_ARTIFACTS.md`、`TOOL_OUTPUT_PERSISTENCE.md` |
| **删除（v2.2.0，#6935）** | `SkillToolPolicyMiddleware`（`skill_tool_policy_middleware.py` 整文件已删除，连同 v2.1.0 目录里的 #18 条目一起下线）。现行语义：`SKILL.md` 的 `allowed-tools` frontmatter 是**兼容元数据**——`assembly_descriptor` 仍把它记进 skill catalog 指纹（`None` / `()` / 非空列表三种状态可区分，顺序不影响指纹），但**永不过滤或授予工具**；工具集由 DeerFlow 的 Agent 配置与授权层（Layer 1 过滤 + `GuardrailMiddleware` Layer 2）决定。lead prompt 里也明确写了这句话（`lead_agent/prompt.py` 的 `**Allowed tools:**` 段）。源码侧的 `skills/tool_policy.py` 已删除（v2.2.0，#6935） |
| **顺序变更** | 基础层扩到 5 个 Layer-1 wrapper：`InputSanitization → KnowledgeScope → ToolOutputBudget → ToolResultSanitization → PiiRedaction(cond)`；`ArtifactResolution` 位于收据层内、策略层外；`ModelContentCompatibility` 位于所有内置 content 改写之后、custom/extension 注入点与尾部之前（`agents/factory.py:440-452`、`lead_agent/agent.py` 尾部） |
| **装配点变化** | `build_middlewares()` 末尾先 `compose_with_extensions(...)`（`extensions/stack.py` 是唯一最终合成点），`extensions/ordering.py::core_ordering_constraints()` 在最终栈上一次性校验顺序不变量；broken invariant 是这套系统里唯一的硬失败 |

## Hook 点分组

Hook 点共 6 种。下表按 **v2.2.0 源码里各 middleware 类自身定义（AST 扫描 `def`/`async def`，去掉 `a` 前缀）** 统计——数字为本表编号：

| Hook | 参与 middleware |
|------|---------------|
| `before_agent` | 2, 6, 7, 8, 17, 20, 25, 34, 35 |
| `before_model` | 19, 23, 24, 25, 30 |
| `wrap_model_call` (before LLM) | 1, 2, 3, 4, 5, 10, 12, 16, 20, 21, 23, 25, 28, 29, 32, 34, 35, 36, 39 |
| `after_model` | 23, 25, 26, 27, 33, 34, 35, 39、`ModelLengthFinishReason`、`SafetyFinishReason`、`Clarification` |
| `wrap_tool_call` (before tool) | 2, 3, 4, 5, 8, 11, 12, 13, 14, 15, 16, 17, 18, 22, 31, `Clarification` |
| `after_agent` | 8, 25, 28, 34, 35 |

> 口径说明：① 只统计 DeerFlow 侧类**自身**定义的 hook；从 LangChain 基类继承的不在此列（`TodoMiddleware` 逐条实现了全部 6 个 hook，所以 #25 处处出现）。② `AgentMiddleware` 没有 `after_tool` hook——旧表的该行已删除；工具结果处理走 `wrap_tool_call`（#11-#18）。③ `KnowledgeScopeMiddleware`（#2）自己定义了 `before_agent`/`wrap_model_call`/`wrap_tool_call` 三类 hook；`PiiRedactionMiddleware`（#5）定义 `wrap_model_call`/`wrap_tool_call`。
>
> ConfiguredExtension（#38）是任意 hook 的透明包装——它实例化 config 声明的 middleware，钩子行为取决于被加载的类。Custom middlewares（#37）同理。
>
> **subagent-only**：`SubagentDateContextMiddleware`（`before_agent`，一次性注入隐藏 `<current_date>`）与 `CompletedSubagentUsageMiddleware`（`after_model`，把中途完成的 subagent 用量并回）只出现在 `build_subagent_runtime_middlewares()` 里，不在 lead 链上。

## 辅助模块（非 middleware，但被 middleware 使用）

| 模块 | 用途 |
|------|------|
| `delegation_ledger.py` | SubagentLimit 使用的委托账本（去重 + total cap） |
| `skill_context.py` | skill 上下文管理（`SKILL_CONTEXT_ENTRY_KEY`/`SKILL_CONTEXT_DENIED_KEY`、`build_skill_entry_metadata_from_read`）。v2.2.0 起服务 SkillActivation 与 ToolErrorHandling 的读侧盖章，不再有 SkillToolPolicy 消费者（`skill_tool_policy_middleware.py` 已删除） |
| `tool_result_meta.py` | ToolErrorHandling 使用的结构化 tool result 元数据 |
| `tool_receipt.py` | 🆕 ToolReceipt 的确定性收据核心（`make_tool_receipt`/`extract_tool_receipts`/`render_tool_receipts`，ledger 派生与渲染、2000 字符预算） |
| `receipt_verification.py` | 🆕 v2.1.0-rc0：父方核查 subagent 报告的 receipt 引用（`[rN]`/`[rN tool_name]`）vs 子方消息流的执行记录。纯函数无 IO（RFC #4651 PR2） |
| `tool_call_args.py` | 🆕 v2.1.0-rc0：elision 类中间件共享的 tool-call 参数重写——在 AIMessage 的全部四个参数面一次改写（provider 适配器读取面不一致） |
| `tool_output_synopsis.py` | 🆕 超大 tool output 的结构化摘要生成 |
| `_bounded_dict.py` | LoopDetection 窗口化 counter 的有界字典 |
| `tool_declarations.py` | 🆕 v2.2.0：**中间件声明工具的 Layer-1 授权**。LangChain `create_agent` 在宿主工具列表被过滤**之后**才把 `middleware.tools` 折进绑定集，所以声明会绕过 Layer 1。五步一次构建：`layer_one_outcome()` 记录普通 pass 的判词 → `collect_declared_tools()` 收 `getattr(m,"tools",())`（非 list/tuple 一律报 `DeclaredToolViewError`）→ `decide_declared_tools()` 用**同一 provider 实例**只裁决没见过的名字（已裁决的复用原判词）→ `apply_declared_tool_view()` 复制被削的 middleware（绝不改调用方实例）→ `verify_declared_tool_view()` 在最终栈上复检。`authorization.enabled` 不为真时全部跳过，返回原始 list 对象 |
| `model_response.py` | 🆕 v2.2.0：响应分类共享助手——`last_ai_message`、`has_tool_call_intent`、`has_visible_content`、`append_visible_text`、`finish_reason`；被 LLMErrorHandling / TerminalResponse / ModelLengthFinishReason 共用 |
| `skill_usage.py` | 🆕 v2.2.0：`SKILL_USAGE_KEY` + `build_skill_usage()`，SkillActivation 为每个 skill 记 usage |
| `../../knowledge_scope.py` | 🆕 v2.2.0：KnowledgeScopeMiddleware 的作用域契约源——`KNOWLEDGE_SCOPE_RUNTIME_KEY` 与 `execution_scope()`；`disabled` 作用域关掉知识检索，模型输入永远不能设置或放宽它 |
| `safety_termination_detectors.py` | SafetyFinishReason 的终止检测器 |
| `model_length_termination_detectors.py` | 🆕 ModelLengthFinishReason 的 provider 终止检测器（`default_detectors()`） |
| `tool_transform_meta.py` | 结果改写中间件的**声明式变换轨迹**：`append_tool_transform(additional_kwargs, kind, *, by, version="1")` 往 `deerflow_tool_transforms` 追加条目，`read_tool_transforms(message)` 读出元组。按**应用顺序**排列（最后一条产出最终可见字节），让观察者从事实而不是"嗅探输出措辞"来分类 raw→visible 变换 |
| `audit_context.py` | 审计 recorder 的**窄作用域解析**：`resolve_audit_recorder(context, recorder_key=...)` 返回 `(recorder, is_subagent, agent_id)`。普通 lead run 拥有 `__run_journal`；task 子 agent 只拿到服务端安装的窄 recorder，**它的存在本身就是子 agent 归属的凭据**——调用方自报的 `is_subagent` 永不被采信。三个键：`__run_loop_detection_recorder` / `__run_tool_promotion_recorder` / `__run_tool_progress_recorder` |
| `message_utils.py` | 消息列表共享助手：`is_genuine_user_message`（排除系统注入的 HumanMessage）、`requires_input_sanitization`、`insert_after_leading_system_messages`（保持 system 块在前的插入位置） |
| `../../agents/human_input.py` | ClarificationMiddleware 的**回执读侧契约**：`HUMAN_INPUT_RESPONSE_KEY = "human_input_response"`，`read_human_input_response(additional_kwargs)` 严格校验 `version==1` + `kind=="human_input_response"` + 非空 `source`/`request_id`/`value`，再分派 `text` / `option`（后者额外要求非空 `option_id`）；任何不合规一律返回 `None`（不抛异常） |
| `../../authz/outcome.py` | Guardrail → observer 的**中立授权结果契约**：`put_authorization_outcome(context, tool_call_id, outcome)` / `pop_authorization_outcome(...)`，键 `__authorization_outcome`（`__` 前缀 → Gateway `build_run_config` 会剥掉调用方伪造的同名值）。发布方与消费方**互不 import**，只依赖这个模块。`AuthorizationOutcome(decision, policy_id, policy_version, reason_codes)`；无 observer 时没人 pop，所以 store 有 `_MAX_TRACKED_OUTCOMES = 500` 上界（最旧的先淘汰），把"授权开启的部署按 run 生命周期无限增长"这一隐患钉死 |
