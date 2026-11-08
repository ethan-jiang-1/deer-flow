# Q7: Agent 图的两个固定 Node——model 和 tools

## 铁律：只有两个 Node，两类 Node，没有第三个

**斩钉截铁地说：整个 agent 循环只有两个固定 node。只有两类。没有任何其他 node。**

这两个 node 是：

| Node | 类型 | 做什么 |
|------|------|--------|
| `"model"` | **思考**节点 | 调 LLM，读消息历史，决定下一步干什么 |
| `"tools"` | **行动**节点 | 执行真实世界的操作（shell、文件、API……） |

**middleware 变出来的那些 node（before_model、after_model……）不是第三种——它们是这两类的"前厅"和"后厅"，挂在思考节点的前后。**

**🔄 同步 #8（v2.2.0）先给结论**：两个固定 node 的结构没变，但「middleware 怎么影响它们」在过去一段时间挪过两次位置，本版把这两处一并核到了 venv：

1. **`Command(goto)` 在 `wrap_model_call` 里被封死**，官方给的是 `jump_to` 状态字段（`before_model`/`after_model` 钩子返回 `{"jump_to": ...}`）。详见 §3.3。
2. **ClarificationMiddleware 早就不走 `jump_to` 了**——`ask_clarification` 是工具，短路发生在 `wrap_tool_call` 返回 `Command(goto=END)`。旧版把「场景 C」写成 `after_model` + `jump_to="end"`，**那是 v2.1.0 之前的形状，已失效**。详见 §4 场景 C。
3. **`jump_to` 在 DeerFlow 里并非没有消费者**——`TodoMiddleware.after_model` 会返回 `{"jump_to": "model"}` 把正要退出的 agent 拉回循环（`agents/middlewares/todo_middleware.py` L313-372）。旧版「只有 clarification 用 jump_to」的判断**已失效**。

下面我用三个层次把这事讲透：设计哲学 → 本质区别 → 源码追踪。

### 层一：设计哲学——为什么只有两个？

这不是 LangChain 拍脑袋决定的。所有 agent 的底层逻辑都可以归结为两件事：

> **思考 → 行动 → 思考 → 行动 → …… → 思考（回答用户）**

这就是 AI 领域著名的 **ReAct 模式**（Reasoning + Acting）。Agent 做的事情本质上就是：

1. **思考（model node）**：拿到所有上下文（用户说了什么、之前做了什么、结果是什么），调用 LLM 推理，输出一个决策——要么直接回答用户，要么"我需要做这些事"（tool_calls）
2. **行动（tools node）**：把模型的决策落到现实世界——执行 bash 命令、读写文件、调 API、查数据库……
3. 行动的结果回到上下文，然后**再思考**（回到 step 1）

循环终止条件：某次思考后，LLM 觉得"够了，我知道答案了"，不产 tool_calls，只产文本。循环结束。

**这就是为什么只需要两个 node。** 因为再复杂的 agent 行为——子 agent 调度、skill 切换、GitHub PR review、定时任务——本质上都是这个循环的反复执行。没有第三种基本操作。

### 层二：两个 Node 的本质区别——理解了就全通了

| 维度 | `"model"` node | `"tools"` node |
|------|---------------|---------------|
| **输入** | 完整 `state.messages`（所有历史） | 最后一条 AIMessage 的 `tool_calls` |
| **核心操作** | `model.invoke(messages)` → LLM API 调用 | `tool.invoke(args)` → 真实世界执行 |
| **输出** | `AIMessage`（文本 或 tool_calls 列表） | `ToolMessage`（执行结果） |
| **谁控制它** | LLM（模型的"意志"） | 模型的决定（模型说调什么就调什么） |
| **能否被 middleware 拦截** | ✅ `wrap_model_call` 洋葱链 | ✅ `wrap_tool_call` 洋葱链 |
| **执行方式** | 单次 LLM 调用 | **并行**执行所有 tool call |
| **输出写到哪** | `state.messages`（追加 AIMessage） | `state.messages`（追加 ToolMessage） |
| **错误会怎样** | LLM 可能返回垃圾/异常 | ToolErrorHandlingMiddleware 捕获→error ToolMessage |

**关键洞察：model node 负责"想"，tools node 负责"做"。想和做的分离是整个架构的基石。**

为什么必须分离？三个原因：
1. **LLM 不能直接做**——LLM 是个文本生成器，它不会执行 shell 命令、不会读文件、不会调 API。必须有个"执行层"把它的意图翻译成行动
2. **执行结果必须回灌给 LLM**——工具执行完后，结果（ToolMessage）追加到 messages，LLM 下一轮就能看到。这就是 agent 的"记忆"
3. **错误隔离**——工具执行失败不应该让 LLM 调用崩溃。ToolErrorHandlingMiddleware 保证了这一点："做"出错了，"想"还能继续，LLM 看到错误后可以换个方式重试

### 层三：middleware 的 node 不是新类型

middleware 的 `before_model`/`after_model` 会被编译成独立 LangGraph node（详见 [Q8](../08_middleware-as-nodes/answer.md)），但它们**不是第三种操作**。它们是：

