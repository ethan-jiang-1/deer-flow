# Middleware 完整目录

19 个 middleware，按 hook 点分组。每个条目：文件位置、触发点、位置编号、用途、配置项、非显而易见的细节。

## before_agent (5 个)

### ThreadDataMiddleware

- **文件:** `deerflow/agents/middlewares/thread_data_middleware.py:24`
- **位置:** 0（链首）
- **用途:** 为每个 thread 创建数据目录映射。计算 virtual→physical 路径映射（`/mnt/user-data` → `~/.deer-flow/users/{uid}/threads/{tid}/user-data/`），存入 `state.thread_data`。给最后一条 HumanMessage 打上 `run_id` 和 `timestamp`。
- **配置:** `config.paths`（通过 `get_paths()`），`settings.user_id`
- **lazy_init:** 默认 True — 只计算路径映射，不创建目录（目录由 sandbox tool 按需创建）
- **为什么是第一个:** 后续 middleware（Uploads、Sandbox、DynamicContext）都依赖 `state.thread_data` 中的路径信息。

### UploadsMiddleware

- **文件:** `deerflow/agents/middlewares/uploads_middleware.py:66`
- **位置:** 1
- **用途:** 检测 `additional_kwargs.files` 中的上传文件，扫描磁盘上的历史文件，向 user message 前置注入 `<uploaded_files>` block。使用 `markitdown` 提取文档大纲（headings + line numbers），方便 LLM 精确定位 `read_file` 的参数。
- **配置:** `config.paths`，磁盘上的 upload 目录
- **注意:** 只处理 markdown 转换后的文档大纲。二进制文件只列出文件名和大小。

### SandboxMiddleware

- **文件:** `deerflow/sandbox/middleware.py:22`
- **位置:** 2
- **用途:** 在 agent 启动时获取 sandbox（`provider.acquire(thread_id)`），结束时释放（`provider.release(thread_id)`）。sandbox_id 存在 state 中，同一 thread 的所有 tool call 复用。
- **配置:** `config.sandbox.use`
- **lazy_init:** 默认 True — `before_agent` 直接 no-op，sandbox 推迟到首次 tool call 时由 `ensure_sandbox_initialized()` 获取。
- **注意:** `after_agent` 中的 release 通过 `asyncio.to_thread` 执行，避免阻塞 event loop。

### DynamicContextMiddleware

- **文件:** `deerflow/agents/middlewares/dynamic_context_middleware.py:81`
- **位置:** 8
- **用途:** 注入两样东西：（1）memory context（用户 profile）；（2）当前日期。使用**冻帧快照**（ID-swap）模式：第一条 HumanMessage 的 ID 给 reminder 消息，原消息用 `{id}__user` 作为新 ID——保证后续 turn 的 prefix cache 能命中。
- **配置:** `config.memory.injection_enabled`
- **检测午夜跨越:** 如果跨天了，注入轻量 date-update reminder 而不是完整 context。
- **防误判:** 通过 `additional_kwargs.dynamic_context_reminder` flag 识别自己的 reminder，不是通过内容扫描（避免用户消息里写 `<system-reminder>` 被误判）。

### LoopDetectionMiddleware（before_agent 部分）

- **文件:** `deerflow/agents/middlewares/loop_detection_middleware.py:174`
- **位置:** 17
- **用途:** 在 `before_agent` 中清理上一轮 run 的 `_pending_warnings`，防止跨 run 泄露。
- **实际检测逻辑:** 在 `after_model` 中。

## before_model (3 个)

### DeerFlowSummarizationMiddleware

- **文件:** `deerflow/agents/middlewares/summarization_middleware.py:98`
- **位置:** 9（可选，`config.summarization.enabled`）
- **用途:** 继承 LangChain 的 `SummarizationMiddleware`，加了 skill-file rescue。当 token 接近上限时，对旧消息做分区总结。**skill-file rescue:** 最近的 `/mnt/skills/` 下的 `read_file` 结果被保留（即使超出 token 预算），保证 agent 不会丢失已加载的 skill 内容。
- **配置:** `config.summarization.*`（enabled, trigger, keep, model_name, summary_prompt, skill_file_read_tool_names, preserve_recent_skill_count 等）
- **注意:** 总结前触发 `BeforeSummarizationHook` 插件（如 memory flush），确保重要信息在压缩前被保存。

### TodoMiddleware（before_model 部分）

