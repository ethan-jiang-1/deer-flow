---
title: "DeerFlow Built-in Tools 全量目录"
description: "DeerFlow 核心内置共有 **28 个唯一 tool name**（28 个 function call；另有随扩展装配的 plugin 工具层），其中 7 个沙箱工具通过 `config.yaml` → `resolve_variable()` 动态加载（默认配置标配），其余在"
type: index
---

# DeerFlow Built-in Tools 全量目录

> 基于源码 `backend/packages/harness/deerflow/tools/` 和 `sandbox/tools.py` 逐文件核实，2026-05-28 初版；同步 #6（`ce635b7d`，2026-09-13）复核更新；**2.2.0 基线复核**补齐 `inspect_run_status`、`schedule_task`/`stop_scheduled_task`、plugin 工具层与个人 MCP 同名丢弃规则。

## 总览

DeerFlow 核心内置共有 **28 个唯一 tool name**（28 个 function call；另有 2.2 新增的 plugin 工具层，名字与数量由扩展决定，不计入此数），其中 7 个沙箱工具通过 `config.yaml` → `resolve_variable()` 动态加载（默认配置标配），其余在 `get_available_tools()` 的条件分支中硬编码（`tools/tools.py`）、`make_lead_agent()` 中按角色追加（`agent.py`）、或由 middleware / lead agent 末尾注入（`write_todos`、task continuity 三件套）。🆕 2.2 新增两个常驻/条件工具：`inspect_run_status`（每次装配都加）与 `schedule_task`/`stop_scheduled_task`（按 host 授予与 mode 二选一）——**两者都计入本表的 28 与 7 类划分之外的例外说明**，见下。

分 7 个类别，每类一个详文：

| 类别 | 数量 | 工具 | 详文 |
|------|------|------|------|
| 运行时控制 | 9 | `present_files`, `ask_clarification`, `view_image`, `list_uploaded_files`, `inspect_run_status` 🆕2.2, `schedule_task` 🆕2.2, `stop_scheduled_task` 🆕2.2（与 `schedule_task` 按 mode 二选一）, `list_background_tasks`, `cancel_background_task` | [A-runtime-control.md](A-runtime-control.md) |
| 沙箱/文件系统 | 7 | `bash`, `ls`, `read_file`, `write_file`, `str_replace`, `glob`, `grep` | [B-sandbox-filesystem.md](B-sandbox-filesystem.md) |
| Agent 定义管理 | 4 | `setup_agent`, `update_agent`, `skill_manage`, `review_skill_package` 🆕 | [C-agent-lifecycle.md](C-agent-lifecycle.md) |
| 任务委派/工具发现 | 5 | `task`, `tool_search`, `batch_task` 🆕, `batch_status` 🆕, `cancel_batch` 🆕 | [D-task-toolsearch.md](D-task-toolsearch.md) |
| 外部 Agent 集成 | 1 | `invoke_acp_agent` | [E-acp-agent.md](E-acp-agent.md) |
| Plan Mode | 1 | `write_todos` | [F-plan-mode.md](F-plan-mode.md) |
| 任务连续性（opt-in）🆕 | 3 | `task_note`, `history_search`, `history_read` | [D-task-toolsearch.md](D-task-toolsearch.md) |
| Plugin 工具（2.2 新增层）🆕 | 0（按插件） | `build_plugin_tools()` 由 operator 在 `config.yaml → plugins:` 里装配，名字随扩展而定 | 见下文「装配顺序」第 4' 步 |

条件加载说明：`list_background_tasks`/`cancel_background_task` 仅在持久 MCP task 运行时安装后注入（`is_mcp_task_runtime_available()`）；`batch_task`/`batch_status`/`cancel_batch` 仅在 `subagent_enabled` 且 SQL-backed 批量运行时可用（`is_subagent_batch_runtime_available()`，且 2.2 起经 `bind_batch_tools(...)` 绑定 submitter）；`review_skill_package` 是常驻 `BUILTIN_TOOLS` 三项之一（`tools/tools.py:33-37`，与 `present_files`、`ask_clarification` 并列）。

🆕 **2.2 的两个新条件工具**：

- `inspect_run_status`（`tools/builtins/inspect_run_status_tool.py:103`）：`get_available_tools()` 末尾**无条件** `builtin_tools.append(build_inspect_run_status_tool(context_window=...))`（`tools/tools.py:218`），上下文窗口来自当前 model 配置。
- `schedule_task` / `stop_scheduled_task`：只在 `scheduler_tools_enabled(config) and is_scheduler_capability(scheduler_capability)` 时注入，且**按 `scheduler_capability.mode` 二选一**（`interactive` → `schedule_task`，否则 → `stop_scheduled_task`，`tools/tools.py:182-186`）。同时 `tools.py:152-154` 会从 YAML 的 `tools[]` 里**剔除**这两个 `use` 路径——在配置里注册它们不能扩大 host 授予或改变交互模式。这是 2.2 新增的"能力授予优于配置"纪律的一个实例。

---

## 装配顺序

`get_available_tools()` (`tools/tools.py:44`) 按以下优先级组装，**同一 name 去重，先注册生效**：

