# Q9: 我写 agentic workflow，到底要不要改 state？

## 直接回答

**90% 的情况下不需要。** ThreadState 的 12 个字段 + messages 消息历史 + sandbox 文件系统，已经覆盖了大多数 agentic workflow 的需求。

**只有当你遇到以下三种情况之一时，才需要加字段：**

1. **你需要跨多轮追踪一个"标量"状态**（如任务完成百分比、自定义计数器），而且它不应该出现在用户可见的消息里
2. **多个 middleware 或 tool 需要同时写同一个数据**，且合并逻辑不是简单的"后来的覆盖前面的"
3. **你需要自定义字段来影响图的路由决策**（在条件边函数中读取它）

下面逐一展开。如果你想深入理解 state 概念本身，从 [01-what-is-state.md](01-what-is-state.md) 开始读。

---

## 为什么不改就能用

### 理由一：messages 就是你最好的"数据库"

Agent 的 messages 列表天然记录了所有上下文——用户说了什么、模型想了什么、工具执行了什么。模型每一轮都能看到完整历史。大多数 workflow 状态其实已经在 messages 里了。

**例子**：你想让 agent 审查代码。审查进度不需要额外字段——模型看到 `AIMessage("我来审查第3个文件")` 就知道进度在哪。

### 理由二：sandbox 文件系统传数据更简单

如果你需要在 agent 循环之间或 middleware 之间传大量数据（如中间计算结果、JSON 配置），写文件比加 state 字段更直接。

**例子**：你的 workflow 需要先抓取 100 个网页，再汇总分析。中间结果写 `workspace/results.json`，汇总阶段 `read_file` 读取——不需要加 state 字段。

### 理由三：ThreadState 已经很全了

| 你想做的事 | 用哪个已有字段 | 哪个 middleware 在管 |
|-----------|--------------|-------------------|
| 产出文件给用户 | `artifacts` | SandboxMiddleware |
| 追踪待办事项 | `todos` | TodoListMiddleware |
| 委托子任务 | `delegations` | DurableContextMiddleware |
| 加载 skill | `skill_context` | SkillActivationMiddleware |
| 设定目标 | `goal` | Goal evaluator |
| 记住用户偏好 | memory 系统（不在 state 里） | MemoryMiddleware |

---

## 什么时候需要加

### 场景 1：跨轮追踪标量状态

**例**：你写了一个 code review workflow，agent 审查 10 个文件。你想在 middleware 里追踪"已审查了几个"，并在最后给用户一个总结。这个数字不应该出现在用户可见的 messages 里。

**方案**：加 `review_count: NotRequired[int]`。

### 场景 2：多个 middleware 同时写，需要自定义合并

**例**：你的 workflow 有多个并行子任务，每个子任务完成后往一个列表里追加结果。你不想后面的结果把前面的覆盖掉。

**方案**：加 `sub_results: Annotated[list[str], merge_sub_results]`，自己写 `merge_sub_results` 做去重追加。

### 场景 3：数据不应该进 messages

**例**：你处理敏感数据（如 API key、内部配置），不想让它出现在 model 的上下文里（会被 LLM 看到）。messages 里的内容全会发给 LLM。

**方案**：加一个 state 字段存储它。用 `PrivateStateAttr` 标记确保它不会出现在 trace 里。

---

## 快速决策流程

```
你想存一个值让它在 agent 循环间传递
    │
    ├── 它应该被 LLM 看到？
    │   └── YES → 放 messages 里（用 ToolMessage 或 AIMessage）
    │
    ├── 它是文件？
    │   └── YES → 写 sandbox 文件系统
    │
    ├── 它是纯量（int/str/bool），只有一个 middleware 写它？
    │   └── YES → NotRequired[T]
    │
    ├── 它是列表/字典，多个 middleware 可能同时写？
    │   └── YES → Annotated[T, custom_reducer]
    │
    └── 它需要影响路由决策？
        └── YES → 加字段 + 在条件边函数中读取
```

---

## 下一步

- [01-what-is-state.md](01-what-is-state.md) —— State 到底是什么（从零开始）
- [02-langgraph-vs-deerflow.md](02-langgraph-vs-deerflow.md) —— 哪些是 LangGraph 的，哪些是 DeerFlow 加的
- [03-notrequired-vs-annotated.md](03-notrequired-vs-annotated.md) —— 两种扩展机制的详细对比
- [04-practical-recipes.md](04-practical-recipes.md) —— 实战配方：不改 state 的替代方案 + 必须要改时的代码模板
