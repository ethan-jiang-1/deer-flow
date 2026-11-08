---



title: "Lead Agent 系统"
description: 'DeerFlow 的核心：`make_lead_agent` 工厂函数创建与 LangGraph 兼容的 Agent。'
topics: [agent, factory, threadstate]
verified_against: v2.2.0
last_verified: 2026-11-08
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

🆕 条件追加的工具（v2.1.0-rc0）：
- **Project shelf tools**：仅当 run 的 runtime context 带有 admission 钉住的 `PROJECT_CONTEXT_KEY` 时才注册（§10.11）——非项目 run 不支付这些工具的 schema token，也看不到它们；项目 run 即使 instructions 和 shelf 都为空也保留。工具在调用时读同一个 pinned key，缺失即 fail closed
- **Memory tools**：受 `memory_enabled` 控制——custom agent 现在可以整体禁用 memory 读写（`skip_memory_flush=not memory_enabled`）
- **Task continuity tools**：`task_continuity.enabled` 开启时追加（opt-in 任务笔记 + 压缩历史召回，见 `docs/task-continuity.md`）

工具名冲突的追加策略统一为 `_append_named_tools_without_conflicts`：只跳过同名工具，不会因为一个重名而丢掉同批次其他工具。

### 6. 生成 System Prompt

```python
system_prompt = apply_prompt_template(
    agent_config=agent_config,
    available_skills=skills,
    is_bootstrap=is_bootstrap,
    app_config=resolved_app_config,
    interaction_policy=interaction_policy,                     # 🆕 v2.2.0
    bash_available=has_bash_tool(authorized_tools),            # 🆕 v2.2.0
    ...
)
```

System prompt 包含：
- 基础 Agent 行为指令
- 启用的 Skills 列表及 container path（`allowed-tools` 只作兼容元数据，不再收窄工具集）
- Subagent 使用说明
- Bootstrap 模式特殊指令（如果创建新 Agent）
- 🆕 `interaction_policy` 决定的三块文案：`interaction_thinking_guidance`（交互模式下鼓励先问再动）、`clarification_system` + `clarification_reminder`（非交互模式下**移除** `ask_clarification` 指引并改成"不要追问，自己决断"）
- 🆕 `bash_available=False`（授权后的工具集里没有 `bash`）时，ACP/workspace-scripts 段降级为不含 bash 的措辞
- 🆕 memory tool 段新增 `memory_get`

**`lead_prompt_overlay`（v2.2.0）**：`apply_prompt_template()` 返回前最后一件事是 `app_config.lead_prompt_overlay.apply(rendered_prompt)`（`lead_agent/prompt.py:1289-1290`）。`PromptOverlay` 是 `{prepend: str, append: str}` 两个 `strict=True` 的字符串字面量，`apply()` 用 `"\n\n"` 把非空部分拼起来——**不做模板展开**，因此可以安全放操作方自己的指令文本；两者都为空时 prompt 字节完全不变（保住 prefix cache）。overlay 之后的 prompt 必须与 graph/descriptor 记录的 prompt 一致。

**`context.locale`（v2.2.0）**：web run 可以在 runtime context 里给 `context.locale`（`en-US` / `zh-CN`）。它只作为**请求内**的语言偏好投影进人数据（DynamicContext 的 transient 块），静态 system prompt 与 locale 无关——所以切换语言的会话仍能复用 system prompt 前缀缓存。

### 6.5 交互策略 `interaction_policy`（🆕 v2.2.0）

`agents/interaction_policy.py` 把"这次 run 能不能向用户追问"变成一个显式、可测试的判定，而不是散落在各处的 flag：

```python
class RunInteractionMode(StrEnum):
    INTERACTIVE = "interactive"
    AUTONOMOUS  = "autonomous"
    WEBHOOK     = "webhook"
    SCHEDULED   = "scheduled"

def resolve_run_interaction_policy(config) -> RunInteractionPolicy: ...
```

判定输入（按优先级）：内部认证调用方带的 `interaction_mode` runtime key → `non_interactive` 开关 → `channel_name == "github"` → scheduled/webhook 能力。`disable_clarification` 与 `non_interactive` 只对**内部认证**的调用方生效，客户端自带的同名值会被丢弃。策略只暴露 `allows_clarification` 等布尔结论，供两处消费：prompt 模板删掉 `ask_clarification` 指引，以及工具装配不注册 `ask_clarification`（`ASK_CLARIFICATION_TOOL_NAME`）。

### 7. 构建 Middleware 并 create_agent

