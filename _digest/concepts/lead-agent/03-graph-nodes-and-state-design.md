---
title: "LangGraph Node 与 State 设计指南"
description: "设计 Agent 时的核心决策：两个固定 node、middleware 即 node、ThreadState 扩展、sub-agent 独立图。"
topics: [langgraph, agent-design, state-management, nodes]
---

# LangGraph Node 与 State 设计指南

设计 DeerFlow Agent 的核心问题是：**图里有哪些 node、state 怎么流、在哪插入自己的逻辑**。

## 图的本质

DeerFlow 的图就是 LangGraph 的图——`create_agent()` 构建，DeerFlow 只管往里填参数（model、tools、middleware、system_prompt、state_schema）。

```python
# agent.py:482 — DeerFlow 的角色是参数装配
return create_agent(
    model=create_chat_model(name=model_name),
    tools=filter_tools_by_skill_allowed_tools(tools),
    middleware=_build_middlewares(config),
    system_prompt=apply_prompt_template(),
    state_schema=ThreadState,
)
```

## 两个固定 Node

图里永远只有两个核心 node，你不能删除它们：

| Node | 做什么 | 怎么影响它 |
|------|--------|-----------|
| `"model"` | 调 LLM → 返回 `AIMessage`（含 text 或 tool_calls） | `wrap_model_call` hook 拦截/修改请求 |
| `"tools"` | `ToolNode` 执行 tool_calls → 返回 `ToolMessage` | `wrap_tool_call` hook 拦截/修改执行 |

## Middleware 就是 Node

**这不是比喻——middleware 的 hook 方法在编译时变成真正的 LangGraph node。**

| Hook | 编译成的 Node | 执行时机 |
|------|-------------|---------|
| `before_agent()` | `"{name}.before_agent"` | 图启动时，只跑一次 |
| `before_model()` | `"{name}.before_model"` | 每次 LLM 调用前 |
| `after_model()` | `"{name}.after_model"` | 每次 LLM 调用后 |
| `after_agent()` | `"{name}.after_agent"` | 图结束时，只跑一次 |

**不在图里的 hook：** `wrap_model_call` 和 `wrap_tool_call`——它们在 `"model"` 和 `"tools"` node 内部运行，不是独立 node。

关键推论：**后加的 middleware 在 after_model 中先执行**（LangChain 反向注册）。这就是为什么 `ClarificationMiddleware` 必须在列表最后——它需要在所有其他 middleware 之前拦截 `ask_clarification`。

## 选哪种 Hook

| 你想做的事 | 用哪个 Hook | 原因 |
|-----------|-----------|------|
| 每次 LLM 调前注入上下文 | `before_model` | 独立 node，可以修改 state |
| 每次 LLM 调后检查输出 | `after_model` | 独立 node，可以触发 jump_to |
| 拦截/重试 LLM 调用 | `wrap_model_call` | 在 model node 内部，外层包裹内层 |
| 拦截/修改 tool 执行 | `wrap_tool_call` | 在 ToolNode 内部 |
| 图启动时初始化 | `before_agent` | 只跑一次 |
| 图结束时清理 | `after_agent` | 只跑一次 |

## State 设计

`ThreadState` 继承 LangChain 的 `AgentState`（提供 `messages` 和 `jump_to`）。新增 12 个 DeerFlow 字段。

### 扩展自己的 State

```python
from typing import NotRequired, Annotated
from deerflow.agents.thread_state import ThreadState

class MyAgentState(ThreadState):
    review_count: NotRequired[int]           # 简单 LastValue
    approved_prs: Annotated[list[str], merge_approved]  # 自定义 reducer
```

传给 `create_deerflow_agent(state_schema=MyAgentState)`。

### Reducer 选择

| 场景 | Reducer |
|------|---------|
| 简单覆盖（标题、状态） | `NotRequired[T]`（默认 LastValue） |
| 追加去重（artifacts、日志） | 自定义 `merge_*` 函数 |
| 追加不去重（消息） | `add_messages` |
| 追加但有上限（delegation） | `merge_delegations`（FIFO + 终态保护） |

### State 流动规则

1. 每个 node 接收完整 `state`，返回 `dict[str, Any]`（只含要更新的 key）
2. LangGraph 按 key 的 reducer 合并
3. `messages` 永远用 `add_messages`（追加）
4. 两个 node 在同一 superstep 写到同一个 key → reducer 被调用

## Sub-agent 的图

Sub-agent 有**完全独立的图**。不嵌套在父图中。

```python
# executor.py — 每次调用 create_agent() 全新构建
agent = create_agent(
    model=subagent_model,
    tools=filtered_tools,
    middleware=build_subagent_runtime_middlewares(),  # 精简版链
    state_schema=ThreadState,
    checkpointer=False,  # 一次性，不恢复
)
```

Sub-agent：独立 middleware 链（只有共享基础层，无 Title/Memory/Summarization）、独立 state、独立 trace。

## jump_to：路由逃生口

任何 middleware 可以设 `state["jump_to"] = JumpTo("end")` 提前终止循环。这是 `ClarificationMiddleware` 的工作方式——agent 调了 `ask_clarification` → middleware 设 jump_to → 图停在当前 turn。

```python
from langgraph.types import Command
return Command(goto=END)  # 立即结束当前 turn
```

## 实战：设计一个代码审查 Agent

1. **不改图结构** → 两个核心 node 足够
2. **不改 state** → `ThreadState` 已包含 sandbox、delegations、artifacts
3. **加 middleware？** 不需要——SOUL.md 定义行为，29 个内置 middleware 覆盖安全/日志/memory
4. **用 sub-agent？** 可选——测试执行委派给 `test-runner` sub-agent
5. **自定义点** → SOUL.md 控制 LLM 行为，`config.yaml` 控制工具集和模型

结论：**大多数情况下你不需要设计 node 或 state**。DeerFlow 的 29 个 middleware 已经覆盖了安全、日志、内存、循环检测。你只需要写 SOUL.md + 配 config.yaml + 可选 sub-agent。

## 关键源码

| 内容 | 文件 |
|------|------|
| create_agent 图构建 | `langchain/agents/factory.py` |
| Middleware → Node 编译 | 同上，`_add_middleware_edges()` |
| ThreadState | `deerflow/agents/thread_state.py` |
| create_deerflow_agent | `deerflow/agents/factory.py` |
| make_lead_agent | `deerflow/agents/lead_agent/agent.py` |
| Sub-agent 图 | `deerflow/subagents/executor.py` |
