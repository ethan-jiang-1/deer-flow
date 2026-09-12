---
title: "subagent"
description: "Lead Agent 把复杂任务委派给后台子 Agent 并行执行；含容量准入、durable batch（含验收清单）、受管子代理、委派作用域与 RFC #4651 报告契约/收据校验。"
type: index
---

# subagent

Lead Agent 把复杂任务委派给后台子 Agent 并行执行。核心机制详见
[dual-threadpool-and-lifecycle.md](dual-threadpool-and-lifecycle.md)（该文件名沿用历史，正文已同步 #6：单一持久隔离 loop + 容量准入取代旧双线程池模型，新增 RFC #4651 layer 2 报告契约与验收体系）。

## 主题索引

- **发现与触发**：LLM 通过 tool schema + system prompt 两个 channel 获知 subagent 类型；`subagent_enabled` 总开关；benefit-based routing。
- **生命周期与执行**：`task_tool` 装配 → `SubagentExecutor.execute_async()` → 持久隔离 loop + `SubagentExecutionCapacity` 容量准入 → 5s 轮询 + SSE 事件；poller 意外退出时 registry 清理钉在持久隔离 loop 上（#5069）。
- **容量准入**：`config.yaml -> subagent_runtime`（`max_running`/`max_queued`/`admission_policy`/`queue_timeout_seconds`），进程级异步 FIFO 控制器。
- **Durable batch**：`config.yaml -> subagent_batches` + `batch_task`/`batch_status`/`cancel_batch` 工具 + 租约驱动的 `SubagentBatchService` + `/api/threads/{thread_id}/subagent-batches` REST API；per-item `acceptance_criteria` 持久化（migration 0021）并由 `batch_acceptance.py` 用沙箱租约跑同一清单。
- **报告契约与验收（RFC #4651 layer 2）**：`report_contract.py` 强制 `[rN]` 收据引用 + 可验证 handle，`receipt_verification.py` 父侧校验引用真实性（建议性 `citation_resolved`），`acceptance_checks.py` 确定性验收清单（`file:`/`file_written:`/`tests_passed:`，不可判定一律 UNVERIFIED，Windows 路径 fail-closed）；verdict 经 delegation ledger 渲染，compaction 后 gap 仍可见。
- **受管子代理**：`/api/subagents` 管理员 CRUD，file/sql 双后端持久化，`allowed_subagents` 委派作用域。
- **上下文与隔离**：isolated date-only context（`SubagentDateContextMiddleware`）、opt-in 父上下文快照（`context_mode=snapshot`，`ParentContextSnapshot`）、历史上传发现（`list_uploaded_files` + uploaded_files 快照边界）、背景任务 ID 隔离（`execution_id` vs `tool_call_id`）、checkpointer 隔离、summarization 继承。

→ Back to [parent README](../README.md)
