# DeerFlow 架构分析

## 总体架构

```
Browser / Client
       │
       ▼
   Nginx (port 2026)
       │
       ├── /api/* ──────────► Gateway API (FastAPI, port 8001)
       │                            │
       │                            └── app.gateway (HTTP 层)
       │                                  │
       │                                  └── deerflow.harness (Agent 框架)
       │                                        │
       │                                        ├── Lead Agent (LangGraph)
       │                                        ├── Middlewares (18 个)
       │                                        ├── Sandbox
       │                                        ├── Subagents
       │                                        ├── Memory
       │                                        └── Skills
       │
       └── /* (其他) ────────► Frontend (Next.js, port 3000)
```

## 核心分层

### Harness 层（可发布框架）

包：`deerflow-harness`，源码：`backend/packages/harness/deerflow/`
导入前缀：`deerflow.*`

**规则：绝不导入 `app.*`**（CI 有 `test_harness_boundary.py` 检查）

| 子包 | 职责 |
|------|------|
| `agents/` | Lead Agent 工厂 + 系统 prompt + 18 个中间件 |
| `agents/memory/` | 用户记忆：提取、队列、存储 |
| `runtime/` | Run 生命周期、checkpointer、stream bridge、事件存储 |
| `sandbox/` | 抽象沙箱接口 + LocalSandboxProvider |
| `subagents/` | 子 Agent：注册表、执行器、内置 general-purpose/bash |
| `tools/` | 工具装配器 `get_available_tools()` |
| `tools/builtins/` | 内置工具：task、present_files、ask_clarification 等 |
| `models/` | 模型工厂，thinking/vision 支持 |
| `mcp/` | MCP 客户端、缓存 |
| `skills/` | Skill 发现、加载、存储 |
| `config/` | 配置系统（29 个文件） |
| `community/` | 社区集成：Tavily、Jina、Firecrawl、DuckDuckGo、AioSandbox |
| `persistence/` | SQLAlchemy ORM、数据库引擎、Alembic 迁移 |
| `guardrails/` | 工具调用鉴权协议 |
| `tracing/` | LangSmith + Langfuse 回调 |
| `reflection/` | 动态模块加载 |
| `uploads/` | 文件上传管理 |

### App 层（应用层，不发布）

包：`app.*`，源码：`backend/app/`

| 子包 | 职责 |
|------|------|
| `gateway/` | FastAPI 应用、15 个路由模块、认证 |
| `channels/` | IM 平台集成：Feishu/Slack/Telegram/WeChat/DingTalk/Discord |

### Frontend

Next.js 16 App Router，React 19，TypeScript 5.8，Tailwind CSS 4。

- `src/core/` — 业务逻辑层（threads、api、settings、memory 等）
- `src/components/workspace/` — 聊天 UI 组件
- 使用 `@langchain/langgraph-sdk` 与 Gateway 通信
- SSE streaming 通过 `useStream` hook

---

## 请求数据流

一次对话请求的完整路径：

```
1. HTTP POST /api/threads/{id}/runs/stream
        │
2. Gateway Router (app.gateway.routers.thread_runs)
        │
3. RunManager 创建 RunRecord，spawn asyncio.Task
        │
4. run_agent() 构建 RunContext (checkpointer, store, stream_bridge)
        │
5. make_lead_agent(config)
   ┌─────────────────────────────────────────────┐
   │  a) 解析模型配置 + 创建 ChatModel              │
   │  b) 注入 tracing callbacks                   │
   │  c) get_available_tools() 装配工具            │
   │  d) apply_prompt_template() 系统 prompt       │
   │  e) _build_middlewares() 18 个中间件           │
   │  f) create_agent(ThreadState) 创建 LangGraph   │
   └─────────────────────────────────────────────┘
        │
6. graph.astream() 执行，stream_mode=["values","updates","messages","custom"]
        │
7. 每个 chunk -> StreamBridge -> SSE events -> Client
```

---

## Middleware 链（18 个）

装配顺序（`_build_middlewares()` in `agents/lead_agent/agent.py`）：

