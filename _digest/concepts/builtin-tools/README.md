---
title: "DeerFlow Built-in Tools 全量目录"
description: "DeerFlow 共有 **17 个唯一 tool name**（17 个 function call），其中 7 个沙箱工具通过 `config.yaml` → `resolve_variable()` 动态加载（默认配置标配），7 个在"
type: index
---

# DeerFlow Built-in Tools 全量目录

> 基于源码 `backend/packages/harness/deerflow/tools/` 和 `sandbox/tools.py` 逐文件核实，2026-05-28。

## 总览

DeerFlow 共有 **17 个唯一 tool name**（17 个 function call），其中 7 个沙箱工具通过 `config.yaml` → `resolve_variable()` 动态加载（默认配置标配），7 个在 `get_available_tools()` 的条件分支中硬编码（`tools/tools.py`），2 个在 `make_lead_agent()` 中按角色追加（`agent.py`），另有 1 个（`write_todos`）由 LangChain Middleware 注入。

分 6 个类别，每类一个详文：

| 类别 | 数量 | 工具 | 详文 |
|------|------|------|------|
| 运行时控制 | 3 | `present_files`, `ask_clarification`, `view_image` | [A-runtime-control.md](A-runtime-control.md) |
| 沙箱/文件系统 | 7 | `bash`, `ls`, `read_file`, `write_file`, `str_replace`, `glob`, `grep` | [B-sandbox-filesystem.md](B-sandbox-filesystem.md) |
| Agent 定义管理 | 3 | `setup_agent`, `update_agent`, `skill_manage` | [C-agent-lifecycle.md](C-agent-lifecycle.md) |
| 任务委派/工具发现 | 2 | `task`, `tool_search` | [D-task-toolsearch.md](D-task-toolsearch.md) |
| 外部 Agent 集成 | 1 | `invoke_acp_agent` | [E-acp-agent.md](E-acp-agent.md) |
| Plan Mode | 1 | `write_todos` | [F-plan-mode.md](F-plan-mode.md) |

---

## 装配顺序

`get_available_tools()` (`tools/tools.py:44`) 按以下优先级组装，**同一 name 去重，先注册生效**：

```
优先级高 → 低（均在 get_available_tools() 内）

1. Config-defined tools (config.yaml tools[] → resolve_variable)
   └── 沙箱 7 工具 + 社区 web_search/web_fetch/image_search

2. Built-in tools (硬编码)
   ├── 始终: present_files, ask_clarification
   ├── skill_evolution.enabled → skill_manage
   ├── supports_vision → view_image
   ├── tool_search.enabled + 有 MCP 工具 → tool_search
   └── subagent_enabled → task

3. MCP tools (extensions_config.json → 懒加载)
   └── 外部 MCP server 动态发现

4. ACP agent tools
   └── config.yaml acp_agents 有配置 → invoke_acp_agent
```

`make_lead_agent()` (`agent.py:461-479`) 在 `get_available_tools()` 返回后追加：

```
5. Agent 创建/自更新 (agent.py)
   ├── is_bootstrap → setup_agent
   └── agent_name 已设置 → update_agent
```

`write_todos` 由 LangChain 的 `TodoListMiddleware` 注入（middleware 位置 10），不入 `get_available_tools()`。

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
