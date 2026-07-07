# Q7: Agent 图的两个固定 Node——model 和 tools

## 铁律：只有两个 Node，两类 Node，没有第三个

**斩钉截铁地说：整个 agent 循环只有两个固定 node。只有两类。没有任何其他 node。**

这两个 node 是：

| Node | 类型 | 做什么 |
|------|------|--------|
| `"model"` | **思考**节点 | 调 LLM，读消息历史，决定下一步干什么 |
| `"tools"` | **行动**节点 | 执行真实世界的操作（shell、文件、API……） |

**middleware 变出来的那些 node（before_model、after_model……）不是第三种——它们是这两类的"前厅"和"后厅"，挂在思考节点的前后。**

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
| `create_agent()` 图构建 | `langchain/agents/factory.py` | 1869 行 |
| `model_node` / `amodel_node` | 同上 | L1296-1362 |
| `_execute_model_sync` | 同上 | L1269-1294 |
| `_get_bound_model` | 同上 | L1140-1267 |
| `_handle_model_output` | 同上 | L1036-1138 |
| `_build_commands` | 同上 | L177-216 |
| `ToolNode` 类 | `langgraph/prebuilt/tool_node.py` | L620-1989 |
| `model_to_tools` 条件边 | `factory.py` | L1695-1753 |
| `tools_to_model` 条件边 | `factory.py` | L1783-1816 |
| DeerFlow 调用入口 | `deerflow/agents/lead_agent/agent.py` | L437-603 |

---

## 1. model node：LLM 调用的完整链路

### 1.1 注册到图上

`factory.py` L1365：

```python
graph.add_node("model", RunnableCallable(model_node, amodel_node, trace=False))
```

`RunnableCallable` 是 LangGraph 的通用 node 包装器（定义在 `langgraph/_internal/_runnable.py`）。它存了两个函数——同步版 `model_node` 和异步版 `amodel_node`。当图执行到这个 node 时，LangGraph 从 `config` 中提取 `runtime` 对象，然后调用：

```
model_node(state, runtime=<Runtime object>)          # 同步
await amodel_node(state, runtime=<Runtime object>)    # 异步
```

### 1.2 `model_node` 函数体（L1296-1314）

```python
def model_node(state: AgentState[Any], runtime: Runtime[ContextT]) -> list[Command[Any]]:
```

它只做三件事：

**第一步：组装请求对象**（L1298-1307）

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

**第二步：经过 middleware 洋葱链调用 LLM**（L1309-1314）

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

### 1.3 `_execute_model_sync`——真正调用 LLM 的地方（L1269-1294）

这是洋葱链最内层，middleware 的 `handler` 参数就指向它：

```python
def _execute_model_sync(request: ModelRequest[ContextT]) -> ModelResponse:
```

**子步骤 1：绑定工具到模型**（L1277）

```python
model_, effective_response_format = _get_bound_model(request)
```

`_get_bound_model`（L1140-1267）做了这些事：

1. 验证所有 tool 确实存在（L1159-1187）
2. 自动选择结构化输出策略（L1191-1212）：
   - `ProviderStrategy`：用 OpenAI 原生 `response_format` 参数（模型本身就支持 structured output）
   - `ToolStrategy`：注入一个特殊的 tool，让模型通过 tool call 输出结构化数据（fallback 方案）
3. 构建最终 tool 列表，调用 `model.bind_tools(final_tools, ...)`（L1228-1267）：
   - ProviderStrategy：`model.bind_tools(final_tools, strict=True, **model_settings)`
   - ToolStrategy：`model.bind_tools(final_tools, tool_choice="any", **model_settings)` —— 强制模型必须调 tool
   - 无 structured output 需求：`model.bind_tools(final_tools, tool_choice=request.tool_choice, **model_settings)`
   - 无任何 tool：`model.bind(**model_settings)`

**子步骤 2：拼上 system message，调用模型**（L1278-1282）

```python
messages = request.messages
if request.system_message:
    messages = [request.system_message, *messages]  # SystemMessage 放在最前面

output = model_.invoke(messages)  # ← 真正的 LLM API 调用
```

`output` 是一个 `AIMessage`，可能是：
- `.content = "你好！"`，`.tool_calls = []` —— 纯文本回复
- `.content = ""`，`.tool_calls = [{"name": "bash", "args": {...}, "id": "call_abc"}]` —— 要调工具

