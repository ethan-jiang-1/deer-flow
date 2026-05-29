# Tracing — 追踪系统

## 文件

- `tracing/factory.py` (55 行) — CallbackHandler 工厂
- `tracing/metadata.py` (106 行) — Langfuse v4 元数据构建器

## 支持的追踪后端

| 后端 | 检测方式 | 初始化 |
|------|---------|--------|
| **LangSmith** | `LANGSMITH_TRACING=true` | `LangChainTracer(project_name=config.project)` |
| **Langfuse** | `LANGFUSE_TRACING=true`（或自动检测 env vars） | `Langfuse()` 客户端 + `LangfuseCallbackHandler` |

## 两层附着策略

追踪回调在两个层级工作：

### 层 1：图根级别（入口点附着）

`make_lead_agent` 和 `DeerFlowClient.stream` 在调用 `graph.astream()` 之前，将 `build_tracing_callbacks()` 返回的 handler 追加到 `config["callbacks"]`。

**为什么在图的根级别？** Langfuse v4 的 `langchain.CallbackHandler` 只在 `on_chain_start(parent_run_id=None)` 时将元数据提升到根 trace。如果回调附着在模型级别，Langfuse 将看不到根 trace 的元数据，每个 LLM 调用将变成独立的 trace。

### 层 2：模型级别（独立调用者回退）

`create_chat_model(attach_tracing=True)`（默认行为）为图外调用者提供模型级附着。例如 `MemoryUpdater` 不在 agent 图中运行，所以它依赖模型级附着。

## 工厂实现 (`factory.py`)

```python
def build_tracing_callbacks() -> list[Any]:
    validate_enabled_tracing_providers()
    enabled_providers = get_enabled_tracing_providers()  # ["langsmith", "langfuse"]
    if not enabled_providers:
        return []

    callbacks = []
    for provider in enabled_providers:
        if provider == "langsmith":
            callbacks.append(LangChainTracer(project_name=config.project))
        elif provider == "langfuse":
            Langfuse(secret_key=..., public_key=..., host=...)
            callbacks.append(LangfuseCallbackHandler(public_key=...))
    return callbacks
```

## Langfuse v4 合约 (`metadata.py`)

### 保留元数据键

Langfuse v4 的 `CallbackHandler._parse_langfuse_trace_attributes()` 从 `RunnableConfig.metadata` 读取以下键：

| 元数据键 | Langfuse 目标 | 来源 |
|---------|--------------|------|
| `langfuse_session_id` | Session（分组同一线程的 traces） | LangGraph `thread_id` |
| `langfuse_user_id` | User（Users 页面） | `get_effective_user_id()` → `"default"`（无认证时） |
| `langfuse_trace_name` | Trace name | `RunRecord.assistant_id` / 客户端 `agent_name` → `"lead-agent"` |
| `langfuse_tags` | Tags | `env:<DEER_FLOW_ENV>` + `model:<model_name>` |

### build_langfuse_trace_metadata()

当 Langfuse 不在启用的 provider 列表中时返回 `{}` — 确保 LangSmith-only 部署不受影响。

### inject_langfuse_metadata() — 双路径共享

```python
def inject_langfuse_metadata(config, *, thread_id, user_id, ...):
    langfuse_metadata = build_langfuse_trace_metadata(...)
    if not langfuse_metadata:
        return  # LangSmith-only deployment

    merged_metadata = dict(config.get("metadata") or {})
    for key, value in langfuse_metadata.items():
        merged_metadata.setdefault(key, value)  # 调用者可以覆盖
    config["metadata"] = merged_metadata
```

关键：**调用者提供的值通过 `setdefault` 优先**。前端可以设置自定义 `langfuse_session_id`，它不会被覆盖。

## 双注入点

`inject_langfuse_metadata()` 在两个入口点调用，共享同一个 helper 以防漂移：

1. **Gateway worker** — `runtime/runs/worker.py::run_agent()` (行 240-247)
2. **嵌入式客户端** — `client.py::DeerFlowClient.stream()`

## 配置

追踪通过环境变量启用（在 `config.yaml` 的 `tracing` 节中定义）：

```yaml
tracing:
  providers:
    - langsmith    # LANGSMITH_TRACING=true
    - langfuse     # LANGFUSE_TRACING=true
  langsmith:
    project: "deer-flow"
  langfuse:
    secret_key: "$LANGFUSE_SECRET_KEY"
    public_key: "$LANGFUSE_PUBLIC_KEY"
    host: "$LANGFUSE_HOST"
```

## 环境标签

设置 `DEER_FLOW_ENV`（或 `ENVIRONMENT`）为追踪添加环境标签，例如 `langfuse_tags: ["env:production", "model:claude-sonnet-4-6"]`。
