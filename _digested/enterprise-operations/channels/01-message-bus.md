---



title: "MessageBus pub/sub + ChannelManager worker pool"
description: 'IM 频道消息总线：有界入站准入、双向 pub/sub、去重占坑与暂存清理，以及 manager 的固定 worker pool。'
topics: [channels, im, messaging]
verified_against: v2.2.0
last_verified: 2026-11-08
---

# MessageBus pub/sub + ChannelManager worker pool

## MessageBus

`app/channels/message_bus.py`（432 行）——核心是一个双向异步 pub/sub。v2.2.0 把它从「无界 `asyncio.Queue` + 盲 `put`」改成**有界准入总线**：入站有容量上限、超载显式拒绝、支持预留（reservation）、支持适配器提前占去重键、并把暂存文件清理所有权交还适配器。

### Inbound 方向（Channel → worker pool）

单个**有界**队列 + 预留计数：

```python
class MessageBus:
    def __init__(self, *, inbound_queue_maxsize: int = DEFAULT_INBOUND_QUEUE_MAXSIZE) -> None:
        if isinstance(inbound_queue_maxsize, bool) or not isinstance(inbound_queue_maxsize, int) or inbound_queue_maxsize <= 0:
            raise ValueError("inbound_queue_maxsize must be a positive integer")
        self._inbound_queue = asyncio.Queue(maxsize=inbound_queue_maxsize)
        self._inbound_admission_lock = threading.Lock()
        self._inbound_queued = 0
        self._inbound_reservations: set[object] = set()
        self._accepting_inbound = True
        ...

    async def publish_inbound(self, msg: InboundMessage) -> None:
        await asyncio.sleep(0)          # 调度让位，不是容量等待
        reservation = self.reserve_inbound(msg)
        try:
            reservation.commit(msg)
        finally:
            reservation.release()
```

关键语义（`message_bus.py:215-300` 一带）：

- `DEFAULT_INBOUND_QUEUE_MAXSIZE = 1000`（`message_bus.py:20`），配置项 `channels.inbound_queue_maxsize`。
- **拒绝而不是等待**：`reserve_inbound()` 在 `_inbound_admission_lock` 内比较 `_inbound_queued + len(_inbound_reservations)` 与 `maxsize`，超限直接抛 `InboundQueueFullError`；producer 不会累积无界 pending put task。满载告警按 1 秒限流，带累计拒绝数（`rejected_total`）。
- `reserve_inbound()` 可**从 SDK 线程**安全调用（`threading.Lock`，非 asyncio 原语），让 provider 回调在把身份/ack 准备调度到 Gateway loop 之前就先占容量。
- 开头的 `await asyncio.sleep(0)` 是有意的**调度让位**：批量发布（典型是 GitHub webhook fan-out）时给固定 worker 出队的机会，使大于队列容量的批次在重投时不会反复撞同一段前缀。它发生在准入之前，取消不会在已提交后再报失败。
- `InboundReservation.commit()` / `.release()`；提交时若 token 已失效抛 `InboundReservationExpiredError`，准入已关闭抛 `InboundQueueClosedError`。
- 生命周期：`close_inbound()` 关准入并作废未提交预留（返回作废数）、`open_inbound()` 供重启、`join_inbound()` 等所有已接受条目完成、`inbound_task_done()`、`discard_pending_inbound()`、只读属性 `inbound_queue_maxsize` / `inbound_queue`。

10 个通道实现（9 个 IM + GitHub）向同一个队列推送；`ChannelManager` 的固定 worker 池在另一侧消费（见下文）。

### 去重占坑（dedupe claim）

有些适配器的**平台副作用**发生在 manager 层去重之前——典型是 Discord 收到重复投递时会重复建 thread。v2.2.0 让适配器在副作用前先占去重键：

```python
InboundClaim = Callable[[InboundMessage], Awaitable[bool]]        # message_bus.py:176
InboundClaimRelease = Callable[[InboundMessage], Awaitable[None]]  # message_bus.py:177

def set_inbound_claim(self, claim, release) -> None: ...   # dispatcher 装入 ChannelManager._claim_inbound
async def claim_inbound(self, msg) -> bool:                # False = 另一次投递拥有它
async def release_inbound_claim(self, msg) -> None:        # 只在 msg.dedupe_claimed 时归还
```

约定：`claim_inbound()` 返回 `True` 时适配器把 `msg.dedupe_claimed` 复制到它发布的消息上；若它最终**没有**发布入站消息，必须调用 `release_inbound_claim()` 把键还给平台重投。没有 dispatcher（测试/直连）时 `claim_inbound()` 一律放行。必须在 Gateway loop 上调用——去重存储的 engine 在那里。worker 侧看到 `dedupe_claimed=True` 就跳过自己的去重检查（否则会把自己判成重复）。

