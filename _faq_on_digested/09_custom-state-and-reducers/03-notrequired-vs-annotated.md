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
- 如果一个 node 返回了更新，另一个没返回这个 key，reducer 仍然被调用（new=None）

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

## 一个帮你判断的规则

> 如果你不确定——先用 `NotRequired`。当你发现数据在丢失（被覆盖了），再改成 `Annotated` + 自定义 reducer。

状态字段从 `NotRequired` 迁到 `Annotated` 只需要改类型标注 + 加 reducer 函数，不破坏现有逻辑。
