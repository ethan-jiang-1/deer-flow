---
title: "持久化与流式"
description: "backend: sqlite           # memory | sqlite | postgres"
topics: [persistence, database, sqlite]
---

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

## ORM 模型明细

`persistence/base.py` — 所有模型共享 `Base(DeclarativeBase)`，提供：

```python
def to_dict(self, exclude: set[str] | None = None) -> dict[str, Any]:
    # 通过 sa_inspect() 迭代 column 属性
    # 自动 __repr__ 格式: <ClassName(key=value, ...)>
```

### RunRow（`run/model.py`）

| 列 | 类型 | 说明 |
|---|------|------|
| `run_id` | `String(64)` PK | UUID |
| `thread_id` | `String(64)` index | 所属 thread |
| `assistant_id` | `String(128)` | 使用的 agent |
| `user_id` | `String(64)` index | 所有者 |
| `status` | `String(20)` | pending/running/success/error/timeout/interrupted |
| `model_name` | `String(128)` | 实际选用的模型 |
| `multitask_strategy` | `String(20)` | reject/interrupt/rollback |
| `metadata_json` | `JSON` | 调用方元数据 |
| `kwargs_json` | `JSON` | 调用方参数（55+ 字段的 RunCreateRequest） |
| `error` | `Text` | 错误消息 |
| `message_count` | `int` | 便利字段：消息数 |
| `first_human_message` | `Text` | 便利字段：首条用户消息 |
| `last_ai_message` | `Text` | 便利字段：末条 AI 消息 |
| `total_input_tokens` / `total_output_tokens` / `total_tokens` | `int` | 总 token |
| `llm_call_count` | `int` | LLM 调用次数 |
| `lead_agent_tokens` / `subagent_tokens` / `middleware_tokens` | `int` | 按调用者分桶 |
| `follow_up_to_run_id` | `String(64)` | 关联的 follow-up run |
| `created_at` / `updated_at` | `DateTime(tz=True)` | 时间戳 |

复合索引：`ix_runs_thread_status (thread_id, status)` — 加速按 thread 过滤状态查询。

### ThreadMetaRow（`thread_meta/model.py`）

| 列 | 类型 | 说明 |
|---|------|------|
| `thread_id` | `String(64)` PK | |
| `assistant_id` | `String(128)` index | |
| `user_id` | `String(64)` index | NULL 表示无主（migration 共享） |
| `display_name` | `String(256)` | 会话标题 |
| `status` | `String(20)` | 默认 `"idle"` |
| `metadata_json` | `JSON` | 扩展元数据 |
| `created_at` / `updated_at` | `DateTime(tz=True)` | |

### FeedbackRow（`feedback/model.py`）

| 列 | 类型 | 说明 |
|---|------|------|
| `feedback_id` | `String(64)` PK | UUID4 |
| `run_id` | `String(64)` index | |
| `thread_id` | `String(64)` index | |
| `user_id` | `String(64)` index | |
| `message_id` | `String(64)` | 可选：关联特定消息 |
| `rating` | `int` | +1 (赞) 或 -1 (踩) |
| `comment` | `Text` | 可选文本反馈 |
| `created_at` | `DateTime(tz=True)` | |

唯一约束：`uq_feedback_thread_run_user (thread_id, run_id, user_id)` — 每个用户对每次 run 只能有一条反馈，`upsert()` 依赖此约束。

### UserRow（`user/model.py`）

| 列 | 类型 | 说明 |
|---|------|------|
| `id` | `String(36)` PK | UUID（36 字符，跨后端可移植） |
| `email` | `String(320)` unique index | |
| `password_hash` | `String(128)` | NULL 表示 OAuth-only |
| `system_role` | `String(16)` | `"admin"` / `"user"` |
| `oauth_provider` | `String(32)` | OAuth provider 名 |
| `oauth_id` | `String(128)` | OAuth 用户 ID |
| `needs_setup` | `bool` | 是否需首次设置 |
| `token_version` | `int` | JWT 失效版本号 |
| `created_at` | `DateTime(tz=True)` | |

