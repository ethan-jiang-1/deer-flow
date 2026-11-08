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

`backend/packages/harness/deerflow/client.py:210-224` — `DeerFlowClient.__init__()`（v2.2.0 行号）

### 它做了什么

```python
class DeerFlowClient:
    def __init__(
        self,
        ...
        available_skills: set[str] | None = None,  # 直接指定 skill 列表（client.py:221）
        ...
    ):
        self._available_skills = set(available_skills) if available_skills is not None else None  # client.py:270
```

然后在 `_ensure_agent()`（client.py:331 起）中，这个参数被直接传给 agent 构建——2.2.0 在中间多插了一道 Layer 1 授权过滤：

```python
# client.py — 不走 configurable，不走 context，直接传参
# v2.2.0：_available_skills 先过 Layer 1 授权过滤，再用于 skill 目录与 prompt
available_skills = filter_available_skills_by_authorization(     # client.py:442-449
    self._available_skills,
    context=cfg, app_config=self._app_config, user_id=effective_user_id,
    candidate_skill_names=candidate_skill_names, authorization=skill_authorization,
)
...
if available_skills is not None:                                  # client.py:476-477
    skills_list = [s for s in skills_list if s.name in available_skills]
# 然后随 agent 装配一起下发（client.py:517 / 553）
# 注意：client.py:389 的 agent 缓存 key 仍用未过滤的 self._available_skills
# ⚠️ 2.2 起 available_skills **不再**联动 allowed-tools —— 那个工具策略在
#    skills/tool_policy.py（**已删除**，#6935）里，配套的
#    SkillToolPolicyMiddleware（skill_tool_policy_middleware.py，**已删除**）也已移除；
#    工具边界改由 agent 组装 + 执行授权（authz/tool_filter.py、authz/adapter.py）决定
```

**这意味着，如果你在 Python 进程中使用 `DeerFlowClient`，你已经可以精准指定任意 skill 集合。** 不需要 LLM 选择，不需要 agent config 文件，就是传参：

```python
client = DeerFlowClient(
    available_skills=["k8s-deploy", "python-testing"],
    agent_name="my-automation-agent",
)
result = client.chat("执行长城任务", thread_id="task-001")
# → 系统 prompt 里只有 k8s-deploy 和 python-testing 两个 skill
# → 但工具集合**不受**这两个 skill 的 allowed-tools 限制（2.2 起 allowed-tools 是兼容元数据）
```

### `DeerFlowClient.__init__()` 完整参数列表

`client.py:210-223`，共 **10 个参数**（v2.2.0；`available_skills` 的类型是 `set[str] | None`，`client.py:221`）：

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

`_get_runnable_config()`（`client.py:317-329`）支持的 per-call 覆盖，共 **5 个**：

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

### `_digested/` 里已有的文档

`_digested/getting-started/03-python-sdk.md` 已列出了全部 10 个 `__init__` 参数（在代码示例块中），但没有区分哪些可在 per-call 覆盖、哪些不能。**per-call kwargs 和 `__init__` 参数的不对称性是文档没有覆盖的。**

### 为什么这很接近你的需求但还不够

- ✅ 精准指定 skill——确定性的，不是 LLM 判断
- ✅ 不受 `_CONTEXT_CONFIGURABLE_KEYS` 白名单限制——直接传参
- ❌ 必须在 Python 进程内——不能通过 HTTP 从外部系统调用
- ❌ `available_skills` 是 `__init__` 参数，不能在每次 `chat()`/`stream()` 时动态切换

---

## 机制 2：Agent config 的 `skills:` 字段（已存在，确定性但不是动态的）

### 位置

`backend/packages/harness/deerflow/config/agents_config.py:221`（`AgentConfig` 定义在 agents_config.py:207）

```python
class AgentConfig(BaseModel):
    skills: list[str] | None = None  # None=全部, []=禁用, ["a","b"]=只选这些
    # 2.2 注释原文（agents_config.py:215-217）："skills controls which skills are
    # discoverable and may be activated by the agent.
    # allowed-tools is compatibility metadata only and never restricts tools"
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
  → load_agent_config("my-automation-agent")  # agents_config.py:332
  → AgentConfig(skills=["k8s-deploy", "python-testing", "db-migration"])
  → _available_skill_names(agent_config, False)  # agent.py:812-817
  → {"k8s-deploy", "python-testing", "db-migration"}
  → filter_available_skills_by_authorization(...)  # agent.py:1041-1047（Layer 1，2.2 新增）
  → get_skills_prompt_section(available_skills={"..."})  # prompt.py:959
  → 系统 prompt 中只注入这 3 个 skill
```

