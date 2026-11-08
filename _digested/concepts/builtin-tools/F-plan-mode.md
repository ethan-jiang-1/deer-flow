---
title: "F. Plan Mode"
description: "## write_todos"
topics: [tools, builtin, sandbox-tools]
---

# F. Plan Mode

---

## write_todos

**来源**: LangChain `TodoListMiddleware`，由 DeerFlow 的 `TodoMiddleware`（middleware 位置 10）包装
**加载条件**: `runtime.config.configurable.is_plan_mode: true`
**Tool Name**: `write_todos`

### 用途

把复杂任务分解为 todo 列表，分步执行并追踪状态。LLM 可以创建、更新、完成、删除 todo。

### 运行时启用

```python
# 调用方式
config = {
    "configurable": {
        "thread_id": thread_id,
        "is_plan_mode": True,
    }
}
```

或通过 API 参数传入。

### Todo 状态

| 操作 | 说明 |
|------|------|
| `todo_start` | 开始一个 todo（标记为 in_progress） |
| `todo_complete` | 完成一个 todo |
| `todo_update` | 更新 todo 内容 |
| `todo_remove` | 删除一个 todo |

### 约束

- 同一时间只能有 **1 个** todo 处于 `in_progress`
- 当前 todo 必须完成后才能开始下一个
- 状态通过 `ThreadState.todos` 追踪

### DeerFlow 的增强

`TodoMiddleware` 包装了 LangChain 原版 `TodoListMiddleware`，增加了：

1. **上下文丢失检测**: 检测 todo 列表是否出现了与对话历史不一致的状态
2. **完成提醒**: 所有 todo 完成时自动提示用户
3. **middleware 链位置**: 在位置 10，处于 SummarizationMiddleware 和 TokenUsageMiddleware 之间

### 与 task tool 的区别

| | write_todos | task |
|------|-------------|------|
| 粒度 | 步骤追踪（内部） | 任务委派（外部） |
| 并发 | 串行，1 个 active | 最多 3 个并发子 Agent |
| 工具隔离 | 主 Agent 自己执行 | 子 Agent 独立上下文 |
| 状态 | ThreadState.todos | SubagentExecutor + 后台线程 |
