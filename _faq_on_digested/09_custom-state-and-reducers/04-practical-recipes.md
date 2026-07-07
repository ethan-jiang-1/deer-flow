# 实战配方：改还是不改 state？

## 配方 0：不改 state——用 messages 追踪进度

### 场景

你的 agent 审查 5 个文件。你想追踪审了几个、还剩几个。

### 你不需要加 state

消息本身已经记录了进度。模型看到对话历史就知道审到哪了：

```
HumanMessage: "审查 src/ 下所有 .py 文件"
AIMessage(tool_calls=[bash("ls src/")])
ToolMessage: "main.py\nutils.py\ntest.py"
AIMessage(tool_calls=[read_file("src/main.py")])
ToolMessage: "def main(): ..."
AIMessage: "main.py 没有问题，继续看 utils.py"
...
```

**LLM 能从 messages 里推断进度。** 不需要你手动维护计数器。

### 什么时候这条不适用

- 你要给**用户**展示一个进度条（需要确定性计数，不能依赖 LLM 推断）
- 进度数据是给**另一个系统**读的（不是给 LLM）

---

## 配方 1：不改 state——用 sandbox 文件传数据

### 场景

你的 workflow 分两个阶段：
1. 抓取 10 个网页的内容
2. 汇总分析

### 方案

第一阶段把结果写文件：

```python
# agent 自动调用 bash
bash("echo '{\"results\": [...]}' > /mnt/user-data/workspace/scrape_results.json")
```

第二阶段读文件：

```python
# agent 自动调用 read_file
read_file("/mnt/user-data/workspace/scrape_results.json")
```

### 为什么不用 state

- 中间结果可能很大（几 MB）
- state 会被序列化到 checkpoint（数据库压力）
- 数据不需要被 LLM 直接看到（LLM 通过 tool call 读文件，结果进 messages）

---

## 配方 2：不改 state——用 memory 系统记偏好

### 场景

你的 agent 多次被同一个用户使用。用户说"我喜欢简洁的回答"。你想记住这个偏好。

### 方案

用 DeerFlow 的 memory 系统（不在 state 里），不是加 state 字段。

Memory 系统会自动提取用户偏好并存为 facts，下次对话注入 `<memory>` 标签。你不需要改任何代码。

---

## 配方 3：加 NotRequired——追踪简单计数器

### 场景

你在写一个 middleware，想追踪 agent 在当前 run 里总共调用了多少次 tool。

### 方案

```python
# 1. 扩展 ThreadState
from deerflow.agents.thread_state import ThreadState
from typing import NotRequired

class ToolTrackingState(ThreadState):
    tool_call_count: NotRequired[int]

# 2. 写 middleware
from langchain.agents.middleware import AgentMiddleware

class ToolCounterMiddleware(AgentMiddleware):
    def after_model(self, state, runtime):
        last_msg = state["messages"][-1]
        new_calls = len(getattr(last_msg, "tool_calls", []) or [])
        if new_calls > 0:
            count = state.get("tool_call_count", 0) + new_calls
            return {"tool_call_count": count}
        return None

# 3. 传给 create_agent
from deerflow.agents.lead_agent import make_lead_agent
# 需要在 build_middlewares 中添加你的 middleware
# 或者在 custom_middlewares 参数中传入
```

**为什么 NotRequired 就够了**：只有这一个 middleware 写 `tool_call_count`，不存在多 writer 冲突。

---

## 配方 4：加 Annotated + 自定义 reducer——收集并行结果

### 场景

你的 workflow 启动多个并行子任务（通过 `task` tool），每个子任务完成后汇报一个结果路径。你需要收集所有结果路径，去重后作为一个列表。

### 方案

```python
# 1. 定义 reducer
def merge_sub_results(existing: list[str] | None, new: list[str] | None) -> list[str]:
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

# 2. 扩展 ThreadState
class ParallelWorkflowState(ThreadState):
    sub_results: Annotated[list[str], merge_sub_results]

# 3. 在 middleware 中读取子任务结果
class SubResultCollectorMiddleware(AgentMiddleware):
    def after_model(self, state, runtime):
        # 检查是否有子任务刚完成
        # ... 你的逻辑 ...
        new_results = [ ... ]  # 从 delegations 中提取新完成的结果
        if new_results:
            return {"sub_results": new_results}
        return None
```

**为什么需要自定义 reducer**：多个子任务可能在同一轮完成，LangGraph 会把它们的更新合并。用 `last_value` 会丢数据，必须用去重追加。

---

## 配方 5：子 agent 间共享数据——走 sandbox，不走 state

### 场景

你的主 agent 先后调了两个子 agent：第一个生成代码，第二个审查代码。第二个需要看到第一个的输出。

### 方案

**通过 sandbox 文件系统传递，不要试图通过 state 传递。**

原因：DeerFlow 的子 agent 使用**全新的 ThreadState**（`agent.py` 里给子 agent 传的是 `state_schema=ThreadState`，不继承你的自定义 state）。子 agent 看不到你在父 agent state 里加的字段。

```python
# 子 agent #1 产出代码
bash("cat > /mnt/user-data/workspace/generated_code.py << 'EOF' ... EOF")

# 子 agent #2 审查
read_file("/mnt/user-data/workspace/generated_code.py")
```

**如果你需要在父 agent 和子 agent 间传结构化数据**：写 JSON 文件到 workspace，子 agent 读文件。

---

## 常见坑

### 坑 1：不要在 messages 上加自定义 reducer

```python
# ❌ 千万不要
class BadState(ThreadState):
    messages: Annotated[list[AnyMessage], my_custom_reducer]
```

`messages` 已经有 `add_messages` reducer，覆盖它会破坏整个消息流。agent 会丢失对话历史、tool call 匹配失败、routing 出错。

### 坑 2：子 agent 看不到你的自定义字段

```python
class MyState(ThreadState):
    my_data: NotRequired[str]

# ❌ 期望子 agent 能读 my_data —— 它不能
# 子 agent 用的是全新的 ThreadState()，不是 MyState()
```

**解决方案**：通过 sandbox 文件系统或 messages 传递数据给子 agent。

### 坑 3：None 值不触发 reducer

LangGraph 的规则：如果一个 node 不返回某个 key（返回值里没有这个 key），reducer 不被调用。只有**两个返回都有这个 key**时 reducer 才执行。

这意味着：如果你用 `Annotated[list[str], merge]`，并且只有一个 middleware 返回了 `{"my_list": [...]}`，reducer 不会被调用——直接用这个值。

### 坑 4：别往 state 里放大文件

State 会被 checkpoint（序列化到数据库）。如果你往 state 里放一个 10MB 的 base64 图片，每次 checkpoint 都写 10MB。大文件放 sandbox 文件系统。

---

## 决策矩阵

| 你的需求 | 用这个方案 | 要不要改 state |
|---------|-----------|--------------|
| 追踪对话进度 | messages 列表 | ❌ 不改 |
| 中间计算结果 | sandbox 文件 | ❌ 不改 |
| 用户偏好 | memory 系统 | ❌ 不改 |
| 单个 middleware 的简单计数器 | `NotRequired[int]` | ✅ 加字段 |
| 多个 middleware 同时写一个列表 | `Annotated[list, reducer]` | ✅ 加字段 + reducer |
| 敏感数据不进 messages | `NotRequired[str]`（可选 `PrivateStateAttr`） | ✅ 加字段 |
| 子 agent 间传数据 | sandbox 文件 | ❌ 不改 |
| 影响路由决策 | 加字段 + 条件边读它 | ✅ 加字段 |