### 优点和局限

- ✅ **完全确定性**——agent config 文件写什么，prompt 里就只有什么 skill
- ✅ 通过 Gateway HTTP API 可达——`body.context.agent_name`
- ✅ 可以预先创建多个 agent（每个任务类型一个），通过 `agent_name` 切换
- ❌ **静态配置**——agent 的 `skills:` 写在文件里，不能按单次任务动态变化
- ❌ 如果需要 50 种不同 skill 组合，需要创建 50 个 agent config 文件

### 结合 `update_agent` 的动态化

`update_agent` tool（`tools/builtins/update_agent_tool.py:78` 起）允许 agent **在运行时修改自己的 `skills:`**：

```python
# update_agent_tool.py
def update_agent(
    runtime: Runtime,
    skills: list[str] | None = None,  # 更新 skill 列表
    ...
) -> Command:
```

**但生效时机是下一个 turn**（见 `_digested/internals/harness-hooks/08-agent-self-modification.md`）。当前 turn 继续用旧配置。

---

## 机制 3：`_CONTEXT_CONFIGURABLE_KEYS` 白名单（已存在，但缺少 `skills` 字段）

### 位置

`backend/app/gateway/services.py:880-895`

```python
_CONTEXT_CONFIGURABLE_KEYS: frozenset[str] = frozenset({
    "model_name", "mode", "thinking_enabled", "reasoning_effort",
    "is_plan_mode", "subagent_enabled", "max_concurrent_subagents",
    "max_total_subagents", "agent_name", "is_bootstrap",
})
```

### 它为谁工作

`merge_run_context_overrides()` (services.py:1005) 会从 `body.context` 中提取这些 key，注入到 `config["configurable"]` 和 `config["context"]`（另有 internal-caller 专属的 `_CONTEXT_INTERNAL_CALLER_KEYS`，外部调用方传了也会被丢弃）。

`_get_runtime_config()` (agent.py:219-226) 合并两者：

```python
def _get_runtime_config(config: RunnableConfig) -> dict:
    cfg = dict(config.get("configurable", {}) or {})
    context = config.get("context", {}) or {}
    if isinstance(context, dict):
        cfg.update(context)  # context 值覆盖 configurable
    return cfg
```

**这意味着：只要一个 key 通过了 `_CONTEXT_CONFIGURABLE_KEYS` 白名单，它就能在 `_get_runtime_config()` 中被读到。**

而 `_make_lead_agent()` 已经在读取这些 key（agent.py:987 / 995 / 1008）：

```python
thinking_enabled = cfg.get("thinking_enabled", True)
is_bootstrap = cfg.get("is_bootstrap", False)
agent_name = validate_agent_name(cfg.get("agent_name"))
...
```

如果要让 `skills` 通过 HTTP API 传递，只需要：
1. 在 `_CONTEXT_CONFIGURABLE_KEYS` 中加 `"skills"`
2. 在 `_make_lead_agent()` 中加 `cfg.get("skills")` 逻辑

**但当前没有这条路径。** 2.2.0 实测白名单仍是那 10 个 key（services.py:880-895），`skills` 不在其中。

---

## 机制 4：DeferredToolFilterMiddleware 的 "延迟发现" 模式（可参考的架构）

### 位置

- `deerflow/agents/middlewares/deferred_tool_filter_middleware.py` — 中间件
- `deerflow/tools/builtins/tool_search.py:113` — `DeferredToolCatalog`（docstring 原文 "Immutable catalog of deferred tools. Pure search, no mutation."）；`search()` 在 tool_search.py:128，promote 状态随图状态传递（返回 `{"promoted": {"catalog_hash", "names"}}`，tool_search.py:268-272）
- ContextVar 隔离：~~tool_search.py:145-158~~ — **v2.1.0-rc0 已重构：tool_search 不再使用 ContextVar**（tool_search.py 顶部注释明确 "no ContextVar"，改为随图状态传递；搜索还支持 `select:` 精确选择与 `+` 前缀必含名匹配，评分逻辑对齐 `SkillCatalog.search`）

### 它的完整生命周期

