# 补充：Agent Workflow 编排 — Main Agent 启动 Sub-agent 的机制

> **问题：** DeerFlow 整个流程是用 Python 控制的，Agent Loop 是 LangGraph 图里的一个节点。这个节点能编排吗？我想做一个 agent workflow——main agent 启动多个 sub-agent 并行干活。这个机制怎么用 Python 搞起来？

---

## 直接回答

**可以。** Main agent 通过 `task()` 工具把任务分发给 sub-agent，LLM 自己决定派什么活、派给谁。一个 turn 内最多 3-4 个 sub-agent 并行。但编排是**意图驱动**而非**代码驱动**——你告诉 agent "做什么"，它自己决定"怎么分派"。

---

## 一、Agent Graph 到底是什么

LangChain 的 `create_agent()` 构建了一个标准的 **ReAct 循环图**：

```
START → agent_model → [routing: 有 tool_calls?] → tools_node → agent_model → ... → END
```

源码：`deerflow/agents/lead_agent/agent.py:482-493`

```python
return create_agent(
    model=create_chat_model(name=model_name, ...),
    tools=filter_tools_by_skill_allowed_tools(tools + extra_tools, ...),
    middleware=_build_middlewares(config, ...),
    system_prompt=apply_prompt_template(...),
    state_schema=ThreadState,
)
```

图只有两个节点：`agent_model`（LLM 调用）和 `tools_node`（工具执行）。中间件的 6 个 hook（`before_model`、`after_model`、`before_tool`、`after_tool` 等）包裹在每个节点外面。

**不能直接在图里加自定义节点**——`create_agent()` 返回的 `CompiledStateGraph` 是黑盒。扩展点就是中间件。

---

## 二、Sub-agent 是怎么启动的

### task() 工具

源码：`deerflow/tools/builtins/task_tool.py:186`

```python
@tool("task", parse_docstring=True)
async def task_tool(
    runtime: Runtime,
    description: str,      # 3-5 词简短描述
    prompt: str,           # 给 sub-agent 的完整任务描述
    subagent_type: str,    # "general-purpose" | "bash" | 自定义名
) -> str:
```

**执行流程：**

```
Main Agent 的 LLM 决定调用 task()
    │
    ├─ 1. get_subagent_config(subagent_type) — 查注册表
    ├─ 2. 从 runtime 提取父 context（sandbox, thread_data, model, tool_groups）
    ├─ 3. 过滤工具（sub-agent 永远拿不到 task 工具——禁止递归嵌套）
    ├─ 4. SubagentExecutor.execute_async(prompt) — 后台线程启动
    ├─ 5. 循环 poll（5s 间隔）直到终态
    │     → SSE events: task_started → task_running → task_completed/failed/timed_out
    └─ 6. 返回结果字符串给 Main Agent
```

### SubagentExecutor

源码：`deerflow/subagents/executor.py:269`

- 为每个 sub-agent 创建**独立的 agent graph**（自己的 model、tools、middleware、system_prompt）
- 双线程池：`_scheduler_pool`（3 workers）+ 持久隔离 event loop
- `execute(prompt)` — 同步阻塞
- `execute_async(prompt)` — 后台执行，返回 task_id

### 并行执行机制

LLM 在一个 turn 内可以发出**多个 tool_calls**。LangChain 的 `create_agent()` 天然支持并行工具调用。`SubagentLimitMiddleware`（`deerflow/agents/middlewares/subagent_limit_middleware.py`）把 `task` 调用数量截断到上限（默认 3，范围 [2,4]）。

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

`RuntimeFeatures` 是一个声明式配置对象——你选 `sandbox=True`，框架自动装配对应的中间件链（14 个）。不能同时用 `middleware`（完全接管）和 `features`。

### 层次 3：自定义 Sub-agent 类型

在 `config.yaml` 中定义专用 sub-agent：

```yaml
subagents:
  enabled: true
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

源码依据：
- `CustomSubagentConfig`：`deerflow/config/subagents_config.py:34-68`
- 内置 sub-agent：`general-purpose`（全部工具除 task）、`bash`（仅 sandbox 工具）
- Sub-agent 自动禁止嵌套 task：`disallowed_tools` 默认 `["task", "ask_clarification", "present_files"]`

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
| make_lead_agent 图构建 | `deerflow/agents/lead_agent/agent.py:482-493` |
| create_deerflow_agent 工厂 | `deerflow/agents/factory.py:61` |
| RuntimeFeatures 声明式配置 | `deerflow/agents/features.py` |
| task() 工具 | `deerflow/tools/builtins/task_tool.py:186` |
| SubagentExecutor | `deerflow/subagents/executor.py:269` |
| SubagentLimitMiddleware | `deerflow/agents/middlewares/subagent_limit_middleware.py` |
| CustomSubagentConfig | `deerflow/config/subagents_config.py:34-68` |
| SubagentConfig | `deerflow/subagents/config.py` |
| 编排指令（系统 prompt） | `deerflow/agents/lead_agent/prompt.py:363` |
| DeerFlowClient | `deerflow/client.py:82` |