- **`before_model`**：思考前的准备（注入上下文、检查限额、拼接 system message）
- **`after_model`**：思考后的检查（是否该反问用户、是否该写标题、是否该总结）
- **`before_agent`**：整个循环启动前的一次性初始化
- **`after_agent`**：整个循环结束后的一次性收尾

它们围绕"思考"节点，不创造新的基本操作类型。**agent 能做的事，本质上永远只有"想"和"做"。**

---

本文余下部分聚焦这两个 node 到底执行了什么 Python 代码、以及它们之间的路由逻辑。

## 核心源码位置

| 组件 | 文件 | 关键行 |
|------|------|--------|
| `create_agent()` 图构建 | `langchain/agents/factory.py` | 全文 2007 行（`def create_agent` 重载签名在 L740/762/786，实体 L808-1680） |
| `model_node` / `amodel_node` | 同上 | `model_node` L1433-1452、`amodel_node` L1481-1500；`_execute_model_sync` L1406-1431、`_execute_model_async` L1453-1479 |
| `_get_bound_model` | 同上 | L1272-1404 |
| `_handle_model_output` | 同上 | L1168-1270 |
| `_build_commands` | 同上 | L193-232（`NotImplementedError` 三连在 L213-227） |
| `ToolNode` 类 | `langgraph/prebuilt/tool_node.py` | 全文 2030 行（class L622，`__init__` L743） |
| `model_to_tools` 条件边 | `factory.py` | `_make_model_to_tools_edge` L1840-1892（`Send` 在 L1881） |
| `tools_to_model` 条件边 | `factory.py` | `_make_tools_to_model_edge` L1921-1954 |
| `jump_edge`（middleware 节点出边） | `factory.py` | `_add_middleware_edge` L1957-2002 |
| DeerFlow 调用入口 | `deerflow/agents/lead_agent/agent.py` | `create_agent(` L1250-1257（`_make_lead_agent` 在 L880 只是薄包装，真正的装配在 `_assemble_lead_agent`） |

> 🔄 同步 #8（v2.2.0）：**整张表按 `backend/.venv` 重新实测**——实装 `langchain` 1.3.14 / `langgraph` 1.2.9 / `langgraph-prebuilt` 1.1.0。旧版记的 1.2.15 / 1.0.11 是 v2.1.0 时代的实装，本次行号全部漂移（`model_node` 1296→1433、`model_to_tools` 1701→1840、`Send` 1732-1743→1881）。为什么能漂这么多：`langchain>=1.3` 没有上界（`backend/packages/harness/pyproject.toml`），LangChain 小版本升级就会连带挪动这张表——参见 [_digested/graph-engineering/06-langgraph-capability-surface.md](../../_digested/graph-engineering/06-langgraph-capability-surface.md) §1 开头。

---

## 1. model node：LLM 调用的完整链路

### 1.1 注册到图上

`factory.py` L1502：

```python
graph.add_node("model", RunnableCallable(model_node, amodel_node, trace=False))
```

紧接着 L1506 才挂 tools，而且带条件——没有工具就没有 tools node：

```python
if tool_node is not None:
    graph.add_node("tools", tool_node)
```

`RunnableCallable` 是 LangGraph 的通用 node 包装器（定义在 `langgraph/_internal/_runnable.py`）。它存了两个函数——同步版 `model_node` 和异步版 `amodel_node`。当图执行到这个 node 时，LangGraph 从 `config` 中提取 `runtime` 对象，然后调用：

```
model_node(state, runtime=<Runtime object>)          # 同步
await amodel_node(state, runtime=<Runtime object>)    # 异步
```

### 1.2 `model_node` 函数体（L1433-1452）

```python
def model_node(state: AgentState[Any], runtime: Runtime[ContextT]) -> list[Command[Any]]:
```

它只做三件事：

**第一步：组装请求对象**（L1435-1450）

```python
request = ModelRequest(
    model=model,                # BaseChatModel 实例（已配置好 thinking/vision）
    tools=default_tools,        # 所有可用工具的列表
    system_message=system_message,  # SystemMessage 对象
    response_format=initial_response_format,
    messages=state["messages"], # ← 完整消息历史从这里来
    tool_choice=None,
    state=state,
    runtime=runtime,
)
```

关键点：`state["messages"]` 是完整的对话历史——LLM 每次调用都能看到从头到尾的所有 HumanMessage、AIMessage、ToolMessage。

**第二步：经过 middleware 洋葱链调用 LLM**（L1450-1452）

如果没有 `wrap_model_call` middleware：
```python
model_response = _execute_model_sync(request)
return _build_commands(model_response)
```

如果有（DeerFlow 总是有）：
```python
result = wrap_model_call_handler(request, _execute_model_sync)
return _build_commands(result.model_response, result.commands)
```

`wrap_model_call_handler` 是所有 `wrap_model_call` middleware 组成的洋葱链。最外层先执行，它可以：
- 修改 request 后调 `handler(request)`（正常流程）
- 调多次 `handler(request)`（重试）
- 不调 `handler` 直接返回（短路/缓存命中）

