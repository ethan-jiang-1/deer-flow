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
| `values` | State 值（title、artifacts、todos） |
| `messages` | 逐 chunk 的消息增量（`messages-tuple` 的 stream_mode 映射） |
| `custom` | 自定义事件 |
| `error` | 错误信息 |
| `end` | run 结束；Gateway SSE 的 `data` 为 `null`，**不携带**累计 usage |
| `gap` | 事件缺口标记 |

**注意 stream_mode 与 SSE 事件名不是一回事**：`messages-tuple` 在
`stream_modes.py:46` 映射为 `messages`；`updates` 在 worker 里发布为 `values`。
`end` 的 usage 只在嵌入式 `client.py:1312` 有，Gateway SSE 的 `end` 是空 data。

### 1.1 subagent 的六种 `task_*` 事件

`subagents/step_events.py` 负责把 `task_*` 映射为 `subagent.*`，**不是发射点**；
实际发射在 `tools/builtins/task_tool.py:1121`、`:1165`、`:1183`。

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

DeerFlow 的内建 OTel 支持是 **Monocle**（可选，默认关，`tracing_config.py:164-168`、
`monocle.py:24-49`）。Langfuse / LangSmith 通过 LangChain callback 接入：

| 状态 | 后果 |
|---|---|
| 配了 tracing | 有 span 树，可看 LLM/tool/graph node 的耗时与嵌套 |
| **没配**（默认） | **这一层完全不存在** |
| 启用 Monocle | 走 OTel exporter；不是默认 |

所以「审计链路」中的 tracing 层，在默认部署里是**空的**。
这是评估时必须先确认的一点。

## 4. 准确的能力定位：有单用户视图，无跨用户/集群视图

| 想要的能力 | 数据是否已产生 | 是否有现成视图 |
|---|---|---|
| 活跃 agent 状态 | **是**（SSE + journal） | **部分**（Console `/stats` 的 `active_runs`，当前用户） |
| tool 调用成功率 | **是**（journal） | **否** |
| 策略违规趋势 | **是**（journal 的 guardrail 事件） | **否** |
| token 消耗趋势 | **是**（usage_metadata） | **部分**（Console `/usage` 按日 + per-model） |
| 异常行为检测 | **否** | **否** |
| 跨层联合视图 | 分散在三个地方 | **否** |

**前四行不是「完全没视图」**：Console 提供**当前用户**的 stats/runs/usage 聚合
（`routers/console.py:289-360`、`:448-457`），但**没有跨用户/集群视图**，
也没有前端仪表盘。要集群级聚合，仍需外部系统去读并聚合。

**第五行不同**：异常行为检测需要基线建模，不是简单聚合，DeerFlow 完全没有。

## 5. 缺口

| 缺口 | 状态 | 边界 |
|---|---|---|
| 集群级聚合视图 | **无** | 无跨 agent / 跨用户的界面；Console 只做单用户，RunJournal / tracing / SSE 数据都能支撑 |
| 行为异常检测 | **无** | 无基线、无阈值、无告警规则 |
| 内置 OTEL 导出 | **部分** | Monocle OTel 可选（默认关）；无通用 OTLP 导出 |
| 跨副本的事件续传 | **有但不覆盖** | redis bridge 支持 `Last-Event-ID`；memory bridge 才重启即丢 |
| 告警 | **无** | 没有任何内建告警通道 |
| 就绪/存活区分 | **有但不覆盖** | 有两个端点（见 [../cost/02-deployment-and-ops.md](../cost/02-deployment-and-ops.md) §1），但无运维说明 |

## 6. 与其他章节的关系

- 审计链路总览：[01-audit-chain.md](01-audit-chain.md)
- 事件覆盖矩阵：[04-event-coverage.md](04-event-coverage.md)
- 多实例与 Redis 后端：[../cost/04-multi-instance.md](../cost/04-multi-instance.md)
