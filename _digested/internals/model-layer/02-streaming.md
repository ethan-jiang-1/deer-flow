---
title: "Streaming"
description: "DeerFlow 的 streaming 在两层上运作：**传输层**（StreamBridge — 怎么把数据从 worker 推到前端）和**模型层**（per-provider chunk 归一化 — 怎么把各家 provider 的"
topics: [models, llm, provider-factory]
---

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
| **DeepSeek** | 基类 inbound 处理正常，但 `reasoning_content` 在 outbound 序列化时丢失 | `_get_request_payload()` 重注入 `reasoning_content` |
| **Gemini via OpenAI** | `thought_signature` 在 tool_call 对象上，LangChain 序列化时丢失 | `_get_request_payload()` 重注入 `thought_signature` |
| **其他 OpenAI-compatible** | 标准 `ChatOpenAI._astream()` | LangChain 内置处理 |

### vLLM：多态 reasoning 字段

vLLM 0.19.0 在 assistant delta 中暴露非标 `reasoning` 字段。LangChain 的标准 `_convert_delta_to_message_chunk` 直接丢弃它——这会导致后续轮次中断，因为 vLLM 要求历史 assistant 消息中携带 prior reasoning。

核心函数 `_convert_delta_to_message_chunk_with_reasoning()`（`vllm_provider.py:94`）是 LangChain 内部函数的完整 fork，关键差异：

```python
reasoning = _dict.get("reasoning")
if reasoning is not None:
    additional_kwargs["reasoning"] = reasoning       # 原始 payload（可能是 string/list/dict）
    reasoning_text = _reasoning_to_text(reasoning)    # 归一化为文本
    if reasoning_text:
        additional_kwargs["reasoning_content"] = reasoning_text
```

`_reasoning_to_text()`（`:65`）递归展平 reasoning——vLLM 返回的 reasoning 可能是 string、list、dict 或嵌套 dict，哪种形状都能处理。

**Outbound 重注入**：`_get_request_payload()` 使用双路径策略匹配消息——
- 消息数一致时按位置对齐
- 不一致时只数 assistant 消息，按计数顺序对齐

这是 DeepSeek 和 vLLM 的共同需求：thinking 模式下 **每一轮** assistant 消息都要带 reasoning，不只是最后一条。

### MiniMax：双源 reasoning + streaming 拼接

MiniMax 同时产出两种 reasoning：
1. **Split reasoning**：`extra_body.reasoning_split=true` → API 返回结构化 `reasoning_details` 数组（`[{type: "reasoning.text", text: "..."}]`）
2. **Inline think tags**：`<think>...</think>` 标签嵌入在 `content` 文本中

**Streaming 路径**：`_convert_chunk_to_generation_chunk()` 用 LangChain 标准 converter 做基础转换，然后调用 `_with_reasoning_content(preserve_whitespace=True)`。`preserve_whitespace=True` 模式的关键行为是**拼接**（不 trim 空格），所以增量 chunk `"The user"` 和 `" asks."` 被焊成 `"The user asks."`。

```python
# patched_minimax.py:88-89
if preserve_whitespace:
    additional_kwargs["reasoning_content"] = existing + new_reasoning
```

**非流式路径**：`_create_chat_result()` 做双重提取——先 regex 剥离 `<think>` 标签，再从 `reasoning_details` 提取，最后 `_merge_reasoning()` 合并去重。

**Request 侧**：`_get_request_payload()` 强制注入 `reasoning_split: True` 到 `extra_body`（`:111-116`），这是 MiniMax 返回结构化 reasoning 的前提。

### MindIE：tool + stream 降级

MindIE 最显著的问题：当 `stream=True` 且 `tools` 存在时，**engine 直接丢弃所有 choices**——provider 的已知 bug。`_astream()` 的处理方式：

```python
# mindie_provider.py:218-249
if tools_present:
    response = await self._agenerate(messages, ...)    # 降级为非流式
    # 合成 fake chunk 模拟 streaming
    chunk_size = 15
    for i in range(0, len(text), chunk_size):
        yield AIMessageChunk(content=text[i:i+chunk_size], ...)
    if tool_calls:
        yield AIMessageChunk(tool_calls=tool_calls, ...)
```

选择 15 字符/chunk 是经过权衡的——太小浪费 CPU，太大则首屏渲染延迟高。tool call 作为单独一个 chunk 在文本之后 emit。

当没有 tools 时，MindIE 走原生 streaming，只做 `\\n` → `\n` 解码（`:222-223`）。

**XML tool call 往返**：MindIE 不支持 LangChain 原生 `tool_calls` 格式——必须将 tool definitions 转成 XML-wrapped text 发送，再将模型返回的 `<tool_call><function=name><parameter=k>v</parameter></function></tool_call>` 解析回 LangChain 标准格式（`_fix_messages()` + `_parse_xml_tool_call_to_dict()`）。

