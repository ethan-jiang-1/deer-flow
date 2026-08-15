---
title: "结构化事件流：RunEventStore 与 RunJournal"
description: "DeerFlow 有一个 append-only 的 run 事件流：RunJournal 把 LangChain 回调标准化成 RunEvent，写入 RunEventStore。它是审计、回放、调试端点、subtask 卡片、workspace 审查的共同数据源。"
topics: [observability, run-events, journal, audit]
---

# 结构化事件流：RunEventStore 与 RunJournal

日志是给人 `grep` 的，事件流是给**程序**读的。DeerFlow 的 `RunEventStore` 是一份 append-only 的 run 记录，`RunJournal` 把 LangChain 回调标准化成 `RunEvent` 写进去。历史、调试、subtask、memory 审计、workspace 审查读的是同一批行的不同投影。

> RunJournal 的缓冲/刷盘/token 分桶细节 → [internals/runtime/04-journal.md](../internals/runtime/04-journal.md)。这里聚焦事件流的**契约和消费方式**。

## 事件目录（`deerflow/runtime/events/catalog.py`）

固定事件（`RunJournal` 产出）：

| event_type | category | 来源回调 |
|-----------|----------|---------|
| `run.start` | `trace` | 根 `on_chain_start()` |
| `run.end` | `outputs` | 根 `on_chain_end()` |
| `run.error` | `error` | `on_chain_error()` |
| `llm.human.input` | `message` | 首条 lead-agent 人类输入 |
| `llm.ai.response` | `message` | `on_llm_end()` |
| `llm.tool.result` | `message` | `on_tool_end()` |
| `llm.error` | `trace` | `on_llm_error()` |
| `context:memory` | `context` | `record_memory_context()` |
| `middleware:{tag}` | `middleware` | `record_middleware()` |

动态模式：`middleware:{tag}`（tag 限 1–21 字符），现有 tag = `guardrail`、`safety_termination`、`skill_activation`、`skill_secrets`。

其它生产者：`subagent.start` / `subagent.step` / `subagent.end`（`subagents/step_events.py`，批量 `put_batch`）；`workspace_changes`（`workspace_changes.record_workspace_changes()`）。

## 信封与顺序保证

| 字段 | 含义 |
|------|------|
| `thread_id` / `run_id` | 归属 |
| `seq` | **thread 全局**严格递增（不是 run 局部） |
| `event_type` / `category` | 固定名或文档化动态模式（type ≤32 字符，category ≤16） |
| `content` | 字符串或 JSON（`run.end.content` 故意 opaque，跨后端不保证嵌套一致） |
| `metadata` | 可过滤/审计元数据 |
| `created_at` | 带时区 ISO-8601 |

后端差异：memory 保留 Python 值；JSONL/DB 经 `json.dumps(default=str)`，非 JSON 嵌套值读回为字符串。**多进程/多 worker 部署必须 `run_events.backend: db`**（JSONL 只在单进程内保证 seq）。

## 消费方式（读同一批行的不同投影）

| 消费者 | 读取路径 |
|--------|---------|
| 前端线程历史 | `GET /api/threads/{id}/messages/page` → `list_messages()`，过滤 middleware 行、subagent AI 响应、被替代的 regenerate run |
| 单 run 消息 | thread-scoped / stateless `GET .../runs/{rid}/messages` → `list_messages_by_run()` |
| **调试/审计端点** | `GET /api/threads/{id}/runs/{rid}/events?event_types=&task_id=&limit=&after_seq=` → `list_events()` |
| 历史 subtask 卡片 | run-events 端点按 `task_id` 过滤 `subagent.step` |
| Memory 审计 | 过滤 `context:memory`，比 `content_sha256`（全文不重复进事件存储） |
| Workspace 审查 | `GET /api/threads/{id}/runs/{rid}/workspace-changes` → 最新 `workspace_changes` |

**调试端点**是生产排障的入口：`event_types` 过滤（如 `context:memory`、`run.error`、`middleware:guardrail`），`task_id` 翻 subagent 步，`after_seq` 前向游标翻页。

## token/成本不靠读事件行

`RunJournal` 在回调触发时**累计**用量，worker 把聚合写进 `RunRow`。不要从事件行反推 token 汇总。

## 已知缺口（`RUN_EVENT_STREAM.md`）

- tool-call 意图内嵌在 `llm.ai.response.content.tool_calls`，**不是**一级事件；丢失/超时的 tool result 可能没有专门 outcome 事件
- `run.end.metadata.status` 只是根图完成标记（恒 `success`）；生命周期以 `RunRow.status` 为准，worker 丢失可能不留终端事件
- loop 检测、deferred-tool 提升目前**不**发 middleware 事件
- 外部 Langfuse/LangSmith 是**并行**的 callback 管线，不读事件行，靠 trace metadata 关联
