---
title: "实时观测：SSE 事件流与 StreamBridge"
description: "StreamBridge 通过 SSE 把一次 run 的实时增量推给前端/IM channel。事件类型、心跳/续传、memory vs redis 后端。这是唯一'活着'的观测面，但保留上限决定了它不是完整回放。"
topics: [observability, sse, streaming, stream-bridge]
---

# 实时观测：SSE 事件流与 StreamBridge

前四层是"事后/聚合"观测，`StreamBridge` 是唯一**实时**的观测面——它把一次 run 的增量推给实时订阅者（前端、IM channel）。

## SSE 事件类型

| 事件 | 内容 |
|------|------|
| `metadata` | `run_id` / `thread_id` / `assistant_id` |
| `updates` | State 值（`title` / `artifacts` / `todos`） |
| `events` | 自定义事件（subagent 状态、tool 进度）：`task_started` / `task_running` / `task_completed` / `task_failed` / `task_timed_out` / `task_cancelled` |
| `messages-tuple` | 逐 chunk 消息增量（AI text delta、tool_call、tool_result） |
| `error` | 错误信息 |
| `end` | run 结束（携带累计 token usage） |

`task_running` 携带 subagent 累计 token 快照，所以折叠的 workspace 卡片能在不重新计算父 run 总计的情况下更新。

## 心跳与续传

- `MemoryStreamBridge` **15 秒无事件**发 `HEARTBEAT_SENTINEL` 保活
- `Last-Event-ID` 支持订阅时续传
- 语法合法但**早于保留水位**的 `Last-Event-ID`（或掉队订阅者）→ `StreamGap`（id-less `gap` 事件），**run 保持 active**，不因重连失败杀掉 run

## 保留上限（关键限制）

memory 和 redis `StreamBridge` 只保留 `stream_bridge.queue_maxsize` 个 **data 事件**。所以 SSE 是**实时窗口**，不是完整回放——完整历史在 `RunEventStore`（`02`），SSE 只保证"正在发生的"。

- **memory**：单进程。语法上 numeric 但低于水位的 cursor 保守视为 gap
- **redis**：跨实例，`stream_ttl_seconds`（TTL 在 `publish()`/`publish_end()` 滚动刷新）作为泄漏保险；XREAD 阻塞只当 wake-up，之后重复原子快照；rolling TTL 不是 run timeout

## 与事件流的分工

| | StreamBridge SSE | RunEventStore |
|--|------------------|---------------|
| 时机 | 实时窗口 | 持久、append-only |
| 消费 | 前端 / IM channel | 历史 / 调试 / 审计端点 |
| 保留 | `queue_maxsize` | 全量（DB） |

> 实时流是"用户体验 + 运维看一眼"，审计/回放/取证必须走事件流。
