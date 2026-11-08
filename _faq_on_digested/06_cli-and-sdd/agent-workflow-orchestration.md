# 补充：Agent Workflow 编排 — Main Agent 启动 Sub-agent 的机制

> **问题：** DeerFlow 整个流程是用 Python 控制的，Agent Loop 是 LangGraph 图里的一个节点。这个节点能编排吗？我想做一个 agent workflow——main agent 启动多个 sub-agent 并行干活。这个机制怎么用 Python 搞起来？

---

## 直接回答

**可以。** Main agent 通过 `task()` 工具把任务分发给 sub-agent，LLM 自己决定派什么活、派给谁。一个 turn 内默认最多 **3** 个 sub-agent 并行（`MAX_CONCURRENT_SUBAGENTS = 3`，`deerflow/subagents/executor.py:2337`），而一次 lead-agent run 的委派总数默认上限是 **6**（`max_total_per_run`）。但编排是**意图驱动**而非**代码驱动**——你告诉 agent "做什么"，它自己决定"怎么分派"。

---

## 一、Agent Graph 到底是什么

LangChain 的 `create_agent()` 构建了一个标准的 **ReAct 循环图**：

```
START → agent_model → [routing: 有 tool_calls?] → tools_node → agent_model → ... → END
```

源码：`deerflow/agents/lead_agent/agent.py:834`（`make_lead_agent()`）→ `:839`（`assemble_lead_agent()`）→ `:1248` 起（`normalize_middleware_state_schemas()` + `create_agent()` 调用）

```python
bound_middlewares = normalize_middleware_state_schemas(middlewares, mode)
verify_declared_tool_view(bound_middlewares, authorized_names=declared_authorized)
graph = create_agent(
    model=chat_model,
    tools=final_tools,
    middleware=bound_middlewares,
    system_prompt=system_prompt,
    state_schema=get_thread_state_schema(mode),
    context_schema=dict,
)
```

> 🔄 同步 #8（v2.2.0）：原引用 `agent.py:796-801` 已漂移；更关键的是**原文那把 `tools=filter_tools_by_skill_allowed_tools(...)` 的写法已删除**（上游 #6935，commit `0d73798be`）。v2.2.0 里工具表在到达 `create_agent()` 之前就由授权层定好（`final_tools`），并多了一道 `verify_declared_tool_view()` 断言；skill 的 `allowed-tools` 只是兼容元数据，**不再参与工具过滤**。曾经的 `skills/tool_policy.py`（已删除）、`agents/middlewares/skill_tool_policy_middleware.py`（已删除）、`SkillToolPolicyMiddleware` 全部不在了。详见 `_digested/concepts/skills-tools/skill-md-and-tool-assembly.md`。

图只有两个节点：`agent_model`（LLM 调用）和 `tools_node`（工具执行）。中间件的 6 个 hook（`before_model`、`after_model`、`before_tool`、`after_tool` 等）包裹在每个节点外面。

**不能直接在图里加自定义节点**——`create_agent()` 返回的 `CompiledStateGraph` 是黑盒。扩展点就是中间件。

---

## 二、Sub-agent 是怎么启动的

### task() 工具

源码：`deerflow/tools/builtins/task_tool.py:753`（`task_tool()`，装饰器 `@tool("task", parse_docstring=True)` 在 `:752`）

```python
@tool("task", parse_docstring=True)
async def task_tool(
    runtime: Runtime,
    prompt: str,                              # 给 sub-agent 的完整任务描述
    subagent_type: str,                       # "general-purpose" | "bash" | 自定义名
    tool_call_id: Annotated[str, InjectedToolCallId],
    *,
    acceptance_criteria: list[str] | None = None,
    description: str = "",                    # 3-5 词简短描述
    context_mode: Literal["isolated", "snapshot"] = "isolated",
    model_name: str | None = None,
) -> str | Command:
```