### 1.3 `_execute_model_sync`——真正调用 LLM 的地方（L1406-1431）

这是洋葱链最内层，middleware 的 `handler` 参数就指向它：

```python
def _execute_model_sync(request: ModelRequest[ContextT]) -> ModelResponse:
```

**子步骤 1：绑定工具到模型**（L1412）

```python
model_, effective_response_format = _get_bound_model(request)
```

`_get_bound_model`（L1272-1404）做了这些事：

1. 验证所有 tool 确实存在（L1281-1300 一带）
2. 自动选择结构化输出策略（L1302-1360 一带）：
   - `ProviderStrategy`：用 OpenAI 原生 `response_format` 参数（模型本身就支持 structured output）
   - `ToolStrategy`：注入一个特殊的 tool，让模型通过 tool call 输出结构化数据（fallback 方案）
3. 构建最终 tool 列表，调用 `model.bind_tools(final_tools, ...)`（L1362-1404）：
   - ProviderStrategy：`model.bind_tools(final_tools, strict=True, **model_settings)`
   - ToolStrategy：`model.bind_tools(final_tools, tool_choice="any", **model_settings)` —— 强制模型必须调 tool
   - 无 structured output 需求：`model.bind_tools(final_tools, tool_choice=request.tool_choice, **model_settings)`
   - 无任何 tool：`model.bind(**model_settings)`

**子步骤 2：拼上 system message，调用模型**（L1413-1422）

```python
messages = request.messages
if request.system_message:
    messages = [request.system_message, *messages]  # SystemMessage 放在最前面

output = model_.invoke(messages)  # ← 真正的 LLM API 调用
```

`output` 是一个 `AIMessage`，可能是：
- `.content = "你好！"`，`.tool_calls = []` —— 纯文本回复
- `.content = ""`，`.tool_calls = [{"name": "bash", "args": {...}, "id": "call_abc"}]` —— 要调工具

**子步骤 3：处理模型输出**（L1424-1426）

```python
handled_output = _handle_model_output(output, effective_response_format)
```

`_handle_model_output`（L1168-1270）三种分支：

| 情况 | 行为 |
|------|------|
| ProviderStrategy + 无 tool_calls | 解析结构化响应 → `{"messages": [output], "structured_response": parsed}` |
| ToolStrategy + 有 structured output tool call | 解析 tool call args → 合成 ToolMessage → `{"messages": [output, tool_msg], "structured_response": parsed}` |
| 默认（普通对话，不是 structured output） | `{"messages": [output]}` —— 原样返回 AIMessage |

**子步骤 4：返回 ModelResponse**（L1428-1431）

```python
return ModelResponse(
    result=messages_list,           # [AIMessage(...)]
    structured_response=...,        # 结构化输出解析结果，或 None
)
```

### 1.4 `_build_commands`——把 LLM 输出写成 LangGraph Command（L193-232）

> 🔄 同步 #8（v2.2.0）：这个函数是本版变化最大的一处。旧版只有「拼 state」两步；现行版本在追加 middleware 返回的 `Command` 之前，逐条检查 `goto` / `resume` / `graph`——任一非空直接 `NotImplementedError`。

```python
def _build_commands(model_response, middleware_commands=None) -> list[Command[Any]]:
    state = {"messages": model_response.result}
    if model_response.structured_response is not None:
        state["structured_response"] = model_response.structured_response

    # L213-227：wrap_model_call 层面封死三种 Command 语义
    for cmd in middleware_commands or []:
        if cmd.goto:
            msg = (
                "Command goto is not yet supported in wrap_model_call middleware. "
                "Use the jump_to state field with before_model/after_model hooks instead."
            )
            raise NotImplementedError(msg)
        if cmd.resume:
            msg = "Command resume is not yet supported in wrap_model_call middleware."
            raise NotImplementedError(msg)
        if cmd.graph:
            msg = "Command graph is not yet supported in wrap_model_call middleware."
            raise NotImplementedError(msg)

    commands: list[Command[Any]] = [Command(update=state)]
    commands.extend(middleware_commands or [])
    return commands
```

**这四行报错文案是本篇最重要的一处「能力边界」**：`wrap_tool_call` 里返回 `Command(goto=END)` 合法（工具层不受限，ClarificationMiddleware 就这么干），`wrap_model_call` 里返回同样的东西**直接炸**。上游连出路都写进提示了——用 `jump_to`。

返回类似：
```python
[Command(update={"messages": [AIMessage(content="你好！")]})]
```

LangGraph 拿到这个 `Command` 后，通过 **reducer** 把更新合入 graph state。对于 `messages` 字段，reducer 是 `add_messages`——它把新 AIMessage **追加**到现有列表末尾，不是覆盖。对于 `structured_response` 这种没有自定义 reducer 的字段，默认是 `last_value`（直接覆盖）。

### 1.5 异步路径：`amodel_node`（L1481-1500）

结构完全一样，唯一区别：
- `await model_.ainvoke(messages)` 代替 `.invoke()`
- `await awrap_model_call_handler(...)` 代替同步版
- `await _execute_model_async(request)` 代替同步版

