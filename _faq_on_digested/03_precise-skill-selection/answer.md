## 核心发现：两条已经存在的路径

经过对 DeerFlow 代码库的全面挖掘，发现**两条已经存在的精准 skill 选择路径**——但它们各自缺少了对方拥有的那部分能力：

| 能力 | Gateway HTTP API | Embedded Client (`DeerFlowClient`) |
|------|-----------------|-------------------------------------|
| **精准指定 skill** | ❌ 只能通过 agent config 的静态 `skills:` 字段 | ✅ `__init__(available_skills=["..."])` 直接指定 |
| **HTTP 可调用** | ✅ 完整的 REST API | ❌ 只能在 Python 进程中嵌入使用 |
| **context key 传递** | ✅ `body.context` → `merge_run_context_overrides` | ❌ 不走 context key，直接传参 |
| **跨进程/跨语言** | ✅ 任何语言都能调 HTTP | ❌ 必须 Python 进程内 |

**这两条路径的关键差异位于 `_make_lead_agent()` 的调用链上**——

---

## 机制 1：Embedded Client 的 `available_skills` 参数（已存在，最接近你的需求）

### 位置

`backend/packages/harness/deerflow/client.py:116-168` — `DeerFlowClient.__init__()`

### 它做了什么

```python
class DeerFlowClient:
    def __init__(
        self,
        ...
        available_skills: list[str] | None = None,  # 直接指定 skill 列表
        ...
    ):
        self._available_skills = available_skills
```

然后在 `_ensure_agent()` (line 220-266) 中，这个参数被直接传给 agent 构建：

```python
# client.py — 不走 configurable，不走 context，直接传参
system_prompt=apply_prompt_template(
    available_skills=self._available_skills,  # ← 确定性的！
    ...
),
# 同时也用于 tool policy
skills_for_tool_policy = _load_enabled_skills_for_tool_policy(
    self._available_skills, ...
)
tools = filter_tools_by_skill_allowed_tools(tools, skills_for_tool_policy)
```

**这意味着，如果你在 Python 进程中使用 `DeerFlowClient`，你已经可以精准指定任意 skill 集合。** 不需要 LLM 选择，不需要 agent config 文件，就是传参：

```python
client = DeerFlowClient(
    available_skills=["k8s-deploy", "python-testing"],
    agent_name="my-automation-agent",
)
result = client.chat("执行长城任务", thread_id="task-001")
# → 系统 prompt 里只有 k8s-deploy 和 python-testing 两个 skill
# → 工具集合也受这两个 skill 的 allowed-tools 限制
```

### `DeerFlowClient.__init__()` 完整参数列表

`client.py:116-129`，共 **10 个参数**：

| 参数 | 类型 | 默认值 | 作用 |
|------|------|--------|------|
| `config_path` | `str \| None` | `None` | config.yaml 路径，None=自动查找 |
| `checkpointer` | 任意 | `None` | LangGraph checkpointer，多轮对话必需 |
| `model_name` | `str \| None` | `None` | 覆盖默认模型名 |
| `thinking_enabled` | `bool` | `True` | 启用扩展思考 |
| `subagent_enabled` | `bool` | `False` | 启用子 agent 委托 |
| `plan_mode` | `bool` | `False` | 启用 TodoList 中间件 |
| `agent_name` | `str \| None` | `None` | 自定义 agent 名称 |
| **`available_skills`** | **`set[str] \| None`** | **`None`** | **限制可用 skill 集合，None=全部** |
| `middlewares` | `Sequence[AgentMiddleware] \| None` | `None` | 注入自定义中间件 |
| `environment` | `str \| None` | `None` | 部署环境标签（`"production"`/`"staging"`），用于 tracing |

### `chat()` / `stream()` per-call kwargs（`**kwargs`）

`_get_runnable_config()` (`client.py:206-218`) 支持的 per-call 覆盖，共 **5 个**：

| kwargs key | 覆盖的 `__init__` 参数 | 备注 |
|------------|----------------------|------|
| `model_name` | `self._model_name` | |
| `thinking_enabled` | `self._thinking_enabled` | |
| `plan_mode` | `self._plan_mode` | |
| `subagent_enabled` | `self._subagent_enabled` | |
| `recursion_limit` | (无) | 默认 100 |

**不在 per-call kwargs 里的参数（只能在 `__init__` 设置，per-call 传了也没效果）：**