**子步骤 3：处理模型输出**（L1287-1288）

```python
handled_output = _handle_model_output(output, effective_response_format)
```

`_handle_model_output`（L1036-1138）三种分支：

| 情况 | 行为 |
|------|------|
| ProviderStrategy + 无 tool_calls | 解析结构化响应 → `{"messages": [output], "structured_response": parsed}` |
| ToolStrategy + 有 structured output tool call | 解析 tool call args → 合成 ToolMessage → `{"messages": [output, tool_msg], "structured_response": parsed}` |
| 默认（普通对话，不是 structured output） | `{"messages": [output]}` —— 原样返回 AIMessage |

**子步骤 4：返回 ModelResponse**（L1291-1294）

```python
return ModelResponse(
    result=messages_list,           # [AIMessage(...)]
    structured_response=...,        # 结构化输出解析结果，或 None
)
```

### 1.4 `_build_commands`——把 LLM 输出写成 LangGraph Command（L177-216）

```python
def _build_commands(model_response, middleware_commands=None) -> list[Command[Any]]:
    state = {"messages": model_response.result}
    if model_response.structured_response is not None:
        state["structured_response"] = model_response.structured_response

    commands = [Command(update=state)]
    commands.extend(middleware_commands or [])
    return commands
```

返回类似：
```python
[Command(update={"messages": [AIMessage(content="你好！")]})]
```

LangGraph 拿到这个 `Command` 后，通过 **reducer** 把更新合入 graph state。对于 `messages` 字段，reducer 是 `add_messages`——它把新 AIMessage **追加**到现有列表末尾，不是覆盖。对于 `structured_response` 这种没有自定义 reducer 的字段，默认是 `last_value`（直接覆盖）。

### 1.5 异步路径：`amodel_node`（L1344-1362）

结构完全一样，唯一区别：
- `await model_.ainvoke(messages)` 代替 `.invoke()`
- `await awrap_model_call_handler(...)` 代替同步版
- `await _execute_model_async(request)` 代替同步版

### 1.6 DeerFlow 怎么调用 `create_agent`

`deerflow/agents/lead_agent/agent.py` L603：

```python
return create_agent(
    model=create_chat_model(name=model_name, thinking_enabled=thinking_enabled, ...),
    tools=final_tools,                # sandbox + MCP + builtins + community + subagent tools
    middleware=build_middlewares(config, ...),  # 30+ middleware
    system_prompt=apply_prompt_template(...),   # 动态 prompt 模板
    state_schema=ThreadState,          # DeerFlow 自定义 state（12 个字段）
)
```

---

## 2. tools node：ToolNode 的并行执行机制

### 2.1 ToolNode 本质

`tool_node.py` L620：

```python
class ToolNode(RunnableCallable):
    def __init__(self, tools, *, name="tools", ...):
        super().__init__(self._func, self._afunc, name=name, tags=tags, trace=False)
```

ToolNode 也是 `RunnableCallable`——和 model node 同一种包装器。初始化时（L741-784）：

1. 把 dict 格式的 tool 包装成 `BaseTool`
2. 按 tool name 建索引 `self._tools_by_name: dict[str, BaseTool]`
3. 预计算每个 tool 的注入参数（`InjectedState`、`InjectedStore`、`ToolRuntime`）

### 2.2 同步并行执行：`_func`（L791-824）

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

`_run_one`（L1012-1065）先查 `wrap_tool_call` 是否存在。DeerFlow 的 `ToolErrorHandlingMiddleware` 提供了它，所以实际路径是：

```
_run_one
  → _wrap_tool_call(tool_request, execute)       # middleware 洋葱链
      → _execute_tool_sync(tool_request, ...)     # 最内层，真正执行
```

`_execute_tool_sync`（L920-1010）的核心：

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

### 2.6 输入解析：`_parse_input`（L1222-1264）

ToolNode 能处理三种输入格式：

| 格式 | 来源 | 处理方式 |
|------|------|---------|
| `[{"name": "...", "args": {...}, "id": "..."}]` | 直接传 tool call 列表 | 直接使用 |
| `{"__type": "tool_call_with_context", "tool_call": {...}, "state": {...}}` | `Send` API fan-out | 提取单个 tool_call |
| `{"messages": [...]}` 或 BaseModel | 标准 graph state | 找最后一条 AIMessage 的 tool_calls |