### 1.6 DeerFlow 怎么调用 `create_agent`

`deerflow/agents/lead_agent/agent.py` L1250-1257（`_make_lead_agent` 在 L880 只是 `_assemble_lead_agent(...).graph` 的薄包装）：

```python
bound_middlewares = normalize_middleware_state_schemas(middlewares, mode)
verify_declared_tool_view(bound_middlewares, authorized_names=declared_authorized)
graph = create_agent(
    model=chat_model,
    tools=final_tools,                # sandbox + MCP + builtins + community + subagent tools
    middleware=bound_middlewares,
    system_prompt=system_prompt,              # 动态 prompt 模板
    state_schema=get_thread_state_schema(mode),   # DeerFlow 自定义 state（按 mode 选择 schema）
    context_schema=dict,
)
```

> 🔄 同步 #8（v2.2.0）：与旧版三处差异——(1) `create_agent` 前多了 `verify_declared_tool_view(...)`，把「声明的工具视图」与「实际 authorized 工具」对账（2.2.0 新增的装配期守卫）；(2) 显式传 `context_schema=dict`；(3) middleware 由 `deerflow.agents.thread_state.normalize_middleware_state_schemas` 统一归一化后再交给 factory，所以 factory 侧看到的 state schema 已经是**全栈合并后**的那一份。middleware 清单与顺序见 [_digested/internals/middleware/03-catalog.md](../../_digested/internals/middleware/03-catalog.md)。

---

## 2. tools node：ToolNode 的并行执行机制

### 2.1 ToolNode 本质

`tool_node.py` L622：

```python
class ToolNode(RunnableCallable):
    def __init__(self, tools, *, name="tools", ...):
        super().__init__(self._func, self._afunc, name=name, tags=tags, trace=False)
```

ToolNode 也是 `RunnableCallable`——和 model node 同一种包装器。初始化时（L743 起）：

1. 把 dict 格式的 tool 包装成 `BaseTool`
2. 按 tool name 建索引 `self._tools_by_name: dict[str, BaseTool]`
3. 预计算每个 tool 的注入参数（`InjectedState`、`InjectedStore`、`ToolRuntime`）

### 2.2 同步并行执行：`_func`（L793-824）

```python
def _func(self, input, config, runtime):
    tool_calls, input_type = self._parse_input(input)  # 解析所有待执行的 tool call
    ...
    with get_executor_for_config(config) as executor:
        outputs = list(executor.map(self._run_one, tool_calls, input_types, tool_runtimes))
    return self._combine_tool_outputs(outputs, input_type)
```

**`executor.map()` 用的是 `ThreadPoolExecutor`——所有 tool call 并行执行。**

### 2.3 异步并行执行：`_afunc`（L826-858）

```python
async def _afunc(self, input, config, runtime):
    ...
    outputs = await asyncio.gather(*coros)  # 所有 tool call 并行
    return self._combine_tool_outputs(outputs, input_type)
```

同样并行，用的是 `asyncio.gather`。

### 2.4 单个 tool 从收到消息到执行完成

`_run_one`（L1014 起）先查 `wrap_tool_call` 是否存在。DeerFlow 的 `ToolErrorHandlingMiddleware` 提供了它，所以实际路径是：

```
_run_one
  → _wrap_tool_call(tool_request, execute)       # middleware 洋葱链
      → _execute_tool_sync(tool_request, ...)     # 最内层，真正执行
```

`_execute_tool_sync`（L922-1012）的核心：

```python
# 注入 state/store/runtime 到 tool 参数（InjectedState 等自动填充）
injected_call = self._inject_tool_args(call, request.runtime, tool)
call_args = {**injected_call, "type": "tool_call"}

# 真正调用工具
response = tool.invoke(call_args, config)   # ← 实际执行

# 标准化返回值 → ToolMessage
return self._normalize_tool_response(response, request.tool_call, input_type)
```

### 2.5 错误处理链——DeerFlow 的关键差异

| 异常类型 | 默认 LangChain 行为 | DeerFlow 行为（ToolErrorHandlingMiddleware） |
|----------|---------------------|---------------------------------------------|
| `ValidationError` | 转为 `ToolInvocationError` → 返回 error ToolMessage | 同 |
| `GraphBubbleUp`（来自 `interrupt()`） | 永远 re-raise（不吞） | 同 |
| **其他所有异常** | **re-raise → run 崩溃** | **捕获 → 返回 error ToolMessage** |

这就是 `ToolErrorHandlingMiddleware` 的价值——工具执行出错不会崩，模型会看到 error ToolMessage 然后自行修正。

### 2.6 输入解析：`_parse_input`（L1224-1290）

ToolNode 能处理三种输入格式：

| 格式 | 来源 | 处理方式 |
|------|------|---------|
| `[{"name": "...", "args": {...}, "id": "..."}]` | 直接传 tool call 列表 | 直接使用 |
| `{"__type": "tool_call_with_context", "tool_call": {...}}`（**不再内联 `state`**） | `Send` API fan-out | 提取单个 tool_call |
| `{"messages": [...]}` 或 BaseModel | 标准 graph state | 找最后一条 AIMessage 的 tool_calls |

