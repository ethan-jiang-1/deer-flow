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

# 3. 把它挂上去——走扩展契约，不要改 core
#    见 extensions/AGENTS.md 的 middleware contributor；
#    core 侧的接入点是 build_middlewares()（agents/lead_agent/agent.py L485）。
```

> 🔄 同步 #8（v2.2.0）：旧版这里写「在 `build_middlewares` 中添加你的 middleware，或者在 `custom_middlewares` 参数中传入」——**`custom_middlewares` 这个入口已删除**，仓库根 `AGENTS.md` 的「Extension-first evaluation」把「把业务逻辑硬编码进 core」列为禁止项。现行做法是写一个 middleware contributor 交给扩展栈：结尾由 `compose_with_extensions(middlewares, AgentScope.LEAD, ...)` 统一合并（`agent.py` L790-792），合并只发生**一次**、且在 lead 专属中间件追加之后，所以你的中间件看到的是完整栈。另外**自定义 state 字段不要指望自动生效**——如果中间件自己声明了 `state_schema`，装配期 `normalize_middleware_state_schemas(...)`（`agent.py` L1248）会按 checkpoint mode 把它换成适配版本，而 lead agent 的 state schema 由 `get_thread_state_schema(mode)` 单独取（L1255）。要加字段，两处必须同时改到位。

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

原因：DeerFlow 的子 agent 使用**全新的 ThreadState**——子代理执行器里 `create_agent(...)` 硬编码 `state_schema=ThreadState` 且 `checkpointer=False`（`subagents/executor.py` L1205-1212），不继承你的自定义 state。子 agent 看不到你在父 agent state 里加的字段。

> 🔄 同步 #8（v2.2.0）核对结论：这条**依然成立**，但行号从「`agent.py` 里」更正到 `subagents/executor.py:1210`；同时子代理这次调用是 `checkpointer=False` 编译的——**子代理没有独立 checkpoint**，所以你在子代理里写的 state 字段连落盘都不会有。详见 [_digested/graph-engineering/06-langgraph-capability-surface.md](../../_digested/graph-engineering/06-langgraph-capability-surface.md) §3「子代理一次性执行」。

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

LangGraph 的规则：如果一个 node 不返回某个 key（返回值里没有这个 key），reducer 不被调用。只有**两个返回都有这个 key**时 reducer 才执行；但 `new=None` 的那次调用在 LangGraph 内部怎么处理，取决于 reducer 自己的签名与默认值。

这意味着：如果你用 `Annotated[list[str], merge]`，并且只有一个 middleware 返回了 `{"my_list": [...]}`，你的 reducer 大概率不会被调用——直接用这个值。**但别把它当保证**：上面 `my_reducer` / `merge_sub_results` 的模板都对 `None` 做了保护（`if new is None: return existing`），原因正是「reducer 可能收到 `None`」。自己写 reducer 时照抄这层保护，比赌它不被调用安全。

> 🔄 同步 #8（v2.2.0）补一条更硬的坑：**delta 模式下 `messages` 根本不是 `add_messages`**。`get_thread_state_schema("delta")` 返回的 schema 里 `messages` 是 `Annotated[list[AnyMessage], DeltaChannel(merge_message_writes, snapshot_frequency=...)]`（`thread_state.py` L487-499）。所以「坑 1 不要覆盖 messages 的 reducer」在 2.2.0 要升级成更强的表述：**连读 `__annotations__` 判断 `messages` 走什么通道都不可靠**——同一个 `ThreadState` 类在两种 mode 下被映射成两个不同的 schema，判断一律走 `get_thread_state_schema(mode)` 或 `adapt_state_schema_for_mode(...)`，别自己读注解。

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
| 影响路由决策 | 加字段 + 条件边读它；或让钩子返回 `jump_to`（须先 `hook_config(can_jump_to=...)` 声明） | ✅ 加字段 |
| 让工件可被追踪/消费 | `tool_artifacts` / `tool_artifact_processed`（2.2.0 已内置） | ❌ 不改 |
| 目标判定结果 | `goal_outcome`（2.2.0 已内置） | ❌ 不改 |
