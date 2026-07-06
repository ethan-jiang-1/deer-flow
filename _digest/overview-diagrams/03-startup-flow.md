# DeerFlow 启动与请求处理全流程

> 从敲命令到 agent 返回第一个 token 的完整时序。基于源码追踪，非推测。

---

## 阶段 0：入口命令

```
用户敲入:
  make dev                 → 本地开发（Gateway + Frontend + Nginx）
  make docker-start        → Docker 开发（docker compose up）
  cd backend && make gateway → 仅 Gateway，端口 8001
  python script.py         → DeerFlowClient 进程内，零服务
```

---

## 阶段 1：`make dev` 本地启动

```
scripts/serve.sh --dev
│
├─ 1. 加载 .env
├─ 2. 清理已有进程 (kill uvicorn/next 进程)
├─ 3. 检查 config.yaml 存在性
├─ 4. 运行 config-upgrade.sh
├─ 5. 安装依赖: uv sync (backend) + pnpm install (frontend)
│
├─ 6. 启动 Gateway (后台)
│   cd backend
│   uv run uvicorn app.gateway.app:app \
│       --host 0.0.0.0 --port 8001 --reload
│
├─ 7. 启动 Frontend (后台)
│   cd frontend
│   pnpm run dev    → localhost:3000
│
└─ 8. 启动 Nginx (前台)
    nginx -c docker/nginx/nginx.local.conf  → localhost:2026
```

---

## 阶段 2：Gateway 进程初始化（lifespan）

```
uvicorn 启动 → app = create_app()
│
├─ 读取 Gateway 配置 (host/port/docs)
├─ 创建 FastAPI app (lifespan=lifespan)
├─ 注册中间件: AuthMiddleware · CSRFMiddleware · CORS
├─ 注册 16 个 Router (models, mcp, memory, skills, threads, ...)
│
└─ 进入 lifespan():
    │
    ├─ 1. get_app_config()  ← 加载 config.yaml
    │     config.yaml → YAML parse → Pydantic AppConfig
    │     check config_version vs config.example.yaml
    │     解析 $ENV_VAR 占位符
    │     → 进程级 singleton cache（mtime 热重载）
    │
    ├─ 2. apply_logging_level(config.log_level)
    │
    ├─ 3. langgraph_runtime(app, startup_config):
    │     ├─ 3a. make_stream_bridge(config)      → StreamBridge 实例
    │     ├─ 3b. init_engine_from_config()       → SQLAlchemy Engine (SQLite/Postgres)
    │     ├─ 3c. make_checkpointer(config)       → Checkpointer (LangGraph)
    │     ├─ 3d. make_store(config)             → LangGraph Store
    │     ├─ 3e. make_run_repository()          → RunRepository (SQL)
    │     ├─ 3f. make_thread_meta_store()       → ThreadMetaStore
    │     ├─ 3g. make_run_event_store()         → RunEventStore
    │     ├─ 3h. RunManager(store=run_store,    → RunManager 实例
    │     │         event_store=...)
    │     └─ 3i. recover orphaned inflight runs (SQLite only)
    │
    ├─ 4. _ensure_admin_user()  ← bootstrap agent / thread 迁移
    │
    ├─ 5. start_channel_service(config)  ← 启动 IM Channel 监听
    │
    └─ 6. yield  ← app 就绪，开始接受请求
```

---

## 阶段 3：`make docker-start` Docker 启动

```
scripts/docker.sh start
│
├─ 1. 读取 config.yaml → 判断 sandbox 模式
│     └─ 如果是 provisioner → 生成 docker-compose 包含 provisioner 服务
│
├─ 2. docker compose -f docker-compose-dev.yaml up -d
│     │
│     ├─ nginx (2026)     ← nginx:alpine
│     ├─ frontend (3000)  ← node:22, pnpm run dev
│     ├─ gateway (8001)   ← python:3.12, dev-entrypoint.sh
│     │   └─ dev-entrypoint.sh:
│     │       ├─ 检查 DEER_FLOW_EXTRAS env → uv sync --extras
│     │       └─ uvicorn app.gateway.app:app --reload ...
│     └─ provisioner (8002, optional) ← k3s pod manager
│
└─ 3. 容器挂载:
      - config.yaml → /app/config.yaml
      - skills/     → /app/skills/
      - backend/    → /app/backend/ (hot-reload)
      - Docker socket (AioSandboxProvider 需要)
```