```python
middlewares = build_middlewares(config, model_name, agent_name, ...)   # lead_agent/agent.py:485
layer_one = layer_one_outcome(authorization_candidates, authorized_tools)
middlewares, declared_authorized = narrow_declared_tools(middlewares, ..., outcome=layer_one)  # :1379
bound_middlewares = normalize_middleware_state_schemas(middlewares, mode)                      # :1403
verify_declared_tool_view(bound_middlewares, authorized_names=declared_authorized)             # :1404
graph = create_agent(
    model=chat_model,
    tools=final_tools,
    middleware=bound_middlewares,
    system_prompt=system_prompt,
    state_schema=get_thread_state_schema(mode),
    context_schema=dict,
)
```

🆕 **v2.2.0：中间件声明工具的 Layer-1 授权（`middlewares/tool_declarations.py`）**。LangChain 在宿主工具列表被授权过滤**之后**才把 `middleware.tools` 折进绑定集，因此 middleware 声明的工具会绕过第 1 层授权。修复方式是在装配期做五步闭环：`layer_one_outcome()` 固化普通 pass 的判词 → `collect_declared_tools()` 收集声明（非 list/tuple 抛 `DeclaredToolViewError`）→ `decide_declared_tools()` 用**同一个 provider 实例**只裁决没见过的名字（已裁决的复用原判词）→ `apply_declared_tool_view()` **复制**被削的 middleware（绝不改调用方实例）→ `verify_declared_tool_view()` 在最终栈上复检。`authorization.enabled` 不为真时全部跳过并返回原始 list 对象。

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
- 🆕 display name 支持 Unicode（如中文 Agent 名）；目录名仍走 `AGENT_NAME_PATTERN` 文件系统安全校验，两者分离
- 🆕 可通过 agent 配置整体禁用 memory（读写都关，见上文 `memory_enabled`）

---

## 🆕 Projects 上下文注入（v2.1.0-rc0）

**核心设计**：run admission 时**一次异步解析**钉住项目快照，之后全部是纯渲染——无数据库/文件系统 I/O，无历史比对。

```
resolve_project_context(thread_store, project_repo, thread_id, document_repo)
  → 一次一致性读：threads_meta.project_id + project 行 + 有界 shelf 快照
    （active 文档数 + 前 shelf_index_max_entries+1 行，updated_at DESC）
  → 钉到 runtime context 的 PROJECT_CONTEXT_KEY 下
```

**关键语义**：

| 语义 | 说明 |
|------|------|
| **latest-only** | 每次 run 渲染当次钉住的快照；旧 run 的 `<project>` 内容不进持久历史，下次 run 直接渲染新快照 |
| **transient message** | 渲染出的 `<project>`（+非空时的 `<documents>` 索引）是一条带 `deerflow_project_context` marker 的临时 user message，**只骑在 model request 上**，从不写入 `state["messages"]` 或 checkpoint |
| **防误删** | 识别 project message 不能只靠 ID 前缀——必须 marker + provenance 双重匹配，用户消息绝不会被移除 |
| **pinned 身份 vs live 数据** | 快照钉住"哪个项目"；shelf 工具调用时查 **live 行**。run 中途文档被删会得到 "no longer on the shelf" 错误而非过期内容 |
| **上下文事件** | 渲染时记录 `project_context_revision` / `project_shelf_revision`（渲染块的 sha256 指纹） |

**渲染边界**（config `projects:` 段）：instructions 超限写入时即 422 拒绝（从不截断）；`<documents>` 索引受 `shelf_index_max_entries`（默认 50）和 `shelf_index_max_bytes`（默认 4096，CJK 文档名下通常先于条目数触顶）双界。

**注入位置**：由 DynamicContextMiddleware 在 model request 组装时插入（与 `<memory>` 块同层；prompt.md 明确告诉模型：request 中的 `<project>` 块是唯一生效来源，历史里提到的旧项目设置一律忽略）。

**架构归档**：`archived/` 状态的项目成员仍保留 instructions 注入和只读 shelf 访问。

> 完整设计文档：`docs/superpowers/specs/2026-09-12-projects-mvp-phase2-design.md`（606 行）。Gateway 侧 routers / trash 见 enterprise-operations/app-layer。

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
    # 🆕 v2.1.0-rc0 新增：
    task_notes: dict | None              # 任务笔记（TaskNotesChannel 自定义 reducer，opt-in task_continuity）
    task_history: dict | None            # 压缩历史召回记录（NotRequired）
    # 🆕 v2.2.0 新增：
    goal_outcome: NotRequired[GoalOutcomeState | None]              # 目标达成快照（普通 LastValue 通道，无 reducer）
    tool_artifacts: Annotated[list[ArtifactEntry], merge_tool_artifacts]        # tool artifact 注册表
    tool_artifact_processed: Annotated[list[str], merge_artifacts]              # 已处理条目的去重 hash 台账