| 参数 | 原因 |
|------|------|
| `available_skills` | 不在 `_get_runnable_config()` 中映射；在 `_ensure_agent()` 中作为 config key 的一部分参与 agent 缓存 hash，但不会从 per-call kwargs 读取 |
| `agent_name` | 不在 `_get_runnable_config()` 中映射；在 `_ensure_agent()` 中直接从 `self._agent_name` 读 |
| `is_bootstrap` | 完全不在 client 路径中——client 没有 bootstrap 模式 |
| `reasoning_effort` | 不在 `_get_runnable_config()` 中；`_ensure_agent()` 中的 `create_chat_model()` 没传这个参数 |
| `max_concurrent_subagents` | 不在 `_get_runnable_config()` 中 |
| `mode` | dead key，全代码库无消费 |

**关键发现：`available_skills` 不仅在 Gateway HTTP API 中不能 per-request 传递（Q2 的分析），在 Embedded Client 中也不能 per-call 动态切换。** 它只能在 client 实例化时设定一次。如果需要同一进程处理不同 skill 集合的任务，必须创建多个 `DeerFlowClient` 实例。

### `_digest/` 里已有的文档

`_digest/integration/04-python-sdk.md` 已列出了全部 10 个 `__init__` 参数（在代码示例块中），但没有区分哪些可在 per-call 覆盖、哪些不能。**per-call kwargs 和 `__init__` 参数的不对称性是文档没有覆盖的。**

### 为什么这很接近你的需求但还不够

- ✅ 精准指定 skill——确定性的，不是 LLM 判断
- ✅ 不受 `_CONTEXT_CONFIGURABLE_KEYS` 白名单限制——直接传参
- ❌ 必须在 Python 进程内——不能通过 HTTP 从外部系统调用
- ❌ `available_skills` 是 `__init__` 参数，不能在每次 `chat()`/`stream()` 时动态切换

---

## 机制 2：Agent config 的 `skills:` 字段（已存在，确定性但不是动态的）

### 位置

`backend/packages/harness/deerflow/config/agents_config.py:49`

```python
class AgentConfig(BaseModel):
    skills: list[str] | None = None  # None=全部, []=禁用, ["a","b"]=只选这些
```

### 它做了什么

每个 custom agent 的 `config.yaml` 可以声明：

```yaml
# agents/my-automation-agent/config.yaml
name: my-automation-agent
description: 企业自动化执行器
skills:
  - k8s-deploy
  - python-testing
  - db-migration
```

然后通过 Gateway API 调用时带上 `agent_name`：

```json
{
  "input": {"messages": [{"role": "human", "content": "执行长城任务"}]},
  "context": {"agent_name": "my-automation-agent"}
}
```

Agent 工厂读取链路：

```
agent_name="my-automation-agent"
  → load_agent_config("my-automation-agent")  # agents_config.py:80
  → AgentConfig(skills=["k8s-deploy", "python-testing", "db-migration"])
  → _available_skill_names(agent_config, False)  # agent.py:359-360
  → {"k8s-deploy", "python-testing", "db-migration"}
  → get_skills_prompt_section(available_skills={"..."})
  → 系统 prompt 中只注入这 3 个 skill
```

### 优点和局限

- ✅ **完全确定性**——agent config 文件写什么，prompt 里就只有什么 skill
- ✅ 通过 Gateway HTTP API 可达——`body.context.agent_name`
- ✅ 可以预先创建多个 agent（每个任务类型一个），通过 `agent_name` 切换
- ❌ **静态配置**——agent 的 `skills:` 写在文件里，不能按单次任务动态变化
- ❌ 如果需要 50 种不同 skill 组合，需要创建 50 个 agent config 文件

### 结合 `update_agent` 的动态化

`update_agent` tool（`tools/builtins/update_agent_tool.py:71-228`）允许 agent **在运行时修改自己的 `skills:`**：

```python
# update_agent_tool.py
def update_agent(
    runtime: Runtime,
    skills: list[str] | None = None,  # 更新 skill 列表
    ...
) -> Command:
```

**但生效时机是下一个 turn**（见 `_digest/harness-hooks/08-agent-self-modification.md`）。当前 turn 继续用旧配置。

---

## 机制 3：`_CONTEXT_CONFIGURABLE_KEYS` 白名单（已存在，但缺少 `skills` 字段）

### 位置

`backend/app/gateway/services.py:124-136`

```python
_CONTEXT_CONFIGURABLE_KEYS: frozenset[str] = frozenset({
    "model_name", "mode", "thinking_enabled", "reasoning_effort",
    "is_plan_mode", "subagent_enabled", "max_concurrent_subagents",
    "agent_name", "is_bootstrap",
})
```

### 它为谁工作

