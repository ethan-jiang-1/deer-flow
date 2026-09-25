---
title: "DeerFlow Built-in Tools 全量目录"
description: "DeerFlow 共有 **27 个唯一 tool name**（27 个 function call），其中 7 个沙箱工具通过 `config.yaml` → `resolve_variable()` 动态加载（默认配置标配），其余在"
type: index
---

# DeerFlow Built-in Tools 全量目录

> 基于源码 `backend/packages/harness/deerflow/tools/` 和 `sandbox/tools.py` 逐文件核实，2026-05-28 初版；同步 #6（`ce635b7d`，2026-09-13）复核更新。

## 总览

DeerFlow 共有 **27 个唯一 tool name**（27 个 function call），其中 7 个沙箱工具通过 `config.yaml` → `resolve_variable()` 动态加载（默认配置标配），其余在 `get_available_tools()` 的条件分支中硬编码（`tools/tools.py`）、`make_lead_agent()` 中按角色追加（`agent.py`）、或由 middleware / lead agent 末尾注入（`write_todos`、task continuity 三件套）。

分 7 个类别，每类一个详文：

| 类别 | 数量 | 工具 | 详文 |
|------|------|------|------|
| 运行时控制 | 6 | `present_files`, `ask_clarification`, `view_image`, `list_uploaded_files` 🆕, `list_background_tasks` 🆕, `cancel_background_task` 🆕 | [A-runtime-control.md](A-runtime-control.md) |
| 沙箱/文件系统 | 7 | `bash`, `ls`, `read_file`, `write_file`, `str_replace`, `glob`, `grep` | [B-sandbox-filesystem.md](B-sandbox-filesystem.md) |
| Agent 定义管理 | 4 | `setup_agent`, `update_agent`, `skill_manage`, `review_skill_package` 🆕 | [C-agent-lifecycle.md](C-agent-lifecycle.md) |
| 任务委派/工具发现 | 5 | `task`, `tool_search`, `batch_task` 🆕, `batch_status` 🆕, `cancel_batch` 🆕 | [D-task-toolsearch.md](D-task-toolsearch.md) |
| 外部 Agent 集成 | 1 | `invoke_acp_agent` | [E-acp-agent.md](E-acp-agent.md) |
| Plan Mode | 1 | `write_todos` | [F-plan-mode.md](F-plan-mode.md) |
| 任务连续性（opt-in）🆕 | 3 | `task_note`, `history_search`, `history_read` | [D-task-toolsearch.md](D-task-toolsearch.md) |

条件加载说明：`list_background_tasks`/`cancel_background_task` 仅在持久 MCP task 运行时安装后注入（`is_mcp_task_runtime_available()`）；`batch_task`/`batch_status`/`cancel_batch` 仅在 `subagent_enabled` 且 SQL-backed 批量运行时可用（`is_subagent_batch_runtime_available()`）；`review_skill_package` 已进入常驻 `BUILTIN_TOOLS` 列表（与 `present_files`、`ask_clarification` 并列）。

---

## 装配顺序

`get_available_tools()` (`tools/tools.py:44`) 按以下优先级组装，**同一 name 去重，先注册生效**：

```
优先级高 → 低（均在 get_available_tools() 内）

1. Config-defined tools (config.yaml tools[] → resolve_variable)
   └── 沙箱 7 工具 + 社区 web_search/web_fetch/image_search

2. Built-in tools (硬编码)
   ├── 始终: present_files, ask_clarification, review_skill_package
   ├── MCP task runtime 安装 → list_background_tasks, cancel_background_task
   ├── include_upload_tool（默认 True）→ list_uploaded_files
   ├── skill_evolution.enabled → skill_manage
   ├── supports_vision → view_image
   └── subagent_enabled → task（+ batch runtime 可用 → batch_task, batch_status, cancel_batch）

3. MCP tools (extensions_config.json → 懒加载)
   └── 外部 MCP server 动态发现

4. ACP agent tools
   └── config.yaml acp_agents 有配置 → invoke_acp_agent
```

`make_lead_agent()` (`agent.py`) 在 `get_available_tools()` 返回后追加：

```
5. Agent 创建/自更新 (agent.py)
   ├── is_bootstrap → setup_agent
   └── agent_name 已设置 → update_agent

6. tool_search (agent.py → assemble_deferred_tools())
   └── tool_search.enabled 时从 MCP 工具装配 deferred 集合
       （不再在 get_available_tools() 内——同步 #6 核实：deferred 装配
         已上移到各 agent 构造点，MCP 工具用 tag_mcp_tool() 打标）

7. 任务连续性 (agent.py → append_task_continuity_tools())
   └── task_continuity.enabled → task_note, history_search, history_read
       （按名去重，opt-in）
```

`write_todos` 由 LangChain 的 `TodoListMiddleware` 注入（middleware 位置 10），不入 `get_available_tools()`。

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
