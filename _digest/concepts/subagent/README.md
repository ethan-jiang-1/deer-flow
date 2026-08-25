---
title: "subagent"
description: "Lead Agent 把复杂任务委派给后台子 Agent 并行执行；含容量准入、durable batch、受管子代理与委派作用域。"
type: index
---

# subagent

Lead Agent 把复杂任务委派给后台子 Agent 并行执行。核心机制详见
[dual-threadpool-and-lifecycle.md](dual-threadpool-and-lifecycle.md)（该文件名沿用历史，正文已同步 #5：单一持久隔离 loop + 容量准入取代旧双线程池模型）。

## 主题索引

- **发现与触发**：LLM 通过 tool schema + system prompt 两个 channel 获知 subagent 类型；`subagent_enabled` 总开关；benefit-based routing。
- **生命周期与执行**：`task_tool` 装配 → `SubagentExecutor.execute_async()` → 持久隔离 loop + `SubagentExecutionCapacity` 容量准入 → 5s 轮询 + SSE 事件。
- **容量准入**：`config.yaml -> subagent_runtime`（`max_running`/`max_queued`/`admission_policy`/`queue_timeout_seconds`），进程级异步 FIFO 控制器。
- **Durable batch**：`config.yaml -> subagent_batches` + `batch_task`/`batch_status`/`cancel_batch` 工具 + 租约驱动的 `SubagentBatchService` + `/api/threads/{thread_id}/subagent-batches` REST API。
- **受管子代理**：`/api/subagents` 管理员 CRUD，file/sql 双后端持久化，`allowed_subagents` 委派作用域。
- **上下文与隔离**：isolated date-only context（`SubagentDateContextMiddleware`）、背景任务 ID 隔离（`execution_id` vs `tool_call_id`）、checkpointer 隔离、summarization 继承。

→ Back to [parent README](../README.md)