```
Session 开始
  │
  ├─ get_available_tools() → DeferredToolCatalog 注册所有 MCP tools
  │
  ├─ DeferredToolFilterMiddleware.wrap_model_call()
  │     → 从 bind_tools 中移除 deferred tool 的 schema
  │     → LLM 看不到这些 tool 的完整定义
  │
  ├─ 系统 prompt 中的 <available-deferred-tools> 只列出名字
  │
  ├─ LLM 决定搜索 → 调用 tool_search("k8s")
  │     → registry.search("k8s") 返回匹配的 tool schema
  │       （支持 `select:name` 精确选择、`+token` 必含名匹配、`_rank_by_intent` 式评分排序）
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

**如果把 `DeferredToolCatalog` 模式套到 skill 上：**

> 🔄 同步 #6（v2.1.0-rc0）：这一设想已部分官方化——skill 侧的对应实现是 **deferred discovery**（`skills_config.skills.deferred_discovery`）：系统 prompt 只渲染 `<skill_index>` 名单，`describe_skill` 工具按需取详情；skill 搜索/排序由 `skills/catalog.py` 的 `_rank_by_intent`/`_intent_score` 字面 intent 排名承担（#5369），外部系统也可通过 `/skill-name` slash 激活（`skills/slash.py` + `SkillActivationMiddleware`）做确定性注入。详见 `_digested/concepts/skills-tools/skill-md-and-tool-assembly.md`。

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

> 🔄 同步 #8（v2.2.0）：上面这个「设计设想」与 2.2 的落地形态要对上号——skill 侧的官方实现叫 **deferred discovery**（`skills_config.skills.deferred_discovery`，`config/skills_config.py:46`，默认 `False`），prompt 只渲染 `<skill_index>`、`describe_skill` 按需取详情；但**它不是 `skill_search`，也没有 promote 概念**：`DeferredToolCatalog` 是 "pure search, no mutation" 的不可变目录（tool_search.py:114），只服务 MCP tools。另外 `build_deferred_tool_setup()` 的 docstring 现在明写 skill 的 `allowed-tools` 是兼容元数据、不参与 deferred 装配（tool_search.py:281-284）。所以「外部系统调 `skill_search` 把 skill promote 进上下文」在 2.2 仍是**设想**，不是现成能力；现成的确定性手段是 `/skill-name` slash 激活与 agent 的 `skills:` 白名单。

---

## 机制 5：Bootstrap —— 一个已工作的 "受限 skill 集" 先例

### 位置

- `backend/app/channels/manager.py:3730-3735` — `/bootstrap` 命令
- `backend/packages/harness/deerflow/agents/lead_agent/agent.py:812-817` — 硬编码限制（`_BOOTSTRAP_SKILL_NAMES = {"bootstrap"}`，agent.py:84）

```python
def _available_skill_names(agent_config, is_bootstrap: bool) -> set[str] | None:
    if is_bootstrap:
        return set(_BOOTSTRAP_SKILL_NAMES)  # 只暴露 bootstrap skill
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

`backend/app/gateway/services.py` — `build_run_config()`（services.py:1328 起）

> 🔄 同步 #6（v2.1.0-rc0）：原文引用的 "forward all top-level keys" 循环（旧 services.py:234-236）已随 `build_run_config` 重写而消失。现行实现按 LangGraph >=0.6.0 语义处理 `body.config`：`context` 与 `configurable` 二选一（同时给出时告警并优先 `context`），`__` 前缀的私有 key 会被剥除（防伪造 skill secret-binding 内部状态，#3938），`recursion_limit` 有 Gateway 级 clamp（`_resolve_gateway_recursion_limits`）。"任意 key 直接透传" 的行为已大幅收窄。

### 实际使用者

- `body.config["recursion_limit"]` → LangGraph graph execution（经 `_resolve_gateway_recursion_limits()` clamp，services.py:1226 起）
- `body.config["metadata"]` → LangSmith/Langfuse tracing（`_ensure_thread_metadata`，services.py:256 起）
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