> 🔄 同步 #8（v2.2.0）：原引用 `task_tool.py:651` 已漂移；签名也变了——`description` 现在是**仅关键字**参数且默认为 `""`，`prompt` 提到了第一位，新增 `acceptance_criteria`、`context_mode`（`isolated` | `snapshot`）、`model_name` 三个可选参数。`tool_call_id` 是平铺的必需参数（`InjectedToolCallId`）。

**执行流程：**

```
Main Agent 的 LLM 决定调用 task()
    │
    ├─ 1. get_subagent_config(subagent_type) — 查注册表（deerflow/subagents/registry.py:106）
    ├─ 2. 从 runtime 提取父 context（sandbox, thread_data, model, tool_groups）
    ├─ 3. 过滤工具（sub-agent 永远拿不到 task 工具——禁止递归嵌套）
    ├─ 4. SubagentExecutor.execute_async(prompt) — 后台线程启动
    ├─ 5. 循环 poll（5s 间隔）直到终态
    │     → SSE events: task_started → task_running → task_completed/failed/timed_out
    └─ 6. 返回结果字符串给 Main Agent
```

### SubagentExecutor

源码：`deerflow/subagents/executor.py:890`（`class SubagentExecutor`）

- 为每个 sub-agent 创建**独立的 agent graph**（自己的 model、tools、middleware、system_prompt）
- 双线程池：`_scheduler_pool`（3 workers）+ 持久隔离 event loop
- `execute(prompt)`（`executor.py:2178`）— 同步阻塞
- `execute_async(prompt)`（`executor.py:2208`）— 后台执行，返回 task_id

> 🔄 同步 #8（v2.2.0）：原引用 `executor.py:771` 已漂移（类定义实际在 `:890`）。另外 v2.2.0 新增了**进程级执行容量** `subagent_runtime`（`config.example.yaml:1994` 起：`max_running: 3` / `max_queued: 64` / `admission_policy: queue|reject` / `queue_timeout_seconds: 300`）——普通 `task` 调用与 durable batch 共享这套槽位，排队是异步的，不会占用调度线程。该段属于重启生效字段（`deerflow/config/reload_boundary.py:45` 的 `STARTUP_ONLY_FIELDS` 含 `subagent_runtime`）。

### 并行执行机制

LLM 在一个 turn 内可以发出**多个 tool_calls**。LangChain 的 `create_agent()` 天然支持并行工具调用。`SubagentLimitMiddleware`（`deerflow/agents/middlewares/subagent_limit_middleware.py:95`）把 `task` 调用数量截断到上限。

> 🔄 同步 #8（v2.2.0）：上限口径变了。原文写「默认 3，范围 [2,4]」——**已过时**。现在并发默认 3（`MAX_CONCURRENT_SUBAGENTS`，`executor.py:2337`），合法范围是 **[1, 64]**（`MIN_CONCURRENT_SUBAGENT_CALLS = 1` / `MAX_CONCURRENT_SUBAGENT_CALLS = 64`，`deerflow/config/subagents_config.py:16-17`），超出按 `clamp_subagent_concurrency()`（`subagents_config.py:20`）夹取，并且还会被进程级 `subagent_runtime.max_running` 进一步压住。另外多了一个**每次 run 的委派总数上限** `subagents.max_total_per_run`，默认 **6**（`subagents_config.py:13` 的 `DEFAULT_MAX_TOTAL_SUBAGENTS_PER_RUN = 6`，合法范围 1-50）——它不是并发限制，而是防止模型在规划检查点后无限重发合法大小的批次。上限触发后中间件返回 `[SUBAGENT LIMIT REACHED]` 提示，让模型用已有结果收尾（`subagent_limit_middleware.py:29` 的 `_TOTAL_LIMIT_STOP_MSG`）。

LLM 这样发：
```json
[
  {"name": "task", "args": {"description": "研究NVIDIA", "prompt": "...", "subagent_type": "general-purpose"}},
  {"name": "task", "args": {"description": "研究AMD",    "prompt": "...", "subagent_type": "general-purpose"}},
  {"name": "task", "args": {"description": "研究Intel",  "prompt": "...", "subagent_type": "general-purpose"}}
]
```
→ 三个 sub-agent 并行跑，Main Agent 等全部返回后汇总。