部分唯一索引 `idx_users_oauth_identity`：`(oauth_provider, oauth_id)` 唯一，但仅当两者均非 NULL 时生效（SQLite: `WHERE oauth_provider IS NOT NULL AND oauth_id IS NOT NULL`），允许纯密码账号与 OAuth 账号共存。

## 仓库模式（Repository Pattern）

所有 SQL 仓库遵循同一模式：

### 核心约定

1. **短生命周期 session** — 每个方法通过 `async with self._sf() as session` 获取自己的 session，方法返回前 commit。后台 worker 可能运行数分钟，不持连接。

2. **`user_id` 三态语义**（`runtime/user_context.py`）：
   - `AUTO`（默认）— 从 request-scoped `contextvar` 解析
   - 显式 `str` — 原样使用
   - 显式 `None` — 绕过所有者过滤（migration/CLI 专用）

3. **`_row_to_dict()` 重映射** — ORM 的 `metadata_json`/`kwargs_json` →
   接口的 `metadata`/`kwargs`；datetime → ISO 字符串（`coerce_iso` 修复 SQLite 丢失 tzinfo 的问题）。

### RunRepository（`run/sql.py`, 353 行）

实现 `RunStore` 接口，12 个方法：

```mermaid
flowchart TD
    subgraph 写入路径
        PUT["put() — INSERT 或 GET+UPDATE"]
        STATUS["update_status()"]
        COMP["update_run_completion()"]
        PROG["update_run_progress() — 仅 WHERE status=running"]
    end

    subgraph 读取路径
        GET["get() — 按 run_id + 所有者过滤"]
        LIST["list_by_thread() — 按 thread_id + 所有者过滤"]
        LP["list_pending() — WHERE status='pending' 按 created_at ASC"]
        LI["list_inflight() — WHERE status IN (pending,running)"]
    end

    subgraph 聚合
        AGG["aggregate_tokens_by_thread() — SQL GROUP BY model"]
    end

    subgraph 其他
        DEL["delete() — 所有者检查"]
        MODEL["update_model_name()"]
    end

    PUT -->|"idempotent: 先 GET, row 存在则 UPDATE, 否则 INSERT"| COMMIT["commit"]
    COMP -->|"写入 token 分桶 + message_count + last_ai_message"| COMMIT
    PROG -->|"运行时进度快照，WHERE status='running' 防已完成覆盖"| COMMIT
    AGG -->|"COALESCE + SUM + CASE WHEN model 分组"| RESULT["{total_tokens, by_model, by_caller}"]
```

**`put()` 的幂等性设计**（行 81-126）：`RunManager` 在 SQLite 瞬时故障后重试 `put`。为避免"成功但未被确认"的第一次 commit 导致重试时主键冲突，`put()` 先 `session.get(run_id)`：
- 行不存在 → `session.add(RunRow(...))`
- 行已存在 → 逐字段 `setattr` 更新
- 最后 `commit`

**`update_run_progress()` 的防覆盖保护**（行 279-301）：WHERE 子句追加 `RunRow.status == "running"` — 如果 run 已完成（status=`success`/`error`），进度刷新不会覆盖最终数据。

**`_safe_json()` 递归序列化**（行 40-64）：确保 `metadata` 和 `kwargs` 值总是 JSON 可序列化的。处理链：
```
None/str/int/float/bool → 原样
dict → {k: _safe_json(v)}
list/tuple → [_safe_json(v)]
有 model_dump() → obj.model_dump()
有 dict() → obj.dict()
最后手段 → str(obj)
```

### FeedbackRepository（`feedback/sql.py`, 220 行）

9 个方法：

