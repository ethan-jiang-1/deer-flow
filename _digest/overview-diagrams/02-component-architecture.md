# DeerFlow 组件结构图

> 展示所有物理组件（进程/服务/模块）及其连接关系。每个框对应一个真实的代码模块或运行中进程。

---

## 进程拓扑

```
                         localhost:2026
                     ┌──────────────────────┐
                     │       Nginx          │
                     │  (docker/nginx/)      │
                     │                      │
                     │  /api/langgraph/* ───┼────┐
                     │  /api/*           ───┼──┐ │
                     │  /                ───┼┐ │ │
                     └──────────────────────┘│ │ │
                                             │ │ │
              ┌──────────────────────────────┘ │ │
              ▼                                │ │
    localhost:8001 (Gateway + LangGraph RT)    │ │
   ┌──────────────────────────────────┐        │ │
   │         FastAPI Gateway          │        │ │
   │  app/gateway/app.py              │        │ │
   │                                  │        │ │
   │  ┌────────────────────────────┐  │        │ │
   │  │    16 Routers              │  │        │ │
   │  │  /api/models               │  │        │ │
   │  │  /api/mcp                  │  │        │ │
   │  │  /api/memory               │  │        │ │
   │  │  /api/skills               │  │        │ │
   │  │  /api/threads/{id}/runs    │  │        │ │
   │  │  /api/threads/{id}/uploads │  │        │ │
   │  │  /api/threads/{id}/artifacts│ │        │ │
   │  │  /api/agents               │  │        │ │
   │  │  /api/auth · /api/feedback │  │        │ │
   │  │  /api/suggestions · ...    │  │        │ │
   │  └────────────────────────────┘  │        │ │
   │                                  │        │ │
   │  ┌────────────────────────────┐  │        │ │
   │  │  LangGraph-Compatible RT   │  │        │ │
   │  │  RunManager · StreamBridge │  │        │ │
   │  │  Checkpointer · RunStore   │  │        │ │
   │  │  RunJournal · RunWorker    │  │        │ │
   │  └──────────┬─────────────────┘  │        │ │
   └─────────────┼────────────────────┘        │ │
                 │                              │ │
                 │ make_lead_agent(config)       │ │
                 ▼                              │ │
   ┌──────────────────────────────────┐        │ │
   │      Harness (deerflow.*)        │        │ │
   │  packages/harness/deerflow/      │        │ │
   │                                  │        │ │
   │  ┌────────────┐ ┌─────────────┐  │        │ │
   │  │  agents/    │ │  sandbox/   │  │        │ │
   │  │  lead_agent │ │  local/     │  │        │ │
   │  │  middlewares│ │  tools.py   │  │        │ │
   │  │  memory/    │ │  middleware │  │        │ │
   │  │  prompt.py  │ │  security   │  │        │ │
   │  └────────────┘ └─────────────┘  │        │ │
   │                                  │        │ │
   │  ┌────────────┐ ┌─────────────┐  │        │ │
   │  │  subagents/ │ │  tools/     │  │        │ │
   │  │  executor   │ │  builtins/  │  │        │ │
   │  │  registry   │ │  MCP tools  │  │        │ │
   │  │  builtins/  │ │  community/ │  │        │ │
   │  └────────────┘ └─────────────┘  │        │ │
   │                                  │        │ │
   │  ┌────────────┐ ┌─────────────┐  │        │ │
   │  │  skills/    │ │  models/    │  │        │ │
   │  │  storage/   │ │  factory.py │  │        │ │
   │  │  parser.py  │ │  patched_*  │  │        │ │
   │  │  tool_policy│ │  vllm_prov  │  │        │ │
   │  └────────────┘ └─────────────┘  │        │ │
   │                                  │        │ │
   │  ┌────────────┐ ┌─────────────┐  │        │ │
   │  │  config/    │ │  runtime/   │  │        │ │
   │  │  app_config │ │  RunManager │  │        │ │
   │  │  26 models  │ │  StreamBr.  │  │        │ │
   │  │  paths.py   │ │  Journal    │  │        │ │
   │  └────────────┘ └─────────────┘  │        │ │
   │                                  │        │ │
   │  ┌────────────┐ ┌─────────────┐  │        │ │
   │  │  mcp/       │ │  community/ │  │        │ │
   │  │  client     │ │  tavily     │  │        │ │
   │  │  cache      │ │  jina_ai    │  │        │ │
   │  │  oauth      │ │  firecrawl  │  │        │ │
   │  └────────────┘ │  aio_sandbox│  │        │ │
   │                  └─────────────┘  │        │ │
   │                                  │        │ │
   │  ┌────────────┐ ┌─────────────┐  │        │ │
   │  │  tracing/   │ │  reflection/│  │        │ │
   │  │  langsmith  │ │  resolvers  │  │        │ │
   │  │  langfuse   │ │             │  │        │ │
   │  └────────────┘ └─────────────┘  │        │ │
   │                                  │        │ │
   │  ┌────────────┐                  │        │ │
   │  │  client.py │ ← DeerFlowClient │        │ │
   │  └────────────┘ (嵌入式 SDK)     │        │ │
   └──────────────────────────────────┘        │ │
                                               │ │
              ┌────────────────────────────────┘ │
              ▼                                  │
    localhost:3000 (Next.js Dev Server)          │
   ┌──────────────────────────────────┐          │
   │        Frontend (frontend/)      │          │
   │  Next.js 16 · App Router         │          │
   │                                  │          │
   │  ┌────────────────────────────┐  │          │
   │  │  core/  (business logic)   │  │          │
   │  │  threads · agents · skills │  │          │
   │  │  mcp · messages · models   │  │          │
   │  │  uploads · memory · api    │  │          │
   │  └────────────────────────────┘  │          │
   │                                  │          │
   │  ┌────────────────────────────┐  │          │
   │  │  components/workspace/     │  │          │
   │  │  chats/ · messages/        │  │          │
   │  │  agents/ · settings/       │  │          │
   │  │  artifacts/ · input-box    │  │          │
   │  │  streaming-indicator       │  │          │
   │  │  token-usage-indicator     │  │          │
   │  └────────────────────────────┘  │          │
   └──────────────────────────────────┘          │
                                                 │
              ┌──────────────────────────────────┘ (Docker dev only)
              ▼
    localhost:8002 (optional, Docker/K3s only)
   ┌──────────────────────────────────┐
   │        Provisioner               │
   │  K3s pod manager                 │
   │  (provisioner/kubernetes 模式)    │
   └──────────────────────────────────┘
```

