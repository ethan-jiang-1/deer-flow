---




title: "A. Agent 运行时控制"
description: 'A. Agent 运行时控制：架构、契约与源码锚点。'
topics: [tools, builtin, sandbox-tools]
verified_against: v2.2.0
last_verified: 2026-11-08
---

# A. Agent 运行时控制

## present_files

**源码**: `packages/harness/deerflow/tools/builtins/present_file_tool.py:83`
**加载条件**: 始终（`BUILTIN_TOOLS` 列表）
**Tool Name**: `present_files`

### 用途

让 LLM 把已创建的产出文件标记为"用户可见"。前端会读取 `artifacts` state 并渲染这些文件，用户可以直接查看、下载。

### 参数

| 参数 | 类型 | 说明 |
|------|------|------|
| `filepaths` | `list[str]` | 要展示的文件绝对路径列表 |

### 安全边界

只允许 `/mnt/user-data/outputs/` 下的路径：

```python
# present_file_tool.py:79
OUTPUTS_VIRTUAL_PREFIX = "/mnt/user-data/outputs"
```

传入的路径会经过 `_normalize_presented_filepath()`：
1. 接受虚拟路径 `/mnt/user-data/outputs/report.md`
2. 也接受宿主机路径（自动转为虚拟路径）
3. 通过 `resolve_virtual_path()` 转 host path，再 `relative_to(outputs_dir)` 校验在范围内
4. 不在 `outputs/` 下的路径 → `ValueError` → 返回 error ToolMessage

### 行为

- 返回 `Command(update={"artifacts": normalized_paths, "messages": [...]})`
- `artifacts` state 用 `merge_artifacts` reducer 去重合并
- 多次调用相同路径不会重复展示

### LLM 使用场景

- 创建完文件后调用，让用户能看到/下载产物
- 可以一次传多个文件路径

---

## ask_clarification

**源码**: `packages/harness/deerflow/tools/builtins/clarification_tool.py:6`
**加载条件**: 始终（`BUILTIN_TOOLS` 列表）
**Tool Name**: `ask_clarification`
**特殊标记**: `return_direct=True`

### 用途

Agent 需要人类输入时暂停执行。这是让 Agent "知道何时该停下来问"的机制。

### 参数

| 参数 | 类型 | 说明 |
|------|------|------|
| `question` | `str` | 要问的问题，必须具体明确 |
| `clarification_type` | `Literal[...]` | 见下表 |
| `context` | `str \| None` | 可选，解释为何需要澄清 |
| `options` | `list[str] \| None` | 可选，给用户的预选选项 |

### clarification_type 枚举

| 值 | 含义 |
|------|------|
| `missing_info` | 缺少必要信息（文件路径、URL、具体要求等） |
| `ambiguous_requirement` | 需求有多种合理理解 |
| `approach_choice` | 多种有效实现方案，需要用户选择 |
| `risk_confirmation` | 即将执行危险操作，必须用户确认 |
| `suggestion` | Agent 有推荐方案但需要用户批准 |

### 拦截链路

这个 tool 本身只是一个**空壳**：

```python
# clarification_tool.py:52-55
# This is a placeholder implementation
# The actual logic is handled by ClarificationMiddleware which intercepts this tool call
# and interrupts execution to present the question to the user
return "Clarification request processed by middleware"
```

真正的逻辑在 `ClarificationMiddleware`（middleware 链最后一个，位置 18）：
1. 检测到 `ask_clarification` 的 tool call
2. 因为 `return_direct=True`，LangGraph 不会继续执行后续 node
3. Middleware 返回 `Command(goto=END)` 暂停图执行
4. 问题通过 SSE 推送到前端，等待用户回复
5. 用户回复后图恢复执行

### LLM 使用指导（来自 tool description 原文）

- **一次只问一个问题**，保持清晰
- 危险操作**必须**先调用确认
- 调用后执行会自动中断，等用户回复再继续
- 不要瞎猜用户的意图

---

## view_image

**源码**: `packages/harness/deerflow/tools/builtins/view_image_tool.py:49`
**加载条件**: 模型配置了 `supports_vision: true`
**Tool Name**: `view_image`

### 用途

让视觉模型"看到"图片。LLM 调用后，图片被读取 → base64 编码 → 存入 state，下一轮 LLM 调用前由 `ViewImageMiddleware` 注入为消息内容。

### 参数

| 参数 | 类型 | 说明 |
|------|------|------|
| `image_path` | `str` | 图片文件的绝对 `/mnt/user-data` 虚拟路径 |

### 安全边界

只允许 3 个虚拟根路径：
```python
_ALLOWED_IMAGE_VIRTUAL_ROOTS = (
    "/mnt/user-data/workspace",
    "/mnt/user-data/uploads",
    "/mnt/user-data/outputs",
)
```

### 校验链