`merge_run_context_overrides()` (services.py:139-153) 会从 `body.context` 中提取这些 key，注入到 `config["configurable"]` 和 `config["context"]`。

`_get_runtime_config()` (agent.py:51-57) 合并两者：

```python
def _get_runtime_config(config: RunnableConfig) -> dict:
    cfg = dict(config.get("configurable", {}) or {})
    context = config.get("context", {}) or {}
    if isinstance(context, dict):
        cfg.update(context)  # context 值覆盖 configurable
    return cfg
```

**这意味着：只要一个 key 通过了 `_CONTEXT_CONFIGURABLE_KEYS` 白名单，它就能在 `_get_runtime_config()` 中被读到。**

而 `_make_lead_agent()` 已经在读取这些 key（agent.py:393-400）：

```python
thinking_enabled = cfg.get("thinking_enabled", True)
is_bootstrap = cfg.get("is_bootstrap", False)
agent_name = validate_agent_name(cfg.get("agent_name"))
...
```

如果要让 `skills` 通过 HTTP API 传递，只需要：
1. 在 `_CONTEXT_CONFIGURABLE_KEYS` 中加 `"skills"`
2. 在 `_make_lead_agent()` 中加 `cfg.get("skills")` 逻辑

**但当前没有这条路径。**

---

## 机制 4：DeferredToolFilterMiddleware 的 "延迟发现" 模式（可参考的架构）

### 位置

- `deerflow/agents/middlewares/deferred_tool_filter_middleware.py` — 中间件
- `deerflow/tools/builtins/tool_search.py` — 搜索 + promote 工具
- ContextVar 隔离：`tool_search.py:145-158`

### 它的完整生命周期

```
Session 开始
  │
  ├─ get_available_tools() → DeferredToolRegistry 注册所有 MCP tools
  │
  ├─ DeferredToolFilterMiddleware.wrap_model_call()
  │     → 从 bind_tools 中移除 deferred tool 的 schema
  │     → LLM 看不到这些 tool 的完整定义
  │
  ├─ 系统 prompt 中的 <available-deferred-tools> 只列出名字
  │
  ├─ LLM 决定搜索 → 调用 tool_search("k8s")
  │     → registry.search("k8s") 返回匹配的 tool schema
  │     → registry.promote({matched_names})
  │
  ├─ 下一次 wrap_model_call:
  │     → 已 promote 的 tool 不再被过滤
  │     → LLM 看到完整 schema → 可以直接调用
```

### 为什么这个模式对 skill 有价值

DeferredTool 模式解决的核心问题和你面对的问题**高度同构**：

| DeferredTool 解决的问题 | Skill 面临的对应问题 |
|------------------------|---------------------|
| 大量 MCP tool 挤占 `bind_tools` context | 大量 skill 挤占系统 prompt context |
| LLM 从 100+ tool 中选不准 | LLM 从 50+ skill 中选不准 |
| 两阶段：名字列表 → 搜索 → 完整 schema | 同样可以：名字+描述 → 搜索 → 完整 SKILL.md |
| ContextVar 隔离 per-request | 同样需要 per-request 隔离 |
| `registry.promote()` 是确定性的 | 同样可以做到确定性选择 |

**如果把 `DeferredToolRegistry` 模式套到 skill 上：**

```
Session 开始
  │
  ├─ 系统 prompt 中只列出 skill 的 name + description（不注入 SKILL.md body）
  │
  ├─ skill_search tool 可用
  │
  ├─ 外部系统（或 LLM）调用 skill_search("k8s deploy")
  │     → 匹配 skill → promote → 注入 SKILL.md 内容到上下文
  │
  ├─ LLM 现在有完整的 skill 指令
```

**重点：即使在 "自主静默执行" 场景下，外部系统也可以在初始消息中直接调用 `skill_search("k8s-deploy", "python-testing")` 来 promote 所需的 skill。** 这绕过了 LLM 自主选择的不可靠性。

---

## 机制 5：Bootstrap —— 一个已工作的 "受限 skill 集" 先例

### 位置

- `backend/app/channels/manager.py:936-941` — `/bootstrap` 命令
- `backend/packages/harness/deerflow/agents/lead_agent/agent.py:357-358` — 硬编码限制

```python
def _available_skill_names(agent_config, is_bootstrap: bool) -> set[str] | None:
    if is_bootstrap:
        return {"bootstrap"}  # 只暴露一个 skill
```

Bootstrap 证明了：**"将可用 skill 集限定为确定性子集" 这个模式已经工作。** 只是目前只有 `/bootstrap` → `{"bootstrap"}` 这一种映射。