---

## Harness/App 边界（CI 强制执行）

```
┌─────────────────────────────────────────┐
│          app.* (unpublished)            │
│  app/gateway/  ·  app/channels/         │
│                                         │
│    import deerflow ✅                   │
│         │                               │
│         ▼                               │
│  ┌─────────────────────────────────┐    │
│  │    deerflow.* (publishable)     │    │
│  │  packages/harness/deerflow/     │    │
│  │                                 │    │
│  │    import app ❌ (CI fails)     │    │
│  └─────────────────────────────────┘    │
│                                         │
│  边界测试: tests/test_harness_boundary.py│
└─────────────────────────────────────────┘
```

---

## 依赖关系图（deerflow-harness 内部）

```
                    ┌──────────────┐
                    │   client.py  │  DeerFlowClient（嵌入式入口）
                    └──────┬───────┘
                           │ 调用
                    ┌──────▼───────┐
                    │   agents/    │  make_lead_agent → create_agent
                    │ lead_agent/  │  ThreadState · prompt
                    │ middlewares/ │  19 个中间件
                    │   memory/    │  MemoryMiddleware → Updater → Queue
                    └──┬───┬───┬──┘
                       │   │   │
          ┌────────────┘   │   └────────────┐
          ▼                ▼                ▼
   ┌──────────┐   ┌──────────────┐   ┌──────────┐
   │ sandbox/ │   │    tools/    │   │ skills/  │
   │ local/   │   │  builtins/   │   │ storage/ │
   │ aio_sb/  │   │  MCP tools   │   │ parser   │
   │ security │   │  community/  │   │ policy   │
   └────┬─────┘   └──────┬───────┘   └────┬─────┘
        │                │                │
        ▼                ▼                ▼
   ┌──────────────────────────────────────────┐
   │              config/                      │
   │  app_config.py (AppConfig, 26 section)    │
   │  sandbox_config · model_config            │
   │  skills_config · extensions_config        │
   │  subagents_config · memory_config ...     │
   │  paths.py (目录布局)                       │
   └──────────────────┬───────────────────────┘
                      │
        ┌─────────────┼─────────────┐
        ▼             ▼             ▼
   ┌─────────┐  ┌──────────┐  ┌──────────┐
   │ models/ │  │ runtime/ │  │   mcp/   │
   │factory  │  │RunManager│  │ client   │
   │patched_*│  │StreamBr. │  │ cache    │
   │vllm     │  │Journal   │  │ oauth    │
   └─────────┘  │Store     │  └──────────┘
                │Checkpointer│
                └──────────┘
```

