---
title: "Subagent — 子 Agent 系统"
description: "Lead Agent 把任务委派给后台子 Agent：容量准入、durable batch、受管子代理、RFC #4651 报告契约与上下文隔离。"
type: index
topics: [subagent, orchestration, delegation]
---

# Subagent — 子 Agent 系统

> **定位**：回答「复杂任务怎么被拆给后台子 Agent 并行跑、并发怎么限、结果怎么验收、父上下文怎么隔离」。核心是执行链路 + 容量准入 + durable batch + 报告契约。给设计委派、调并发或排查子 Agent 失败的人。
> **边界**：不覆盖 `task` / batch 工具的装配条件（见 [builtin-tools/D-task-toolsearch.md](../builtin-tools/D-task-toolsearch.md)），不覆盖 batch REST 端点的完整参考（见 [enterprise-operations/app-layer](../../enterprise-operations/app-layer/README.md)），前端进度展示见 [frontend/05-subagent-ui.md](../../frontend/05-subagent-ui.md)。

## 阅读路径

1. **先看**：[dual-threadpool-and-lifecycle.md](dual-threadpool-and-lifecycle.md) — Phase 1–5 的完整生命周期、容量准入与 stop reason。
2. **深入**：同篇「Durable Batch」「报告契约与收据引用验证」「验收清单」三节 — 批量窗口读取、`[rN]` 收据校验与确定性 acceptance checks。

## 本篇目

| 文件 | 主题 | 深度 |
|---|---|---|
| [dual-threadpool-and-lifecycle.md](dual-threadpool-and-lifecycle.md) | 单一持久隔离 loop、容量准入、durable batch 与仓储 API 契约、RFC #4651 报告/收据、stop reason 四轴、上下文与 checkpointer 隔离 | 深入 |

## 速览

- **发现与执行**：LLM 经 tool schema + system prompt 两个 channel 获知子 Agent 类型，`subagent_enabled` 是总开关；`task_tool` → `SubagentExecutor.execute_async()` → 持久隔离 loop + 容量准入 → 5s 轮询 + SSE。poller 意外退出时 registry 清理钉在持久隔离 loop 上（#5069）。另有 `/api/subagents` 管理员 CRUD（file/sql 双后端）与 `allowed_subagents` 委派作用域。
- **容量准入**：`config.yaml -> subagent_runtime` 的 `max_running` / `max_queued` / `admission_policy` / `queue_timeout_seconds`，进程级异步 FIFO 控制器。
- **Durable batch**：`subagent_batches` + `batch_task` / `batch_status` / `cancel_batch` / `read_batch_result`（有界窗口：`position` / `offset` / `max_chars` 1–8192 默认 4000 / `expected_revision` 64-hex；`restart_required` / `budget_too_small` / `next_offset` 协议）+ 租约驱动的 `SubagentBatchService` + `/api/threads/{thread_id}/subagent-batches`；per-item `acceptance_criteria` 持久化（migration 0021），由 `batch_acceptance.py` 用沙箱租约跑同一清单。仓储契约见正文「仓储层 API 契约」节。
- **报告契约（RFC #4651 layer 2）**：`report_contract.py` 强制 `[rN]` 收据引用 + 可验证 handle，`receipt_verification.py` 父侧校验真实性（建议性 `citation_resolved`），`acceptance_checks.py` 跑确定性清单（`file:` / `file_written:` / `tests_passed:`，不可判定一律 UNVERIFIED，Windows 路径 fail-closed）；verdict 经 delegation ledger 渲染，compaction 后 gap 仍可见。
- **stop reason 四轴与隔离**：`turn_capped` / `token_capped` / `loop_capped` / `model_length_capped` 均经 `consume_stop_reason()` 交回 executor，被截断的子 Agent 到 lead 是 `completed` + `stop_reason`；`prompt_overlay` 的 per-agent `prepend` / `append` 包在完整 system message 外，date-only context、knowledge scope / `knowledge_sources`（≤100）、opt-in `context_mode=snapshot`、上传发现、`execution_id` vs `tool_call_id`、checkpointer 与 summarization 继承各自独立。

## 宪章与约定

- 本目录无独立宪章；研究纪律沿用 [根 README](../../README.md)（不修改源码、`main` 只镜像上游、笔记只落在 `ethan`）。
- 文件名沿用历史（"dual-threadpool"），正文已同步 #6 的「单一持久隔离 loop + 容量准入」模型；旧双线程池描述不再有效。

## 相关目录

- [builtin-tools/](../builtin-tools/README.md) — `task` 与 batch 三件套的装载条件。
- [sandbox/](../sandbox/README.md) — 验收清单执行所依赖的沙箱租约。
- [lead-agent/](../lead-agent/README.md) — 委派发起方的工厂与 ThreadState。
- [enterprise-operations/app-layer/](../../enterprise-operations/app-layer/README.md) — `/api/subagents` 与 batch 的 REST 面。