`InboundMessage.dedupe_claimed: bool = False`（`message_bus.py:114`）。

### 暂存文件清理（adapter-owned staging）

入站附件可能由适配器写进临时目录，清理责任必须跟着适配器走：

```python
INBOUND_FILE_CONTENT_KEY = "_content"    # message_bus.py:34
INBOUND_FILE_CLEANUP_KEY = "_cleanup"    # message_bus.py:37

async def cleanup_inbound_files(files: list[dict[str, Any]]) -> None:
    callbacks = [f.pop(INBOUND_FILE_CLEANUP_KEY, None) for f in files if isinstance(f, dict)]
    callbacks = [callback for callback in callbacks if callable(callback)]
    ...
    await await_drained(asyncio.to_thread(cleanup))
```

安全语义：**只有适配器能提供 callable**——provider metadata 里的路径不授予删除权限；`_cleanup` 会在持久化 metadata 之前被消费掉一次（pop）。清理在 worker 线程执行，并通过 `await_drained()` 等待落地，取消路径也不会漏删；单个回调失败只记 warning，不影响其余附件。

### 其余 metadata 键

| 键 | 值 | 含义 |
|----|----|------|
| `PENDING_CLARIFICATION_METADATA_KEY` | `"pending_clarification"` | 待回答的澄清请求（`message_bus.py:22`） |
| `HUMAN_INPUT_REQUEST_METADATA_KEY` | `"human_input_request"` | `ask_clarification` 工具消息的完整 `human_input` 载荷，挂在**最终出站**上，供通道渲染更丰富的交互（Feishu 按钮卡片）（`:26`） |
| `HUMAN_INPUT_RESPONSE_METADATA_KEY` | `"human_input_response"` | 通道合成的 human-input 答案（如 Feishu 卡片点击），随入站消息带回，manager 挂到 human message 的 `additional_kwargs`（`:30`） |
| `RESOLVED_FROM_PENDING_CLARIFICATION_METADATA_KEY` | `"resolved_from_pending_clarification"` | 该入站是某条待答澄清的回复（`:31`） |

### Outbound 方向（Dispatcher → Channel）

回调注册模式，v2.2.0 改为**派发开始时快照**监听器列表：

```python
async def publish_outbound(self, msg: OutboundMessage) -> None:
    listeners = tuple(self._outbound_listeners)   # 快照：派发期间的订阅/退订只影响后续消息
    for callback in listeners:
        await callback(msg)

def unsubscribe_outbound(self, callback: OutboundCallback) -> None:
    """Remove a callback from subsequent outbound dispatches.
    This does not cancel or wait for callbacks in an in-flight dispatch."""
    self._outbound_listeners = [cb for cb in self._outbound_listeners if cb != callback]
```

每个 channel 注册一个 callback → 收到消息后在 `_on_outbound` 中按 `msg.channel_name == self.name` 过滤——只有目标 channel 处理，其余跳过。快照语义保证：一个通道在 `stop()` 中退订自己时，不会影响已经开始的这轮派发，也不会留下半退订状态。

### 数据模型

```python
class InboundMessageType(StrEnum):
    CHAT = "chat"
    COMMAND = "command"

@dataclass
class InboundMessage:
    channel_name: str
    chat_id: str
    user_id: str
    text: str
    msg_type: InboundMessageType = InboundMessageType.CHAT
    thread_ts: str | None = None
    topic_id: str | None = None
    connection_id: str | None = None    # 有值时映射按连接划分，而非全局 channel_name:chat_id 键
    owner_user_id: str | None = None    # DeerFlow 用户 id；平台 id 留在 user_id
    workspace_id: str | None = None
    files: list[dict[str, Any]] = field(default_factory=list)
    metadata: dict[str, Any] = field(default_factory=dict)
    created_at: float = field(default_factory=time.time)
    dedupe_claimed: bool = False        # v2.2.0 🆕

@dataclass
class OutboundMessage:
    channel_name: str
    chat_id: str
    thread_id: str
    text: str
    artifacts: list[str] = field(default_factory=list)
    attachments: list[ResolvedAttachment] = field(default_factory=list)
    is_final: bool = True               # 流式通道的关键标志
    thread_ts: str | None = None
    metadata: dict[str, Any] = ...
    connection_id: str | None = None
    owner_user_id: str | None = None
```

## ChannelManager worker pool

