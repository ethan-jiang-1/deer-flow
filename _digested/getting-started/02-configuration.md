---
title: "配置接入概览"
description: "| 文件 | 用途 | 生成方式 |"
topics: [setup, configuration, quickstart]
---

# 配置接入概览

> 从接入/运维视角看 DeerFlow 的配置体系。字段级参考见 [配置全景 00-config-overview.md](00-config-overview.md)。

## 两份配置文件

| 文件 | 用途 | 生成方式 |
|------|------|----------|
| `config.yaml` | 主配置（`config.example.yaml` 当前 **3021 行**，`config_version: 45`） | `make config`（`scripts/configure.py`）从 `config.example.yaml` 复制，已存在则中止 |
| `extensions_config.json` | MCP + Skills 启停 + `middlewares`；**可选**（找不到按搜索路径解析，最终返回空配置） | `make config` **不生成**；`make docker-start` 时由 `scripts/docker.sh:388-395` 从 `extensions_config.example.json` 复制（无模板则写 `{}`） |

## 配置解析优先级

1. 显式代码传参 `config_path`（config.yaml 与 extensions_config.json 同名参数）
2. 环境变量 `DEER_FLOW_CONFIG_PATH` / `DEER_FLOW_EXTENSIONS_CONFIG_PATH`（设了但文件不存在 → `FileNotFoundError`，**不回落搜索**）
3. `project_root()/config.yaml`，其中 `project_root()` = `DEER_FLOW_PROJECT_ROOT`（设了且是存在的目录）否则 `Path.cwd()`（`config/runtime_paths.py:7-16`）——所以从 `backend/` 启动时即 `backend/config.yaml`，从仓库根启动时即根目录 `config.yaml`
4. legacy 候选：`backend/config.yaml` → `repo_root/config.yaml`（`config/app_config.py:156-160`）；extensions 侧的搜索名是 `extensions_config.json` → 旧名 `mcp_config.json`，最终仍找不到则返回 `None`（extensions 可选）

环境变量替换：`api_key: $OPENAI_API_KEY` → 自动读取环境变量（AppConfig 缺变量报错，ExtensionsConfig 缺变量存空串）。

## config.yaml 核心段

| 段 | 用途 | 需要重启？ |
|----|------|-----------|
| `config_version` | Schema 版本号，`make config-upgrade` 合并新字段 | — |
| `models` | LLM 模型列表；`models[].use` 是任意的 provider 类路径（如 `langchain_openai.ChatOpenAI`、`deerflow.models.patched_deepseek:PatchedChatDeepSeek`），内置适配器模块有 9 个：`patched_deepseek` / `patched_openai` / `patched_minimax` / `patched_mimo` / `patched_stepfun` / `vllm_provider` / `claude_provider` / `openai_codex_provider` / `mindie_provider` | **否**（热加载） |
| `models[].use` | Provider 类路径，reflection 加载 | 否 |
| `tool_groups` | 工具分组（web/ file:read/ file:write/ bash/ browser/ knowledge） | 否 |
| `tools` | 内置工具 provider 列表（web_search/web_fetch/image_search/ls/bash 等） | 否 |
| `tool_search` | 延迟加载 / 工具检索（`auto_promote_top_k` 默认 3，夹在 1..5） | 否 |
| `sandbox` | 沙箱实现选择（Local/Docker/K3s/BoxLite/E2B/OpenSandbox） | **是**（`sandbox.use` 被 provider 单例缓存） |
| `sandbox.allow_host_bash` | 主机 bash 开关，默认 false（`config.example.yaml:1441`） | 否 |
| `sandbox.network` | 沙箱出网管控（open/isolated/allowlist，见 `config.example.yaml:1508` 起） | **是**（属 `sandbox` 段） |
| `subagents` | 子 Agent 超时/最大轮次/模型覆盖 | 否 |
| `subagent_runtime` / `subagent_batches` | 原生子 Agent 进程级准入 / 持久化 batch 服务限额 | **是**（启动时构造单例） |
| `acp_agents` | 外部 Agent 协议（Claude Code/Codex） | 否 |
| `summarization` | 上下文摘要触发条件 + 保留策略 | 否 |
| `memory` | 用户记忆存储 + 注入策略 | 否 |
| `database` | 持久化后端（memory/sqlite/postgres）；统一驱动 checkpointer、LangGraph Store 与应用库 | **是** |
| `guardrails` | 工具调用鉴权（Allowlist/OAP/自定义） | 否 |
| `circuit_breaker` | LLM 连续失败熔断 | 否 |
| `loop_detection` | Agent 死循环检测 + 频次限制 | 否 |
| `uploads` | 文件上传大小限制 + 文档自动转换 | 否 |
| `title` | 对话标题自动生成 | 否 |
| `verification` | 子 Agent 结果校验（receipts/checklist/judge） | 否 |
| `safety_finish_reason` | provider 安全过滤 finish_reason 拦截 | 否 |
| `input_polish` / `suggestions` | 发送前改写 / 追问建议（各是一次非 graph 的 LLM 调用） | 否 |
| `projects` / `task_continuity` | 项目工作区限额 / 任务笔记 + 压缩消息召回（默认关） | 否 |
| `skill_scan` / `skill_evolution` | 原生 skill 安全扫描 / agent 自演进 | 否 |
| `tool_output` / `read_before_write` | 上下文成本工程：superseded/blocked write payload 剔除 | 否 |
| `auth.local` | 登录限流（`max_login_attempts`/`lockout_seconds`） | **否**（每次登录实时读，`app/gateway/routers/auth.py:187-207`） |
| `log_level` / `logging` | 日志级别 / trace 字段格式 | **是** |
| 🔄 `recursion_limit` / `max_recursion_limit` | run 的 super-step 默认上限与硬上限（默认 100 / 1000） | 否 |
| `plugins` | 打包扩展列表（会被 import，属代码执行边界） | **是** |
| `run_events` / `agent_storage` / `stream_bridge` / `checkpointer` | 事件存储 / agent 存储 / SSE 桥 / legacy checkpointer | **是** |
| `scheduler` / `mcp_tasks` / `run_ownership` / `dedupe_storage` | 定时任务 / MCP 长任务 / run 租约 / 入站去重存储 | **是**（`scheduler.recursion_limit` 例外，每次派发实时读） |