---

## 三、Python 代码：两种编排层次

### 层次 1：DeerFlowClient（最简单）

你在 Python 脚本里打开 sub-agent 开关、描述任务，LLM 自己决定怎么分派：

```python
from deerflow.client import DeerFlowClient

client = DeerFlowClient(
    subagent_enabled=True,   # ← 开启 sub-agent
    plan_mode=True,          # ← 可选：让 agent 先用 write_todos 规划
)

# 你描述"做什么"，agent 自己决定"怎么分派"
result = client.chat(
    "我需要三份独立的研究报告：\n"
    "1) NVIDIA — 财务表现和 AI 芯片市场份额\n"
    "2) AMD — 竞争定位和近期产品发布\n"
    "3) Intel — 转型策略和代工业务\n"
    "每份报告独立研究后，做一个对比总结。",
    thread_id="research-session"
)

print(result)
```

系统 prompt（`deerflow/agents/lead_agent/prompt.py`）已经包含了详细的编排指令——告诉 LLM 如何拆解任务、分批派发、汇总结果。

### 层次 2：create_deerflow_agent()（更多控制）

绕过 `DeerFlowClient`，直接控制图的构造参数：

```python
from deerflow.agents.factory import create_deerflow_agent
from deerflow.agents.features import RuntimeFeatures
from deerflow.models import create_chat_model
from langchain_core.messages import HumanMessage

model = create_chat_model(name="deepseek-v3")

agent = create_deerflow_agent(
    model=model,
    features=RuntimeFeatures(
        sandbox=True,      # 自动注入 SandboxMiddleware
        subagent=True,     # 自动注入 task 工具 + SubagentLimitMiddleware
        memory=True,       # 自动注入 MemoryMiddleware
    ),
    system_prompt=(
        "你是一个研究编排器。面对多公司的复杂分析任务时，"
        "将任务拆解为独立研究子任务，委托给 general-purpose sub-agent 并行执行。"
    ),
)

state = {"messages": [HumanMessage(content="分析 NVIDIA、AMD、Intel 三家公司")]}
result = agent.invoke(state, config={"configurable": {"thread_id": "research-1"}})
```

`RuntimeFeatures` 是一个声明式配置对象（`deerflow/agents/features.py:18`）——你选 `sandbox=True`，框架自动装配对应的中间件链。不能同时用 `middleware`（完全接管）和 `features`（`create_deerflow_agent()` 的 docstring 明确写了 "Cannot be combined"）；`extra_middleware` 也只在 `features` 模式下可用，靠 `@Next`/`@Prev` 定位插入点。

> 🔄 同步 #8（v2.2.0）：原文写「框架自动装配对应的中间件链（14 个）」——**这个数字已不再成立**，v2.2.0 的 lead 链是 39 个条目位分两阶段组装（`_build_runtime_middlewares()` 前 16 条 + `build_middlewares()` 追加 23 条，`lead_agent/agent.py:485`），具体装几条取决于你开了哪些 feature。以后别再引用固定条数，以 `_digested/internals/middleware/03-catalog.md` 为准。另外 `RuntimeFeatures` 现在有 12 个开关：`sandbox` / `memory`（含 `memory_config`）/ `summarization` / `subagent` / `vision` / `auto_title` / `guardrail` / `loop_detection` / `token_budget`，默认值分别是 `sandbox=True`、`loop_detection=True`，其余 `False`。`create_deerflow_agent()` 还新增了 `subagent_runtime` 与 `pii_redaction_config` 两个关键字参数（`deerflow/agents/factory.py:67`）：直接 SDK 建图时若要与 lead agent 共享原生 subagent 容量，必须显式传 `subagent_runtime`。

### 层次 3：自定义 Sub-agent 类型

在 `config.yaml` 中定义专用 sub-agent：