> 🔄 同步 #8（v2.2.0）：**结论不变，但要补三点 2.2 的口径修正。**
> 1. **工具边界不再由 skill 决定。** 2.1 时代几个机制（`DeerFlowClient(available_skills=...)`、slash 激活、agent `skills:`）都「顺带」受 skill 的 `allowed-tools` 收紧，形成「选定 skill 集 = 锁定工具集」的组合。2.2 已把 `allowed-tools` 降级为**兼容元数据**（上游 #6935 / `0d73798be`）：**已删除** `skills/tool_policy.py`（65 行）与 `agents/middlewares/skill_tool_policy_middleware.py`（529 行），`build_middlewares()` 的注册一并移除。权限上限改为由 **Layer 1 `AuthorizationProvider`**（`authz/provider.py:86` + `apply_tool_authorization()`，`authz/tool_filter.py:25-33`）与 **Layer 2 `GuardrailAuthorizationAdapter`**（`authz/adapter.py:27`）拥有。所以上面的三种「精准 skill 选择」方案，现在**只能**管 skill 可见性，管不了工具——要限制工具请用 `disallowed_tools` / `authorization` / agent 的 `tool_groups`。
> 2. **多了一道 Layer 1 过滤。** 嵌入式 client 与 lead agent 在应用 `available_skills` 前都要先过 `filter_available_skills_by_authorization()`（client.py:442-449、agent.py:1041-1047），所以「传进去的集合」≠「模型看到的集合」——授权策略可以进一步收窄它。`deerflow/client.py:389` 的 agent 缓存 key 用未过滤的 `self._available_skills`，但上方 client.py:415 注释已声明这是**有意为之**：「`self._available_skills` is left untouched (it feeds the cache key at line 282)」——过滤只在装配时生效。
> 3. **`skills` 仍未进白名单。** `_CONTEXT_CONFIGURABLE_KEYS`（services.py:880-895）在 2.2 依旧是那 10 个 key，所以「5 行代码的最小整合点」在原样成立之前仍待实现，且实现时**不要**顺手把工具收紧逻辑挂到 skill 上（那是 2.1 已删除的机制）。

---

## 相关 digest 笔记

- `_faq_on_digested/01_skill-selection-accuracy/` — Q1: skill 选取精度问题
- `_faq_on_digested/02_command-skill-linkage/` — Q2: 任务 MD 与 skill 联动
- `_digested/internals/harness-hooks/04-agent-middleware-hooks.md` — DeferredToolFilterMiddleware 在 chain 中的位置
- `_digested/internals/harness-hooks/06-mcp-interceptors.md` — MCP 工具发现机制
- `_digested/internals/harness-hooks/07-context-config-override.md` — ContextVar 运行时覆盖 + 配置优先级
- `_digested/internals/harness-hooks/08-agent-self-modification.md` — `update_agent` 原子写入 + 生效时机
- `_digested/internals/middleware/03-catalog.md` — 完整 37 middleware 目录 + DeferredToolFilterMiddleware 位置

Sources（行号为 v2.2.0 实测）:
- DeerFlow 源码: `deerflow/client.py:210-224, 221, 317-329, 389, 442-449, 476-477, 517, 553` — `DeerFlowClient.available_skills` 参数与 Layer 1 过滤
- DeerFlow 源码: `deerflow/config/agents_config.py:207, 215-221, 332` — `AgentConfig.skills` 字段（含 allowed-tools 兼容元数据注释）
- DeerFlow 源码: `deerflow/agents/lead_agent/agent.py:84, 812-817` — `_available_skill_names()`
- DeerFlow 源码: `deerflow/agents/lead_agent/agent.py:219-226` — `_get_runtime_config()` 合并逻辑
- DeerFlow 源码: `app/gateway/services.py:880-895, 1005` — `_CONTEXT_CONFIGURABLE_KEYS` + `merge_run_context_overrides`
- DeerFlow 源码: `app/gateway/services.py:1328` — `build_run_config()`（forward-all 行为已收窄）
- DeerFlow 源码: `deerflow/tools/builtins/tool_search.py:113, 128, 268-272, 281-284` — `DeferredToolCatalog`（不可变、纯搜索、无 ContextVar）
- DeerFlow 源码: `deerflow/skills/catalog.py:76-96` — `_intent_score`/`_rank_by_intent` 字面 intent 排名
- DeerFlow 源码: `deerflow/skills/slash.py:39, 54` — slash skill 激活解析
- DeerFlow 源码: `deerflow/agents/middlewares/skill_activation_middleware.py:118, 318-355` — 激活三层判据（已收窄，不再改工具集）
- DeerFlow 源码: `deerflow/authz/tool_filter.py:25-33`、`deerflow/authz/provider.py:86`、`deerflow/authz/adapter.py:27` — 工具权限上限的两个所有者（Layer 1 / Layer 2）
- DeerFlow 源码: `deerflow/agents/middlewares/deferred_tool_filter_middleware.py` — deferred schema 的 filter 生命周期
- DeerFlow 源码: `deerflow/tools/builtins/update_agent_tool.py:78-82` — agent 自修改 skills
- DeerFlow 源码: `app/channels/manager.py:2276-2300, 3730-3735` — `_resolve_available_skill_names()` 与 `/bootstrap`