---

## 阶段 4：一个请求的完整生命周期

```
用户发送消息 (Web UI 或 curl):

POST /api/threads/{thread_id}/runs/stream
Body: {"input": {"messages": [...]}, "context": {...}}
─────────────────────────────────────────────────────

Nginx (:2026)
  │  /api/langgraph/* → rewrite → /api/*
  │  其他 /api/*      → 直接转发
  ▼
Gateway (:8001)
  │
  ├─ AuthMiddleware → 验证身份 (JWT / Internal / Anonymous)
  ├─ CSRFMiddleware → CSRF token 检查
  │
  ▼
Router: thread_runs.py → stream_run()
  │
  ├─ 1. get_stream_bridge(request)    → StreamBridge
  ├─ 2. get_run_manager(request)      → RunManager
  │
  └─ 3. await start_run(body, thread_id, request):
        │
        ├─ 3a. 验证 model (如果配置了 allowlist)
        ├─ 3b. RunManager.create_or_reject(thread_id, ...) → RunRecord
        ├─ 3c. upsert_thread_metadata(thread_id, ...)
        ├─ 3d. 解析 agent_factory = make_lead_agent
        ├─ 3e. normalize input messages
        ├─ 3f. build_run_config(body) → RunnableConfig:
        │       ├─ configurable: {thread_id, model_name, ...}
        │       ├─ context: 用户传入的 context
        │       ├─ recursion_limit, metadata, callbacks
        │       └─ merge_run_context_overrides():
        │             只提取 _CONTEXT_CONFIGURABLE_KEYS 白名单中的 key
        │             (model_name, thinking_enabled, is_plan_mode,
        │              subagent_enabled, agent_name, is_bootstrap, ...)
        ├─ 3g. inject_authenticated_user_context()
        │
        └─ 3h. asyncio.create_task(
                run_agent(run_context, input, config, ...)
              )
              │
              ▼
        ┌─────────────────────────────────────────┐
        │  run_agent() — runtime/runs/worker.py   │
        │                                         │
        │  1. 解包 RunContext (checkpointer,       │
        │     store, event_store, ...)             │
        │  2. 初始化 RunJournal (callback handler) │
        │  3. set_status → "running"               │
        │  4. 捕获 pre-run checkpoint 快照         │
        │  5. publish metadata event               │
        │  6. build_runtime_context(thread_id,     │
        │     run_id, caller_context, app_config)  │
        │  7. install __pregel_runtime in config   │
        │  8. inject journal as callback handler   │
        │  9. inject_langfuse_metadata()           │
        │ 10. resolve_root_run_name()              │
        │                                         │
        │ 11. agent = agent_factory(config)        │
        │     = make_lead_agent(config)            │
        │     ┌─────────────────────────────────┐  │
        │     │ _make_lead_agent(config):        │  │
        │     │                                  │  │
        │     │ a. _get_runtime_config(config)   │  │
        │     │   合并 configurable + context     │  │
        │     │                                  │  │
        │     │ b. resolve model_name:           │  │
        │     │   request → agent config → global│  │
        │     │                                  │  │
        │     │ c. load_agent_config(name)       │  │
        │     │    custom agent 或 default       │  │
        │     │                                  │  │
        │     │ d. inject tracing callbacks      │  │
        │     │                                  │  │
        │     │ e. get_available_tools():        │  │
        │     │   config tools + MCP +           │  │
        │     │   community + subagent(task)     │  │
        │     │                                  │  │
        │     │ f. create_chat_model(name,       │  │
        │     │    thinking_enabled)             │  │
        │     │   → resolve_class(use)           │  │
        │     │   → ChatOpenAI / ChatAnthropic / │  │
        │     │     ChatDeepSeek / ...           │  │
        │     │                                  │  │
        │     │ g. _available_skill_names():     │  │
        │     │   agent_config.skills            │  │
        │     │   or is_bootstrap → {bootstrap}  │  │
        │     │   or None → all enabled skills   │  │
        │     │                                  │  │
        │     │ h. filter tools by skill         │  │
        │     │    allowed-tools policy          │  │
        │     │                                  │  │
        │     │ i. _build_middlewares(config):   │  │
        │     │   _build_runtime_middlewares()   │  │
        │     │   + DynamicContextMiddleware     │  │
        │     │   + SummarizationMiddleware      │  │
        │     │   + TodoListMiddleware           │  │
        │     │   + TokenUsageMiddleware         │  │
        │     │   + TitleMiddleware              │  │
        │     │   + MemoryMiddleware             │  │
        │     │   + ViewImageMiddleware          │  │
        │     │   + DeferredToolFilterMdlwr      │  │
        │     │   + SubagentLimitMiddleware      │  │
        │     │   + LoopDetectionMiddleware      │  │
        │     │   + SafetyFinishReasonMdlwr      │  │
        │     │   + ClarificationMiddleware      │  │
        │     │   (共 19 个, 严格顺序)            │  │
        │     │                                  │  │
        │     │ j. apply_prompt_template():      │  │
        │     │    <memory> + <available_skills> │  │
        │     │    + SOUL.md + <deferred-tools>  │  │
        │     │    + <thread_data> + ...         │  │
        │     │                                  │  │
        │     │ k. create_agent(model, tools,    │  │
        │     │    middleware, system_prompt,     │  │
        │     │    state_schema=ThreadState)      │  │
        │     │ → CompiledStateGraph             │  │
        │     └─────────────────────────────────┘  │
        │                                         │
        │ 12. attach checkpointer + store         │
        │ 13. set interrupt nodes                 │
        │ 14. map stream modes                    │
        │     (messages-tuple → messages)          │
        │                                         │
        │ 15. agent.astream(input, config)        │
        │     ┌──────────────────────────────┐    │
        │     │  LangGraph Pregel 执行:       │    │
        │     │                              │    │
        │     │  turn 1:                     │    │
        │     │  before_model → LLM call     │    │
        │     │    → AIMessage (text +       │    │
        │     │      tool_calls)             │    │
        │     │  after_model → tool execute  │    │
        │     │    → ToolMessage(s)          │    │
        │     │  after_tool → after_step     │    │
        │     │                              │    │
        │     │  turn 2..N:                  │    │
        │     │  (循环直到无 tool_calls 或    │    │
        │     │   达到 recursion_limit)       │    │
        │     └──────────┬───────────────────┘    │
        │                │                        │
        │ 16. 每个 chunk → serialize()            │
        │     → StreamBridge.publish(run_id, evt) │
        │                                         │
        │ 17. finally:                            │
        │     ├─ flush journal                    │
        │     ├─ sync title                       │
        │     ├─ update status → "success"/"error"│
        │     └─ publish END_SENTINEL             │
        └─────────────┬───────────────────────────┘
                      │
                      ▼
┌─────────────────────────────────────────────────┐
│  StreamingResponse(sse_consumer(bridge, ...))    │
│                                                  │
│  sse_consumer 循环:                              │
│    bridge.subscribe(run_id)                      │
│    → async for event                            │
│    → 序列化为 SSE frame                          │
│        event: values/data:{...}\n\n              │
│        event: messages-tuple/data:{...}\n\n      │
│        event: custom/data:{...}\n\n              │
│        event: end/data:{...}\n\n                 │
│    → yield to HTTP response                      │
└─────────────────────────────────────────────────┘
                      │
                      ▼
              浏览器 / curl 接收 SSE 流
              前端 useStream hook 解析
              → 实时渲染消息、tool calls、artifacts
```

