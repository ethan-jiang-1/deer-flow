---
title: "可观测性"
description: "SSE 六类事件、心跳与断线续传的实现细节、tracing 的可选性，以及为什么「数据都在，但没有聚合视图」是当前的准确定位。"
topics: [governance, audit]
---

# 可观测性

可观测性回答「**现在正在发生什么**」。
审计回答「**过去发生了什么**」——两者用不同的数据，不能互相替代。

## 1. SSE 事件流

`StreamBridge`（`runtime/stream_bridge/base.py:66`，抽象基类）向实时订阅者推送事件。

| 事件类型 | 内容 |
|---------|------|
| `metadata` | run_id / thread_id / assistant_id |
| `updates` | State 值（title、artifacts、todos） |
| `events` | 自定义事件（见下） |
| `messages-tuple` | 逐 chunk 的消息增量 |
| `error` | 错误信息 |
| `end` | run 结束（携带累计 token usage） |

### 1.1 subagent 的六种 `task_*` 事件

`subagents/step_events.py` 定义了子代理生命周期的全部事件：

| 事件 | 行 | 性质 |
|---|---|---|
| `task_started` | `:215` | 开始 |
| `task_running` | `:226` | 运行中（流式内容在此推送） |
| `task_completed` | `:47-52` | **终止** |
| `task_failed` | `:47-52` | **终止** |
| `task_cancelled` | `:47-52` | **终止** |
| `task_timed_out` | `:47-52` | **终止** |

`_TERMINAL_EVENT_STATUS`（`:47-52`）只收录后四种——
这是一个有用的区分：**只有终止事件会更新持久化状态**，
`started`/`running` 是瞬时通知。

## 2. 心跳与断线续传

| 机制 | 实现 |
|---|---|
| 心跳间隔 | **15.0 秒**（`config/stream_bridge_config.py:10` `DEFAULT_HEARTBEAT_INTERVAL_SECONDS`） |
| 可配上限 | 86400 秒（`:11`） |
| 心跳载体 | `HEARTBEAT_SENTINEL`（`stream_bridge/base.py`，导出见 `backend/packages/harness/deerflow/runtime/stream_bridge/__init__.py:24`） |
| 断线续传 | `Last-Event-ID`（`stream_bridge/memory.py:33`） |

`memory.py:33` 的原文：

> reconnecting clients can replay buffered events from `Last-Event-ID`

### 2.1 续传的边界

| 场景 | 是否可续 |
|---|---|
| 同一进程内断线重连 | **是**（缓冲在内存里） |
| 进程重启 | **否**——内存缓冲丢失 |
| 多副本之间切换 | 取决于是否用 Redis 后端（见 [../cost/04-multi-instance.md](../cost/04-multi-instance.md)） |

**第二行是实际影响最大的一条**：Gateway 重启时，正在观看的客户端无法续上。

## 3. Tracing 是可选的

DeerFlow **不内建** OpenTelemetry 导出。
Langfuse / LangSmith 通过 callback 接入：

| 状态 | 后果 |
|---|---|
| 配了 tracing | 有 span 树，可看 LLM/tool/graph node 的耗时与嵌套 |
| **没配**（默认） | **这一层完全不存在** |

所以「三层审计」中的 tracing 层，在默认部署里是**空的**。
这是评估时必须先确认的一点。

## 4. 准确的能力定位：数据有，视图无

| 想要的能力 | 数据是否已产生 | 是否有现成视图 |
|---|---|---|
| 活跃 agent 状态 | **是**（SSE + journal） | **否** |
| tool 调用成功率 | **是**（journal） | **否** |
| 策略违规趋势 | **是**（journal 的 guardrail 事件） | **否** |
| token 消耗趋势 | **是**（usage_metadata） | **否** |
| 异常行为检测 | **否** | **否** |
| 跨层联合视图 | 分散在三个地方 | **否** |

**前四行是「能算但没界面」**：数据都在各自的存储里，需要外部系统（Grafana、BI、自建服务）去读并聚合。

**第五行不同**：异常行为检测需要基线建模，不是简单聚合，DeerFlow 完全没有。

## 5. 缺口

| 缺口 | 状态 | 边界 |
|---|---|---|
| 集群级聚合视图 | **无** | 无跨 agent / 跨用户的界面；RunJournal / tracing / SSE / Console 数据都能支撑，缺的是 UI |
| 行为异常检测 | **无** | 无基线、无阈值、无告警规则 |
| 内置 OTEL 导出 | **无** | 仅 callback 形式支持 Langfuse/LangSmith |
| 跨副本的事件续传 | **部分** | 内存缓冲；重启即丢 |
| 告警 | **无** | 没有任何内建告警通道 |
| 就绪/存活区分 | **有但不覆盖** | 有两个端点（见 [../cost/02-deployment-and-ops.md](../cost/02-deployment-and-ops.md) §1），但无运维说明 |

## 6. 与其他章节的关系

- 三层审计总览：[01-audit-chain.md](01-audit-chain.md)
- 事件覆盖矩阵：[03-event-coverage.md](03-event-coverage.md)
- 多实例与 Redis 后端：[../cost/04-multi-instance.md](../cost/04-multi-instance.md)
