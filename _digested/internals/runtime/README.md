---
title: "Runtime — 运行基础设施"
description: "deerflow.runtime 是 DeerFlow 自建的运行基础设施：图执行、事件流发布/订阅、运行生命周期、序列化与 LLM 调用日志；v2.2.0 的主轴是「终态要有凭据、活着要有信号、归属要显式、进展要有证据」。"
type: index
topics: [runtime, run-manager, stream-bridge, journal]
---

# Runtime — 运行基础设施

> **定位**：`deerflow.runtime` 回答「一次 run 怎样被执行、发布、记账、收尾与恢复」：RunManager 管生命周期与所有权，StreamBridge 管 SSE 发布/订阅，RunJournal 管 LLM 调用日志与 token，serialization 管对象 → JSON。
> **边界**：checkpoint 的存储表示与历史缓存去 [../persistence/](../persistence/README.md)；事件目录、日志与追踪的观测视角去 [../../observability/](../../observability/README.md)；agent loop 本身去 [../agent-loop/](../agent-loop/README.md)。Gateway 侧的租约恢复消费方、SSE 响应头等属 app 层，不在本目录。

## 阅读路径

1. **先看**：[01-run-manager.md](01-run-manager.md) — 运行 CRUD、状态机、多任务策略、lease 与孤儿恢复。
2. **再看**：[02-stream-bridge.md](02-stream-bridge.md) — SSE 发布/订阅、心跳、gap、memory/Redis 两后端与生产者租约。
3. **深入**：[05-run-ownership-and-rollback.md](05-run-ownership-and-rollback.md) — multi-worker 归属、取消语义、rollback 与 delivery receipt。

## 本篇目

| 文件 | 主题 | 深度 |
|---|---|---|
| [01-run-manager.md](01-run-manager.md) | RunManager：CRUD、状态机、多任务策略、SQLite 事务保护、幂等准入、execution fence、`reserve_thread_operation` | 概览 |
| [02-stream-bridge.md](02-stream-bridge.md) | StreamBridge 协议、心跳/gap、memory/Redis 后端、Redis 生产者租约与 `ping()` | 深入 |
| [03-serialization.md](03-serialization.md) | `serialize()` 的 values/messages/custom 三模式、LangChain → OpenAI Chat Completions 转换 | 概览 |
| [04-journal.md](04-journal.md) | RunJournal：回调 → 事件、token 分桶、消息去重、进度刷盘、写入隔离与证据结算 | 深入 |
| [05-run-ownership-and-rollback.md](05-run-ownership-and-rollback.md) | lease/heartbeat/orphan recovery、fenced cancel、rollback、delivery receipt | 深入 |
| [goal-continuation.md](goal-continuation.md) | Goal 续跑：evaluator、blocker、no-progress breaker、stand-down、`goal_outcome` | 深入 |
| [task-continuity.md](task-continuity.md) | opt-in 任务笔记 + 压缩历史召回：三工具、thread 级 SQLite、retention 与作用域 | 深入 |

## 宪章与约定

- 包内有独立宪章：[backend/packages/harness/deerflow/runtime/AGENTS.md](../../../backend/packages/harness/deerflow/runtime/AGENTS.md)（397 行）；写作纪律沿用 [根 README](../README.md)。

## 相关目录

- [internals 父级](../README.md) — 13 个内部机制子目录的总入口。
- [agent-loop](../agent-loop/README.md) — `run_agent()` 消费的 loop 本体。
- [persistence](../persistence/README.md) — checkpointer、Store 与迁移链。
- [observability](../../observability/README.md) — RunEvent、trace 与 Console 的观测面。

## 速览

- **终态是有凭据的事实**：`_persist_status()` 拿到 `TerminalCommitProof` 的 ACK 才算落地；`terminal_commit_pending` 是一等状态且租约继续续；`run.terminal`（协议 v1）+ `finish_evidence()` → `JournalSealReceipt`（`evidence_state = complete` 或 `partial`），未知结果永久隔离。
- **每个「活着」与「谁写的」都显式**：per-run 续租 + 本地 `call_later` 截止守卫、`try_start` 启动栅栏、`ExecutionFence`、`reserve_thread_operation`；Redis 生产者租约 30s TTL / 10s 续租 / token 比对 Lua，END 与数据在同一次原子调用里判序；`evidence_origin` / `evidence_agent_id`、`run_origin.py` 的 `deerflow_origin`（只接受服务端盖章）、`client_context.py` 白名单、`secret_context.py` 脱敏。
- **Goal 的进展有工具级证据**：`goal_progress.py` 只存 `sha256([name, args, output_sha256, output_bytes])`，与文本签名并列为 no-progress 判据；达成写 `goal_outcome` 通道。
- **分页、幂等与历史同步**：`0023_run_change_seq` 稳定游标、`/runs/page` keyset 翻页、`Idempotency-Key` 重放（输入不同 409）、`0019_thread_incarnations` 与 #4696 的 `deerflow_seq` 盖章；sync #6/#7/#8 还带来事件循环卫生（#5217/#5224/#5335、#5112 的终态内存回收）、压缩/摘要修复（#5248/#4901/#5249）与 checkpoint 保留契约（#5051/#5255，见 persistence 页）。
- **新增/大改的横切件与关键设计决策**：2.2 新增 `keyed_lock.py`、`events/{message_identity,message_seq,terminal,evidence}.py`、`run_origin.py`、`client_context.py`、`assembly_evidence.py`、`checkpoint_mode.py`、`cancellation.py`、`thread_spans.py`、`context_keys.py`、`stream_modes.py`、`runs/stream_cleanup.py`，`checkpoint_state.py`、`context_compaction.py`、`store/*` 也有扩展，本域代码量增长约 45%；journal 只在 `on_llm_end` 写完整消息（不在 `on_llm_new_token`），`on_chat_model_start` 优先于 `on_llm_start`，不支持 LangGraph `events` 模式而用 `values` + `messages` 等效，ContextVar 做任务隔离，Langfuse 注入双路径共享。