1. **路径范围**: `_is_allowed_image_virtual_path()` — 是否在 3 个允许的根路径下
2. **路径验证**: `validate_local_tool_path(path, thread_data, read_only=True)` — 防穿越
3. **文件存在**: `path.exists()` + `path.is_file()`
4. **后缀白名单**: `.jpg` / `.jpeg` / `.png` / `.webp`
5. **Magic byte 校验**: 检查文件头字节（`\xff\xd8\xff` = JPEG, `\x89PNG` = PNG, `RIFF...WEBP` = WebP）
6. **MIME 一致性**: magic byte 推断的 MIME 必须与后缀匹配
7. **大小限制**: 最大 20 MiB（`_MAX_IMAGE_BYTES = 20 * 1024 * 1024`）

### 注入链路

1. Tool 返回 `Command(update={"viewed_images": {path: {base64, mime_type}}})`
2. `merge_viewed_images` reducer 合并入 state
3. `ViewImageMiddleware` (位置 14) 在下一次 LLM 调用前，将 viewed_images 转为 `HumanMessage` 的 image content block
4. 处理完后自动清除 viewed_images

### 错误处理

所有错误都返回带 `tool_call_id` 的 ToolMessage，包含具体原因（文件不存在/格式不支持/过大/路径不允许等）。

---

## list_uploaded_files 🆕

**源码**: `packages/harness/deerflow/tools/builtins/list_uploaded_files_tool.py:188`
**加载条件**: 始终（`get_available_tools()`，`include_upload_tool` 默认 True，`tools.py:98`）
**Tool Name**: `list_uploaded_files`

### 用途

让 agent **按需发现历史上传文件**（之前轮次上传的）。与 `<current_uploads>`（只列当前 run 新增上传）互补——本工具**排除当前 run 上传的文件**。

### 参数

| 参数 | 类型 | 说明 |
|------|------|------|
| `include_outline` | `bool \| list[str]` | 是否返回文档大纲/预览（`.md`-convertible 文件）。`False`（默认）只返回文件名+大小+路径；`True` 全部；`list[str]` 指定文件 |
| `max_results` | `int` | 最大返回数（默认 20，max 100） |
| `query` | `str` (opt) | 🆕 文件名子串过滤（casefold 包含匹配），在 mtime 截断**之前**应用——让更早的上传不被默认 20 条上限挤掉（#5341） |
| `extensions` | `list[str]` (opt) | 🆕 扩展名过滤；token 归一化为小写点后缀（`"PDF"`→`.pdf`，模型给的 glob 形如 `*.pdf` 会剥掉 `*`），空集 = 不过滤 |

### LLM 使用场景

- 用户提到之前上传的文件但没指名（"分析我之前上传的那些 PDF"）
- agent 需要检查当前 thread 有哪些文件可用

### 实现要点

- `_resolve_thread_id()` 从 runtime context → RunnableConfig → `get_config()` 三级解析 thread_id
- `_resolve_user_id()` 用 `resolve_runtime_user_id()` 解析用户（与其它工具一致）
- 返回 dict：`{"files": [...]}`；无 runtime context / 找不到 thread 时返回空列表 + message

---

## inspect_run_status 🆕 2.2

**源码**: `packages/harness/deerflow/tools/builtins/inspect_run_status_tool.py:100-113`（`build_inspect_run_status_tool(*, context_window)` 闭包工厂 + `@tool("inspect_run_status")` 内层函数，装饰器在 `:103`）
**加载条件**: **每次装配都加**——`get_available_tools()` 末尾无条件 `builtin_tools.append(build_inspect_run_status_tool(context_window=model_config.context_window if model_config else None))`（`tools/tools.py:218`）
**Tool Name**: `inspect_run_status`

### 用途

让 agent 自查**本次 run 的用量与进度**（token 消耗、上下文填充率、消息/工具调用计数、todo 进度），而不必把对话正文再读一遍。工具是 **只读**的，`snapshot_run_status()` 的 docstring 明写「no message or todo text leaves the tool」——返回体里没有任何消息内容或 todo 文本。

### 参数

无业务参数，只吃注入的 `runtime`（`state` + `context`）。模型可见签名是 `inspect_run_status()`。

### 返回体（`snapshot_run_status`，`inspect_run_status_tool.py:39-98`）

| 字段 | 含义 |
|------|------|
| `scope` | `current_run_visible` 或更宽的可见范围（`_current_messages(list, context)` 决定） |
| `token_usage` | `{input, output, total}`，逐条累加 `AIMessage.usage_metadata` |
| `usage_missing_messages` | 没有 `usage_metadata` 的 AIMessage 条数（provider 没报用量） |
| `message_count` | 可见消息数 |
| `tool_calls_this_run` | 仅当 `scope == "current_run_visible"` 时给数字，否则 `None` |
| `context_fill` | `{used_input_tokens, limit_tokens, fraction(3 位小数), basis: "last_reported_model_input"}`；**需要** `context_window` 有效且最后一条 AI 消息报了 `input_tokens`，否则整体为 `None` |
| `has_summary` | `state["summary_text"]` 是否是非空字符串（即上下文已被压缩过） |
| `todos` | `{pending, in_progress}` 计数（不返回 todo 文本） |

### 契约级细节

