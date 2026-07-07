# State 到底是什么——从零开始

## 一句话

**State 是 agent 的"记忆笔记本"。** 图上每个 node 读这本笔记、做事、然后把更新写回去。下一个 node 看到的是更新后的笔记。

## 为什么需要 State

LangGraph 的 `StateGraph` 不是随便执行 node 的——每个 node 的执行结果需要通过 **reducer** 合并到 state 里，下一个 node 才能看到。没有 state，node 之间就是信息孤岛。

```
Node A: 调用 LLM → 返回 AIMessage("你好")
            │
            ▼
        LangGraph 把 AIMessage 追加到 state.messages
            │
            ▼
Node B: 从 state.messages 里看到 "你好"，基于它做下一步决策
```

## State 的数据结构

LangGraph 的 state 是一个 **TypedDict**（Python 的类型化字典）。每个 key 声明了类型和合并策略：

```python
class AgentState(TypedDict):
    messages: Required[Annotated[list[AnyMessage], add_messages]]
    #        ^^^^^^^^  ^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^
    #        必填      类型          合并策略（reducer）
```

- **`messages`**：key 的名字
- **`list[AnyMessage]`**：值的类型
- **`add_messages`**：reducer——当两个 node 都返回 `{"messages": [...]}` 时，怎么合并？`add_messages` 的答案是：追加到末尾
- **`Required`**：这个 key 必须有初始值，不能缺失

## Reducer 是什么

Reducer 是一个函数，签名是：

```python
def reducer(existing_value, new_value) -> merged_value:
    ...
```

LangGraph 在两个时机调用它：

1. **Node 返回更新时**：Node A 返回 `{"messages": [msg1]}`，state 里已有 `messages = [msg0]` → 调用 `add_messages([msg0], [msg1])` → 得到 `[msg0, msg1]`
2. **多个 node 在同一 superstep 返回更新时**：Node A 返回 `{"artifacts": ["a.txt"]}`，Node B 同时返回 `{"artifacts": ["b.txt"]}` → 调用 `merge_artifacts(["a.txt"], ["b.txt"])` → 得到 `["a.txt", "b.txt"]`

**如果没有自定义 reducer**（即普通的 `NotRequired[str]`），LangGraph 默认使用 `last_value`——后来的值直接覆盖旧值。

## 关键理解

1. **State 是整个 graph 共享的**——所有 node 看到同一份 state，不是每个 node 有自己的 state
2. **Reducers 定义了冲突解决规则**——当两个 node 同时写同一个 key 时，怎么合并？没有 reducer = 覆盖（last wins）
3. **messages 用 add_messages reducer**——消息列表只追加、不覆盖，这是 agent 能"记住"对话历史的根本原因
4. **State 不经过网络**——它是内存中的 Python 对象（checkpoint 时序列化到数据库）。node 读 state 是 O(1) 的字典查找