---

## 数据存储（Persistence）

```
config.yaml                              .deer-flow/
├── models: [...]                        ├── data/
├── sandbox: {...}                       │   └── deerflow.db (SQLite)
├── tools: [...]                         │       ├── run_store
├── subagents: {...}                     │       ├── thread_meta
├── memory: {...}                        │       ├── feedback
├── summarization: {...}                 │       └── run_events
├── title: {...}                         │
├── guardrails: {...}                    ├── users/{uid}/
├── tool_search: {...}                   │   ├── memory.json
├── loop_detection: {...}                │   ├── agents/{name}/
├── ... (26 sections)                    │   │   ├── SOUL.md
└── ...                                  │   │   └── config.yaml
                                         │   └── threads/{tid}/
extensions_config.json                   │       └── user-data/
├── mcpServers: {...}                    │           ├── workspace/
│   ├── github: {enabled, ...}           │           ├── uploads/
│   └── filesystem: {enabled, ...}       │           └── outputs/
└── skills: {...}                        │
    ├── bootstrap: {enabled: true}       skills/
    └── my-skill: {enabled: true}        ├── public/  (23 built-in skills)
                                         └── custom/  (user skills, gitignored)
```

---

## IM Channels 连接架构

```
Feishu · Slack · Telegram · DingTalk
        │
        ▼
┌─────────────────────────────────┐
│    app/channels/                │
│  ┌───────────────────────────┐  │
│  │     ChannelManager        │  │
│  │  message_bus.py (pub/sub) │  │
│  │  store.py (thread 映射)    │  │
│  └───────────┬───────────────┘  │
│              │                   │
│  ┌───────────▼───────────────┐  │
│  │  Platform Implementations │  │
│  │  feishu.py · slack.py     │  │
│  │  telegram.py · dingtalk.py│  │
│  └───────────────────────────┘  │
└─────────────┬───────────────────┘
              │ langgraph-sdk HTTP client
              ▼
┌─────────────────────────────────┐
│    Gateway (internal auth)      │
│  /api/threads/*/runs            │
└─────────────────────────────────┘
```

---

## 关键源码索引

| 组件 | 源码路径 |
|------|---------|
| Gateway 入口 | `backend/app/gateway/app.py:create_app()` |
| Harness 包 | `backend/packages/harness/deerflow/` |
| LangGraph 图注册 | `backend/langgraph.json` |
| Makefile 入口 | `Makefile` · `scripts/serve.sh` |
| Docker Compose | `docker/docker-compose-dev.yaml` |
| Nginx 路由 | `docker/nginx/nginx.local.conf` · `nginx.conf` |
| 前端核心逻辑 | `frontend/src/core/` |
| 前端组件 | `frontend/src/components/workspace/` |
| 边界测试 | `backend/tests/test_harness_boundary.py` |
