# NotRequired vs Annotated——两种扩展机制

## NotRequired[T]：简单覆盖

### 语法

```python
class MyState(ThreadState):
    review_count: NotRequired[int]
    last_action: NotRequired[str | None]
```

### 行为

- 默认 reducer：`last_value`——后来的值直接覆盖旧值
- 字段可以不传（NotRequired = 不是必须的 key）
- 适合：**只有一个 writer**，不需要合并逻辑

### 在 middleware 中用

```python
class MyMiddleware(AgentMiddleware):
    def after_model(self, state, runtime):
        count = state.get("review_count", 0)  # 读（给默认值，因为可能不存在）
        return {"review_count": count + 1}     # 写（覆盖旧值）
```

### 什么时候用

- 只有一个 middleware 会写这个字段
- 值就是简单的覆盖关系（新值换旧值）
- 不需要自定义合并逻辑

## Annotated[T, reducer]：自定义合并

### 语法

```python
def my_reducer(existing: list[str] | None, new: list[str] | None) -> list[str]:
    """合并两个列表，去重追加"""
    if existing is None:
        return new or []
    if new is None:
        return existing
    seen = set(existing)
    result = list(existing)
    for item in new:
        if item not in seen:
            seen.add(item)
            result.append(item)
    return result

class MyState(ThreadState):
    processed_files: Annotated[list[str], my_reducer]
```

### 行为

- 当两个 node 在**同一个 superstep** 里都返回了 `{"processed_files": [...]}` 时，LangGraph 调用 `my_reducer(existing, new)` 合并
- 只有一个 node 返回这个 key 时，通常直接用该值、不调 reducer——**但 reducer 自身要对 `new=None` 做保护**，上例已经这么写了（`if new is None: return existing`）。把「不会被调用」当保证是常见翻车点，见 [04-practical-recipes.md](04-practical-recipes.md) 坑 3。

### Reducer 的调用规则

1. **初始化时**：不调用 reducer。State 用初始值。
2. **Node 返回更新时**：`reducer(state[key], node_return[key])`
3. **多个 Node 同时返回时**：逐个合并，`reducer(reducer(state, nodeA), nodeB)`

### 什么时候用

- 多个 tool 或 middleware 可能同时在同一个 key 上写数据
- 需要自定义合并逻辑（去重、取最大、保留特定状态）
- 值的语义不只是"覆盖"

## 对比

| | NotRequired[T] | Annotated[T, reducer] |
|---|---|---|
| 合并策略 | last_value（覆盖） | 自定义 |
| 单 writer | ✅ 最佳选择 | 可以但没必要 |
| 多 writer | ❌ 后来的覆盖前面的 | ✅ 用 reducer 控制 |
| 复杂度 | 低 | 中等（需要写 reducer 函数） |
| None 的行为 | 直接覆盖 | 看你的 reducer 怎么处理 |
| 示例 | `review_count: NotRequired[int]` | `processed_files: Annotated[list[str], merge_files]` |

## 第三种形态（v2.2.0 现实里存在）：通道类 reducer

`Annotated[T, reducer]` 的第二个位置**不一定是函数**，也可以是一个 reducer 类。DeerFlow 的 `task_notes` 就是：

```python
task_notes: Annotated[dict | None, TaskNotesChannel(dict | None, merge_task_notes)]   # thread_state.py L394
```

`TaskNotesChannel` 继承 LangGraph 的 `BinaryOperatorAggregate`（定义在 `agents/task_continuity/state.py` L92），把「怎么合并」（`merge_task_notes`，L81）和「怎么聚合/序列化」拆成两层。什么时候需要它：当你的字段不只要「二元合并」，还要控制它在 checkpoint 里怎么落地、怎么按快照折叠时。绝大多数自定义字段用不上，但看到 `Annotated[T, SomeClass(...)]` 别以为是笔误。

## 一个帮你判断的规则

> 如果你不确定——先用 `NotRequired`。当你发现数据在丢失（被覆盖了），再改成 `Annotated` + 自定义 reducer。

状态字段从 `NotRequired` 迁到 `Annotated` 只需要改类型标注 + 加 reducer 函数，不破坏现有逻辑。

**v2.2.0 加一条边界**：`messages` 这个字段**不在**这两条路里。它在 delta 模式下由 `DeltaChannel(merge_message_writes, ...)` 承载（`thread_state.py` L487-497），两种 mode 对应两个不同的 schema，取法只有一个——`get_thread_state_schema(mode)`（L520-530）。别自己去改 `messages` 的标注。

## 迁移与 mode 的相互作用（v2.2.0 必读）

「从 `NotRequired` 迁到 `Annotated` 只要改标注」这句话有一个前提：**你的字段只在 lead agent 的 state 里**。2.2.0 的装配路径有两个动作会让这个前提失效：

1. lead agent 的 schema 由 `get_thread_state_schema(mode)` 现取（`agents/lead_agent/agent.py` L1255）；
2. 每个 middleware 的 `state_schema` 会被 `normalize_middleware_state_schemas(middlewares, mode)` 逐项替换成适配版本（L1248，实现于 `thread_state.py` L558-571，delta 模式才改动、用 `copy.copy` 换 `state_schema` 属性）。

所以：**你的中间件看到的 `state` 和你声明的 schema 类在 delta 模式下不是同一个类对象**。凡是「`isinstance(state, MyState)`」「`type(state).__name__` 比对」「把 schema 类当字典 key 缓存」的写法，都会在 delta 模式下失配。判断当前 schema 一律用 `adapt_state_schema_for_mode(...)`（`thread_state.py` L541-550）或直接读注入的 schema，不要硬编码类。

另外，`NotRequired` 声明的是「这个 key 可以缺席」，**不是**「这个 key 不落盘」——要它不进 trace，得叠 AgentState 里用到的 `PrivateStateAttr`；要它不进调用方 input，得叠 LangChain 的 OmitFromInput 标记（`AgentState.structured_response` 就是这么做的，`langchain/agents/middleware/types.py` L352）。三个标记管三件不同的事，不要混。
