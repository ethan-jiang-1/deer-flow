---
title: "A. Agent 运行时控制"
description: "## present_files"
topics: [tools, builtin, sandbox-tools]
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