```mermaid
flowchart TD
    CREATE["create() — UUID4 + 校验 rating ∈ {+1, -1}"]
    UPSERT["upsert() — SELECT then UPDATE or INSERT"]
    GET["get() — 按 feedback_id"]
    LBR["list_by_run() — (thread_id, run_id)"]
    LBT["list_by_thread() — thread_id"]
    DEL["delete() — 单条删除"]
    DBR["delete_by_run() — 删除用户对某 run 的反馈"]
    LBG["list_by_thread_grouped() → {run_id: feedback_dict}"]
    AGG["aggregate_by_run() — SQL CASE WHEN 计数"]

    UPSERT -->|"SELECT WHERE (thread_id, run_id, user_id)"| FOUND{row 存在?}
    FOUND -->|"Yes: 原地更新 rating + comment"| COMMIT
    FOUND -->|"No: session.add(新 FeedbackRow)"| COMMIT

    AGG -->|"SELECT COUNT(*) + SUM(CASE WHEN rating=1 THEN 1 ELSE 0 END) + SUM(CASE WHEN rating=-1 THEN 1 ELSE 0 END)"| STATS["{total, positive, negative}"]
```

**`aggregate_by_run()` 的数据库端计数**（行 205-219）：使用 SQLAlchemy `case()` + `func.sum()` + `func.coalesce()`，在 SQL 层完成正/负面反馈计数，避免应用层循环。

### ThreadMetaStore 双后端（`thread_meta/`）

```mermaid
flowchart TD
    subgraph 工厂
        FACTORY["make_thread_store(session_factory, store)"]
        FACTORY -->|"session_factory 存在"| SQL[ThreadMetaRepository]
        FACTORY -->|"memory 模式"| MEM[MemoryThreadMetaStore]
    end

    subgraph SQL 后端
        SQL --> SF["async_sessionmaker → 短生命周期 session"]
        SQL --> ROW["ThreadMetaRow ORM"]
    end

    subgraph Memory 后端
        MEM --> BS["LangGraph BaseStore"]
        MEM --> NS["命名空间: ('threads',)"]
    end

    subgraph 共享接口
        BASE["ThreadMetaStore (ABC)"]
        METHODS["create / get / search / update_display_name / update_status / update_metadata / check_access / delete"]
    end

    SQL -.->|实现| BASE
    MEM -.->|实现| BASE
    BASE --> METHODS
```

两者实现相同的 `ThreadMetaStore` 抽象，支持：
- `create()` — 创建 thread 元数据记录
- `get()` / `search()` — 读取/搜索，含 metadata JSON 过滤
- `update_display_name()` / `update_status()` / `update_metadata()` — 带所有权检查的更新
- `check_access()` — 两模式：permissive（read 路径，`require_existing=False`）和 strict（write 路径，`require_existing=True`）
- `delete()` — 带所有权检查的删除

**`check_access()` 的双模式语义**（`thread_meta/sql.py` 行 81-109）：

| 模式 | `require_existing` | 行为 | 使用场景 |
|------|-------------------|------|---------|
| Permissive | `False`（默认） | 行不存在 → `True`（向后兼容 legacy thread） | GET、list 等读取操作 |
| Strict | `True` | 行不存在 → `False`（防止对已删除 thread 的操作） | DELETE、PATCH、state-update |

**`search()` 的 metadata 过滤**（行 119-150）：使用 `JsonMatch` 自定义 ColumnElement 对 `metadata_json` 列进行类型安全过滤。如果所有客户端提供的 filter key 都被拒绝（不安全字符），抛出 `InvalidMetadataFilterError` 并返回 400。

**Memory 后端的 `coerce_iso` 修复**（`memory.py` 行 149-150）：旧版 Gateway 将时间戳写为 `str(time.time())`（Unix epoch 秒），`coerce_iso()` 将这些值标准化为 ISO 8601。

## JSON 匹配系统（`json_compat.py`, 196 行）