- **文件:** `deerflow/agents/middlewares/todo_middleware.py:109`
- **位置:** 10（仅 `plan_mode=True` 时）
- **用途:** 在 `before_model` 中检测 context loss——如果总结把原始的 `write_todos` 调用从 context window 中移除，注入 `<system_reminder>` 带当前 todo 状态。
- **注意:** 这是 LangChain `TodoListMiddleware` 的扩展。context loss 检测通过扫描 messages 中是否依然存在 `write_todos` tool_call 和对应的 ToolMessage 来实现。

### ViewImageMiddleware

- **文件:** `deerflow/agents/middlewares/view_image_middleware.py:19`
- **位置:** 14（仅 model `supports_vision` 时）
- **用途:** 当上一轮 AIMessage 中包含 `view_image` tool call 且已完成时，自动创建一个带 base64 图片数据和文字描述的 HumanMessage，让 vision model 直接看到图片。
- **配置:** `config.models[name].supports_vision`
- **注意:** 在 `before_model` 中触发（不是 `before_agent`），所以每一轮 step 都会检查。防重复注入通过 content string 比对实现。

## wrap_model_call (5 个)

### DanglingToolCallMiddleware

- **文件:** `deerflow/agents/middlewares/dangling_tool_call_middleware.py:30`
- **位置:** 3（非可选）
- **用途:** 检测 AIMessage 中有 tool_calls 但没对应 ToolMessage 的情况（比如用户中断了 agent）。在 AIMessage 后立即注入合成的 error ToolMessage，让模型看到干净的消息序列。
- **意外之处:** 使用 `wrap_model_call` 而不是 `before_model`——因为需要把补丁 ToolMessage 插入到每个 dangling AIMessage 的**精确后面**（不是末尾）。还会重排已有的 ToolMessages 让它们跟在正确的 AIMessage 后面。

### LLMErrorHandlingMiddleware

- **文件:** `deerflow/agents/middlewares/llm_error_handling_middleware.py:66`
- **位置:** 4（lead agent 路径；SDK 路径无）
- **用途:** LLM 调用失败时重试（3 次，指数退避 1s→2s→4s，cap 8s）。实现了**熔断器**：连续失败超过 `circuit_breaker.failure_threshold` 次后，打开熔断，后续请求快速失败并返回用户可见的 AIMessage。识别可重试错误（408/409/425/429/500/502/503/504、busy 模式、超时）和致命错误（quota、auth）。尊重 `Retry-After` 头。
- **配置:** `config.circuit_breaker.failure_threshold`, `config.circuit_breaker.recovery_timeout_sec`
- **注意:** 能识别中文 busy 信号（"负载较高"、"服务繁忙"）。熔断器用半开状态（单个探测请求）测试恢复。

### TodoMiddleware（wrap_model_call 部分）

- **文件:** `deerflow/agents/middlewares/todo_middleware.py`
- **用途:** 注入 completion reminder——model 说做完了但 todos 还有未完成的 → 在下一次 model 调用前注入隐藏 HumanMessage 提醒。
- **注意:** 通过 `wrap_model_call` 注入（而不是持久化到 state），所以不会泄露到用户可见的对话记录中。最多 2 次提醒防止死循环。

### LoopDetectionMiddleware（wrap_model_call 部分）

- **文件:** `deerflow/agents/middlewares/loop_detection_middleware.py`
- **用途:** 排出 `_pending_warnings` 队列——在 `after_model` 中检测到的循环警告，延迟到此处注入（作为隐藏 HumanMessage），避免破坏 OpenAI/Moonshot 的 AIMessage-ToolMessage 配对要求。
- **这是整个系统最精妙的设计细节之一。**

### DeferredToolFilterMiddleware（wrap_model_call 部分）

- **文件:** `deerflow/agents/middlewares/deferred_tool_filter_middleware.py:26`
- **位置:** 15（仅 `config.tool_search.enabled` 时）
- **用途:** 当 tool_search 启用时，MCP deferred tools 的 schema 从 `bind_tools` 中移除（节省 context token）。Agent 通过 `tool_search` tool 在运行时发现它们。
- **注意:** 这是减少 token 消耗的优化——MCP server 可能有几十上百个 tool，全部放入 schema 会撑爆 context window。

## after_model (6 个)

### TodoMiddleware（after_model 部分）

- **文件:** `deerflow/agents/middlewares/todo_middleware.py:352-357`
- **用途:** 检测 model 产出 final answer 但 todos 未完成 → 不直接注入消息，而是设置内部状态，让 `wrap_model_call` 注入 completion reminder。使用 `hook_config(can_jump_to=["model"])` 实现 graph 跳转。