**但当前 factory 走的是格式 1 的变体**：`model_to_tools` 每个待执行 tool call 发一个 `Send("tools", [tool_call])`，载荷是**单元素 list**，于是 `_parse_input` 判成 `input_type="tool_calls"`（`tool_node.py` L1231-1234）。格式 3 是「直接 `add_edge("model","tools")`」那种老构图路径用的，`create_agent` 不这么接。

**🔄 同步 #8（v2.2.0）关键变更**：`Send` 载荷里的 `state` 被删了。上游在 `factory.py` L1876-1879 留了理由：

```python
# 4. If there are pending tool calls, jump to the tool node.
# The tool node hydrates ToolRuntime.state from channels via
# CONFIG_KEY_READ at execution time, so we no longer inline the
# full state into each Send (previously O(N^2) in TASKS writes).
```

即：以前把整个 `state` 塞进每个 `Send`，N 个并发 tool call 就是 N 份全量 state 写进 `TASKS` 通道，写下复杂度 O(N²)。现在 ToolNode 在执行时通过 LangGraph 的 CONFIG_KEY_READ 配置通道从 channel 现取。**如果你见过旧版 FAQ / 旧代码里写 `ToolCallWithContext(tool_call=..., state=state)`，那是已删除的形状。**

---

## 3. 条件路由：两个决策函数决定图往哪走

### 3.1 `model_to_tools`——模型输出后往哪走（L1840-1892）

挂在 `loop_exit_node` 上（如果没有 after_model middleware 就是 `"model"` node，如果有就是最外层的 after_model node；两者在 L1603-1612 算出来）。边并用 `graph.add_conditional_edges(...)` 在 L1656-1668 注册，可选目标 `["tools", exit_node, loop_entry_node]`（L1652-1654 决定是否把 `loop_entry_node` 加进去）。

**决策优先级（严格按顺序检查）：**

```
1. state["jump_to"] 有值？
   → YES: 按 jump_to 跳（"tools" / "model" / "end"）
   → NO: 继续

2. 最后一条是 AIMessage？
   → NO（消息被清空等异常）: → END
   → YES: 继续

3. len(last_ai.tool_calls) == 0？
   → YES（模型返回纯文本）: → END
   → NO: 继续

4. 有尚未执行的 tool call？（tool_call 没有对应的 ToolMessage，排除 structured output tool）
   → YES: return [Send("tools", [tool_call]) for each pending call]
         → 每个待执行的 tool call 获得一个并行 ToolNode 调用
   → NO: 继续

5. state 中有 "structured_response"？
   → YES: → END（结构化输出已完成）
   → NO: 继续

6. 所有 tool call 都有 ToolMessage 了，但没有 structured_response
   → 回到 model 继续对话
```

步骤 4 的 `Send` 机制是关键（L1881，一行）：

```python
return [Send("tools", [tool_call]) for tool_call in pending_tool_calls]
```

每个 `Send` 让 LangGraph 为一个 tool call 启动一个独立的 ToolNode 调用。**多个 `Send` 并行执行。**

> 🔄 同步 #8（v2.2.0）：旧版这里写的是 `Send("tools", ToolCallWithContext(__type=..., tool_call=..., state=state))`——**该载荷形状已删除**，改用裸 list。理由见 §2.6 的 CONFIG_KEY_READ 注释。`ToolCallWithContext` 这个 TypedDict 仍留在 `tool_node.py` L286 供旧构图路径与外部调用方使用，但 `create_agent` 不再产生它。

### 3.2 `tools_to_model`——工具执行完后往哪走（L1921-1954）

挂在 `"tools"` node 上。可选目标：`[loop_entry_node, exit_node]`——注意 `exit_node` **只在有 `return_direct` 工具或有 structured output 工具时才被加进候选**（`factory.py` L1625-1630）。

```
1. 最后一条是 AIMessage？
   → NO: → 回到 model
   → YES: 继续

2. 所有已执行的 tool 都有 return_direct=True？
   → YES: → END（工具说了"执行完就停"）

3. 有 structured output tool 被执行了？
   → YES: → END（结构化输出已产生）

4. 默认: → 回到 model（标准循环继续）
```

### 3.3 `jump_to`——middleware 改流向的合法通道

`jump_to` 是 **middleware 钩子**用来改变循环流向的机制。**注意「middleware 钩子」这个限定词**：`wrap_model_call`（钩 `model` node 本体）里做不到这件事，上游把那条路封了。

**类型与 state 声明**（`langchain/agents/middleware/types.py`）：

```python
JumpTo = Literal["tools", "model", "end"]                     # L66

class AgentState(TypedDict, Generic[ResponseT]):              # L347
    jump_to: NotRequired[Annotated[JumpTo | None, EphemeralValue, PrivateStateAttr]]   # L351
```

**`EphemeralValue`** 意味着读一次就消失。条件边函数 `state.get("jump_to")` 读完之后，后续边函数不会再看到同一个值——这防止一次 jump 在循环里反复生效。