为 metadata 过滤实现跨 SQLite/PostgreSQL 的类型安全 JSON 值比较。

### 设计约束

- key 必须是 `[A-Za-z0-9_-]+`（防止 SQL/JSONPath 注入 — key 被插入到编译的 SQL 路径表达式）
- value 必须是 `None | bool | int（signed 64-bit）| float | str`（不允许 list/dict/bytes）
- int 限制在 signed 64-bit 范围：SQLite 绑定更大值会溢出，PostgreSQL 在 BIGINT 转型时溢出

### 方言自适应编译

```mermaid
flowchart TD
    JM["JsonMatch(column, key, value)"] --> VALIDATE["validate key 字符集 + value 类型"]
    VALIDATE --> DIALECT{"compiler.dialect.name"}

    DIALECT -->|sqlite| SL["json_type(col, '$.key')<br/>json_extract(col, '$.key')"]
    DIALECT -->|postgresql| PG["json_typeof(col -> 'key')<br/>(col ->> 'key')"]
    DIALECT -->|其他| ERR["NotImplementedError"]

    SL --> BUILD["_build_clause() — 类型感知比较"]
    PG --> BUILD

    BUILD --> NULL{"value is None?"}
    NULL -->|Yes| N["typeof = 'null'"]
    NULL -->|No| BOOL{"value is bool?"}
    BOOL -->|Yes| B["typeof = 'true'/'false'<br/>(PG: + boolean type check)"]
    BOOL -->|No| INT{"value is int?"}
    INT -->|Yes| I["CAST extract AS INTEGER/BIGINT = bind<br/>(PG: 额外 ~ '^-?[0-9]+$' 防止 float CAST 错误)"]
    INT -->|No| FLOAT{"value is float?"}
    FLOAT -->|Yes| F["CAST extract AS REAL/DOUBLE PRECISION = bind"]
    FLOAT -->|No| STR["typeof = 'text'/'string' AND extract = bind"]
```

**bool 检查必须在 int 之前** — Python 中 `bool` 是 `int` 的子类，顺序错误会导致 bool 值被误判为 int。

**PostgreSQL 额外 int guard**：`json_typeof` 对 int 和 float 都返回 `'number'`，所以 PostgreSQL 编译添加正则 `~ '^-?[0-9]+$'` 以确保 CAST 到 BIGINT 前值是整数格式。

### 安全防护

```python
_KEY_CHARSET_RE = re.compile(r"^[A-Za-z0-9_\-]+$")
```
key 字符集限制为字母数字 + 下划线 + 连字符。这是注入防御 — key 直接插入编译的 SQL 字符串（`$."<key>"` / `->` 字面量）。

## Alembic 迁移（`migrations/`）

```
migrations/
├── alembic.ini
├── env.py         # 迁移环境配置
└── versions/
    └── .gitkeep   # 目前无实际迁移（项目较新）
```

### env.py 关键配置

```python
target_metadata = Base.metadata  # 自动发现所有 ORM 模型

def do_run_migrations(connection):
    context.configure(
        connection=connection,
        target_metadata=target_metadata,
        render_as_batch=True,  # SQLite ALTER TABLE 支持
    )
```

**明确的范围隔离**（env.py 行 1-5）：
> ONLY manages DeerFlow's tables (runs, threads_meta, cron_jobs, users). LangGraph's checkpointer tables are managed by LangGraph itself — they have their own schema lifecycle and must not be touched by Alembic.

**`render_as_batch=True`**：SQLite 对 ALTER TABLE 支持有限，batch 模式通过创建新表 + 复制数据 + 重命名来模拟 ALTER。

**模型注册**（行 19-26）：`import deerflow.persistence.models` 触发所有 ORM 模型（`RunRow`、`ThreadMetaRow`、`FeedbackRow`、`UserRow`、`RunEventRow`）注册到 `Base.metadata`。如果 import 失败，Alembic 以当前已知的 metadata 继续运行。