### TokenUsageMiddleware

- **文件:** `deerflow/agents/middlewares/token_usage_middleware.py:267`
- **位置:** 11（可选，`config.token_usage.enabled`）
- **用途:** 记录每次 model 调用的 token 消耗。给 AIMessage 标注 `token_usage_attribution` metadata（step kind、tool call actions、精确的 todo diff）。合并 subagent 的 token 使用回 dispatching AIMessage。
- **配置:** `config.token_usage.enabled`
- **注意:** `write_todos` 的 attribution 极其细致——diff 前/后 todos，给每个 item 标注 `todo_start`/`todo_complete`/`todo_update`/`todo_remove`。Subagent token 按 `tool_call_id` 缓存，扫描 ToolMessages 找回 dispatching AIMessage（处理并发 task 调用）。

### TitleMiddleware

- **文件:** `deerflow/agents/middlewares/title_middleware.py:29`
- **位置:** 12
- **用途:** 首次完整交换后（恰好 1 条 user message + 至少 1 条 assistant response）自动生成 thread 标题。sync 路径只做本地 fallback（取 user message 前 50 字符）；async 路径调用轻量 LLM 生成标题。
- **配置:** `config.title.enabled`, `config.title.max_words`, `config.title.max_chars`, `config.title.prompt_template`, `config.title.model_name`
- **注意:** sync `after_model` 故意不做 LLM 调用（会阻塞 event loop）。LLM 只在 `aafter_model` 中。strip `<think>` 标签处理 reasoning model 输出。

### SubagentLimitMiddleware

- **文件:** `deerflow/agents/middlewares/subagent_limit_middleware.py:25`
- **位置:** 16（仅 subagent 启用时）
- **用途:** 截断单个 model response 中的 `task` tool call 数量，强制上限。比 prompt 中的限制更可靠（LLM 不一定遵守 prompt 中的数量限制）。
- **配置:** `config.configurable.max_concurrent_subagents`（默认 3，clamp 到 [2,4]）
- **注意:** 返回修改后的 AIMessage（同 id，`add_messages` 替换原消息）。

### LoopDetectionMiddleware（after_model 部分）

- **文件:** `deerflow/agents/middlewares/loop_detection_middleware.py`
- **用途:** 两层检测：（1）hash-based：hash tool call set（name + stable args key），滑动窗口 20，3 次重复→warn，5 次→hard-stop 清除所有 tool_calls；（2）frequency-based：每种 tool type 计数，30→warn，50→hard-stop。
- **配置:** `config.loop_detection.*`（warn_threshold, hard_limit, window_size, max_tracked_threads, tool_freq_warn, tool_freq_hard_limit, tool_freq_overrides）
- **注意:** `read_file` 按 200 行分桶（防止连续读文件被误判为死循环）。hard-stop 同时清除 structured `tool_calls` 和 raw provider `additional_kwargs.tool_calls`。

### SafetyFinishReasonMiddleware

- **文件:** `deerflow/agents/middlewares/safety_finish_reason_middleware.py:67`
- **位置:** 18（可选，`config.safety_finish_reason.enabled`；在 custom middleware 之后）
- **用途:** 检测 provider 安全终止（OpenAI `content_filter`、Anthropic `refusal`、Gemini `SAFETY`）。清除所有 tool_calls 防止执行被截断/不安全的 tool call。发送 `safety_termination` SSE 事件，写入 `RunJournal` 审计。
- **配置:** `config.safety_finish_reason.enabled`, `config.safety_finish_reason.detectors`
- **为什么在这个位置:** 在 custom middleware 之后注册，利用 `after_model` 反向执行——Safety 最先看到原始 model 输出，在处理 tool_calls 的其他 middleware 运行之前清除污染。策略模式 detector（3 个内置：OpenAI/Anthropic/Gemini）可通过 config reflection 扩展。**故意不记录被 suppress 的 tool call args**（那是 provider filter 掉的内容，不应该审计）。

## wrap_tool_call (5 个)

### GuardrailMiddleware

- **文件:** `deerflow/guardrails/middleware.py:20`
- **位置:** 5（可选，`config.guardrails.enabled`）
- **用途:** 调用可插拔 `GuardrailProvider.evaluate(GuardrailRequest)` 判断是否允许执行。deny → 返回 error ToolMessage（tool 不执行）。provider 异常 → `fail_closed`（默认 deny）/ `fail_open`（放行）。
- **配置:** `config.guardrails.enabled`, `config.guardrails.provider`, `config.guardrails.fail_closed`
- **注意:** Guardrail 收到的是 LLM 原始的 `tool_call["args"]`，不是 tool 内部路径解析后的实际入参。Guardrail provider 无法审计路径翻译结果。

