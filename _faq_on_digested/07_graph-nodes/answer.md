# Q7: 两个固定 Node——model 和 tools

## 它们怎么工作

LangGraph 的 `create_agent()` 构建一个循环图。只有两个核心 node：

```
START → [before_model hooks] → "model" → [after_model hooks]
                                      ↓
                              有 tool_calls?
                              ↙           ↘
                         "tools"        END
                            ↓
                      [回到 model]
```

**`"model"` node**：接收完整的 `state.messages` 列表，调用 `model.invoke(messages)`，返回 `Command(update={"messages": [AIMessage]})`。AIMessage 可能包含纯文本（循环结束）或 `tool_calls`（需要执行工具）。

**`"tools"` node**：LangGraph 的 `ToolNode`。收到 `tool_calls` 后逐个执行，每个返回一个 `ToolMessage`。所有 `ToolMessage` 被追加到 `state.messages`，然后路由回 model node。

## 怎么影响它们

你不能删除这两个 node，但有两种 hook 可以深度介入：

### `wrap_model_call` — 在 model node **内部**拦截

执行顺序：外层 middleware 包裹内层。适合：重试、缓存、短接。

```python
class RetryMiddleware(AgentMiddleware):
    def wrap_model_call(self, request, handler):
        for attempt in range(3):
            try:
                return handler(request)  # 调用内层（最终到真实 model.invoke）
            except Exception:
                if attempt == 2:
                    raise
```

DeerFlow 里用 `wrap_model_call` 的例子：
- `LLMErrorHandlingMiddleware`：分类错误（quota/auth/transient/busy），指数退避重试，断路器
- `SystemMessageCoalescingMiddleware`：合并多条 SystemMessage 为一条
- `InputSanitizationMiddleware`：转义 `<system>` 等 XML tag

### `wrap_tool_call` — 在 ToolNode **内部**拦截

执行顺序同样是外层包裹内层。适合：tool 结果修改、停滞检测、错误归一化。

```python
class LoggingMiddleware(AgentMiddleware):
    def wrap_tool_call(self, request, handler):
        logger.info(f"Tool: {request.tool_call['name']}")
        result = handler(request)  # 执行真实 tool
        logger.info(f"Result: {str(result)[:200]}")
        return result
```

DeerFlow 里用 `wrap_tool_call` 的例子：
- `ToolErrorHandlingMiddleware`：捕获异常→error ToolMessage，注入 `deerflow_tool_meta`
- `ToolProgressMiddleware`：停滞状态机（ACTIVE→WARNED→BLOCKED）
- `ReadBeforeWriteMiddleware`：写文件前检查是否读过

### `before_model` / `after_model` — 在 model node **外部**，作为独立 node

这些是独立 graph node，不是拦截器。适合：state 准备、输出检查、注入上下文。

### 对比

| | wrap_model_call | before_model | after_model |
|---|---|---|---|
| 位置 | model node 内部 | model node 之前 | model node 之后 |
| 是独立 Node? | 否 | 是 | 是 |
| 能阻止 LLM 调用? | 是（不调 handler） | 是（jump_to） | 否（已调用完） |
| 能改 state? | 否 | 是 | 是 |
| 执行顺序 | 外层→内层 | 列表顺序 | **反向**（后加的先执行） |

## 选哪种

- 想**拦截/重试 LLM 调用** → `wrap_model_call`
- 想**在 LLM 调前准备数据** → `before_model`
- 想**在 LLM 调后检查输出** → `after_model`
- 想**拦截/修改 tool 执行** → `wrap_tool_call`

## 关键源码

- `langchain/agents/factory.py`：`create_agent()` 构建图，line 1365-1639
- `deerflow/agents/middlewares/llm_error_handling_middleware.py`：`wrap_model_call` 实例
- `deerflow/agents/middlewares/tool_error_handling_middleware.py`：`wrap_tool_call` 实例
- `deerflow/agents/middlewares/input_sanitization_middleware.py`：`wrap_model_call` 实例
