---
title: "MessageBus pub/sub + ChannelManager dispatch loop"
description: "IM 频道消息总线：双向 pub/sub、入站队列、出站回调。"
topics: [channels, im, messaging]
---

# MessageBus pub/sub + ChannelManager dispatch loop

## MessageBus

`app/channels/message_bus.py` — 核心是一个双向异步 pub/sub：

### Inbound 方向（Channel → Dispatcher）

单个 `asyncio.Queue[InboundMessage]`：

```python
class MessageBus:
    def __init__(self):
        self._inbound_queue: asyncio.Queue[InboundMessage] = asyncio.Queue()

    async def publish_inbound(self, msg: InboundMessage):
        await self._inbound_queue.put(msg)

    async def get_inbound(self) -> InboundMessage:
        return await self._inbound_queue.get()  # 阻塞等待
```

所有 7 个 channel 向同一个队列推送——`ChannelManager._dispatch_loop()` 在队列另一侧阻塞等待。

### Outbound 方向（Dispatcher → Channel）

回调注册模式：

```python
class MessageBus:
    def __init__(self):
        self._outbound_callbacks: list[OutboundCallback] = []

    def subscribe_outbound(self, callback: OutboundCallback):
        self._outbound_callbacks.append(callback)

    async def publish_outbound(self, msg: OutboundMessage):
        for callback in self._outbound_callbacks:
            await callback(msg)  # 每个 channel 的 _on_outbound 自行过滤
```

每个 channel 注册一个 callback → 收到消息后在 `_on_outbound` 中按 `msg.channel_name == self.name` 过滤——只有目标 channel 处理，其余跳过。

### 数据模型

```python
@dataclass
class InboundMessage:
    channel_name: str      # "feishu", "slack", ...
    chat_id: str           # 平台会话 ID
    user_id: str           # 发送者 ID
    text: str              # 消息文本
    msg_type: str          # "CHAT" | "COMMAND"
    thread_ts: str | None  # 平台消息时间戳
    topic_id: str | None   # 主题/线程 ID（各平台语义不同）
    files: list            # 附件
    metadata: dict         # 平台特定元数据

@dataclass
class OutboundMessage:
    channel_name: str
    chat_id: str
    thread_id: str         # DeerFlow thread ID
    text: str              # Agent 响应文本
    artifacts: list        # Artifact 文件路径
    attachments: list      # 已解析的附件
    is_final: bool         # 流式通道的关键标志
    thread_ts: str | None  # 回复目标消息
```

## ChannelManager Dispatch Loop

`app/channels/manager.py` — 1024 行核心调度器：

```python
class ChannelManager:
    def __init__(self, bus, store, langgraph_url, gateway_url, default_session=None):
        self._semaphore = asyncio.Semaphore(5)  # 并发上限

    async def _dispatch_loop(self):
        while self._running:
            msg = await self.bus.get_inbound()    # 阻塞等消息
            await self._semaphore.acquire()        # 获并发许可
            task = asyncio.create_task(self._handle_message_with_semaphore(msg))
            task.add_done_callback(lambda _: self._semaphore.release())

    async def _handle_message(self, msg: InboundMessage):
        if msg.msg_type == "COMMAND":
            return await self._handle_command(msg)
        else:
            return await self._handle_chat(msg)
```

每个消息在独立的 `asyncio.create_task` 中处理。`Semaphore(5)` 限制同时最多 5 个消息被处理——防止大型部署中消息突增打爆 LangGraph server。

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

## LangGraph SDK Client

ChannelManager 自己构造一个 `langgraph_sdk` async client，注入 internal auth token + CSRF token：

```python
client = get_asyncio_client(
    api_url=self._langgraph_url,
    headers={
        "X-DeerFlow-Internal-Token": internal_token,
        "X-CSRF-Token": csrf_token,
    }
)
```

这使得 channel worker 可以调用 `client.threads.create()`、`client.runs.stream()` 和 `client.runs.wait()` 而不需要浏览器 session。

## Custom Agent 路由

当 `assistant_id` 不是 `"lead_agent"` 时：
1. 将名称规范化为 lowercase + hyphens
2. 作为 `agent_name` 注入到 run context
3. 仍然通过 `lead_agent` 执行（`lead_agent` 内部有路由逻辑将 `agent_name` 映射到具体的 agent 工厂）