- `context_fill` 的 `basis` 刻意写死成 `"last_reported_model_input"`：它不是"当前上下文占用"的精确值，只是**最后一次模型上报的输入 token 数**。装配时绑定的 `context_window` 来自当前 model 配置（`build_inspect_run_status_tool` 的 docstring：「Bind the effective model's configured context size at assembly time」），所以换模型必须重新装配，不能复用旧工具实例。
- **子代理分发消息会清空 `last_input`**（`inspect_run_status_tool.py:63-66`）：`TokenUsageMiddleware` 会把已完成的子代理用量折叠进那条 dispatch 的 `AIMessage`，此时它的 `input_tokens` 不再是上下文大小的代理量，因此 `last_input = None` → `context_fill = None`。
- 计数天然可选：docstring 直说「Counts may omit compacted messages or provider-omitted usage」——压缩掉的消息不计入，`usage_missing_messages` 就是后者的计数器。

---

## schedule_task / stop_scheduled_task 🆕 2.2

**源码**: `packages/harness/deerflow/tools/scheduled_tasks.py:34-41`（`schedule_task`）、`:165-166`（`stop_scheduled_task`）
**加载条件**: `scheduler_tools_enabled(config) and is_scheduler_capability(scheduler_capability)` 时**二选一**注入——`scheduler_capability.mode == "interactive"` → 只加 `schedule_task`，否则（`scheduled`）→ 只加 `stop_scheduled_task`（`tools/tools.py:182-186`）。同时 `tools/tools.py:148` 会把 YAML `tools[]` 里 `deerflow.tools.scheduled_tasks:schedule_task` / `:stop_scheduled_task` 两条**剔掉**：在配置里注册不能扩大 host 授予，也不能改变跑在哪种 mode。
**Tool Name**: `schedule_task` / `stop_scheduled_task`（同一装配里**永不同时存在**）

### 用途

- `schedule_task`：在**当前交互对话里**替用户增删改查自己的定时任务。`action ∈ {create, update, list, pause, resume, delete, note, trial}`。
- `stop_scheduled_task`：**在一次计划运行内部**，让它按自己的停止条件把这个 schedule 暂停掉（本次 run 继续跑完，暂停在 run 结束后生效）。docstring 特意点明：「Meeting this run's goal does not by itself mean the stop rule is met」——单次目标达成不结束循环计划。

### 参数（`schedule_task`，全部可选除 `action`/`runtime`）

| 参数 | 类型 | 说明 |
|------|------|------|
| `action` | Literal | 见上 |
| `task_id` | `str \| None` | update/pause/resume/delete/note 的目标 |
| `title` / `prompt` / `stop_condition` | `str \| None` | 任务本体；docstring 要求 prompt 里**只写每次跑做什么**，不写节奏、停止规则或任何 ID |
| `schedule_type` | `once \| interval \| cron \| None` | 与 `schedule_spec` 搭配 |
| `schedule_spec` / `timezone` | `dict` / `str \| None` | 时间规格与时区 |
| `context_mode` | `fresh_thread_per_run`（默认）/ `reuse_thread` | 只在 `create` 时写进 request |
| `goal_objective` / `max_runs` / `end_at` | `str` / `int` / `str \| None` | 目标与终止条件 |
| `note` | `str \| None` | 写备忘 |
| `clear_fields` | `list["goal_objective" \| "max_runs" \| "end_at" \| "stop_condition"] \| None` | 显式清空字段（而不是靠传 `None`） |

### 运行时授予校验 `_capability(runtime, mode)`（`scheduled_tasks.py:18-31`）

**四道门全部通过才返回 capability**，任一失败返回 `None` → 工具回结构化错误：

1. `runtime.context["is_subagent"]` 为真 → `None`（子代理拿不到）；
2. `scheduler_tools_enabled(context["app_config"])` 为假 → `None`（总开关）；
3. `context[SCHEDULER_CAPABILITY_CONTEXT_KEY]` 不是合法 `SchedulerRunCapability`，或其 `mode` 与请求的 mode 不符 → `None`；
4. `resolve_run_interaction_policy(config)` 抛 `ValueError`，或解析出的 `policy.mode.value` 与 mode 不符 → `None`（交互模式与授予打架时**默认拒绝**）。

`stop_scheduled_task` 的失败返回固定为 `{"error": "Stopping a schedule is unavailable in this run.", "code": "scheduler_tools_disabled", "status_code": 503}`（`scheduled_tasks.py:186-187`）。

### 为什么值得在 builtin 目录里记一笔

这两个工具是 2.2 「**能力由 host 授予，配置不能扩权**」纪律的最干净样本：同一对 `config.yaml` 开关（`scheduler.enabled` **且** `scheduler.tool_enabled`，`scheduler_tools_enabled()` 要求两者皆真，`scheduler/runtime.py:23-26`）在不同运行模式下产出**不同工具集**，而 YAML 里的同名 `use` 会被主动剥离。调度器子系统本身属于 persistence/scheduler 域，此处只钉工具装配面。