---

## 阶段 5：DeerFlowClient 进程内路径（对比）

```
用户 Python 脚本:
  from deerflow.client import DeerFlowClient
  client = DeerFlowClient()
  result = client.chat("hello", thread_id="t1")

DeerFlowClient.chat()
  │
  ├─ _ensure_agent():
  │   与 Gateway 路径完全相同的:
  │   ├─ get_app_config()
  │   ├─ create_chat_model()
  │   ├─ get_available_tools()
  │   ├─ _build_middlewares()
  │   ├─ apply_prompt_template()
  │   └─ create_agent(model, tools, middleware, ...)
  │
  └─ 直接调用 agent.astream()  ← 无 HTTP, 无 Nginx, 无 FastAPI
     → 逐 chunk 累积 → 返回最终文本
```

---

## 阶段 6：`make docker-start` 具体服务启动时序

```
docker compose up -d
│
├─ 1. 网络创建: deer-flow-network
├─ 2. provisioner (if sandbox=provisioner/k8s)
│     └─ 等待 K3s API 就绪
├─ 3. gateway:
│     ├─ 加载 config.yaml
│     ├─ uv sync (首次 + 依赖变更时)
│     ├─ uvicorn 启动 → lifespan (阶段 2)
│     └─ health check: GET /health → 200
├─ 4. frontend:
│     ├─ pnpm install
│     └─ next dev → port 3000
├─ 5. nginx:
│     ├─ 等待 gateway:8001 和 frontend:3000 就绪
│     └─ 开始接受 :2026 请求
└─ 6. 整个栈就绪
```

