---
title: "实时观测：SSE 事件流与 StreamBridge"
description: "StreamBridge 通过 SSE 把一次 run 的实时增量推给前端/IM channel。事件类型、心跳/续传、memory vs redis 后端、v2.2.0 的 producer lease 与 SSE 反压缩响应头。这是唯一'活着'的观测面，但保留上限决定了它不是完整回放。"
topics: [observability, sse, streaming, stream-bridge, producer-lease]
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

## 🆕 v2.2.0：SSE 响应头（`app/gateway/sse_headers.py`）

新增 28 行的共享模块，**所有** SSE 端点统一从这里取头（不再各路由手写）：

| 头 | 值 | 为什么 |
|----|----|--------|
| `Cache-Control` | `no-cache, no-transform`（`SSE_CACHE_CONTROL`，`sse_headers.py:12`） | `no-transform` 告诉压缩型代理（例如 `pnpm start` 的 Next.js rewrite 代理）**不要** gzip 响应体。压缩代理必须缓冲到够出块才发，去掉它 SSE 帧会成批到达浏览器而不是边产生边到 |
| `Connection` | `keep-alive` | 长连接 |
| `X-Accel-Buffering` | `no` | nginx 侧的同一个开关 |
| `Content-Location` | 仅建 run 的路由传入（`sse_response_headers(content_location=...)`，`sse_headers.py:15`） | LangGraph SDK 靠它读 run id |

**观测意义**：如果你在前端"看不到实时增量、只见整段一次性出现"，先查这三层是否有人吃掉了 `no-transform` / `X-Accel-Buffering`——这是 v2.2.0 新增的、最典型的"SSE 看起来很慢"根因。nginx 配置本身故意**不压缩** SSE（见根 `AGENTS.md` 的 "compresses HTML and configured textual assets, deliberately leaving SSE … uncompressed"，钉在 `backend/tests/test_nginx_browser_websocket.py`）。

## 心跳与续传

- 默认**15 秒**无事件发 `HEARTBEAT_SENTINEL`（`DEFAULT_HEARTBEAT_INTERVAL_SECONDS = 15.0`，`config/stream_bridge_config.py:10`；配置键 `stream_bridge.heartbeat_interval_seconds`，上限 86400，两个后端同一默认）
- `Last-Event-ID` 支持订阅时续传
- 语法合法但**早于保留水位**的 `Last-Event-ID`（或掉队订阅者）→ `StreamGap`（id-less `gap` 事件），**run 保持 active**，不因重连失败杀掉 run

## 保留上限（关键限制）

memory 和 redis `StreamBridge` 只保留 `stream_bridge.queue_maxsize` 个 **data 事件**（默认 256，下限 1）。所以 SSE 是**实时窗口**，不是完整回放——完整历史在 `RunEventStore`（`02`），SSE 只保证"正在发生的"。

- **memory**：单进程。语法上 numeric 但低于水位的 cursor 保守视为 gap。🆕 v2.2.0 的 `cleanup()`（`stream_bridge/memory.py:198`）改成**退役代际**而不是直接删 map 项：置 `retired=True`、`start_offset += len(events)`、清空 payload、并 `condition.notify_all()`——已经建立起来的 generator 仍持有那个 stream 对象，旧做法会让它们在孤儿对象上永远等下去；现在它们被唤醒后去重读持久状态。`close()` 也改成逐个 `cleanup()` 而不是 `clear()`
- **redis**：跨实例，`stream_ttl_seconds`（默认 86400，设 0 关闭；TTL 在 `publish()`/`publish_end()` 滚动刷新）作为泄漏保险；XREAD 阻塞只当 wake-up，之后重复原子快照；rolling TTL **不是** run timeout

## 🆕 v2.2.0：producer lease（redis 后端，+728 行）

v2.1.0 的 redis 桥有个形态性缺陷：**worker 进程死掉后，订阅者永远等不到 `end`**——因为没人知道"生产者还在不在"。v2.2.0 给每个 run 加了跨进程 **producer lease**：

| 常量 | 值（`runtime/stream_bridge/redis.py`） |
|------|-----------------|
| `_PRODUCER_LEASE_SECONDS` | 30（key 的 `ex`，即过期窗口） |
| `_PRODUCER_LEASE_RENEW_INTERVAL_SECONDS` | 10（后台续租间隔，最长挂到 30s deadline） |
| `_PRODUCER_LEASE_START_TIMEOUT_SECONDS` / `_PRODUCER_LEASE_RELEASE_TIMEOUT_SECONDS` | 5.0 / 5.0 |
| `_PRODUCER_TRACKING_MIN_TTL_SECONDS` | 120（= 30×4，tracking key 保底 TTL，确保过期后仍能判定 `expired` 而不是直接消失成 `untracked`） |

