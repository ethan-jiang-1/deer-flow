---
title: "Lead Agent 系统"
description: "DeerFlow 的核心：`make_lead_agent` 工厂函数创建与 LangGraph 兼容的 Agent。"
topics: [agent, factory, threadstate]
---

# Lead Agent 系统

DeerFlow 的核心：`make_lead_agent` 工厂函数创建与 LangGraph 兼容的 Agent。

> **交叉引用：** Agent 如何挂载 middleware 链见 [middleware/03-catalog.md](../../internals/middleware/03-catalog.md)。

## 入口

```python
# langgraph.json 中注册
"lead_agent": "deerflow.agents:make_lead_agent"

# 函数签名
def make_lead_agent(config: RunnableConfig):
    """LangGraph graph factory; keep the signature compatible with LangGraph Server."""
    runtime_config = _get_runtime_config(config)
    runtime_app_config = runtime_config.get("app_config")
    return _make_lead_agent(config, app_config=runtime_app_config or get_app_config())
```

LangGraph Server 通过 `langgraph.json` 发现 graph，调用 `make_lead_agent(config)` 获取 compiled graph。

## `_make_lead_agent` — 七个步骤

### 1. 解析运行时配置

```python
cfg = _get_runtime_config(config)
thinking_enabled = cfg.get("thinking_enabled", True)
reasoning_effort = cfg.get("reasoning_effort", None)
requested_model_name = cfg.get("model_name") or cfg.get("model")
is_plan_mode = cfg.get("is_plan_mode", False)
subagent_enabled = cfg.get("subagent_enabled", False)
max_concurrent_subagents = cfg.get("max_concurrent_subagents", 3)
is_bootstrap = cfg.get("is_bootstrap", False)
agent_name = validate_agent_name(cfg.get("agent_name"))
```

这些值来自 HTTP request body 的 `config.configurable` 字段。

### 2. 模型名称解析

```python
# 优先级：request model → agent config model → global default
model_name = _resolve_model_name(
    requested_model_name or agent_model_name,
    app_config=resolved_app_config
)
```

三层 fallback：
1. 请求指定的 model_name
2. 自定义 Agent 的 `agent_config.model`
3. config.yaml 中 models 列表的第一个

### 3. 创建 ChatModel

```python
model_config = resolved_app_config.get_model_config(model_name)
model = create_chat_model(model_name, thinking_enabled=thinking_enabled)
```

`create_chat_model`：
- 通过 `resolve_class(cfg.use, BaseChatModel)` 动态加载 provider 类
- 应用 `api_key`、`api_base`、`timeout`、`max_tokens`、`temperature` 等配置
- 如果 `thinking_enabled` 且模型支持，应用 `when_thinking_enabled` 覆盖参数

### 4. 注入 Tracing

```python
tracing_callbacks = build_tracing_callbacks()
config["callbacks"] = (config.get("callbacks") or []) + tracing_callbacks

# Langfuse metadata
config["metadata"].update({
    "langfuse_session_id": thread_id,
    "langfuse_user_id": get_effective_user_id(),
    "langfuse_trace_name": agent_name or "lead-agent",
    "langfuse_tags": [f"env:{env}", f"model:{model_name}"]
})
```

Tracing callbacks 在 graph root 附加（而非 model 层），所以一次 run 产生一个 trace，所有 node/LLM/tool call 作为 child span。

### 5. 装配 Tools

```python
tools = get_available_tools(
    groups=None,
    include_mcp=True,
    model_name=model_name,
    subagent_enabled=subagent_enabled,
)
```

装配顺序：
1. Config-defined tools (`config.yaml` → `tools[]`)
2. MCP tools (enabled servers, mtime cache)
3. Built-in tools (`present_files`, `ask_clarification`, `view_image` 等)
4. Subagent tool (`task`)
5. ACP agents (`invoke_acp_agent`)

### 6. 生成 System Prompt

```python
system_prompt = apply_prompt_template(
    agent_config=agent_config,
    available_skills=skills,
    is_bootstrap=is_bootstrap,
    app_config=resolved_app_config,
)
```

System prompt 包含：
- 基础 Agent 行为指令
- 启用的 Skills 列表及 container path
- Subagent 使用说明
- Bootstrap 模式特殊指令（如果创建新 Agent）

### 7. 构建 Middleware 并 create_agent

```python
middlewares = _build_middlewares(config, model_name, agent_name)
graph = create_agent(
    model=model,
    tools=tools,
    middleware=middlewares,
    state_schema=ThreadState,
    checkpointer=checkpointer,
)
```

`create_agent()` 来自 `langchain.agents`，内部创建 LangGraph `StateGraph`，绑定 middleware 再到各个 lifecycle hook。

## Bootstrap 模式

当 `is_bootstrap=True` 时：
- Skills 限制为 `{"bootstrap"}`
- 额外的内置工具：`setup_agent`（创建自定义 Agent 的 SOUL.md + config.yaml）
- 不同的 system prompt
- 用于 Agent 创建向导

## Custom Agent 模式

当 `agent_name` 不为空且非 bootstrap：
- 加载 Agent 的 `SOUL.md` 作为 personality
- 加载 Agent 的 `config.yaml` 覆盖默认配置
- 额外的内置工具：`update_agent`（Agent 自我更新 SOUL.md + config.yaml）
- 受 `allowed-tools` policy 限制的工具集

---

## ThreadState — 状态 Schema

```python
class ThreadState(AgentState):
    sandbox: SandboxState | None
    thread_data: ThreadDataState | None
    title: str | None
    artifacts: list[str]                 # 去重 reducer
    todos: list | None                   # 合并 reducer
    uploaded_files: list[dict] | None
    viewed_images: dict[str, ViewedImageData]
    # 🆕 以下为新增字段（详见 internals/middleware/ 中 DurableContextMiddleware 和 SkillActivationMiddleware）
    delegations: list[DelegationEntry]   # task 委派台账（merge_delegations）
    skill_context: list[SkillEntry]      # 已加载 skill 引用（merge_skill_context）
    summary_text: str | None             # summarization 产出的压缩文本（LastValue）
    promoted: PromotedTools | None       # deferred MCP tool 提升记录（merge_promoted）
```

### 自定义 Reducers

| 字段 | Reducer | 行为 |
|------|---------|------|
| `artifacts` | `merge_artifacts` | 合并 + 去重 |
| `todos` | `merge_todos` | None=保留旧值；非None=覆盖 |
| `viewed_images` | `merge_viewed_images` | `{}`→清空；非空→合并覆盖 |
| `delegations` | `merge_delegations` | 🆕 追加，同 ID 最新胜，终态不可降级，上限 50 |
| `skill_context` | `merge_skill_context` | 🆕 按 path 去重，最近读取的保留，上限 8 |
| `promoted` | `merge_promoted` | 🆕 catalog-hash 作用域，catalog 变更时全量替换 |