---

## 关键启动配置加载顺序

```
1. load_dotenv()           ← app_config.py 模块导入时自动执行
2. DEER_FLOW_CONFIG_PATH   ← env var 优先级最高
3. config.yaml             ← 项目根目录（推荐）
4. config.example.yaml     ← config_version 比对
5. extensions_config.json  ← MCP servers + skills enabled 状态
6. .env                    ← API keys ($OPENAI_API_KEY 等)
```

---

## 关键源码索引

| 步骤 | 源码 |
|------|------|
| serve.sh 启动脚本 | `scripts/serve.sh` |
| Docker 启动脚本 | `scripts/docker.sh` |
| Gateway create_app | `backend/app/gateway/app.py:create_app()` |
| Gateway lifespan | `backend/app/gateway/app.py:lifespan()` |
| langgraph_runtime | `backend/app/gateway/langgraph_runtime.py` |
| stream_run handler | `backend/app/gateway/routers/thread_runs.py:stream_run()` |
| start_run | `backend/app/gateway/services.py:start_run()` |
| build_run_config | `backend/app/gateway/services.py:build_run_config()` |
| merge_run_context_overrides | `backend/app/gateway/services.py:merge_run_context_overrides()` |
| run_agent | `deerflow/runtime/runs/worker.py:run_agent()` |
| make_lead_agent | `deerflow/agents/lead_agent/agent.py:make_lead_agent()` |
| _make_lead_agent | `deerflow/agents/lead_agent/agent.py:_make_lead_agent()` |
| get_available_tools | `deerflow/tools/tools.py:get_available_tools()` |
| create_chat_model | `deerflow/models/factory.py:create_chat_model()` |
| _build_middlewares | `deerflow/agents/lead_agent/agent.py:_build_middlewares()` |
| apply_prompt_template | `deerflow/agents/lead_agent/prompt.py:apply_prompt_template()` |
| sse_consumer | `backend/app/gateway/routers/thread_runs.py:sse_consumer()` |
| Config 加载 | `deerflow/config/app_config.py:AppConfig.from_file()` |
| 热重载机制 | `deerflow/config/app_config.py:get_app_config()` |
| DeerFlowClient | `deerflow/client.py:DeerFlowClient` |
