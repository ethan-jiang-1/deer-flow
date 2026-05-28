# DeerFlow Built-in Tools 全量目录

> 基于源码 `backend/packages/harness/deerflow/tools/` 和 `sandbox/tools.py` 逐文件核实，2026-05-28。

## 总览

DeerFlow 共有 **17 个唯一 tool name**（17 个 function call），其中 11 个硬编码在 `tools/tools.py` 的 `BUILTIN_TOOLS` 及其条件分支中，7 个沙箱工具通过 `config.yaml` → `resolve_variable()` 动态加载（但默认配置标配），另有 1 个（`write_todos`）由 LangChain Middleware 注入。

分 6 个类别：

| 类别 | 数量 | 工具 |
|------|------|------|
| [运行时控制](#a-agent-运行时控制) | 3 | `present_files`, `ask_clarification`, `view_image` |
| [沙箱/文件系统](#b-沙箱文件系统) | 7 | `bash`, `ls`, `read_file`, `write_file`, `str_replace`, `glob`, `grep` |
| [Agent 定义管理](#c-agent-定义管理) | 3 | `setup_agent`, `update_agent`, `skill_manage` |
| [任务/工具发现](#d-任务委派--工具发现) | 2 | `task`, `tool_search` |
| [外部 Agent](#e-外部-agent-集成) | 1 | `invoke_acp_agent` |
| [Plan Mode](#f-plan-mode) | 1 | `write_todos` |

---

## 装配顺序

`get_available_tools()` (`tools/tools.py:44`) 按以下优先级组装，**同一 name 去重，先注册生效**：

```
优先级高 → 低

1. Config-defined tools (config.yaml tools[] → resolve_variable)
   └── 沙箱 7 工具 + 社区 web_search/web_fetch/image_search

2. MCP tools (extensions_config.json → 懒加载)
   └── 外部 MCP server 动态发现

3. Built-in tools (硬编码)
   ├── 始终: present_files, ask_clarification
   ├── skill_evolution.enabled → skill_manage
   ├── supports_vision → view_image
   ├── tool_search.enabled + 有 MCP 工具 → tool_search
   ├── subagent_enabled → task
   └── bootstrap/custom agent → setup_agent / update_agent

4. ACP agent tools
   └── config.yaml acp_agents 有配置 → invoke_acp_agent
```

---

## A. Agent 运行时控制

Agent 与用户交互的元操作。这 3 个不操作文件系统，只影响对话流程。

### `present_files`

- **源码**: `tools/builtins/present_file_tool.py:83`
- **加载条件**: 始终
- **作用**: 把输出目录里的文件标记为"用户可见"，前端会渲染/展示。LLM 创建完文件后调用，用户端就能看到并可下载
- **关键参数**: `filepaths: list[str]` — 必须是 `/mnt/user-data/outputs/` 下的绝对路径
- **安全边界**: 只允许 `outputs/` 子目录，传 `workspace/` 或 `uploads/` 路径会报错
- **返回值**: `Command`，更新 `artifacts` state（前端读取展示）+ ToolMessage

### `ask_clarification`

- **源码**: `tools/builtins/clarification_tool.py:6`
- **加载条件**: 始终
- **作用**: 需要人类输入时暂停 Agent。`ClarificationMiddleware`（middleware 链最后一个）拦截它，`return_direct=True` → `Command(goto=END)` 暂停图执行，等用户回复后再继续
- **关键参数**:
  - `question: str` — 要问的问题
  - `clarification_type` — `missing_info` / `ambiguous_requirement` / `approach_choice` / `risk_confirmation` / `suggestion`
  - `context: str` — 可选，解释为什么需要澄清
  - `options: list[str]` — 可选，给用户的选项
- **最佳实践**（来自 tool description 原文）: 一次只问一个问题；危险操作前必须调用确认

### `view_image`

- **源码**: `tools/builtins/view_image_tool.py:49`
- **加载条件**: 模型 `supports_vision: true`
- **作用**: 读取图片文件 → base64 编码 → 存入 `ThreadState.viewed_images`。`ViewImageMiddleware` 在下一次 LLM 调用前注入为 `HumanMessage` content block，让视觉模型"看到"图片
- **关键参数**: `image_path: str` — 只允许 3 个虚拟路径：`/mnt/user-data/workspace/`, `/mnt/user-data/uploads/`, `/mnt/user-data/outputs/`
- **安全**: 文件名后缀 + magic byte 双重校验（jpeg/png/webp），最大 20MB，路径防穿越

---

## B. 沙箱/文件系统

定义在 `sandbox/tools.py`，通过 `config.yaml` 的 `tools[]` 段加载（`deerflow.sandbox.tools:xxx_tool`）。默认配置全部标配。

### `bash`

- **源码**: `sandbox/tools.py:1328`
- **加载条件**: 默认加载（`group: bash`）；本地沙箱时需 `allow_host_bash: true`
- **作用**: 在沙箱里执行 shell 命令。本地模式有虚拟路径翻译 + CWD 自动注入；Docker/K3s 模式在容器内执行
- **安全**: 本地模式拒绝绝对路径（只允许 `/mnt/user-data/`、`/mnt/skills/`、`/mnt/acp-workspace/`、配置的 mount 路径、系统路径前缀如 `/bin/`、`/dev/`）；禁用 `..` 路径穿越；拒绝 `file://` URL
- **输出截断**: 默认 20,000 chars，头尾各保留 50%（中间截断），因为 stdout/stderr 可能混排

### `ls`

- **源码**: `sandbox/tools.py:1384`
- **加载条件**: 默认加载（`group: file:read`）
- **作用**: 列目录，tree 格式，最大 2 层深度
- **输出截断**: 默认 20,000 chars，头部截断

### `read_file`

- **源码**: `sandbox/tools.py:1606`
- **加载条件**: 默认加载（`group: file:read`）
- **作用**: 读文件内容，支持 `start_line`/`end_line` 按行范围读取（1-indexed）
- **输出截断**: 默认 50,000 chars，头部截断
- **特殊处理**: `LoopDetectionMiddleware` 以 200 行 bucket 粒度统计 `read_file` 调用，避免误报循环

### `write_file`

- **源码**: `sandbox/tools.py:1674`
- **加载条件**: 默认加载（`group: file:write`）
- **作用**: 写文件（overwrite 为默认），支持 `append: true` 追加。自动创建父目录
- **并发安全**: 用 `file_operation_lock` 对 `(sandbox_id, path)` 加锁，防止同一进程内并发写同一个文件

### `str_replace`

- **源码**: `sandbox/tools.py:1734`
- **加载条件**: 默认加载（`group: file:write`）
- **作用**: 基于子字符串替换的文件编辑。默认 `replace_all: false` 只替换第一次出现（且要求 `old_str` 在文件中出现恰好 1 次），`replace_all: true` 替换全部
- **并发安全**: 同 `write_file`，有 file_operation_lock

### `glob`

- **源码**: `sandbox/tools.py:1438`
- **加载条件**: 默认加载（`group: file:read`）
- **作用**: 文件名模式匹配（`**/*.py` 等），可配置是否包含目录
- **结果上限**: 默认 200，最大 1000（受 `config.yaml` 控制）

### `grep`

- **源码**: `sandbox/tools.py:1510`
- **加载条件**: 默认加载（`group: file:read`）
- **作用**: 文件内容搜索，支持正则/字面量、大小写、glob 过滤
- **结果上限**: 默认 100，最大 500

---

## C. Agent 定义管理

让 Agent 自己创建和修改自身的配置。只在特定模式下可用。

### `setup_agent`

- **源码**: `tools/builtins/setup_agent_tool.py:16`
- **加载条件**: bootstrap 模式（`runtime.context['is_bootstrap'] = True`）
- **作用**: 创建全新自定义 Agent。写 `SOUL.md`（行为定义）+ `config.yaml`（技能白名单/描述等）到 `{base_dir}/users/{user_id}/agents/{name}/`
- **关键参数**: `soul: str` — 完整的 SOUL.md 内容；`description: str` — 一行描述；`skills: list[str]` — 可选技能白名单
- **原子性**: 先写文件，失败则回滚删除该 agent 目录

### `update_agent`

- **源码**: `tools/builtins/update_agent_tool.py:70`
- **加载条件**: custom agent 模式（`runtime.context['agent_name']` 已设置 + 非 bootstrap）
- **作用**: Agent 在对话中自我更新 SOUL.md 和 config.yaml。部分更新（只改传了的字段，不传不变）
- **关键参数**: `soul`, `description`, `skills`, `tool_groups`, `model` — 全部可选，传了就更新
- **原子性**: 先把所有要改的文件写到 temp 文件，全部成功后 `Path.replace`（POSIX 原子）切进去，任意一步失败都不影响现有文件

### `skill_manage`

- **源码**: `tools/skill_manage_tool.py:204`
- **加载条件**: `skill_evolution.enabled: true`
- **作用**: 管理 `skills/custom/` 下的自定义技能。支持 6 种 action：`create`（新建 SKILL.md）、`edit`（全量替换）、`patch`（子串替换）、`delete`（删除）、`write_file`（写附带文件如脚本）、`remove_file`（删附带文件）
- **安全扫描**: 每次写入前过 `scan_skill_content()`（block/allow/warn），可执行文件（`scripts/` 下）额外校验
- **并发**: 同 skill name 用 `asyncio.Lock` 串行化

---

## D. 任务委派 & 工具发现

### `task`

- **源码**: `tools/builtins/task_tool.py:186`
- **加载条件**: `subagent_enabled: true`（运行时参数或 config）
- **作用**: 把任务委派给子 Agent，在独立线程池中后台执行。主 Agent 用 `asyncio.sleep(5)` 轮询等结果
- **关键参数**: `subagent_type` — `general-purpose`（全工具，不含 task 防止递归嵌套）或 `bash`（命令执行专家）或自定义；`description` — 3-5 词任务描述；`prompt` — 完整任务说明
- **并发限制**: `SubagentLimitMiddleware` 限制最多 3 个并发，超量直接截断 tool call
- **超时控制**: 执行超时 + 60s buffer，超时后发 cancel 信号 + 延迟清理
- **Token 追踪**: 子 Agent 的 token 消耗会上报到父 RunJournal
- **SSE 事件**: `task_started → task_running → task_completed / task_failed / task_timed_out / task_cancelled`

### `tool_search`

- **源码**: `tools/builtins/tool_search.py:164`
- **加载条件**: `tool_search.enabled: true` 且存在 MCP 工具
- **作用**: 运行时发现延迟加载的 MCP 工具。MCP 工具的完整 schema 不出现在 LLM 的 `bind_tools` 里（`DeferredToolFilterMiddleware` 过滤），只有 name 在 system prompt 的 `<available-deferred-tools>` 中。Agent 需要某个工具时调 `tool_search` 查询，匹配后工具 schema 被 "promote" 出来，后续调用
- **查询语法**:
  - `select:name1,name2` — 直接点名获取
  - `+keyword rest` — 要求 name 包含 keyword，按 rest 相关性排序
  - `keyword query` — 正则搜索 name + description
- **上下文优化**: 减少 MCP server 工具多时 token 浪费（比如 GitHub MCP 几十个 tool）

---

## E. 外部 Agent 集成

### `invoke_acp_agent`

- **源码**: `tools/builtins/invoke_acp_agent_tool.py:139`
- **加载条件**: `config.yaml` 的 `acp_agents` 段有配置
- **作用**: 调用外部 ACP（Agent Communication Protocol）兼容 Agent，如 Claude Code CLI、Codex CLI 的 ACP 适配器。外部 Agent 在独立工作目录运行（`acp-workspace/`），结果只读
- **关键参数**: `agent: str` — 配置的 Agent 名称；`prompt: str` — 发给外部 Agent 的任务描述
- **MCP 透传**: 可把 DeerFlow 的 MCP server 配置转成 ACP 格式透传给外部 Agent
- **权限**: 支持 `auto_approve_permissions` 配置（允许自动 approve ACP 权限弹窗）
- **工作区隔离**: 每个 thread 有独立 `{base_dir}/threads/{thread_id}/acp-workspace/`

---

## F. Plan Mode

### `write_todos`

- **来源**: LangChain `TodoListMiddleware`，由 DeerFlow 的 `TodoMiddleware`（middleware 位置 10）包装
- **加载条件**: `runtime.config.configurable.is_plan_mode: true`
- **作用**: 复杂任务分解和状态追踪，LLM 可以创建/更新/完成/删除 todo
- **Todo 状态**: `todo_start`, `todo_complete`, `todo_update`, `todo_remove`
- **额外能力**: 上下文丢失检测 + 完成提醒（DeerFlow 的 `TodoMiddleware` 对 LangChain 原版的增强）

---

## 不在此列的

以下**不算是**原生 built-in tool，而是通过 config 配置的 provider 实现：

| Tool Name | Providers | 说明 |
|-----------|-----------|------|
| `web_search` | DuckDuckGo, Tavily, Serper, Exa, Firecrawl, InfoQuest | 需在 `config.yaml` 的 `tools[]` 中选一个配置 |
| `web_fetch` | Jina AI, Exa, InfoQuest, Firecrawl | 同上 |
| `image_search` | DuckDuckGo, InfoQuest | 同上 |
| MCP tools | 任意 MCP server | 通过 `extensions_config.json` 配置，动态发现 |

---

## 关键源码索引

| 文件 | 内容 |
|------|------|
| `packages/harness/deerflow/tools/tools.py` | `get_available_tools()` 装配逻辑，`BUILTIN_TOOLS` 列表 |
| `packages/harness/deerflow/tools/builtins/present_file_tool.py` | `present_files` |
| `packages/harness/deerflow/tools/builtins/clarification_tool.py` | `ask_clarification` |
| `packages/harness/deerflow/tools/builtins/view_image_tool.py` | `view_image` |
| `packages/harness/deerflow/tools/builtins/setup_agent_tool.py` | `setup_agent` |
| `packages/harness/deerflow/tools/builtins/update_agent_tool.py` | `update_agent` |
| `packages/harness/deerflow/tools/builtins/tool_search.py` | `tool_search` + `DeferredToolRegistry` |
| `packages/harness/deerflow/tools/builtins/task_tool.py` | `task` (subagent) |
| `packages/harness/deerflow/tools/builtins/invoke_acp_agent_tool.py` | `invoke_acp_agent` |
| `packages/harness/deerflow/tools/skill_manage_tool.py` | `skill_manage` |
| `packages/harness/deerflow/sandbox/tools.py` | `bash`, `ls`, `read_file`, `write_file`, `str_replace`, `glob`, `grep` |