**触发方式**（两条路都合法，`types.py` L869-916 是 `hook_config` 的实现）：

```python
from langchain.agents.middleware import hook_config

@hook_config(can_jump_to=["model"])
def after_model(self, state, runtime):
    return {"jump_to": "model"}

# 或者直接写在装饰器上（before_model / after_model 都支持，L905）：
@before_model(can_jump_to=["end"])
def before_model(self, state, runtime):
    return {"jump_to": "end"}
```

`hook_config(can_jump_to=...)` 只是把 `__can_jump_to__` 记在函数上（L914-915），**真正消费它的是 factory**：`_get_can_jump_to`（L491）读出来，`_add_middleware_edge`（L1957-2002）据此决定给这个 middleware node 挂 `jump_edge` 条件边还是普通 `add_edge`。**没在 `can_jump_to` 里声明的目标，路由表里就没有这条边**——声明错了不会报错，只会静默走 `default_destination`。

#### 关键变更：`Command(goto)` 在 `wrap_model_call` 里被封死

这正是 `jump_to` 存在的原因。`_build_commands`（L193-232）在拼装 model node 返回值时逐条检查：

```python
if cmd.goto:
    msg = ("Command goto is not yet supported in wrap_model_call middleware. "
           "Use the jump_to state field with before_model/after_model hooks instead.")
    raise NotImplementedError(msg)
if cmd.resume: raise NotImplementedError("Command resume is not yet supported in wrap_model_call middleware.")
if cmd.graph:  raise NotImplementedError("Command graph is not yet supported in wrap_model_call middleware.")
```

**判读**：`wrap_model_call` 的洋葱链只能改 request、多次调 handler、提前返回 ModelResponse——**不能改图往哪走**。要改流向只有两条合法路径：(a) 钩 `before_model`/`after_model`/`before_agent`/`after_agent` 并返回 `jump_to`；(b) 钩 `wrap_tool_call` 并返回 `Command(goto=...)`（工具层不受这条限制，见 §4 场景 C）。

#### `jump_to` 检查点分布

| 谁执行完 | 下一个条件边 | 检查 jump_to？ |
|----------|-------------|---------------|
| before_agent middleware node | `jump_edge`（L1957-2002） | ✅ 若声明了 `can_jump_to` |
| before_model middleware node | `jump_edge` | ✅ 若声明了 `can_jump_to` |
| after_model middleware node | `jump_edge` | ✅ 若声明了 `can_jump_to` |
| after_agent middleware node | `jump_edge` | ✅ 若声明了 `can_jump_to` |
| model（或最外层 after_model = `loop_exit_node`） | `model_to_tools` | ✅（L1846-1860 第一优先级） |
| tools | `tools_to_model` | ❌ **不检查** |

两点补充：

1. **middleware 节点不是「检查 jump_to」，是「有自己的 jump_edge」**——只有声明了 `can_jump_to` 的钩子才挂这个条件边；没声明的钩子仍是 `add_edge(name, default_destination)`（L2001-2002 的 else 分支）。
2. `tools_to_model` 不检查 `jump_to`，所以「工具执行完之后再想跳」这条路不存在。DeerFlow 的两个用例都不落在这个死角里：`TodoMiddleware` 在 `after_model` 设、`ClarificationMiddleware` 干脆走 `wrap_tool_call` 的 `Command`。详见场景 C。

#### DeerFlow 的两个真实消费者

| 消费者 | 位置 | 干什么 | 走哪条路 |
|---|---|---|---|
| `TodoMiddleware.after_model` | `agents/middlewares/todo_middleware.py` L313-372（`@hook_config(can_jump_to=["model"])` 在 L313、返回 `{"jump_to": "model"}` 在 L372） | 模型想干净退出但 todo 还有未完成项 → 注入提醒 `HumanMessage` 并**拉回 model node** 继续干；有 `_MAX_COMPLETION_REMINDERS`（默认 2）防死循环 | `jump_to` |
| `ClarificationMiddleware._handle_clarification` | `agents/middlewares/clarification_middleware.py` L519-522（`return Command(update={"messages": [tool_message]}, goto=END)`） | 模型调 `ask_clarification` → **不进 tools 执行**，直接把 ToolMessage 写进 state 并终止本轮 | `wrap_tool_call` + `Command(goto=END)` |

`TodoMiddleware` 那处的注释还顺手揭示了两个 2.2.0 才有的护栏：`deerflow_error_fallback` 标记的 AIMessage、以及 `model_length_termination` 标记的长度截断轮次，都**不允许**被 todo 提醒拉回——否则会在同一个超长 tool call 上原地打转。相关背景见 [_digested/graph-engineering/06-langgraph-capability-surface.md](../../_digested/graph-engineering/06-langgraph-capability-surface.md) §2 的 `jump_to` 行。

**🔄 同步 #8 更正**：旧版本节写「middleware 通过返回 `{"jump_to": "end"}` 来设值，ClarificationMiddleware 在 `after_model` 设的」——**该用法已删除**。`ClarificationMiddleware` 现在只实现 `wrap_tool_call` / `awrap_tool_call`，`after_model` 短路那套已经不在了。