### DeepSeek：outbound 序列化修复

`langchain_deepseek` 基类的 inbound streaming 处理是正常的——`reasoning_content` 正确存储在 `AIMessageChunk.additional_kwargs` 中。Bug 在 **outbound** 侧：序列化消息给 DeepSeek API 时不带 `reasoning_content`，导致 thinking 模式下的多轮对话 400 错误。

`PatchedChatDeepSeek._get_request_payload()` 使用与 vLLM 相同的双路径策略重注入 `reasoning_content`——按位置对齐或按 assistant 计数对齐。与 vLLM 不同，DeepSeek 的 reasoning 是顶层 key（`payload_msg["reasoning_content"] = reasoning_content`），不是嵌套在 `additional_kwargs` 里。

### Codex：内部 SSE，无公开流式

`CodexChatModel` 直接继承 `BaseChatModel`，自己实现 HTTP 层，连接 `chatgpt.com/backend-api/codex/responses`。虽然内部使用 `stream: True` 走 SSE，但 **公开接口不流式**——`_stream_response()` 收集完整 SSE stream 后返回单个 `ChatResult`。

SSE 解析追踪两个事件：
- `response.output_item.done` — 单个 output item（文本/tool_call/reasoning）
- `response.completed` — 最终 envelope

关键 merge 逻辑：Codex endpoint 可能在 `response.completed` 到达时 `output` 数组为空，而实际内容仅出现在 stream events 中。代码用 `None` 填充 merged output 数组，再按 index 填入 streamed items。

Reasoning 提取：从 type 为 `"reasoning"` 的 output item 中读 `summary` → `summary_text`。

### Gemini via OpenAI：thought_signature 保留

通过 OpenAI 兼容网关连接 Gemini 时，API 在 function call 对象上返回 `thought_signature`。LangChain 的 `ChatOpenAI` 存它在 `additional_kwargs["tool_calls"]` 中，但序列化 outbound payload 时只保留 `{id, type, function}`，签名被丢弃——下一轮 API 请求 400。

`PatchedChatOpenAI._get_request_payload()` 重注入签名，同时检查 `thought_signature`（snake_case）和 `thoughtSignature`（camelCase），因为不同网关实现使用了不同的大小写。

### 共同模式：outbound reasoning 重注入

vLLM、DeepSeek、Gemini/OpenAI 三个 provider 共享同一个结构性模式：

1. `self._convert_input(input_).to_messages()` → 拿到带 `additional_kwargs` 的原始 LangChain 消息
2. `super()._get_request_payload(...)` → 拿到序列化后的 payload
3. 匹配 payload 消息与原始消息（位置对齐 → assistant 计数 fallback）
4. 把 reasoning/signature 从 `AIMessage.additional_kwargs` 拷贝到 payload dict

这个模式在三个文件中各自实现了一份——没有共享基类。

## 工厂层的 streaming 相关行为

`factory.py:create_chat_model()` 有两个 streaming 相关的修正：

1. **`stream_usage` 默认开启**（`:34`）：LangChain 只在 `base_url` 为 OpenAI 官方 endpoint 时自动开 `stream_usage`。第三方网关（vLLM、Ollama 等）会因 `stream_usage=False` 导致 streaming 模式丢失 token usage。factory 强制默认 `stream_usage=True`。

2. **MindIE 强制 `max_retries=1`**（`:150-152`）：防止 MindIE 超时时级联重试放大延迟。

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

## Provider 流式能力对比

| Provider | 原生流式 | Reasoning 保留 | 降级模式 | Outbound 重注入 |
|----------|---------|---------------|---------|---------------|
| OpenAI | 标准 `ChatOpenAI._astream()` | N/A | 无 | 无 |
| Anthropic | 标准 `ChatAnthropic._astream()` | 基类处理 | 无 | 无 |
| vLLM | 是，自定义 chunk converter | 多态 `reasoning` 字段 | 无 | `reasoning` → payload |
| DeepSeek | 基类 inbound 正常 | 基类处理 | 无 | `reasoning_content` → payload |
| MiniMax | 是，`preserve_whitespace=True` 拼接 | `reasoning_details` + `<think>` 双源 | 无 | 无（API 自动保留） |
| MindIE | 仅无 tools 时；tools 触发降级 | 无 reasoning 支持 | 15 字符合成 chunk | N/A |
| Codex | 内部 SSE，公开接口不流式 | `summary_text` 提取 | 全量收集后返回 | N/A |
| Gemini/OpenAI | 走 ChatOpenAI 流式 | N/A | 无 | `thought_signature` → payload |