```yaml
# config.yaml（注意：config.example.yaml 里 subagents: 整段是注释状态，先取消注释）
subagents:
  custom_agents:
    financial-analyst:
      description: "财务分析专家：分析财报、利润率、现金流"
      system_prompt: |
        你是财务分析专家。分析公司财报时关注：收入增长、利润率趋势、
        现金流健康度、研发投入占比、负债水平。
      tools: [bash, read_file, write_file, web_search]
      skills: [financial-analysis]
      model: deepseek-v3
      max_turns: 120
      timeout_seconds: 1800

    code-reviewer:
      description: "代码审查专家：检查代码质量、安全漏洞、性能问题"
      system_prompt: |
        你是资深代码审查专家。按以下维度审查：正确性、安全性、性能、可维护性。
      tools: [read_file, write_file, bash, ls, glob, grep]
      skills: [code-review]

    test-writer:
      description: "测试工程师：为指定模块生成 pytest 单元测试"
      system_prompt: |
        你是测试工程师。生成覆盖正常路径、边界条件、异常情况的 pytest 测试。
      tools: [read_file, write_file, bash, ls]
```

然后 Main Agent 在对话中就可以：
```
task("code-reviewer", "审查 sandbox/tools.py 中的安全问题")
task("financial-analyst", "分析 NVIDIA 最新财报的利润率趋势")
task("test-writer", "为 models/factory.py 生成单元测试")
```

> 🔄 同步 #8（v2.2.0）：两个改动。(1) `subagents.enabled` 这个总开关**已删除**——v2.2.0 的 `config.example.yaml` 里 `subagents:` 只有 `timeout_seconds` / `max_turns` / `max_total_per_run` / `token_budget` / `agents` / `custom_agents`（`config.example.yaml:1994-2068`），是否给 lead agent 装 subagent 能力仍由请求侧 `subagent_enabled` 决定（`DeerFlowClient(subagent_enabled=True)`）。留着 `enabled: true` 不会报错，但它不起作用。(2) `tools:` 仍是**工具白名单**（`null` = 继承全部），`skills:` 是 skill 发现/激活白名单（`null` = 全部，`[]` = 一个都不给）——注意 `skills` 收窄的**不是**工具，而 `allowed-tools` 也不再收窄任何东西（见 `_digested/concepts/skills-tools/skill-md-and-tool-assembly.md`）。

源码依据：
- `CustomSubagentConfig`：`deerflow/config/subagents_config.py:124`（`class CustomSubagentConfig`）
- 内置 sub-agent：`general-purpose`（全部工具除 task）、`bash`（仅 sandbox 工具，且仅在允许 host bash 或用隔离 shell sandbox 时可用）
- Sub-agent 自动禁止嵌套 task：`SubagentConfig.disallowed_tools` 默认 `["task"]`（`deerflow/subagents/config.py:46`）

> 🔄 同步 #8（v2.2.0）：原引用 `subagents_config.py:102` 已漂移（类定义在 `:124`）。`disallowed_tools` 的默认值原文写的是 `["task", "ask_clarification", "present_files"]`——v2.2.0 源码里默认只有 `["task"]`（`subagents/config.py:46`）。另外 `config.yaml` 的 `subagents.custom_agents` 段还支持 `token_budget`、`model: inherit`、`max_turns`、`timeout_seconds`（默认 900；内置 subagent 走全局 `subagents.timeout_seconds`，默认 1800），见 `config.example.yaml:1988-2068`。注意 `subagents:` **整段在 example 里是注释掉的**，要用得先取消注释。

---

## 四、编排的本质：LLM 驱动 vs 确定性编排

DeerFlow 的编排是 **LLM 驱动的**——agent 自己决定：
- 要不要分派
- 派给谁（哪个 subagent_type）
- 派什么活（prompt 怎么写）
- 什么时候汇总

这适合**探索性任务**（"帮我研究这三家公司"），但不适合**确定性工作流**（"先做 A，再做 B，最后用 C 检查"）。

### 如果你需要确定性编排

DeerFlow 目前没有内置的工作流引擎。但你可以：