| # | 中间件 | 触发点 | 作用 |
|---|--------|--------|------|
| 1 | ThreadDataMiddleware | 运行时 | 每线程目录隔离 |
| 2 | UploadsMiddleware | 运行时 | 追踪上传文件 |
| 3 | SandboxMiddleware | 运行时 | 获取沙箱，存 sandbox_id |
| 4 | DanglingToolCallMiddleware | after_model | 修补缺失 ToolMessage |
| 5 | LLMErrorHandlingMiddleware | 运行时 | 归一化 LLM 错误 |
| 6 | GuardrailMiddleware | after_model | 工具调用前鉴权 |
| 7 | SandboxAuditMiddleware | after_model | 安全日志 |
| 8 | ToolErrorHandlingMiddleware | 运行时 | 工具异常 -> ToolMessage |
| 9 | DynamicContextMiddleware | before_model | 注入日期/记忆 |
| 10 | SummarizationMiddleware | before_model | 接近 token 上限时摘要 |
| 11 | TodoListMiddleware | 可选 | 计划模式任务追踪 |
| 12 | TokenUsageMiddleware | after_tool | token 用量记录 |
| 13 | TitleMiddleware | after_step | 自动生成标题 |
| 14 | MemoryMiddleware | after_step | 记忆提取入队 |
| 15 | ViewImageMiddleware | before_model | 注入 base64 图片 |
| 16 | DeferredToolFilterMiddleware | before_model | 延迟 MCP 工具过滤 |
| 17 | SubagentLimitMiddleware | before_model | 子 Agent 并发限制 |
| 18 | LoopDetectionMiddleware | after_model | 工具调用循环检测 |
| 19 | SafetyFinishReasonMiddleware | before_model | 安全终止拦截 |
| 20 | ClarificationMiddleware | after_model | ask_clarification 拦截（最后一个） |

> 运行时中间件（前 8 个）始终激活。其余按配置开关。

---

## 核心抽象

### Agent

- **Lead Agent**: `make_lead_agent(config)` -> `_make_lead_agent()` -> `create_agent(ThreadState)`
- 注册在 `langgraph.json` 中：`"lead_agent": "deerflow.agents:make_lead_agent"`
- 支持 bootstrap（最小 Agent，用于创建自定义 Agent）和 normal 两种模式
- 自定义 Agent 支持 per-agent 的 SOUL.md/config.yaml/tools/skills

### ThreadState

扩展 LangChain `AgentState`，增加：
- `sandbox_id` — 沙箱标识
- `thread_data` — workspace/uploads/outputs 路径
- `title` — 自动标题
- `artifacts` — 产物路径（去重 reducer）
- `todos` — 计划任务（合并 reducer）
- `uploaded_files` — 上传文件
- `viewed_images` — base64 图片缓存

### Sandbox

- **抽象接口**：`Sandbox(ABC)` — execute_command, read_file, write_file, glob, grep 等
- **本地实现**：`LocalSandboxProvider` — 文件系统隔离，LRU 缓存 256 条
- **Docker 实现**：`AioSandboxProvider` — 容器隔离
- **虚拟路径**：`/mnt/user-data/{workspace,uploads,outputs}` -> host 路径

### Subagent

- 限制：最多 3 个并发，15 分钟超时
- 内置：`general-purpose`（all tools except `task`）、`bash`（命令专家）
- 可自定义：`config.yaml` -> `subagents.custom_agents`
- 子 Agent 接收过滤后的 tools、skills、sandbox state

### Memory

- **存储**：`{base_dir}/users/{user_id}/memory.json`
- **结构**：User Context + History Segments + Facts
- **更新**：LLM 提取事实，30s debounce

### Skills

- 路径：`skills/public/`（18 个已提交）+ `skills/custom/`（gitignored）
- 格式：`SKILL.md`（YAML frontmatter + markdown body）
- 加载：`LocalSkillStorage` via `asyncio.to_thread`
- 启停状态：`extensions_config.json`

### Tool 装配

`get_available_tools()` 按顺序装配：
1. config.yaml 定义的工具（`resolve_variable(cfg.use, BaseTool)`）
2. MCP 工具（mtime 缓存）
3. 内置工具（task、present_files 等）
4. ACP 工具（`invoke_acp_agent`）

按名称去重，config 优先。

---

## 数据库/持久化

| 后端 | 配置值 | 场景 |
|------|--------|------|
| Memory | `database.backend: memory` | 进程内，无持久化 |
| SQLite | `database.backend: sqlite`（默认） | 单机 |
| PostgreSQL | `database.backend: postgres` | 多 worker / 生产 |

Checkpointer 同样支持三种后端（memory/sqlite/postgres），通过 `langgraph.json` 配置。