---

## 4. 三个完整执行场景（逐步骤追踪）

### 场景 A：模型返回纯文本

**初始 state**：`messages = [HumanMessage("你好")]`

| # | 谁 | 做什么 |
|---|-----|-------|
| 1 | `model_node` | `_get_bound_model` → `model.bind_tools(...)` 绑定所有工具 |
| 2 | `_execute_model_sync` | `model_.invoke([SystemMessage, HumanMessage("你好")])` |
| 3 | LLM 返回 | `AIMessage(content="你好！有什么可以帮你？", tool_calls=[])` |
| 4 | `_handle_model_output` | Default 分支 → `{"messages": [AIMessage]}` |
| 5 | `_build_commands` | `[Command(update={"messages": [AIMessage]})]` |
| 6 | LangGraph reducer | `add_messages` 追加 AIMessage 到 state |
| 7 | `model_to_tools` | `len(tool_calls) == 0` → **END** |

用户收到："你好！有什么可以帮你？"

### 场景 B：模型返回 tool calls（最完整的 loop）

**初始 state**：`messages = [HumanMessage("列出 /tmp 下的文件")]`

| # | 谁 | 做什么 |
|---|-----|-------|
| 1 | `model_node` | 同上调用链路 |
| 2 | LLM 返回 | `AIMessage(content="", tool_calls=[{"name": "bash", "args": {"command": "ls /tmp"}, "id": "call_abc"}, {"name": "bash", "args": {"command": "cat /tmp/readme.txt"}, "id": "call_def"}])` |
| 3 | `_handle_model_output` | Default → `{"messages": [AIMessage]}` |
| 4 | `model_to_tools` | jump_to 空、AIMessage 存在、2 个 tool_call 都无对应 ToolMessage → **pending**（`factory.py` L1866-1873） |
| 5 | `model_to_tools` 返回 | `[Send("tools", [bash/ls]), Send("tools", [bash/cat])]`（L1881） |
| 6 | LangGraph | **并行**启动 2 个 ToolNode 调用 |
| 7a | ToolNode #1 `_parse_input` | 载荷是单元素 list 且首项 `type == "tool_call"` → `input_type="tool_calls"`，取出 call_abc |
| 7b | ToolNode #2 `_parse_input` | 同时取出 call_def |
| 8a | `_run_one` → `_execute_tool_sync` | `bash.invoke({"command": "ls /tmp"})` → `"file1.txt\nfile2.txt"` |
| 8b | `_run_one` → `_execute_tool_sync` | `bash.invoke({"command": "cat /tmp/readme.txt"})` → `"hello world"` |
| 9 | LangGraph reducer | 两个 ToolMessage 都追加到 state |
| 10 | **state 现在是** | `[HumanMessage, AIMessage(tool_calls=[call_abc, call_def]), ToolMessage("file1.txt\nfile2.txt", id=call_abc), ToolMessage("hello world", id=call_def)]` |
| 11 | `tools_to_model` | AIMessage 存在、bash 不是 return_direct、不是 structured output → **回到 model** |
| 12 | `model_node`（第二轮） | LLM 看到完整上下文（包含两个 ToolMessage），返回 `AIMessage(content="/tmp 下有 file1.txt 和 file2.txt，readme.txt 内容是 'hello world'", tool_calls=[])` |
| 13 | `model_to_tools` | `len(tool_calls) == 0` → **END** |

用户收到："/tmp 下有 file1.txt 和 file2.txt，readme.txt 内容是 'hello world'"

### 场景 C：ClarificationMiddleware 在 `wrap_tool_call` 返回 `Command(goto=END)`

DeerFlow 处理「反问用户」的机制。`ask_clarification` 是**一个真工具**，模型照常发起 tool call，短路发生在工具层而不是路由层：

| # | 谁 | 做什么 |
|---|-----|-------|
| 1 | `model_node` | LLM 返回 `AIMessage(tool_calls=[{"name": "ask_clarification", "args": {"question": "你指的是哪个文件？"}}])` |
| 2 | `model_to_tools` | 有 pending tool call → `Send("tools", [tool_call])` |
| 3 | `ToolNode._run_one` | 查到 `wrap_tool_call` 洋葱链，`ClarificationMiddleware.wrap_tool_call` 在最内层之前拦截（`clarification_middleware.py` L524 起） |
| 4 | `ClarificationMiddleware._handle_clarification` | 组装 ToolMessage（`id=request_id`、`artifact={"human_input": payload}`）→ **`return Command(update={"messages": [tool_message]}, goto=END)`**（L519-522） |
| 5 | LangGraph | 工具层返回的 `Command` 被接受（`wrap_tool_call` 不受 `_build_commands` 那三条 `NotImplementedError` 约束），本轮直接进 `__end__` |

**`ask_clarification` 的函数体从未被真正执行**——中间件在洋葱链外层就把它换成了 `Command`。用户看到反问消息，下一轮对话带着答案回来继续。