**方案 1：多 turn 手动编排**

```python
client = DeerFlowClient(subagent_enabled=True, checkpointer=MemorySaver())

# Turn 1: 让 agent 审查代码
client.chat("审查 sandbox/tools.py", thread_id="workflow-1")

# Turn 2: 基于审查结果，让 agent 修复
client.chat("根据上一轮的审查结果，修复发现的安全问题", thread_id="workflow-1")

# Turn 3: 让 agent 生成测试
client.chat("为修复后的代码生成单元测试", thread_id="workflow-1")
```

**方案 2：自己用 LangGraph 构建 workflow**

```python
from langgraph.graph import StateGraph, END
from deerflow.subagents import SubagentExecutor, SubagentConfig

# 构建你自己的 StateGraph
# 节点 A: 代码审查 sub-agent
# 节点 B: 修复 sub-agent
# 节点 C: 测试 sub-agent
# 条件边: A → B → C → END

# 每个节点里直接调用 SubagentExecutor.execute(prompt)
```

`SubagentExecutor` 是公开 API（`deerflow/subagents/__init__.py`），可以直接在你的 LangGraph 节点中实例化和调用。这是最灵活的方式——你完全控制执行顺序、条件分支、错误处理。

---

## 五、启动实验的最短路径

如果你想现在就感觉一下 Main Agent 启动 Sub-agent：

```bash
cd backend && PYTHONPATH=. uv run python
```

```python
from deerflow.client import DeerFlowClient

# 1. 开启 sub-agent
client = DeerFlowClient(subagent_enabled=True, plan_mode=True)

# 2. 给一个明显需要并行研究的任务
client.chat(
    "帮我研究三个东西，每个出 200 字总结：\n"
    "1) LangGraph 是什么\n"
    "2) MCP 协议是什么\n"
    "3) SKILL.md 标准是什么",
    thread_id="experiment-1"
)
```

观察 agent 的行为——它应该会自动分派 3 个 `general-purpose` sub-agent。如果你打开 Web UI（`localhost:2026`）同时看，能看到 sub-agent 的 `task_started`/`task_completed` 事件。

---

## 关键源码索引

| 机制 | 位置 |
|------|------|
| make_lead_agent 图构建 | `deerflow/agents/lead_agent/agent.py:834`（`make_lead_agent`）、`:839`（`assemble_lead_agent`）、`:1250`（`create_agent()` 调用） |
| build_middlewares | `deerflow/agents/lead_agent/agent.py:485` |
| create_deerflow_agent 工厂 | `deerflow/agents/factory.py:67`（`create_deerflow_agent`） |
| RuntimeFeatures 声明式配置 | `deerflow/agents/features.py:18` |
| task() 工具 | `deerflow/tools/builtins/task_tool.py:753`（装饰器 `:752`） |
| SubagentExecutor | `deerflow/subagents/executor.py:890`；并发常量 `MAX_CONCURRENT_SUBAGENTS = 3` 在 `:2337` |
| SubagentLimitMiddleware | `deerflow/agents/middlewares/subagent_limit_middleware.py:95` |
| CustomSubagentConfig | `deerflow/config/subagents_config.py:124`（`class CustomSubagentConfig`） |
| SubagentConfig | `deerflow/subagents/config.py`（`disallowed_tools` 默认值在 `:46`） |
| subagent 注册表 | `deerflow/subagents/registry.py:106`（`get_subagent_config`） |
| 编排指令（系统 prompt） | `deerflow/agents/lead_agent/prompt.py:451`（`_build_subagent_section`，调用点 `:1191`） |
| DeerFlowClient | `deerflow/client.py:177`（`class DeerFlowClient`） |

> 🔄 同步 #8（v2.2.0）：全表行号按 v2.2.0 源码重核。原文 `agent.py:796-801`、`factory.py:66`、`task_tool.py:651`、`executor.py:771`、`subagents_config.py:102`、`prompt.py:342`、`client.py:145` 均已漂移。