`app/channels/manager.py` — **4162 行**核心调度器（v2.2.0 实测）。v2.1.0 的 `_dispatch_loop()` + `asyncio.Semaphore(5)` + per-message `asyncio.create_task` 已删除，现行是**固定数量的长驻 worker**：

```python
DEFAULT_CHANNEL_MAX_CONCURRENCY = 5                  # manager.py:79
DEFAULT_CHANNEL_SHUTDOWN_GRACE_PERIOD_SECONDS = 3.0  # manager.py:80

async def start(self) -> None:
    self.bus.open_inbound()
    self._worker_tasks = {
        asyncio.create_task(self._worker_loop(worker_index),
                            name=f"deerflow-channel-worker-{worker_index}")
        for worker_index in range(self._max_concurrency)     # manager.py:2342-2346
    }
    logger.info("ChannelManager started (workers=%d, inbound_queue_maxsize=%d, shutdown_grace=%.1fs)", ...)

async def _worker_loop(self, worker_index: int) -> None:      # manager.py:2466
    while self._running or not self.bus.inbound_queue.empty():
        msg = await self.bus.get_inbound()
        with ensure_trace_context(), _run_admission_scope(fresh=True):
            if not msg.dedupe_claimed and await self._is_duplicate_inbound(msg):
                continue
            await self._handle_message(msg)                   # 内联 await，绝不 per-message 建 task
        # finally: await cleanup_inbound_files(msg.files)
```

要点：

- **并发是结构性的**，不是许可令牌：`max_concurrency` 个工作协程决定同时在跑的入站消息数（配置 `channels.max_concurrency`，默认 5）。
- **内联处理**：`_handle_message()` 被直接 `await`，注释明确 "never create a task per message"——避免无界 task 增长。慢的一条消息只会占用它自己的 worker。
- **每条消息一个 trace + 一个 run 准入作用域**：`ensure_trace_context()` + `_run_admission_scope(fresh=True)`（worker 任务是长驻且复用的，作用域必须随消息关闭而不是泄漏到下一条）。入站长连接没有任何 ASGI middleware，这是它们唯一拿到 trace id 的地方。
- **去重先于"received"日志**：provider 重投 N 次不会记 N 条接受日志；已被适配器占坑（`dedupe_claimed`）的消息不再重复记录。
- **失败/取消时归还去重键**：worker 捕获 `CancelledError` 与 `Exception` 时，若已记录去重键且 `_keep_dedupe_key_after()` 判定 Gateway 可能已在执行该 run（会活过本 worker），才保留键；否则归还，让平台重投仍可重试。去重后端故障不得让固定 worker 池缩小——清理异常全部吞在循环内。
- **收尾**：`finally` 里 `await cleanup_inbound_files(msg.files)` 释放适配器暂存。

### 停机顺序

```python
async def stop(self) -> None:                    # manager.py:2364
    invalidated_reservations = self.begin_shutdown()   # 关准入、作废未提交预留
    for task in watcher_tasks: task.cancel()           # follow-up watcher 立即停（它们会造新 run）
    join_task = asyncio.create_task(self.bus.join_inbound(), ...)
    done = await asyncio.wait({join_task}, timeout=shutdown_grace_period_seconds)
    for task in worker_tasks: task.cancel()            # 宽限期满后取消
    discarded_messages = await self._discard_pending_inbound()
```

`_discard_pending_inbound()`（`manager.py:2440`）：丢弃未派发的入站时，**先** `cleanup_inbound_files()` 释放附件，**再**对 `msg.dedupe_claimed` 的消息归还去重键——否则该键要占满整个 TTL，让对端实例的重投被误判成重复。成功返回意味着没有 worker 或 follow-up watcher 还能继续使用通道资源；进程级超时由 Gateway lifespan 兜底。

### LangGraph SDK Client

`ChannelManager` 通过 `langgraph_sdk.get_client()` 取得 async client，并在请求上注入 internal auth token + CSRF（`_csrf_headers` / `_get_client`，`manager.py:2300` 一带）：

```python
from langgraph_sdk import get_client
client = get_client(url=self._langgraph_url, headers={... "X-CSRF-Token": ...})
```

这使得 channel worker 可以调用 `client.threads.create()`、`client.runs.stream()` 和 `client.runs.wait()` 而不需要浏览器 session。（v2.1.0 的 `get_asyncio_client(` 直接构造已删除。）

### 幂等 run 准入 🆕

provider 重投同一条消息时，manager 保证**同一个 run 只被准入一次**：