```

🆕 **v2.2.0 的 `tool_artifacts` / `tool_artifact_processed`（issue #4676）**：`ArtifactEntry` 是 tool 结果里轻量引用的持久形态——模型只看得到短 `handle`（`art_` + 8 hex），真实引用（`real_ref`：路径 / URL / task id）留在这里，tool 调用时由 `ArtifactResolutionMiddleware` 还原。字段：`handle`、`tool_name`、`tool_call_id`、`call_index`、`artifact_type`、`display_name`、`real_ref`（以上必填）、`mime_type`、`created_at`、`consumed_by`。因为走 reducer 通道，条目**跨 summarization 压缩存活**。`tool_artifact_processed` 记录已处理的结果/消费调用的去重 hash（**空结果也记**），使捕获在 checkpoint 重载、graph 重建、压缩之后仍然幂等——不能被"按当前保留的 handle 推断"替代。

`GoalOutcomeState`（`status` 字面量 `"achieved"`）由 `agents/goal_state.py` 定义：`objective`、`goal_created_at`、`achieved_at`、`continuation_count`、`max_continuations`、`reason`、`relied_on_assumption`、`reply_message_id`。对应的 `GoalEvaluation` 也新增 `relied_on_assumption: NotRequired[bool]`。

### DelegationEntry 🆕 验收字段（RFC #4651）

```python
class DelegationEntry(TypedDict):
    ...
    stop_reason: NotRequired[str]          # turn_capped / loop_capped（此前已有）
    receipt_verdict: NotRequired[dict]     # 🆕 PR2：父方 receipt 引用核查结论（建议性证据），task 写回时盖章
    acceptance_verdict: NotRequired[dict]  # 🆕 PR4：确定性验收清单结论（同 provenance）
    created_at: str
```

旧历史没有这两个字段（NotRequired）。详见 [concepts/subagent/](../subagent/)。

### ViewedImageData 🆕

```python
class ViewedImageData(TypedDict):
    mime_type: str
    size: int
    actual_path: str
    sha256: str                            # 🆕 校验宿主同步副本与上次查看的字节一致
    source_sandbox_id: NotRequired[str]    # 🆕 字节来自哪个 sandbox
```

图片字节仍按需读取（不进 checkpoint），但现在可以从"大小+SHA-256 都匹配的宿主同步副本"读取，sandbox 重建后不失效。

### 自定义 Reducers

| 字段 | Reducer | 行为 |
|------|---------|------|
| `artifacts` | `merge_artifacts` | 合并 + 去重 |
| `todos` | `merge_todos` | None=保留旧值；非None=覆盖 |
| `viewed_images` | `merge_viewed_images` | `{}`→清空；非空→合并覆盖 |
| `delegations` | `merge_delegations` | 追加，**同 `(run_id, tool-call id)` 最新胜**（v2.2.0 起身份带 run 作用域——provider 的 id 在同 thread 的后续 run 里可能重复）；无 `run_id` 的旧更新仍匹配最近的同 id 条目；终态不被非终态覆盖；上限 50 |
| `skill_context` | `merge_skill_context` | 按 path 去重，最近读取的保留，上限 8 |
| `promoted` | `merge_promoted` | v2.2.0 起作用域 = `(catalog_hash, turn_id)`：`catalog_hash` 或显式 `turn_id` 变化 → 全量替换并丢弃陈旧名字；同作用域 → 并集去重保序；缺 `turn_id` 时继承既有作用域（`tool_search` 在 filter 之后的写入就是这个形状）。坏掉的 `names`（非 list-of-str）按空处理而不抛错 |
| `viewed_images` | `merge_viewed_images` | `{}`→清空；非空→合并覆盖，且**被更新的 key 移到末尾**——注入 middleware 按最新优先接纳并在省略时提示模型重新查看，恢复路径依赖"重看的条目确实变成最新"（#6825/#6829） |
| `tool_artifacts` | `merge_tool_artifacts` | 🆕 同 handle 最新胜并保首见序；尾部 `{"op": "trim_to", "keep": N}` 指令让配置上限成为滑动窗口；无指令时不淘汰任何条目；**绝对上限 1000**（operator 配置 `tool_artifacts.max_entries`，默认 100、范围 10–1000，由 ArtifactCapture 在发更新时按 agent 执行，故同进程两个 agent 可以有不同上限） |
| `tool_artifact_processed` | `merge_artifacts` | 🆕 去重合并（与 `artifacts` 共用 reducer） |

`THREAD_STATE_REDUCER_FIELDS`（`thread_state.py:510`）已把 `tool_artifacts` / `tool_artifact_processed` 列入 reducer 字段集——checkpoint 模式归一化要靠这张表。