## extensions_config.json 核心段

| 键 | 用途 |
|----|------|
| `mcpServers` | MCP 服务器注册（stdio/sse/http），含 OAuth 支持 |
| `mcpInterceptors` | 自定义 MCP tool 拦截器 class path 列表（`extensions_config.py` 的 schema 外键，经 `model_extra` 读取并由 `mcp/interceptors.py` 解析） |
| `skills` | Skill 启用/禁用开关 |
| `middlewares` | `AgentMiddleware` 条目（class path 或 `{class, kwargs}`），作用于 lead + subagent 运行时 |

运行时 API：`PUT /api/mcp/config`、`PUT /api/skills/{name}`。

## 接入关键决策

1. **模型选择** — `models[].use` 填 provider 类路径，Ollama 必须用 `langchain_ollama:ChatOllama`（OpenAI 兼容模式会丢失 thinking 内容）
2. **沙箱选择** — 开发用 Local，团队测试用 Docker，生产用 K3s Provisioner。macOS 自动优先 Apple Container
3. **web_search 只能有一个** — 多个 provider 按 config.yaml 顺序去重，先列出的生效
4. **Internal Token** — 模块加载时自动生成，多 worker 必须手动设为相同值
5. **数据库** — sqlite 单机够用，postgres 用于多 worker 生产

## 改后生效规则

权威清单在 `config/reload_boundary.py::STARTUP_ONLY_FIELDS`（schema 侧用统一的 `"startup-only:"` 描述前缀标注，`tests/test_reload_boundary.py` 双向钉住）。

| 无需重启（热加载，`get_app_config()` 每请求/每 run 重读） | 需重启（启动时被单例/引擎捕获） |
|---------------------|--------|
| models、summarization、title、memory、subagents、tools、tool_search、tool_output、read_before_write、verification、projects、task_continuity、system prompt、guardrails、circuit_breaker、loop_detection、uploads、safety_finish_reason、input_polish、suggestions、skill_scan、skill_evolution、recursion_limit / max_recursion_limit、auth.local、`scheduler.recursion_limit` | `plugins`、`database`、`checkpointer`、`run_events`、`agent_storage`、`stream_bridge`、`sandbox`（含 `sandbox.network`）、`skills.container_path`、`log_level`、`logging`、`channels`、`channel_connections`、`scheduler`、`mcp_tasks`、`subagent_runtime`、`subagent_batches`、`run_ownership`、`dedupe_storage` |

## 完整参考

字段级配置手册见 [internals/configuration/04-config-reference.md](../internals/configuration/04-config-reference.md)，设计原理见 [配置全景 00-config-overview.md](00-config-overview.md)。
