# Gateway 一致性测试

`backend/tests/test_gateway_conformance.py` — 验证 SDK 直接调用和通过 Gateway HTTP API 调用产生相同的结果。

## 测试原理

同一条 Agent 配置，通过两条路径执行相同的输入，逐字段对比输出：

```
                 ┌─ SDK 路径 ─────────────┐
                 │ create_chat_model()     │
  Agent Config ──┤ create_agent()          ├── 对比输出
                 │ agent.invoke(input)     │
                 └────────────────────────┘
                 ┌─ Gateway 路径 ──────────┐
                 │ POST /api/threads/{id}/ │
                 │   runs (HTTP API)       │
                 │ SSE stream 消费          │
                 └────────────────────────┘
```

## 覆盖维度

### 消息格式一致性

| 对比项 | SDK 输出 | Gateway 输出 |
|--------|---------|-------------|
| AIMessage.content | `agent.invoke()` 返回的 content | SSE `messages-tuple` 累积后的 content |
| ToolMessage.content | tool call 结果 | SSE tool result 内容 |
| message.additional_kwargs | reasoning_content, thought_signature 等 | SSE 传输后保持完整 |
| message.id | LangGraph message ID | 经过序列化后保持一致 |

### Tool Call 一致性

- Tool call arguments → JSON 序列化/反序列化后类型保持（int 不变成 string）
- Tool call 数量相等
- Tool call 顺序一致

### Streaming Chunk 一致性

- Chunk 数量相同（SDK `astream_events()` vs SSE events）
- Chunk 内容相同（经过 `AIMessageChunk` 序列化后）
- Token usage metadata 正确传输

## 为什么重要

Gateway 路径在 SDK 之上引入了多层序列化：
1. Python AIMessage → JSON（Pydantic model_dump）
2. JSON → SSE event（JSON stringify + SSE framing）
3. SSE event → JSON parse（前端 LangGraph client）
4. JSON → LangChain Message（Pydantic model_validate）

任何一层的数据丢失/类型变化都会导致 Gateway 行为和 SDK 行为不一致——用户通过 API 调用的结果和本地开发时不同。一致性测试捕获的就是这些序列化层引入的 regression。

## 测试数据

使用 shared test fixtures（`backend/tests/conftest.py` 或模块级 fixture）：
- Model config — 多个 provider（OpenAI-compatible mock, Anthropic mock）
- Tool config — web_search, read_file, bash
- Test input — 标准 prompt（"What is 2+2?" / "Search for Python tutorials"）

## 何时运行

- PR 中有 Gateway 路由/序列化代码变更 → 必须运行
- Harness 层 model/tool config 变更 → 建议运行（确保 Gateway 兼容）
- 新增 provider → 必须加对应的 conformance case
