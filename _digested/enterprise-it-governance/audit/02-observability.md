---
title: "可观测"
description: "SSE 事件流、心跳重连、OTEL 集成、缺失的 Fleet Dashboard。"
topics: [governance, audit]
---

# 可观测

SSE 事件流、心跳重连、OTEL 集成、缺失的 Fleet Dashboard。

## 可观测

### SSE 事件流

`StreamBridge` 通过 SSE 向实时 subscriber 推送事件：

| 事件类型 | 内容 |
|---------|------|
| `metadata` | run_id, thread_id, assistant_id |
| `updates` | State values（title, artifacts, todos） |
| `events` | 自定义事件（subagent 状态、tool 进度）——包括 `task_started`, `task_running`, `task_completed`, `task_failed`, `task_timed_out`, `task_cancelled` |
| `messages-tuple` | 逐 chunk 的消息增量（AI text delta, tool_call, tool_result） |
| `error` | 错误信息 |
| `end` | run 结束（携带累计 token usage） |

### 心跳与重连

`MemoryStreamBridge` 15 秒无事件时发 `HEARTBEAT_SENTINEL` 保持连接。`Last-Event-ID` 支持 subscribe 时续传。

### OTEL / External Monitor 集成

DeerFlow 不直接集成 OpenTelemetry 或外部监控系统。但 Langfuse/LangSmith tracing callback 可以集成到外部平台。如果企业有自建监控基础设施，需要通过这些 callback 桥接。

### 缺失：Fleet Dashboard

DeerFlow 没有 agent 级别的聚合仪表盘。IT 管理者无法在一个界面看到：

- 所有活跃 agent 的状态
- Tool 调用成功率/失败率
- 策略违规趋势
- Token 消耗趋势
- 异常行为检测

**行业方向：** Microsoft Agent Governance Toolkit 提供 Agent Map 可视化；TrueFoundry Agent Gateway 提供统一的可观测仪表盘。DeerFlow 的数据（RunJournal、tracing span、SSE events）**能**支撑这些能力，只是目前没有内建 UI。