| 常量 | 位置 | 作用 |
|------|------|------|
| `IDEMPOTENCY_KEY_HEADER` | `manager.py:129` | 发往 Gateway 的 `Idempotency-Key` 头名 |
| `_RUN_IDEMPOTENCY_KEY_PREFIX = "channel-inbound:v1:"` | `manager.py:130` | 键前缀（带 schema 版本） |
| `_HUMAN_MESSAGE_ID_NAMESPACE` | `manager.py:134` | uuid5 命名空间：由去重键派生确定的人类消息 id |
| `ALREADY_ADMITTED_MESSAGE` | `manager.py:138` | 已准入时下发给用户的文案 |
| `_LIVE_RUN_STATUSES` | `manager.py:139` | 仍视为"活着"的 run 状态集合 |

`_run_admission_scope()`（`manager.py:167`）用 `_RUN_ADMISSION` ContextVar（`manager.py:153`）在一条消息的处理过程中记录"本次准入"，`_RunAdmission`（`manager.py:142`）保存键/消息 id/结果；`_RunFailedFrame`（`manager.py:162`）把失败帧与"请求是否真的到达了 Gateway"（`_RUN_REQUEST_REACHED_GATEWAY_ERRORS`，`manager.py:158`）区分开，避免把网络层失败误报成 run 失败。

辅助方法：`_run_idempotency_key()`（`manager.py:2579`）、`_human_message_id()`（`manager.py:2589`，uuid5）、`_claim_inbound()`（`manager.py:2597`）、`_release_inbound_claim()`、`_is_duplicate_inbound()`、`_release_inbound_dedupe_key()`（`manager.py:2632`）、`_keep_dedupe_key_after()`（`manager.py:2647`）。`ALREADY_ADMITTED_MESSAGE` 的三处下发点在 `manager.py:3434`、`:3461`、`:3664`；流式键的释放在 `manager.py:3694`。

### 入站去重存储

`app/channels/dedupe_store.py`（309 行）两级：进程内 `MemoryInboundDedupeStore`（TTL）或 `PostgresInboundDedupeStore`（多副本共享），由 `make_inbound_dedupe_store(app_config)` 在 `ChannelService` 构造时选定并注入 manager（`service.py:251,264`）。Buzz 另有连接层 durable seen-id 存储（`buzz_seen_events.py`）。

### 跟进消息缓冲 🆕

线程正忙时新到的消息不会被丢弃，而是进 `buffer_followups_on_busy` 策略控制的缓冲：`FOLLOWUP_BUFFER_MAX_PER_THREAD = 20`（`manager.py:254`），配套 `_followup_watcher_tasks` 集合（`stop()` 里立即取消）与 `get_stream_bridge` 钩子（run 结束后自动排空缓冲）。`THREAD_BUSY_MESSAGE`（`manager.py:111`）是「线程忙」的提示文案。

## Config 层叠合并

`_resolve_run_params(channel_name, user_id)` — 4 层合并，外层覆盖内层：

```
1. DEFAULT_RUN_CONFIG / DEFAULT_RUN_CONTEXT  (硬编码 fallback)
     ↓ 被覆盖
2. channels.session  (全局默认，如 assistant_id="lead_agent")
     ↓ 被覆盖
3. channels.{channel}.session  (per-channel，如 feishu 有自己的 agent)
     ↓ 被覆盖
4. channels.{channel}.session.users.{user_id}  (per-user 覆盖，最外层)
```

每层可以覆盖 `assistant_id`（指定用哪个 agent）、`config`（temperature/max_tokens 等）、`context`（thinking_enabled 等）。

`recursion_limit` 有单独的覆盖/下限逻辑（`manager.py:2200-2230` 一带）：per-channel/per-user 配置可提高上限，但不会低于平台默认；`_apply_channel_policy()`（`manager.py:2235-2272`）在其后写入 `run_context["interaction_mode"]`，非 `interactive` 时同时置 `disable_clarification`（见 [02-stream-strategies.md](02-stream-strategies.md)）。

## Custom Agent 路由

当 `assistant_id` 不是 `"lead_agent"` 时：
1. 将名称规范化为 lowercase + hyphens
2. 作为 `agent_name` 注入到 run context
3. 仍然通过 `lead_agent` 执行（`lead_agent` 内部有路由逻辑将 `agent_name` 映射到具体的 agent 工厂）

会话级的固定选择由 `/agent list` / `/agent use <name>` 写入线程元数据（见 [03-thread-mapping.md](03-thread-mapping.md)）；消息级覆盖（如 GitHub webhook fan-out 一条 repo 绑多个 agent）走 `_resolve_message_assistant_id()`（`manager.py:1726`）。
