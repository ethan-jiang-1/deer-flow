---
title: "DeerFlow Built-in Tools 全量目录"
description: "28 个内置 tool name 的装配顺序、条件加载与同名去重规则，按 7 个类别组织、A–F 六个分册。"
type: index
topics: [tools, builtin, tool-assembly]
---

# DeerFlow Built-in Tools 全量目录

> **定位**：回答「Agent 手里到底有哪些内置工具、谁在什么条件下把它们装进去」。A–F 六个分册覆盖 28 个唯一 tool name（任务连续性三件套并入 D 篇），含运行时控制、沙箱文件、Agent 自更新、委派与发现、ACP、Plan Mode。给要查工具行为、改装配或排查「工具没出现」的人。
> **边界**：不覆盖由 community provider 实现的 `web_search` / `web_fetch` / `image_search` / `knowledge_search`（见 [community-tools](../community-tools/README.md)），不展开 MCP 服务的懒加载与鉴权（见 [internals/mcp](../../internals/mcp/README.md)），也不讲 subagent 执行内部（见 [subagent](../subagent/README.md)）。

## 阅读路径

1. **先看**：[A-runtime-control.md](A-runtime-control.md) — 运行时控制类工具，是用户可见行为（澄清、产物展示、看图、定时任务）的直接来源。
2. **再看**：[D-task-toolsearch.md](D-task-toolsearch.md) — `task` / `tool_search` / batch 三件套与 opt-in 的任务连续性工具。
3. **深入**：[B-sandbox-filesystem.md](B-sandbox-filesystem.md) — 七个沙箱工具的路径、权限与失败语义，以及它们为什么走 `config.yaml` 动态加载。

## 本篇目

| 文件 | 主题 | 深度 |
|---|---|---|
| [A-runtime-control.md](A-runtime-control.md) | 运行时控制：`present_files`、`ask_clarification`、`view_image`、`list_uploaded_files`、`inspect_run_status`、`schedule_task` / `stop_scheduled_task`、后台任务 | 概览 |
| [B-sandbox-filesystem.md](B-sandbox-filesystem.md) | 沙箱七工具：`bash`、`ls`、`read_file`、`write_file`、`str_replace`、`glob`、`grep` | 深入 |
| [C-agent-lifecycle.md](C-agent-lifecycle.md) | Agent 定义管理：`setup_agent`、`update_agent`、`skill_manage`、`review_skill_package` | 深入 |
| [D-task-toolsearch.md](D-task-toolsearch.md) | 任务委派与发现：`task`、`tool_search`、`batch_task`/`batch_status`/`cancel_batch`、`task_note`/`history_search`/`history_read` | 深入 |
| [E-acp-agent.md](E-acp-agent.md) | 外部 Agent 集成：`invoke_acp_agent` 的接入条件与调用协议 | 概览 |
| [F-plan-mode.md](F-plan-mode.md) | Plan Mode：`write_todos` 与 `TodoListMiddleware` 的注入位置 | 概览 |

## 速览

- **规模**：28 个唯一 tool name（28 个 function call）；另有 2.2 的 plugin 工具层，名字与数量由 operator 在 `config.yaml → plugins:` 装配，不计入 28。
- **两类加载**：7 个沙箱工具经 `config.yaml` → `resolve_variable()` 动态加载；其余在 `get_available_tools()` 条件分支硬编码、`make_lead_agent()` 按角色追加，或由 middleware / lead agent 末尾注入（`write_todos`、task continuity 三件套）。
- **装配优先级**（同一 name 先注册者胜）：config tools → builtin → MCP → ACP → plugin。因此 config 压过同名 builtin，plugin 排最后、不能覆盖 core；但 personal MCP 与部署 MCP 同名时**整条个人工具被丢弃并 warn**，不是先到先得。
- **2.2 增量**：`inspect_run_status` 每次装配都加；`schedule_task` / `stop_scheduled_task` 按 scheduler capability 的 mode 二选一注入，且会从 YAML 的 `tools[]` 里被剔除——写进配置不能扩大授予。
- **源码入口**：`tools/tools.py::get_available_tools()`（装配与 `BUILTIN_TOOLS`）、`sandbox/tools.py`（沙箱七工具）、`agents/lead_agent/agent.py`（`setup_agent` / `update_agent` 追加）、`agents/task_continuity/tools.py`（连续性三件套）；每个分册开头都标了自己的源码与加载条件。

## 宪章与约定

- 本目录无独立宪章；研究纪律沿用 [根 README](../../README.md)（不修改源码、`main` 只镜像上游、笔记只落在 `ethan`）。
- 核对基线：以 `backend/packages/harness/deerflow/tools/` 与 `sandbox/tools.py` 逐文件核实（2026-05-28 初版，同步 #6 与 2.2.0 基线两次复核）；行号以当期工作树为准。

## 相关目录

- [community-tools/](../community-tools/README.md) — 同名工具的 provider 侧实现与选型。
- [subagent/](../subagent/README.md) — `task` / batch 工具背后的执行、容量与验收。
- [skills-tools/](../skills-tools/README.md) — `skill_manage`、`review_skill_package` 对应的技能系统。
- [internals/middleware/](../../internals/middleware/README.md) — 工具如何被中间件包裹与裁剪。