## 数据流总结

```mermaid
flowchart LR
    subgraph 应用层
        GW["Gateway API"]
        WRK["Worker run_agent()"]
    end

    subgraph 仓库层
        RR["RunRepository"]
        FR["FeedbackRepository"]
        TMR["ThreadMetaRepository"]
    end

    subgraph ORM
        BASE["Base (DeclarativeBase)"]
        MODELS["RunRow / FeedbackRow / ThreadMetaRow / UserRow"]
    end

    subgraph 引擎
        ENG["AsyncEngine"]
        SF["async_sessionmaker"]
    end

    subgraph 后端
        SQLITE["SQLite (WAL)"]
        PG["PostgreSQL"]
        MEMORY["Memory"]
    end

    GW --> RR
    GW --> FR
    GW --> TMR
    WRK --> RR

    RR --> SF
    FR --> SF
    TMR --> SF

    SF --> ENG
    ENG --> SQLITE
    ENG --> PG

    BASE --> MODELS
    SF -.->|使用| MODELS

    MEMORY -.->|"MemoryThreadMetaStore<br/>(绕过 SQL)"| GW
```

## 迁移：SQLite → Postgres（含数据）

### 前置条件

- 运行中的 PostgreSQL 实例（`auto_create_postgres_db` 在 `engine.py` 中处理自动建库）
- 安装 asyncpg 驱动：
  ```bash
  # 本地
  cd backend && uv sync --all-packages --extra postgres
  # Docker：设置 UV_EXTRAS=postgres 环境变量
  ```

### 切换步骤

```bash
# 1. 在 .env 中设置连接 URL
echo 'DATABASE_URL=postgresql://user:pass@host:5432/deerflow' >> .env

# 2. 修改 config.yaml
# database:
#   backend: postgres
#   postgres_url: $DATABASE_URL

# 3. 重启
make dev
```

DeerFlow 将自动：创建数据库（如不存在）→ `bootstrap_schema()` 创建所有表 → 运行 alembic 迁移 → 初始化 checkpointer 和 Store。

### 数据迁移

**没有内置数据迁移工具。** 切换后端后，旧 SQLite 文件（`.deer-flow/data/deerflow.db`）仍存在但不再使用。

**使用 pgloader（推荐）：**
```bash
pgloader sqlite://.deer-flow/data/deerflow.db postgresql://user:pass@host:5432/deerflow
```

需迁移的表：
- DeerFlow app 表：`runs`, `threads_meta`, `feedback`, `users`, `run_events`, `channel_connections`, `channel_credentials`, `channel_oauth_states`, `channel_conversations`
- LangGraph checkpointer 表：`checkpoints`, `checkpoint_blobs`, `checkpoint_writes`
- 跳过 `alembic_version`（每个后端独立维护）
- 注意类型差异：SQLite TEXT → Postgres JSONB

**不受数据库影响的数据**（文件系统，不需要迁移）：
- Memory 文件（`memory.json`）
- 上传文件（`.deer-flow/users/{uid}/threads/{tid}/user-data/`）
- Skills、Agent 配置

### 多 Worker 执行

`GATEWAY_WORKERS > 1` 时，非 Postgres 后端（SQLite/memory）Gateway 拒绝启动。Postgres 使用 `pg_advisory_lock` 跨进程串行化 bootstrap。

### 数据存储布局

- **SQLite**：checkpointer、Store、应用表全部在同一个 `deerflow.db` 文件中（WAL 日志模式，写不阻塞读）
- **Postgres**：checkpointer 和 app 使用同一数据库但独立连接池（checkpointer 用 `psycopg_pool`，app 用 SQLAlchemy+asyncpg）

### 已废弃

`checkpointer` 配置段已废弃。统一使用 `database` 段。如两者都存在，`checkpointer` 段优先级更高（仅用于 LangGraph checkpointer 和 Store；app repository 始终使用 `database`）。