### SandboxAuditMiddleware

- **文件:** `deerflow/agents/middlewares/sandbox_audit_middleware.py:197`
- **位置:** 6（lead agent 路径；SDK 路径无）
- **用途:** 只审计 bash tool。高危命令（`rm -rf /`、`dd if=`、`mkfs`、`cat /etc/shadow`、pipe to shell、`LD_PRELOAD` 注入、fork bomb 等）→ block。中危命令（`chmod 777`、`pip install`、`sudo` 等）→ warn（执行但附加警告）。所有 bash 调用都写审计日志。
- **配置:** 无——高危模式硬编码在 `_HIGH_RISK_PATTERNS` 中。这是内置的、不可配置的。
- **输入清洗:** 拒绝空命令、>10,000 字符的命令、null byte。引号感知的 `&&`/`||`/`;` 切分，两轮扫描（先全命令高危，再逐子命令分类）。

### ToolErrorHandlingMiddleware

- **文件:** `deerflow/agents/middlewares/tool_error_handling_middleware.py:21`
- **位置:** 7（非可选）
- **用途:** 捕获 tool 执行中的所有异常，转换为 error ToolMessage。错误详情截断到 500 字符。保留 `GraphBubbleUp`（LangGraph 控制流异常）不捕获。
- **配置:** 无
- **注意:** 这是 tool 层的兜底——没有它，一个 tool 抛异常就会终止整个 agent run。

### DeferredToolFilterMiddleware（wrap_tool_call 部分）

- **文件:** `deerflow/agents/middlewares/deferred_tool_filter_middleware.py`
- **用途:** 拦截尚未被 `tool_search` promote 的 deferred tool——直接拒绝执行。防止 agent 通过幻觉调用不存在的 tool。

### ClarificationMiddleware

- **文件:** `deerflow/agents/middlewares/clarification_middleware.py:25`
- **位置:** 19（**永远最后**）
- **用途:** 拦截 `ask_clarification` tool call，不执行 tool，返回 `Command(goto=END)` 中断 graph。用户看到 clarification 消息后回复，agent 继续。
- **配置:** 无
- **为什么必须是最后一个:** `Command(goto=END)` 跳过后续所有 middleware——如果它不是最后，后面的 middleware 永远不会执行。
- **注意:** 使用确定性 message ID（`clarification:{tool_call_id}` 或 hash-based），重试时替换而不是追加消息。

## after_agent (3 个)

### SandboxMiddleware（after_agent 部分）

- **文件:** `deerflow/sandbox/middleware.py`
- **用途:** `provider.release(thread_id)` 释放 sandbox。Local: no-op；Docker: 容器放回 warm pool；K3s: 删除 Pod+Service。

### MemoryMiddleware

- **文件:** `deerflow/agents/middlewares/memory_middleware.py:28`
- **位置:** 13
- **用途:** 过滤本轮 messages（user inputs + final AI responses，排除 tool calls），入队异步 memory update（debounce 30s）。检测 corrections 和 reinforcements。
- **配置:** `config.memory.enabled`
- **注意:** 在入队时捕获 `user_id`（而不是在 timer thread 中读 ContextVar），因为 timer thread 没有 HTTP request context。

### LoopDetectionMiddleware（after_agent 部分）

- **文件:** `deerflow/agents/middlewares/loop_detection_middleware.py`
- **用途:** 清理线程本地状态（`_pending_warnings`），释放追踪数据。

---

## 位置速查

```
 0  ThreadData              before_agent
 1  Uploads                 before_agent
 2  Sandbox                 before_agent, after_agent
 3  DanglingToolCall        wrap_model_call
 4  LLMErrorHandling        wrap_model_call
 5  Guardrail               wrap_tool_call
 6  SandboxAudit            wrap_tool_call
 7  ToolErrorHandling       wrap_tool_call
 8  DynamicContext          before_agent
 9  Summarization           before_model
10  Todo                    before_model, after_model, wrap_model_call
11  TokenUsage              after_model
12  Title                   after_model
13  Memory                  after_agent
14  ViewImage               before_model
15  DeferredToolFilter      wrap_model_call, wrap_tool_call
16  SubagentLimit           after_model
17  LoopDetection           before_agent, after_model, wrap_model_call, after_agent
18  SafetyFinishReason      after_model
19  Clarification           wrap_tool_call
```