**🔄 同步 #8 更正（这是一整段失效结论）**：旧版场景 C 描述的是「`ClarificationMiddleware.after_model` 检测到 `ask_clarification` 后返回 `{"jump_to": "end"}`，`model_to_tools` 第一步读到它」——**该机制已删除**。三个事实层面同时变了：

1. **不再有 `after_model` 短路**——`ClarificationMiddleware` 现在只实现 `wrap_tool_call`（L524）/ `awrap_tool_call`（L549）；
2. **不再设 `jump_to`**——它返回的是 `Command(goto=END)`，走 `wrap_tool_call` 的合法通道；
3. **仍然「永远最后一个」**——`agent.py` L777-778 的 `middlewares.append(ClarificationMiddleware())`（注释仍是 "ClarificationMiddleware should always be last"），但这一位置现在保证的是**洋葱链最外层**（`wrap_tool_call` 先拿到请求），不再是 `loop_exit_node` 的身份。

顺带一个现行分支值得知道：`_handle_disabled_clarification`（L446-469）——在非交互上下文（如定时任务）里，`ask_clarification` 不返回 `Command`，而是返回一条**普通 ToolMessage**，docstring 明说「Returns a plain ToolMessage (not a `Command(goto=END)`) so the agent loop continues instead of ending」。同一个中间件，两种短路策略，按交互模式选。

---

## 总结

| 问题 | 答案 |
|------|------|
| 固定 node 有几个？ | **2 个**：`model` 和 `tools`（且 `tools` 只在有工具时才挂，`factory.py` L1505-1506）。middleware hook 会在编译时变成额外 node |
| model node 核心逻辑？ | 组装 `ModelRequest` → `_get_bound_model` 绑定工具 → `model.invoke(messages)` → `_handle_model_output` 处理结果 → `_build_commands` 写回 state |
| tools node 怎么执行？ | `ThreadPoolExecutor.map`（同步）或 `asyncio.gather`（异步）并行执行所有 tool call |
| 怎么决定往哪走？ | `model_to_tools`（6 级优先级）和 `tools_to_model`（4 级）两棵决策树 |
| middleware 怎么改流向？ | 两条路：钩 `before_model`/`after_model` 返回 `jump_to`（需先 `hook_config(can_jump_to=...)` 声明）；或钩 `wrap_tool_call` 返回 `Command(goto=END)`。**`wrap_model_call` 里返回 `Command` 会 `NotImplementedError`** |
| 工具出错怎么办？ | DeerFlow 的 `ToolErrorHandlingMiddleware` 捕获所有异常 → error ToolMessage，不崩溃 |
| 多个 tool call 怎么并行？ | `Send("tools", [tool_call])` — 每个 tool call 一个 Send，LangGraph 并行调度；**state 不再内联进 Send**（改为执行时 CONFIG_KEY_READ） |

## 关键源码

- `langchain/agents/factory.py`（2007 行）：`_build_commands` L193-232（`NotImplementedError` 三连 L213-227）、`_get_can_jump_to` L491、`_handle_model_output` L1168-1270、`_get_bound_model` L1272-1404、`_execute_model_sync` L1406-1431、`model_node` L1433-1452、`amodel_node` L1481-1500、`graph.add_node("model")` L1502、`add_node("tools")` L1505-1506、`_make_model_to_tools_edge` L1840-1892（`Send` L1881）、`_make_tools_to_model_edge` L1921-1954、`_add_middleware_edge`（`jump_edge`）L1957-2002
- `langgraph/prebuilt/tool_node.py`（2030 行）：`ToolCallWithContext` L286、`ToolNode` L622、`__init__` L743、`_func` L793-824、`_afunc` L826-858、`_execute_tool_sync` L922-1012、`_run_one` L1014、`_parse_input` L1224-1290
- `langchain/agents/middleware/types.py`：`JumpTo` L66、`AgentState.jump_to` L351、`hook_config(can_jump_to=...)` L867-916
- `deerflow/agents/lead_agent/agent.py`（1446 行）：`_make_lead_agent` L880、`_assemble_lead_agent` 内 `create_agent(` L1250-1257、`build_middlewares` L485、`ClarificationMiddleware` 追加 L777-778
- `deerflow/agents/middlewares/todo_middleware.py`：`after_model` L312-372（`@hook_config(can_jump_to=["model"])` L313、`return {"jump_to": "model"}` L372）
- `deerflow/agents/middlewares/clarification_middleware.py`：`_handle_disabled_clarification` L446-469、`_handle_clarification` L471-522、`Command(goto=END)` L519-522、`wrap_tool_call` L524、`awrap_tool_call` L549

> 🔄 同步 #8（v2.2.0）：以上行号全部按 `backend/.venv` 实装的 langchain 1.3.14 / langgraph 1.2.9 / langgraph-prebuilt 1.1.0 与 v2.2.0 源码树重新核对，**旧版的 langchain 侧行号（1.2.15 / 1.0.11 时代）一条都不再成立**。LangChain 侧每升一个次版本，这张表就得重扫——这是「依赖无上界」的直接代价，不是一次性工作。