**状态机**（`StreamProducerLeaseState`，`stream_bridge/base.py:58`）：`untracked`（没有 tracking key）／ `active`（tracking 与 active key 的 token 相同）／ `expired`（tracking 还在但 active 过期或被清）。判定实现 `producer_lease_state()`（`redis.py:636`）。

**API**：`start_producer_lease(run_id)` / `finish_producer_lease(run_id)` / `abort_producer_lease(run_id)` / `transfer_producer_lease(run_id, owner_task)`（takeover 时移交所有权）/ `producer_lease_state(run_id)` / `cleanup_expired_producer(run_id)`。基类默认 `producer_lease_recovery_enabled = False`。

**所有 Redis 写路径都走 Lua 脚本做 compare-and-XADD**（`_COMPARE_XADD_SCRIPT` / `_XADD_IF_NO_ACTIVE_PRODUCER_SCRIPT` / `_COMPARE_RENEW_SCRIPT` / `_COMPARE_DELETE_SCRIPT` / `_CLEANUP_IF_TOKEN_SCRIPT` / `_DELETE_EXPIRED_TRACKING_SCRIPT`），所以**失主的生产者写不进去**——不是靠客户端自觉。续租失败 → 取消本进程的 publish task（`_cancel_lost_producer`）。

**三个新增配置键**（`config/stream_bridge_config.py`，都只对 redis 生效）：

| 键 | 默认 | 语义 |
|----|------|------|
| `legacy_end_scan_enabled` | `true` | END 不在尾部时是否扫描保留的历史（**包括第一次发布 END**）。设为 `false` 后 END 检测变成**只看尾部**，更快但不兼容旧缓冲区。只在所有旧 writer 停掉、所有旧 replay buffer 过期/删除后才关；**改完要重启每个 Gateway** |
| `producer_lease_recovery_enabled` | `false` | 允许终态 redis 消费者**从已过期的 producer lease 恢复缺失的 END**。只在**所有** Gateway writer 都升级完、且升级前的 run 已排空后才开 |
| `recovered_stream_cleanup_delay_seconds` | 60.0 | 为恢复的孤儿 run 发布 END 之后，等多久再删 stream key（上限 86400），给重连的 SSE 客户端时间收 END |

**恢复路径**在 Gateway 侧：`app/gateway/deps.py:556-577` 对每个 recovered run 先 `stream_exists()`，不存在就 `cleanup_expired_producer()`（清不掉就重试），存在才 `publish_end()`（失败重试）。`app/gateway/services.py:301` 的 `_stream_producer_lease_state()` 提供只读探测（桥没有该方法时按 `untracked` 处理；异常时返回 `None` 而不是伪造状态）。

**运维结论**：`producer_lease_state == expired` 且 run 已经是终态，就是"这个流没人会再写 END"的强信号——可以直接按上面的配置开恢复，或者靠 `recovered_stream_cleanup_delay_seconds` 之后让 key 自己过期。

## 🆕 就绪探针会 ping 桥

`app/gateway/health.py:278` 的 readiness probe 对 `supports_cross_process` 的桥做 `await bridge.ping()`：**进程内 memory 桥直接返回 `PROBE_NOT_CONFIGURED`**（没有外部依赖可探），redis 桥探测失败 → `PROBE_UNREACHABLE`（fail-closed）。探测本身**串行化**（`_probe_gate("stream_bridge")`）并带 `_PROBE_TIMEOUT_SECONDS`，避免未认证的探测流量把 Redis 连接池撑大。`RedisStreamBridge.ping()` 在 `redis.py:786`。

## 与事件流的分工

| | StreamBridge SSE | RunEventStore |
|--|------------------|---------------|
| 时机 | 实时窗口 | 持久、append-only |
| 消费 | 前端 / IM channel | 历史 / 调试 / 审计端点 |
| 保留 | `queue_maxsize`（+ redis `stream_ttl_seconds`） | 全量（DB） |
| 终态信号 | `end` 帧（可能因 worker 死亡而缺失，靠 producer lease 判定） | `run.terminal`（权威，见 `02`） |

> 实时流是"用户体验 + 运维看一眼"，审计/回放/取证必须走事件流。**SSE 的 `end` 不是终态证据**——它只表示生产者收尾了，不携带业务结局；结局看 `run.terminal` 或 `RunRow.status`。