```
优先级高 → 低（均在 get_available_tools() 内）

1. Config-defined tools (config.yaml tools[] → resolve_variable)          tools.py:144-163
   ├── 沙箱 7 工具 + 社区 web_search/web_fetch/image_search
   └── 先剔除：scheduled_tasks 的 schedule/stop 两个 use（:148）、
       未授权的 conversation reader（:149-150）、knowledge_base 未启用时的
       knowledge 组（:155-159）、禁止 host bash 时的 bash 组（:160-162）

2. Built-in tools (硬编码)                                                  tools.py:181-220
   ├── 始终: present_files, ask_clarification, review_skill_package       :181（BUILTIN_TOOLS）
   ├── scheduler 授予 → schedule_task 或 stop_scheduled_task（二选一）      :182-186
   ├── MCP task runtime 安装 → list_background_tasks, cancel_background_task :187-188
   ├── include_upload_tool（默认 True）→ list_uploaded_files                :189-190
   ├── skill_evolution.enabled → skill_manage                              :191-195
   ├── subagent_enabled → task（+ batch runtime 可用 → batch_task, batch_status, cancel_batch） :197-203
   ├── 始终 → inspect_run_status（带 context_window）                       :218
   └── supports_vision → view_image                                        :219-221

3. MCP tools (extensions_config.json → 懒加载)                              tools.py:246-306
   ├── 部署 MCP（cache，tag_mcp_tool）
   ├── 个人 MCP（get_user_mcp_tools；与部署同名者整条丢弃并 warn）
   └── filter_mcp_plugins(mcp_tools, mcp_plugins, extensions_config)（deny-by-default 白名单）

4. ACP agent tools
   └── config.yaml acp_agents 有配置 → invoke_acp_agent

4'. 🆕 Plugin tools（2.2）                                                   tools.py:338-343
   └── build_plugin_tools(extensions, groups=groups) 追加在最后
```

`make_lead_agent()` (`agent.py`) 在 `get_available_tools()` 返回后追加：

```
5. Agent 创建/自更新 (agents/lead_agent/agent.py)
   ├── setup_agent：无条件追加到 raw_tools（:1170 `... + [setup_agent]`，由 is_bootstrap 决定是否走到该分支）
   └── update_agent：extra_tools = [update_agent] if agent_name and not is_webhook_channel else []（:1318）
       🆕 2.2：webhook 通道（_WEBHOOK_CHANNELS = {"github"}，:92）拿不到 update_agent

6. tool_search (agent.py → assemble_deferred_tools())
   └── tool_search.enabled 时从 MCP 工具装配 deferred 集合
       （不再在 get_available_tools() 内——同步 #6 核实：deferred 装配
         已上移到各 agent 构造点，MCP 工具用 tag_mcp_tool() 打标）

7. 任务连续性 (agent.py → append_task_continuity_tools())
   └── task_continuity.enabled → task_note, history_search, history_read
       （按名去重，opt-in）
```

`write_todos` 由 LangChain 的 `TodoListMiddleware` 注入（middleware 位置 10），不入 `get_available_tools()`。

🆕 **同名去重的实际语义**：`all_tools` 的拼接顺序是 `loaded_tools + builtin_tools + mcp_tools + acp_tools + plugin_tools`，最终由 `_ensure_sync_invocable_tool` 统一包装，**先注册者胜**。因此 config 里写的工具永远压过同名 builtin，而 plugin 工具排在最后——插件不能覆盖 core 工具名。

⚠️ **personal MCP 与部署 MCP 同名**：不是"先注册胜"，而是**整条个人工具被丢弃**（`tools.py:293-299`：`colliding_names = extensions_config.mcp_servers.keys() & personal_config.mcp_servers.keys()`，命中即 `logger.warning("Skipping personal MCP tools with deployment name collisions: ...")` 并把该 server 的工具全部滤掉）。

---

## 不在此列的

以下**不算是**原生 built-in tool，而是通过 config 配置的 provider 实现：

| Tool Name | Providers | 说明 |
|-----------|-----------|------|
| `web_search` | DuckDuckGo, Tavily, Serper, Exa, Firecrawl, InfoQuest, Serply 🆕, Tencent WSA 🆕, Sofya 🆕 | 需在 `config.yaml` 的 `tools[]` 中选一个配置 |
| `web_fetch` | Jina AI, Exa, InfoQuest, Firecrawl, Sofya 🆕 | 同上 |
| `image_search` | DuckDuckGo, InfoQuest | 同上 |
| `knowledge_search` | RAGFlow, LightRAG 🆕 | 同上；两者同名互斥 |
| MCP tools | 任意 MCP server（含可选的 Parallel Search server 🆕） | 通过 `extensions_config.json` 配置，动态发现 |

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
| `packages/harness/deerflow/tools/builtins/tool_search.py` | `tool_search` + `DeferredToolCatalog`（+ `DeferredToolSetup`，promotion 存 graph state） |
| `packages/harness/deerflow/tools/builtins/task_tool.py` | `task` (subagent) |
| `packages/harness/deerflow/tools/builtins/batch_task_tool.py` | `batch_task`, `batch_status`, `cancel_batch`（durable batch） |
| `packages/harness/deerflow/tools/builtins/background_tasks_tool.py` | `list_background_tasks`, `cancel_background_task`（durable MCP task） |
| `packages/harness/deerflow/tools/builtins/list_uploaded_files_tool.py` | `list_uploaded_files` |
| `packages/harness/deerflow/tools/builtins/review_skill_package_tool.py` | `review_skill_package` |
| `packages/harness/deerflow/tools/builtins/invoke_acp_agent_tool.py` | `invoke_acp_agent` |
| `packages/harness/deerflow/agents/task_continuity/tools.py` | `task_note`, `history_search`, `history_read`（opt-in） |
| `packages/harness/deerflow/tools/skill_manage_tool.py` | `skill_manage` |
| `packages/harness/deerflow/sandbox/tools.py` | `bash`, `ls`, `read_file`, `write_file`, `str_replace`, `glob`, `grep` |
