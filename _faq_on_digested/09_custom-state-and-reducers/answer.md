# Q9: 扩展 ThreadState

## ThreadState 现有字段

DeerFlow 的 `ThreadState` 已有 12 个字段：`messages`、`sandbox`、`thread_data`、`title`、`artifacts`、`todos`、`goal`、`uploaded_files`、`viewed_images`、`promoted`、`delegations`、`skill_context`、`summary_text`。

源码：`deerflow/agents/thread_state.py`

## 扩展方式

```python
from typing import NotRequired, Annotated
from deerflow.agents.thread_state import ThreadState

class MyAgentState(ThreadState):
    review_count: NotRequired[int]                       # 简单覆盖
    approved_prs: Annotated[list[str], merge_approved]   # 自定义 reducer
    last_review_at: NotRequired[str | None]              # 简单覆盖
```

传给 agent：
```python
agent = create_deerflow_agent(
    model=model,
    features=RuntimeFeatures(sandbox=True),
    state_schema=MyAgentState,  # ← 这里
)
```

## NotRequired[T] — 简单覆盖

**什么时候用**：只有一个 node 会写这个字段，或者后来的值完全覆盖旧值就行。

**原理**：LangGraph 的默认行为是最后一个 node 写入的值生效（LastValue）。`NotRequired` 是 TypedDict 的类型标注，表示这个 key 可以不存在。

```python
class MyState(ThreadState):
    review_count: NotRequired[int]       # 只被 review_middleware 写
    last_review_at: NotRequired[str]     # 只被 review_middleware 写
```

在 middleware 中写入：
```python
class ReviewTrackingMiddleware(AgentMiddleware):
    def after_model(self, state, runtime):
        if self._is_review_complete(state):
            count = state.get("review_count", 0) + 1
            return {"review_count": count, "last_review_at": datetime.now().isoformat()}
        return None
```

## Annotated[T, reducer] — 自定义合并

**什么时候用**：多个 node 可能**在同一个 superstep** 同时写这个字段。需要用 reducer 定义合并逻辑。

**原理**：`Annotated[list[str], merge_approved]` 告诉 LangGraph：当两个 node 同时返回 `{"approved_prs": ["a"]}` 和 `{"approved_prs": ["b"]}`，调用 `merge_approved(["a"], ["b"])` 得到 `["a", "b"]`。

### 示例：去重追加

```python
def merge_approved(existing: list[str], new: list[str]) -> list[str]:
    """追加 + 去重，保持顺序。"""
    seen = set(existing)
    result = list(existing)
    for item in new:
        if item not in seen:
            seen.add(item)
            result.append(item)
    return result

class MyState(ThreadState):
    approved_prs: Annotated[list[str], merge_approved]
```

### DeerFlow 自己的 reducer 参考

| Reducer | 行为 | 源码 |
|---------|------|------|
| `merge_artifacts` | 并集+去重 | `thread_state.py` |
| `merge_todos` | None=保留旧值，非None=覆盖 | `thread_state.py` |
| `merge_delegations` | 追加，同ID最新胜，终态保护，上限50 | `thread_state.py` |
| `merge_skill_context` | 按path去重，最近读取优先，上限8 | `thread_state.py` |
| `merge_promoted` | catalog-hash作用域，catalog变更时全量替换 | `thread_state.py` |

## 在 middleware 中读/写自定义 state

```python
class ReviewTrackingMiddleware(AgentMiddleware):
    def after_model(self, state, runtime):
        # 读
        count = state.get("review_count", 0)
        approved = state.get("approved_prs", [])

        # 检查是否刚完成审查
        last_msg = state["messages"][-1]
        if hasattr(last_msg, "tool_calls"):
            for tc in last_msg.tool_calls:
                if tc["name"] == "gh_pr_approve":
                    pr_num = tc["args"].get("pr_number", "unknown")
                    return {
                        "review_count": count + 1,
                        "approved_prs": [f"PR#{pr_num}"],
                    }
        return None
```

## 注意事项

1. **messages 字段不要自定义**——它已经有 `add_messages` reducer，覆盖会破坏消息流
2. **Reducer 函数必须是纯函数**——相同输入产生相同输出，无副作用
3. **None 的处理**——LangGraph 在 state 初始化时不调用 reducer；只在两个值都非 None 时才调用
4. **子 agent 的 state**——子 agent 使用全新 `ThreadState`，不会继承你的自定义字段。如果需要共享数据，用 sandbox 文件系统

## 关键源码

- `deerflow/agents/thread_state.py`：所有内置 reducer
- `deerflow/agents/factory.py:create_deerflow_agent()`：`state_schema` 参数
- LangGraph 文档：`Annotated` state 和 reducer 机制
