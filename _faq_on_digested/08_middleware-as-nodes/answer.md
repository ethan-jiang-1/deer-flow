# Q8: Middleware 就是 Node

## 不是比喻

LangChain 的 `create_agent()` 在编译时检查每个 middleware 实现了哪些 hook。每实现一个 `before_model`/`after_model`/`before_agent`/`after_agent`，**就在 `StateGraph` 上增加一个真实的 node**。

```python
# langchain/agents/factory.py (简化)
for mw in middleware:
    if hasattr(mw, 'before_model'):
        graph.add_node(f"{mw.name}.before_model", mw.abefore_model)
    if hasattr(mw, 'after_model'):
        graph.add_node(f"{mw.name}.after_model", mw.aafter_model)
    if hasattr(mw, 'before_agent'):
        graph.add_node(f"{mw.name}.before_agent", mw.abefore_agent)
    if hasattr(mw, 'after_agent'):
        graph.add_node(f"{mw.name}.after_agent", mw.aafter_agent)
```

29 个 middleware × 每个可能实现 1-4 个 hook = **图上可以多出 50+ 个 node**。它们通过 `add_edge`/`add_conditional_edges` 串成链。

## 四类 Node vs 两类拦截器

### 变成独立 Node 的 Hook

| Hook | Node 名 | 何时运行 |
|------|---------|---------|
| `before_agent()` | `"{name}.before_agent"` | 图启动时一次 |
| `before_model()` | `"{name}.before_model"` | 每次 LLM 调用前 |
| `after_model()` | `"{name}.after_model"` | 每次 LLM 调用后 |
| `after_agent()` | `"{name}.after_agent"` | 图结束时一次 |

这些 node 可以做：
- 读写 `state`（返回 `dict[str, Any]`）
- 通过 `jump_to` 改变路由
- 通过 `Command(goto=END)` 中断循环

### 不变成 Node 的 Hook

| Hook | 机制 |
|------|------|
| `wrap_model_call()` | 在 `"model"` node 内部组成洋葱链 |
| `wrap_tool_call()` | 在 `ToolNode` 内部组成洋葱链 |

这两者在 node 内部运行——外层先执行，把请求传给内层，最终到达真实的 `model.invoke()` 或 tool 执行函数。

## 为什么 after_model 是反向执行

这是最关键的设计点。LangChain **按列表顺序添加 node，但 after_model 的边是反向连的**：

```
graph.add_edge("model", last_added.after_model)       # model → 最后加的
graph.add_edge(last_added.after_model, second_last.after_model)  # → 倒数第二
...
graph.add_edge(second.after_model, first_added.after_model)     # → 第一个加的
graph.add_conditional_edges(first_added.after_model, ...)        # → tools 或 END
```

效果：**后加的 middleware 在 after_model 中最靠近 model**，最先看到 LLM 输出。

这就是为什么 `ClarificationMiddleware` 必须在列表最后——它需要第一个检查 `ask_clarification`，在 Title/Memory/TokenUsage 等 middleware 处理之前拦截。

```
model 输出 AIMessage
    │
    ▼
ClarificationMiddleware.after_model   ← 列表最后，最先执行
    │
    ▼
SafetyFinishReasonMiddleware.after_model
    │
    ▼
...（中间 10+ 个 middleware）...
    │
    ▼
ThreadDataMiddleware.after_model      ← 列表最前，最后执行
    │
    ▼
条件边 → tools 或 END
```

## before_model 是正向

before_model 的边是**正向**连的——先加的 middleware 先执行。如果你要注入数据，你的 middleware 应该加在列表前面。

## 关键源码

- `langchain/agents/factory.py`：`_add_middleware_node()` line 1372-1453，`_add_middleware_edge()` line 1807-1839
- `deerflow/agents/lead_agent/agent.py`：`build_middlewares()` line 269-405，展示完整列表顺序