**标准 agent loop 走格式 3**：ToolNode 自己从 `state.messages` 中找最后一条 AIMessage，提取所有 `tool_calls`，一次性并行执行。

---

## 3. 条件路由：两个决策函数决定图往哪走

### 3.1 `model_to_tools`——模型输出后往哪走（L1695-1753）

挂在 `loop_exit_node` 上（如果没有 after_model middleware 就是 `"model"` node，如果有就是最外层的 after_model node）。可选目标：`["tools", exit_node, loop_entry_node]`。

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
   → YES: return [Send("tools", ToolCallWithContext(...)) for each pending call]
         → 每个待执行的 tool call 获得一个并行 ToolNode 调用
   → NO: 继续

5. state 中有 "structured_response"？
   → YES: → END（结构化输出已完成）
   → NO: 继续

6. 所有 tool call 都有 ToolMessage 了，但没有 structured_response
   → 回到 model 继续对话
```

步骤 4 的 `Send` 机制是关键（L1732-1743）：

```python
return [
    Send("tools", ToolCallWithContext(
        __type="tool_call_with_context",
        tool_call=tool_call,
        state=state,
    ))
    for tool_call in pending_tool_calls
]
```

每个 `Send` 让 LangGraph 为一个 tool call 启动一个独立的 ToolNode 调用。**多个 `Send` 并行执行。**

### 3.2 `tools_to_model`——工具执行完后往哪走（L1783-1816）

挂在 `"tools"` node 上。可选目标：`[loop_entry_node, exit_node]`。

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

### 3.3 `jump_to`——middleware 的紧急逃生口

`jump_to` 是 middleware 用来绕过正常路由的机制。

类型（`types.py` L69）：`JumpTo = Literal["tools", "model", "end"]`

State 声明（`types.py` L350-355）：
```python
jump_to: NotRequired[Annotated[JumpTo | None, EphemeralValue, PrivateStateAttr]]
```

**`EphemeralValue`** 意味着——读一次就消失。在条件边函数中 `state.get("jump_to")` 之后，后续边函数不会再看到同一个值。这防止了 `jump_to` 在多次循环中反复生效。

middleware 通过返回 `{"jump_to": "end"}` 来设值。`model_to_tools`（L1704）在第一优先级就检查它。

`jump_to` 检查点分布：

| 谁执行完 | 下一个条件边 | 检查 jump_to？ |
|----------|-------------|---------------|
| before_agent middleware node | `jump_edge` | ✅ |
| before_model middleware node | `jump_edge` | ✅ |
| after_model middleware node | `jump_edge` | ✅ |
| after_agent middleware node | `jump_edge` | ✅ |
| model（或最外层 after_model） | `model_to_tools` | ✅（L1704） |
| tools | `tools_to_model` | ❌ **不检查** |

`tools_to_model` 不检查 `jump_to`。如果 middleware 在工具执行后才设 `jump_to`，那就太晚了。但实际上 DeerFlow 的关键用例（ClarificationMiddleware）是在 `after_model` 设的，此时 `model_to_tools` 还来得及读，工具根本没机会执行。详见下方场景 C。

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
| 4 | `model_to_tools` | jump_to 空、AIMessage 存在、2 个 tool_call 都无对应 ToolMessage → **pending** |
| 5 | `model_to_tools` 返回 | `[Send("tools", {tool_call: bash/ls}), Send("tools", {tool_call: bash/cat})]` |
| 6 | LangGraph | **并行**启动 2 个 ToolNode 调用 |
| 7a | ToolNode #1 `_parse_input` | `__type == "tool_call_with_context"` → 提取 call_abc |
| 7b | ToolNode #2 `_parse_input` | 同时提取 call_def |
| 8a | `_run_one` → `_execute_tool_sync` | `bash.invoke({"command": "ls /tmp"})` → `"file1.txt\nfile2.txt"` |
| 8b | `_run_one` → `_execute_tool_sync` | `bash.invoke({"command": "cat /tmp/readme.txt"})` → `"hello world"` |
| 9 | LangGraph reducer | 两个 ToolMessage 都追加到 state |
| 10 | **state 现在是** | `[HumanMessage, AIMessage(tool_calls=[call_abc, call_def]), ToolMessage("file1.txt\nfile2.txt", id=call_abc), ToolMessage("hello world", id=call_def)]` |
| 11 | `tools_to_model` | AIMessage 存在、bash 不是 return_direct、不是 structured output → **回到 model** |
| 12 | `model_node`（第二轮） | LLM 看到完整上下文（包含两个 ToolMessage），返回 `AIMessage(content="/tmp 下有 file1.txt 和 file2.txt，readme.txt 内容是 'hello world'", tool_calls=[])` |
| 13 | `model_to_tools` | `len(tool_calls) == 0` → **END** |

用户收到："/tmp 下有 file1.txt 和 file2.txt，readme.txt 内容是 'hello world'"

### 场景 C：ClarificationMiddleware 设 jump_to 短路

DeerFlow 处理"反问用户"的机制。当模型调用 `ask_clarification` 工具时：

| # | 谁 | 做什么 |
|---|-----|-------|
| 1 | `model_node` | LLM 返回 `AIMessage(tool_calls=[{"name": "ask_clarification", "args": {"question": "你指的是哪个文件？"}}])` |
| 2 | `ClarificationMiddleware.after_model` | 检测到 `ask_clarification` → 返回 `{"jump_to": "end", "messages": [ToolMessage(content="请回答：你指的是哪个文件？")]}` |
| 3 | State 更新 | `jump_to="end"`（EphemeralValue），ToolMessage 写入 messages |
| 4 | `model_to_tools` | **第一步就检查：** `state.get("jump_to")` → `"end"` |
| 5 | `_resolve_jump("end")` | → `end_destination` → **END** |

**`ask_clarification` 工具从未被真正执行。** 图直接终止，用户看到反问消息。

这可行的原因：ClarificationMiddleware 是 DeerFlow middleware 列表中的**最后一个**（`agent.py` L404: `middlewares.append(ClarificationMiddleware())`）。在 `after_model` 的反向执行顺序中（详见 Q8），最后一个 = 最外层 = 第一个执行 = **它就是 `loop_exit_node`**。所以 `model_to_tools` 条件边挂在 ClarificationMiddleware 的 after_model 后面，`jump_to` 在工具执行前就被读取了。

---

## 总结

| 问题 | 答案 |
|------|------|
| 固定 node 有几个？ | **2 个**：`model` 和 `tools`。middleware hook 会在编译时变成额外 node |
| model node 核心逻辑？ | 组装 `ModelRequest` → `_get_bound_model` 绑定工具 → `model.invoke(messages)` → `_handle_model_output` 处理结果 → `_build_commands` 写回 state |
| tools node 怎么执行？ | `ThreadPoolExecutor.map`（同步）或 `asyncio.gather`（异步）并行执行所有 tool call |
| 怎么决定往哪走？ | `model_to_tools`（6 级优先级）和 `tools_to_model`（4 级）两棵决策树 |
| middleware 怎么短路？ | `jump_to="end"`（EphemeralValue，读一次就消失），在 `model_to_tools` 第一步读取 |
| 工具出错怎么办？ | DeerFlow 的 `ToolErrorHandlingMiddleware` 捕获所有异常 → error ToolMessage，不崩溃 |
| 多个 tool call 怎么并行？ | `Send("tools", ToolCallWithContext(...))` — 每个 tool call 一个 Send，LangGraph 并行调度 |

## 关键源码

- `langchain/agents/factory.py`：`model_node` L1296-1314, `_execute_model_sync` L1269-1294, `_get_bound_model` L1140-1267, `_handle_model_output` L1036-1138, `_build_commands` L177-216, `model_to_tools` L1695-1753, `tools_to_model` L1783-1816
- `langgraph/prebuilt/tool_node.py`：`ToolNode.__init__` L620-784, `_func` L791-824, `_run_one` L1012-1065, `_execute_tool_sync` L920-1010, `_parse_input` L1222-1264
- `langchain/agents/middleware/types.py`：`AgentState.jump_to` L350-355, `JumpTo` L69
- `deerflow/agents/lead_agent/agent.py`：`_make_lead_agent` L437-603, `build_middlewares` L269-405
