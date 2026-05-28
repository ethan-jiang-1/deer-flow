# Streaming

DeerFlow 的 streaming 在两层上运作：**传输层**（StreamBridge — 怎么把数据从 worker 推到前端）和**模型层**（per-provider chunk 归一化 — 怎么把各家 provider 的 chunk 变成统一的格式）。

## 传输层：StreamBridge

StreamBridge 是一个 **pub/sub 协议**，解耦 agent worker（producer）和 SSE endpoint（consumer）：

```
Agent Worker                    StreamBridge                    SSE Endpoint (前端)
     │                               │                                │
     │─ publish(run_id, event, data) →│                                │
     │                               │─ subscribe(run_id) ──────────→│
     │                               │   yield StreamEvent            │
     │                               │   yield HEARTBEAT (15s)        │
     │─ publish_end(run_id) ───────→│                                │
     │                               │   yield END_SENTINEL ────────→│
```

### 核心抽象

```python
# base.py
class StreamBridge(ABC):
    async def publish(run_id, event, data)     # producer: 推一个事件
    async def publish_end(run_id)               # producer: 信号——没有更多事件了
    def subscribe(run_id, last_event_id) -> AsyncIterator[StreamEvent]  # consumer: 异步迭代
    async def cleanup(run_id, delay)            # 释放资源

@dataclass(frozen=True)
class StreamEvent:
    id: str        # 单调递增，用于 SSE id: 和 Last-Event-ID 重连
    event: str     # SSE event name: "metadata", "updates", "events", "error", "end"
    data: Any      # JSON-serializable payload
```

### MemoryStreamBridge — 当前唯一实现

- **Per-run event log** — 每个 `run_id` 有独立的 event list + `asyncio.Condition`
- **Bounded buffer** — 默认 256 events，超出后丢弃最旧的事件
- **Last-Event-ID 重连** — consumer 断开重连时传 `last_event_id`，bridge 从该位置之后开始 replay
- **Heartbeat** — 15 秒无事件时 yield `HEARTBEAT_SENTINEL`，保持 SSE 连接不超时
- **Redis 实现标记为 Phase 2** — `make_stream_bridge()` 选择 `MemoryStreamBridge` 或 raise `NotImplementedError`

### 事件流

SSE 的 event 类型：
- `metadata` — run 的元信息（run_id, thread_id, assistant_id）
- `updates` — LangGraph state values（标题、artifact 等非消息状态）
- `events` — LangGraph 自定义事件（subagent 状态变更、tool 进度等）
- `messages-tuple` — 逐 chunk 的消息增量（AI text delta、tool call、tool result）
- `error` — 错误信息
- `end` — stream 结束（携带累计 token usage）

## 模型层：Per-Provider Chunk 归一化

LangChain 的 `BaseChatModel._astream()` 负责把 provider 的 streaming chunk 转成 `AIMessageChunk`。但各家 provider 在 chunk 里塞了自己的格式——DeerFlow 的 patch 类 override `_astream()` 或 `_convert_chunk_to_generation_chunk()` 来做归一化：

| Provider | Chunk 问题 | Patch 方式 |
|----------|-----------|-----------|
| **vLLM** | assistant delta 有非标 `reasoning` 字段 | 自定义 `_convert_delta_to_message_chunk_with_reasoning()` 提取 `reasoning` → `reasoning_content` |
| **MiniMax** | streaming delta 里有 `reasoning_details`；完整响应有 `<think>` 标签 | `_convert_chunk_to_generation_chunk()` 解析 `reasoning_details`；`_parse_reasoning_content()` 提取 `<think>` |
| **MindIE** | tool 存在时 streaming 丢 choices | 降级为非流式生成 → 模拟流式 yield（15 字符/chunk） |
| **Codex** | Responses API SSE 格式不同于 Chat Completions | `_stream_response()` 消费 SSE，收集 `response.output_item.done` 和 `response.completed` |
| **其他 OpenAI-compatible** | 标准 `ChatOpenAI._astream()` | LangChain 内置处理 |

### MindIE 的特殊处理

MindIE 在 `stream=True + tools` 时直接丢弃所有 choices——这是 provider 的已知限制。`MindIEChatModel._astream()` 的处理方式：

```python
if tools_present:
    # 降级为非流式
    response = await self._agenerate(messages, ...)
    # 然后手动模拟 streaming yield
    for chunk in _simulate_streaming(response):
        yield chunk
```

这不是理想方案（首 token 延迟会增加），但在 MindIE 修复之前是唯一可行的方案。

## 两层之间的关系

```
Model 层                               传输层
provider chunk → AIMessageChunk → LangGraph stream_mode → StreamEvent → SSE → 前端
         ↑                                    ↑
    per-provider patch               StreamBridge pub/sub
    (格式归一化)                      (异步解耦)
```

两层是**正交**的：
- Model 层负责 **"chunk 长什么样"** — 把各家的格式统一成 LangChain 标准
- 传输层负责 **"chunk 怎么送到前端"** — 异步解耦、缓冲、重连、心跳

model 层不知道 StreamBridge 的存在，StreamBridge 不知道 provider 的细节。它们通过 LangGraph 的 `stream_mode` 机制衔接。
