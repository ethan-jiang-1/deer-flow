---
title: "DeerFlow 启动与请求处理全流程"
description: "![Startup Sequence](figures/startup-sequence.svg)"
topics: [architecture, system-overview]
---

# DeerFlow 启动与请求处理全流程

> 从敲命令到 agent 返回第一个 token 的完整时序。基于源码追踪，非推测。

---

## 启动入口总览

![Startup Sequence](figures/startup-sequence.svg)

四种启动入口在同一张图中对比：`make dev`（本地）· `make docker-start`（Docker）· `make gateway`（后端 only）· `DeerFlowClient`（进程内）。所有模式共享 `lifespan()` 和 `_make_lead_agent()`。

---

## Gateway 进程初始化（lifespan）

![Gateway Lifespan](figures/gateway-lifespan.svg)

从 uvicorn 启动到 app 就绪的 6 步：`create_app()` → `get_app_config()` → `langgraph_runtime()`（先跑 5 道启动门，再建 StreamBridge / Checkpointer / Store / 事件库 / RunManager）→ `_ensure_admin_user()` → `start_channel_service()` → `yield`。

`_gateway_lifespan`（`backend/app/gateway/app.py:637`）在 v2.2.0 多做了 6 件启动期工作：

| 步骤 | 位置 | v2.2.0 语义 |
|------|------|------------|
| 容量冻结 | `app.py:657` `configure_subagent_execution_capacity()` | 子代理执行容量 startup-only 冻结，热重载配置不能让"广告的并发上限"和"实际强制值"分叉 |
| 公共 skill 投影 | `app.py:671` | `ensure_public_skill_projection()` 走 `asyncio.to_thread`，用户投影在沙箱获取时惰性修复 |
| 检索索引预热 | `app.py:688`-`703` | memory 检索索引在后台上重建，**不阻塞就绪** |
| trash 清扫 | `app.py:759`（`_run_startup_trash_sweep`） | 启动期一次保留期清扫，作为后台 task，就绪不等它 |
| 启动门 | `deps.py:784`-`799` | `_enforce_postgres_for_multi_worker` / `_enforce_credentials_key` / `_validate_agent_storage` / `_validate_login_throttle_storage` / `_validate_memory_retrieval_index` |
| IM 通道租约 | `app.py:837`-`841` | `start_channel_service(..., multi_process=multi_process_deployment(startup_config), lease_owner_id=run_manager.worker_id)`——通道 leader lease 的 owner 就是本实例的 run worker id，租约日志与 run 日志同源 |

---

## 一个请求的完整生命周期

![Request Lifecycle](figures/request-lifecycle.svg)

17 步完整追踪，分 6 个 Phase：

| Phase | 文件 | 做什么 |
|-------|------|--------|
| 1. HTTP Entry | Nginx + Gateway | 路由、Auth、CSRF |
| 2. stream_run | `thread_runs.py` | 获取 bridge/run_mgr，调用 start_run |
| 3. start_run | `services.py` | 8 步准备（model 验证 → RunRecord → build_run_config → context override） |
| 4. run_agent | `worker.py` | 17 步执行（journal → checkpoint → agent factory → astream → finally） |
| 5. make_lead_agent | `agent.py` | 7 步装配 Agent Graph（config → model → tools → middlewares → prompt → create_agent）；v2.2.0 起 Gateway worker 用 `assemble_lead_agent()` 拿 `LeadAgentAssembly`（图 + 装配描述），不再从 LangGraph 私有 runtime key 反推 |
| 6. Pregel + SSE | LangGraph + StreamBridge | Turn 1..N 循环 → serialize → Bridge.publish → SSE frames |

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
| langgraph_runtime | `backend/app/gateway/deps.py:langgraph_runtime()`（async context manager，由 `lifespan()` 进入） |
| stream_run handler | `backend/app/gateway/routers/thread_runs.py:stream_run()` |
| start_run | `backend/app/gateway/services.py:start_run()` |
| build_run_config | `backend/app/gateway/services.py:build_run_config()` |
| merge_run_context_overrides | `backend/app/gateway/services.py:merge_run_context_overrides()` |
| run_agent | `deerflow/runtime/runs/worker.py:run_agent()` |
| make_lead_agent | `deerflow/agents/lead_agent/agent.py:make_lead_agent()` |
| _make_lead_agent | `deerflow/agents/lead_agent/agent.py:_make_lead_agent()` |
| get_available_tools | `deerflow/tools/tools.py:get_available_tools()` |
| create_chat_model | `deerflow/models/factory.py:create_chat_model()` |
| build_middlewares | `deerflow/agents/lead_agent/agent.py:build_middlewares()`（`agent.py:485`，公开名，被 `client.py` 跨模块 import）；运行时基底是 `tool_error_handling_middleware.py:build_lead_runtime_middlewares()`（`:538`），内部转 `_build_runtime_middlewares()`（`:347`） |
| apply_prompt_template | `deerflow/agents/lead_agent/prompt.py:apply_prompt_template()` |
| sse_consumer | `backend/app/gateway/routers/thread_runs.py:sse_consumer()` |
| Config 加载 | `deerflow/config/app_config.py:AppConfig.from_file()` |
| 热重载机制 | `deerflow/config/app_config.py:get_app_config()` |
| DeerFlowClient | `deerflow/client.py:DeerFlowClient` |