### 类比： `/task` 命令

如果 channel 系统增加了类似逻辑：

```python
# 假设的 /task 命令
if command == "task":
    # 从任务名 → skill 名的映射
    task_skills = {"deploy": ["k8s-deploy", "python-testing"], ...}
    skills = task_skills.get(parts[1], [])
    await self._handle_chat(chat_msg, extra_context={"skills": skills})
```

这个模式的扩展是自然的——只需要一个 task→skill 映射表（或从前端/外部系统传入）。

---

## 机制 6：`build_run_config()` 的 "forward all keys" 行为（未文档化）

### 位置

`backend/app/gateway/services.py:234-236`

```python
# All other top-level keys from body.config are forwarded
for key, value in body.config.items():
    if key not in ("configurable", "context"):
        config[key] = value
```

**这意味着 `body.config` 中的任意 key 都会被放入 `RunnableConfig`。** 虽然它们不一定会被 `_get_runtime_config()` 读到（因为那个函数只看 `configurable` 和 `context`），但如果一个 middleware 直接在 `RunnableConfig` 上读一个 key，它就能读到。

### 实际使用者

- `body.config["recursion_limit"]` → LangGraph graph execution（services.py:197）
- `body.config["metadata"]` → LangSmith/Langfuse tracing（services.py:256）
- `body.config["callbacks"]` → 自定义 callback 注入
- `body.config["tags"]` → trace tagging

---

## 综合积木清单

详见 [building-blocks.md](building-blocks.md)。

## 实现路径

详见 [implementation-paths.md](implementation-paths.md)。

---

## 结论

**你找的东西分散在 DeerFlow 的各个角落——它们存在，但被隔离在不同的边界里。**

最直接可用的是**嵌入式客户端路径**（`DeerFlowClient.available_skills`）——它已经支持精准指定 skill，只是不能通过 HTTP 访问。第二直接的是**agent config 文件路径**——它已经通过 Gateway 可达，但需要静态配置文件。

最小的整合点是把 `skills` 加入 `_CONTEXT_CONFIGURABLE_KEYS` 白名单——这会打通 HTTP API 的精准 skill 选择通道。**改动量是 5 行代码。**

对于"长城任务"场景，当前最务实的方案是：**预建 agent config（每种任务类型一个 agent，每个 agent 配置好 skills），通过 `agent_name` context key 切换。** 这不需要改任何代码。

---

## 相关 digest 笔记

- `_faq_on_digested/skill-selection-accuracy/` — Q1: skill 选取精度问题
- `_faq_on_digested/command-skill-linkage/` — Q2: 任务 MD 与 skill 联动
- `_digest/harness-hooks/04-agent-middleware-hooks.md` — DeferredToolFilterMiddleware 在 chain 中的位置
- `_digest/harness-hooks/06-mcp-interceptors.md` — MCP 工具发现机制
- `_digest/harness-hooks/07-context-config-override.md` — ContextVar 运行时覆盖 + 配置优先级
- `_digest/harness-hooks/08-agent-self-modification.md` — `update_agent` 原子写入 + 生效时机
- `_digest/middleware/03-catalog.md` — 完整 19 middleware 目录 + DeferredToolFilterMiddleware 位置

Sources:
- DeerFlow 源码: `deerflow/client.py:116-168` — `DeerFlowClient.available_skills` 参数
- DeerFlow 源码: `deerflow/config/agents_config.py:38-49` — `AgentConfig.skills` 字段
- DeerFlow 源码: `deerflow/agents/lead_agent/agent.py:356-361` — `_available_skill_names()`
- DeerFlow 源码: `deerflow/agents/lead_agent/agent.py:51-57` — `_get_runtime_config()` 合并逻辑
- DeerFlow 源码: `app/gateway/services.py:124-153` — `_CONTEXT_CONFIGURABLE_KEYS` + `merge_run_context_overrides`
- DeerFlow 源码: `app/gateway/services.py:188-257` — `build_run_config()` forward-all 行为
- DeerFlow 源码: `deerflow/tools/builtins/tool_search.py:39-158` — `DeferredToolRegistry` + ContextVar 隔离
- DeerFlow 源码: `deerflow/agents/middlewares/deferred_tool_filter_middleware.py` — promote/filter 生命周期
- DeerFlow 源码: `deerflow/tools/builtins/update_agent_tool.py:71-228` — agent 自修改 skills
- DeerFlow 源码: `app/channels/manager.py:936-941` — `/bootstrap` → `extra_context={"is_bootstrap": True}`
