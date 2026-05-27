# 持久化与流式

## 数据库

### 三种后端

```yaml
database:
  backend: sqlite           # memory | sqlite | postgres
  sqlite_dir: .deer-flow/data
```

| 后端 | 场景 | 持久化 |
|------|------|--------|
| `memory` | 开发测试 | 无，重启丢失 |
| `sqlite` | 单机部署（默认） | `.deer-flow/data/deerflow.db`（WAL 模式） |
| `postgres` | 生产多节点 | `postgresql://...` |

### 引擎管理

`persistence/engine.py`：

```python
async def init_engine_from_config(db_config) -> Engine:
    # 创建 async SQLAlchemy engine
    # sqlite: aiosqlite + WAL journal
    # postgres: asyncpg + connection pool (默认 5)

async def close_engine():
    # 关闭 engine，释放所有连接
```

**注意**：`database.*` 改后需重启才生效。Engine 在 `langgraph_runtime()` 启动时创建一次，之后不会重建。

### ORM Models

| Model | 用途 |
|-------|------|
| `Run` | 运行记录 (run_id, thread_id, status, timestamps) |
| `ThreadMeta` | 线程元数据 |
| `Feedback` | 用户反馈 (score, comment) |
| `User` | 用户（auth） |

Alembic migrations 在 `persistence/migrations/` 下。

## Checkpointer

LangGraph state 持久化。通过 `async_provider.py:make_checkpointer` 工厂函数创建。

三种实现：

| 类型 | 库 | 场景 |
|------|-----|------|
| `InMemorySaver` | `langgraph` 内置 | 开发 |
| `AsyncSqliteSaver` | `langgraph-checkpoint-sqlite` | 单机 |
| `AsyncPostgresSaver` | `langgraph-checkpoint-postgres` | 生产 |

Checkpointer 在请求范围内通过 `checkpointer_context()` 上下文管理器使用：

```python
async with checkpointer_context(checkpointer) as cp:
    graph = create_agent(..., checkpointer=cp)
```

## Run Events

运行事件（消息和 trace）的存储：

```yaml
run_events:
  backend: memory             # memory | db | jsonl
  max_trace_content: 10240    # trace 内容截断阈值 (bytes)
  track_token_usage: true     # token 用量累积
```

| 后端 | 场景 |
|------|------|
| `memory` (默认) | 开发，无持久化 |
| `db` | 生产，SQL ORM，完整查询 |
| `jsonl` | 轻量单机持久化，追加写 |

## Stream Bridge

Gateway 和 Client 使用不同的 bridge 实现：

### SSE Bridge (Gateway)

```
graph.astream()
    │
    ▼
stream_bridge.write_event(type, data)
    │
    ▼
sse-starlette EventSourceResponse
    │
    ▼
Client (EventSource / fetch)
```

### Memory Bridge (DeerFlowClient)

```
graph.astream()
    │
    ▼
stream_bridge.write_event(type, data)
    │
    ▼
asyncio.Queue
    │
    ▼
client.stream() generator
```

两者接口一致：`write_event(type, data)` → 消费方收到统一格式事件。

## SSE 流式协议

### 事件类型

```
event: metadata
data: {"run_id": "xxx", "thread_id": "yyy"}

event: values
data: {"messages": [...], "title": "...", "artifacts": [...], "todos": [...]}

event: messages-tuple
data: [{"type": "AIMessageChunk", "content": "增量文本块"}]

event: custom
data: {"type": "task_started", "task_id": "..."}

event: end
data: {"usage": {"input_tokens": 5000, "output_tokens": 2000}}
```

### 前端消费

```typescript
// frontend/src/core/threads/hooks.ts
import { useStream } from "@langchain/langgraph-sdk/react";

const stream = useStream({
  threadId,
  apiUrl: "/api/langgraph",
  // ...
});
```

`useStream` (来自 `@langchain/langgraph-sdk`) 处理 SSE 连接和事件解析。状态更新通过 React context 流向 workspace 组件。

### Server-Sent Event 的 `data` 字段格式

- `values` → ThreadState 全量快照（json）
- `messages-tuple` → `[message, ...]` 数组（json）
  - 首次出现该 message id + content 时提供全量
  - 后续更新是增量 delta
- `custom` → 任意 json
- `end` → `{usage: {input_tokens, output_tokens}}` (json)

## 前端 SSR → Gateway

Next.js Server Components 需要直接调用 Gateway API：

```
Next.js Server (SSR)
    │  fetch("/api/langgraph/...")
    │  或 fetch("http://gateway:8001/api/...")
    ▼
Gateway API
```

环境变量：
```
DEER_FLOW_INTERNAL_GATEWAY_BASE_URL=http://localhost:8001
```

Docker 中这个值改为 `http://gateway:8001`（Docker 网络内部）。

## 数据库升级到 Postgres

```bash
# 1. 编辑器，安装 postgres extra
UV_EXTRAS=postgres

# 2. .env 中设置连接字符串
DATABASE_URL=postgresql://deerflow:password@localhost:5432/deerflow

# 3. config.yaml 切换后端
database:
  backend: postgres
  postgres_url: $DATABASE_URL

# 4. 本地启动
make dev          # 自动检测 postgres backend，传递 --extra postgres 给 uv sync

# 5. Docker 启动
make down && make up    # UV_EXTRAS=postgres 在 build 时安装 asyncpg
```

详见 config.example.yaml 中的详细注释（PR #2584, #2754 修复了相关安装路径问题）。
