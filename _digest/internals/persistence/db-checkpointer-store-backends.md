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
async def init_engine(backend, *, url="", echo=False, pool_size=5, pool_recycle=...,
                      command_timeout=..., sqlite_dir="", postgres_schema="") -> None:
    # 创建 async SQLAlchemy engine + session factory，最后交给 bootstrap_schema 建表
    # memory: 直接 return，不建 engine
    # sqlite: aiosqlite；每条新连接执行 PRAGMA journal_mode=WAL
    # postgres: asyncpg + connection pool（默认 pool_size=5，可 pin search_path 到 schema）

async def init_engine_from_config(config) -> None:
    # 便捷包装：吃 DatabaseConfig 并转发给 init_engine（memory 时 no-op）

async def close_engine() -> None:
    # dispose engine，释放所有连接，并把 _engine / _session_factory 置回 None
```

证据：`engine.py:85-95`（`init_engine` 签名，返回 `None`）、`engine.py:241-255`（`init_engine_from_config` 返回 `None`，并非返回 `Engine`）、`engine.py:268-275`（`close_engine`）、`engine.py:142-163`（SQLite WAL）。

**注意**：`database.*` 改后需重启才生效。Engine 在 `langgraph_runtime()` 启动时创建一次，之后不会重建。

### ORM Models

`persistence/models/__init__.py`（61 行）的 import + `__all__` 是唯一的显式注册入口：**22 个 Row 类 / 22 张表**（`persistence/models/__init__.py:17-36` 为 import，`:38-61` 为 `__all__` 的 22 项）。`RunEventRow` 是唯一留在 `models/run_event.py` 的模型，其余按实体子包分放。

| Row | 表 | 用途 |
|-----|-----|------|
| `RunRow` | `runs` | 运行记录 |
| `RunChangeClockRow` | `run_change_clock` | 全局单调 change clock 单例行（`0023_run_change_seq`） |
| `ThreadMetaRow` | `threads_meta` | 线程元数据（owner / project / incarnation） |
| `FeedbackRow` | `feedback` | 用户反馈 (rating, comment) |
| `UserRow` | `users` | 用户（auth） |
| `UserPreferenceRow` | `user_preferences` | 按 `(user_id, key)` 独立持久化的偏好（`0023_user_preferences`） |
| `RunEventRow` | `run_events` | 运行事件（消息 / trace） |
| `AgentRow` | `agents` | 自定义 Agent SOUL |
| `ManagedSubagentRow` | `managed_subagents` | 部署级 managed subagent 目录 |
| `McpTaskRow` | `mcp_tasks` | 长跑 MCP 任务（lease 恢复） |
| `PersonalAccessTokenRow` | `personal_access_tokens` | PAT（`0017`） |
| `ProjectRow` | `projects` | Projects 工作区（`0019_projects`） |
| `ProjectDocumentRow` | `project_documents` | document shelf（`0024`） |
| `ScheduledTaskRow` | `scheduled_tasks` | 定时任务定义 |
| `ScheduledTaskRunRow` | `scheduled_task_runs` | 定时任务每次 occurrence |
| `SubagentBatchRow` / `SubagentBatchItemRow` | `subagent_batches` / `subagent_batch_items` | durable native-subagent batch |
| `WebhookDeliveryRow` | `webhook_deliveries` | webhook 去重 |
| `ChannelConnectionRow` / `ChannelCredentialRow` / `ChannelOAuthStateRow` / `ChannelConversationRow` | `channel_connections` / `channel_credentials` / `channel_oauth_states` / `channel_conversations` | IM 渠道连接 / 凭据 / OAuth state / 会话映射 |

Alembic migrations 在 `persistence/migrations/` 下。

## Checkpointer

LangGraph state 持久化。通过 `make_checkpointer()` 工厂创建（`runtime/checkpointer/async_provider.py:216`，async generator）。

三种实现：

| 类型 | 库 | 场景 |
|------|-----|------|
| `InMemorySaver` | `langgraph` 内置 | 开发 |
| `AsyncSqliteSaver` | `langgraph-checkpoint-sqlite` | 单机 |
| `AsyncPostgresSaver` | `langgraph-checkpoint-postgres` | 生产 |

CLI/测试里要确定性清理时用**同步**上下文管理器 `checkpointer_context()`（`runtime/checkpointer/provider.py:268`；**不接收参数**、不缓存实例——每次 `with` 新建并销毁自己的连接）：

```python
with checkpointer_context() as cp:
    graph = create_agent(..., checkpointer=cp)
```

**checkpoint 的存储表示是另一个维度**：`database.checkpoint_channel_mode` 决定同一条链用 `full`（整快照 `channel_values`）还是 `delta`（LangGraph `DeltaChannel`：哨兵 blob + 每步 writes）存；delta 模式下 `make_checkpointer()` 还会把内层 saver 包进 `CachedHistorySaver`（`runtime/checkpoint_cache/` 的只读历史缓存）。进程冻结、元数据标记、fail-closed 门、`CheckpointStateAccessor` 与缓存后端的完整契约见 **[checkpoint-dual-mode-and-history-cache.md](checkpoint-dual-mode-and-history-cache.md)**。

## Store（LangGraph `BaseStore`）

Store 与 Checkpointer **共用同一个 `CheckpointerConfig`** 与同一套后端选择规则（`runtime/store/provider.py` 的 `_resolve_store_config()` / `runtime/store/async_provider.py` 复用同一函数）：

```
legacy checkpointer: 段存在 → 原样用它
否则 database.backend：memory → InMemoryStore
                       sqlite → SqliteStore / AsyncSqliteStore（database.checkpointer_sqlite_path）
                       postgres → PostgresStore / AsyncPostgresStore（database.postgres_url + postgres_schema）
```

所以"checkpointer 和 Store 同后端"是**结构性保证**，不是巧合；`database.postgres_schema` 会被转发，让 Store 表与 checkpointer 表、应用 ORM 表落在同一个 schema。

四个入口，用途不同：

| 入口 | 形态 | 生命周期 |
|------|------|----------|
| `make_store(app_config=None)` | **async** context manager（`store/async_provider.py`） | FastAPI lifespan 用；`async with make_store() as store: app.state.store = store` |
| `get_store()` | **sync 单例**（`store/provider.py`） | 跨调用复用，进程退出时关闭；`reset_store()` 显式重建（测试/配置变更后） |
| `store_context()` | **sync** context manager | **不缓存**实例，每次 `with` 新建并销毁连接——CLI/测试要确定性清理时用 |
| `reset_store()` | 函数 | 关掉打开的后端连接并清缓存实例 |

单例的锁序是刻意的：`get_store()` **先**在 provider 锁外解析完整配置（配置加载会重置两个持久化单例，锁内解析会造成锁序反转），**再**进 `_store_lock` 双检。

sqlite 路径处理统一走 `store/_sqlite_utils.py`：`resolve_sqlite_conn_str()` 把普通路径（相对/绝对）解析成绝对路径，但 `":memory:"` 与 `file:` URI **原样返回**；`ensure_sqlite_parent_dir()` 建父目录，同样对内存库/URI no-op。

## Postgres schema 固定（`persistence/postgres_schema.py`，257 行）

`database.postgres_schema` / `checkpointer.postgres_schema` 为空时保持服务端默认 `search_path`（通常 `public`）；非空时**同一份实现**同时服务三处消费者（应用 ORM engine、LangGraph checkpointer、LangGraph Store）。难点是两个 PG 驱动认的机制**不同**：

| 驱动 | 消费者 | 固定 search_path 的方式 |
|------|--------|------------------------|
| asyncpg | 应用 ORM engine（SQLAlchemy） | 只认 `connect_args.server_settings`——**不认** libpq 的 `options=-c ...` |
| psycopg | LangGraph checkpointer / Store | libpq `options=-c search_path=...`（pool kwarg 或 DSN query 参数） |

导出面：

| 函数 | 作用 |
|------|------|
| `build_asyncpg_connect_args(schema)` | `{}` 或 `{"server_settings": {"search_path": schema}}` |
| `build_psycopg_options(schema)` | `None` 或 `"-c search_path=<schema>"` |
| `create_schema_sql(schema)` | `None` 或 `CREATE SCHEMA IF NOT EXISTS "<schema>"`；**边界处重新校验**（见下） |
| `normalize_libpq_dsn(dsn)` | 去掉 SQLAlchemy `+driver` 后缀（`postgresql+asyncpg://` → `postgresql://`）；无 scheme 的 keyword DSN 原样返回；非 PG scheme 抛 `ValueError` |
| `dsn_with_search_path(dsn, schema)` | 把 search_path 合进 DSN query 的 `options`，保留其它 query 参数 |
| `ensure_postgres_schema(conn_string, schema, *, install_hint)` / `..._async(...)` | 用一条**新建**的 psycopg 连接执行 `create_schema_sql`；缺 psycopg 时把 `ImportError` 映射成调用方的 `install_hint` |

不平凡的细节（都是踩过的坑）：

- **`options` 必须合并而不是覆盖**：`_merge_search_path_option()` 用 libpq 自己的分词规则（反斜杠转义，**不是** POSIX shell 引号）切成 token，丢掉已有的 `-c search_path=`（两种拼写 `-c X` 与 `-csearch_path=` 都认），保留其它 `-c` 设置，最后追加新的。所以 DSN 里已有的 `statement_timeout` 之类不会被静默丢掉。**不能用 `shlex.join`**：它产生的单引号在 libpq 里是字面字符。
- **空白必须转义**：`_join_libpq_options()` 转义 token 内**所有**空白字节（不只空格）——`_split_libpq_options` 会把转义过的 TAB/CR/LF 保留在同一 token 里，如果重新拼接时裸露它们，libpq 会重新分词并破坏调用方原有的 `options`。
- **URL 里空格必须编码成 `%20` 而不是 `+`**：libpq 不把 `+` 当空格（那是 HTML form 约定），用 `urlencode(..., quote_via=quote)` 才不会退化成单个坏 token `-c+search_path=...`。
- **psycopg3 的 `Connection.__exit__` 只 commit/rollback，不 close**（相对 psycopg2 的行为变更），所以 `ensure_postgres_schema*` 显式用 `try/finally` 关连接，而不是泄漏到 GC。
- **SQL 生成边界二次校验**：`create_schema_sql()` 自己再调 `validate_postgres_schema()`，因为它是公开导出、而 psycopg 接受 `;` 分隔的多语句——未来绕过 `DatabaseConfig`/`CheckpointerConfig` 的调用方（如测试 helper）不能通过这个 f-string 边界注入 SQL。
- **schema 名只允许小写 plain identifier**（`config/postgres_schema.py` 的 `POSTGRES_SCHEMA_PATTERN = r"[a-z_][a-z0-9_]{0,62}"`，`re.fullmatch` 而非 `$` 锚定）。理由：schema 被**加引号**创建（大小写保留），却通过**不加引号**的 `search_path` token 生效（PG 折成小写）；允许大写会让两者分叉，表静默落进 `public`。同理不用 `$` 锚定：`$` 会接受尾随换行（`"deerflow\n"`），造出名为 `deerflow\n` 的引号 schema 而 `search_path` 折成 `deerflow`，同样静默落进 `public`。

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

### 🆕 events store 加固（sync #6）

`runtime/events/` 新增两个支撑模块：

- **`message_identity.py`** — 消息的稳定 UI 身份：`ToolMessage` 按 `tool_call_id` 而非自身 id 识别；
  `DynamicContextMiddleware` 注入产生的 user 副本（`X__user` re-key）与原消息折叠为同一身份。
  与前端 `frontend/src/core/threads/hooks.ts` 的 `messageIdentity` 必须保持同步。
- **`message_seq.py`** — `stamp_messages_with_seq()`：checkpoint 里的消息本身没有 seq，REST 打开会话时
  按 feed 身份批量回填 `deerflow_seq`（`additional_kwargs` key，服务端所有，客户端回传前会被剥掉），
  修复分页 + 上下文压缩重叠时早期用户消息错位（#4696）。查不到/出错一律降级为"无 seq"，不抛异常。

DB/JSONL store 的锁与取消修复：

| 修复 | commit | 内容 |
|------|--------|------|
| DB 写锁 generation 跨删除保持 | #5462 | 删除事件期间保留 DB store 写锁 generation，避免并发写者持过期代 |
| JSONL 锁 generation 跨删除保持 | #5455 | 同上，JSONL 版 |
| cancellation 前排空 | #5439 | 传播取消前先排空在途 JSONL 变更，防止截断/丢失已接受写入 |
| Unicode 分隔符 | #5429 | JSONL 事件记录保留 Unicode 分隔符（此前被规范化破坏） |

测试锚点：`backend/tests/test_db_event_store_lock_lifecycle.py`、`test_jsonl_event_store_lock_lifecycle.py`、
`test_jsonl_event_store_cancellation.py`、`test_jsonl_event_store_unicode.py`。

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
| `operation_kind` | `String(32)` | 默认 `"run"`（default + `server_default 'run'`）；reservation 行用 `checkpoint_write` / `artifact_write` / `artifact_archive` / `branch` / `delete` |
| `idempotency_key` | `String(255)` nullable | 唯一索引 `uq_runs_idempotency_key` |
| `change_seq` | `BigInteger` | 🆕 单调变更序号（`0023_run_change_seq`，稳定分页游标，`server_default 0`） |
| `status` | `String(20)` | pending/running/success/error/timeout/interrupted |
| `model_name` | `String(128)` | 实际选用的模型 |
| `multitask_strategy` | `String(20)` | reject/interrupt/rollback |
| `metadata_json` | `JSON` | 调用方元数据 |
| `kwargs_json` | `JSON` | 调用方参数（55+ 字段的 RunCreateRequest） |
| `error` | `Text` | 错误消息 |
| `stop_reason` | `String(50)` | 终止原因 |
| `message_count` | `int` | 便利字段：消息数 |
| `first_human_message` / `last_ai_message` | `Text` | 便利字段：首条用户消息 / 末条 AI 消息 |
| `total_input_tokens` / `total_output_tokens` / `total_tokens` | `int` | 总 token |
| `llm_call_count` | `int` | LLM 调用次数 |
| `lead_agent_tokens` / `subagent_tokens` / `middleware_tokens` | `int` | 按调用者分桶 |
| `token_usage_by_model` | `JSON` | 按模型分桶（`server_default '{}'`） |
| `follow_up_to_run_id` | `String(64)` | 关联的 follow-up run |
| `owner_worker_id` | `String(128)` nullable | 多 worker lease 所有者 |
| `lease_expires_at` | `DateTime(tz=True)` nullable | lease 过期时间 |
| `cancel_action` / `cancel_requested_at` | `String(20)` / `DateTime(tz=True)` nullable | 非 owner worker 的取消交接（首个 action 生效） |
| `created_at` / `updated_at` | `DateTime(tz=True)` | 时间戳 |

索引（`run/model.py:62-79`）：`ix_runs_thread_status (thread_id, status)`、`ix_runs_lease (lease_expires_at)`、`uq_runs_idempotency_key (idempotency_key)` unique、`ix_runs_change_seq (change_seq, run_id)`、`ix_runs_user_change_seq (user_id, change_seq, run_id)`、以及部分唯一索引 `uq_runs_thread_active (thread_id WHERE status IN ('pending','running'))`（SQLite/PostgreSQL 各自谓词）。

### RunChangeClockRow（`run/model.py:82-88`）

`run_change_clock`：`id` Integer PK + `value` BigInteger（`server_default 0`）的单例行。`RunRepository._next_change_seq()`（`run/sql.py:40-53`）用 `INSERT … ON CONFLICT DO NOTHING (id=1)` + `UPDATE … SET value = value + 1 RETURNING value` 在同一事务里分配位置。

### ThreadMetaRow（`thread_meta/model.py`）

| 列 | 类型 | 说明 |
|---|------|------|
| `thread_id` | `String(64)` PK | |
| `incarnation` | `String(32)` nullable | 🆕 thread incarnation id（`0019_thread_incarnations`）。**值会被写入/复制，但没有任何 fencing/校验逻辑消费它**：新行由 `ThreadMetaRepository.create()` 写 `uuid4().hex`（`thread_meta/sql.py:82`；memory 侧 `thread_meta/memory.py:74` 对已存在行继承、否则新生成），SQLite 建 MCP task 时把它抄进 `mcp_tasks.thread_incarnation`（`mcp_tasks/sql.py:157-164`；PostgreSQL 走 `FOR SHARE` 读，`:169`）；它只出现在内部记录 dict 里，任务响应显式 pop（`mcp_tasks/sql.py:102`）、HTTP 响应模型 `extra="ignore"`（`threads.py:435-437`）。全仓没有 `incarnation` 的等值比较或 fencing 调用点 |
| `assistant_id` | `String(128)` index | |
| `user_id` | `String(64)` index | NULL 表示无主（migration 共享） |
| `project_id` | `String(64)` index nullable | 🆕 Projects 成员关系（`0020_threads_meta_project_id`，无外键，项目删除时先清成员） |
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

### UserPreferenceRow（`user/model.py:33-39`）与 UserPreferencesRepository（`user/preferences.py`）

| 列 | 类型 | 说明 |
|---|------|------|
| `user_id` | `String(36)` PK，FK `users.id` ON DELETE CASCADE | 复合主键 `(user_id, key)` |
| `key` | `String(40)` PK | |
| `value` | `JSON` nullable | 单键值；`null` 表示重置该字段 |

`patch()`（`user/preferences.py:19-25`）按 `sorted(values.items())` 逐键 upsert（按方言选 `pg_insert` / `sqlite_insert` 的 `on_conflict_do_update`，`index_elements=["user_id","key"]`），**只写显式给出的 key**——不同客户端改不同字段互不冲突、同字段 last-commit-wins，排序键还避免相反顺序的行锁环。Gateway 只暴露 notification / default model / conversation mode / reasoning effort 四类键（见 `persistence/user/AGENTS.md`）。

### PersonalAccessTokenRow（`personal_access_tokens/model.py`，`0017`）

| 列 | 类型 | 说明 |
|---|------|------|
| `id` | `String(64)` PK | |
| `user_id` | `String(64)` index | |
| `name` | `String(128)` | |
| `token_digest` | `String(64)` | 唯一索引 `ix_personal_access_tokens_token_digest`；存 SHA-256 hex，明文 `dfp_…` token 只出现在创建响应里，从不落库/打日志 |
| `scopes` | `JSON` | 路由权限字符串子集（`app.gateway.authz`） |
| `expires_at` / `last_used_at` / `created_at` / `revoked_at` | `DateTime(tz=True)` | |

### Scheduled 两表

- `scheduled_tasks`（`scheduled_tasks/model.py`）：任务定义 + 调度状态。`schedule_type` / `schedule_spec`(JSON) / `timezone` / `status`（默认 `"enabled"`）/ `overlap_policy`（默认 `"enqueue"`）/ `next_run_at` / `last_run_at` / `last_run_id` / `last_thread_id` / `last_error` / `lease_owner` / `lease_expires_at` / `run_count` / `last_occurrence_seq`(BigInteger, `server_default 0`，`0022`)。
- `scheduled_task_runs`（`scheduled_task_runs/model.py`）：一次 occurrence。`task_id` 索引 + `occurrence_seq`(nullable) / `launch_accounted`(nullable)（`0022`）、`thread_id` / `run_id` / `scheduled_for` / `trigger` / `status` / `error` / lease 两列 / `attempt_count`（默认 0）/ `started_at` / `finished_at`；两个唯一索引 `uq_scheduled_task_run_occurrence_seq (task_id, occurrence_seq)` 与部分唯一 `uq_scheduled_task_run_active`（每 task 至多一条 `queued|launching|running`）。

### ProjectDocumentRow（`projects/model.py:51`，`0024`）

`project_documents`：`id` / `project_id` / `user_id` / `name` / `stored_relpath` / `sha256` / `size_bytes`，nullable 晋升来源 `source_thread_id` / `source_kind` / `source_name`，回收站字段 `trashed_at` / `trash_origin`(JSON)，加时间戳；索引 `project_id` / `user_id` / `sha256` / `trashed_at`，**没有 `project_id` 外键**（删除项目在自身事务里 trash 整个 shelf）。

### 线程操作 reservation 在 persistence 侧的落点

- `RunRepository.create_thread_operation_atomic()`（`run/sql.py:789-906`）是**唯一**带跨进程线程唯一性的原子建 run 入口：先取一次 change clock 位置，`interrupt` / `rollback` 时 `SELECT … FOR UPDATE` 抢占在途行（lease 未过期的他人 run、以及未过期 lease 的非 `run` reservation 都直接 `ConflictError`），再 INSERT 新行；`reject` 直接靠 `uq_runs_thread_active` 兜底，冲突可按 `idempotency_key` 转成 `RunIdempotencyConflict`。
- `RunRepository.delete_thread_operation()`（`run/sql.py:399-401`）用 reservation **捕获的 owner**（不是请求上下文）释放，转到单行 `delete()`。
- `reserve_checkpoint_write()` **不在 persistence**：它在 `app/gateway/services.py:98`，最终经 `RunManager.reserve_thread_operation()` 落到上面的 `create_thread_operation_atomic()`，写入 `operation_kind="checkpoint_write"` 的 reservation 行；`artifact_write` / `artifact_archive` / `branch` / `delete` 同路。
- `RunStore` 抽象基类（`runtime/runs/store/base.py:112`）**没有**声明 `delete_by_thread`：它是 `RunRepository`（SQL）与 `MemoryRunStore` 各自提供、由 Gateway 用 `getattr` 探测的**可选能力**，不是接口方法（详见下节「线程删除清理」）。

### json_compat 的内存侧孪生

`json_compat.py` 除 `JsonMatch`（SQL 编译，`json_compat.py:91`）外还导出 `json_value_matches()`（`json_compat.py:61-88`），给 memory / JSON 后端做**同语义**的内存比较：missing ≠ null、bool ≠ int、float filter 接受 JSON int 或 real。`ALLOWED_FILTER_VALUE_TYPES = (NoneType, bool, int, float, str)`（`json_compat.py:21`）。两侧语义必须一致，`ThreadMetaStore.search()` 才可能在 memory / SQLite / PostgreSQL 三后端给出同样结果。

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

### RunRepository（`run/sql.py`, 906 行）

实现 `RunStore` 接口，25 个公开方法（下图只画主要路径；完整清单见文件内 `async def`，含 lease/takeover/cancel 与线程操作 reservation）：

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
        AGG["aggregate_tokens_by_thread() — 过滤 thread + operation_kind='run' + 状态"]
    end

    subgraph 其他
        DEL["delete() — 所有者检查"]
        DBT["delete_by_thread() — 只删 operation_kind='run'，保留线程操作 reservation"]
        MODEL["update_model_name()"]
    end

    PUT -->|"idempotent: 先 GET, row 存在则 UPDATE, 否则 INSERT"| COMMIT["commit"]
    COMP -->|"写入 token 分桶 + message_count + last_ai_message"| COMMIT
    PROG -->|"运行时进度快照，WHERE status='running' 防已完成覆盖"| COMMIT
    AGG -->|"Python 端累加（非 SQL GROUP BY）：by_model 由 token_usage_by_model JSON 归约，旧行回退 model_name + total_tokens"| RESULT["{total_tokens, total_input_tokens, total_output_tokens, total_runs, by_model, by_caller}"]
```

**`put()` 的幂等性设计**（`run/sql.py:108-165`，`session.get` 分支在 `:159-164`）：`RunManager` 在 SQLite 瞬时故障后重试 `put`。为避免"成功但未被确认"的第一次 commit 导致重试时主键冲突，`put()` 先 `session.get(run_id)`：
- 行不存在 → `session.add(RunRow(...))`
- 行已存在 → 逐字段 `setattr` 更新
- 最后 `commit`

**`update_run_progress()` 的防覆盖保护**（`run/sql.py:495-534`，`WHERE` 在 `:533`）：WHERE 子句追加 `RunRow.status == "running"` — 如果 run 已完成（status=`success`/`error`），进度刷新不会覆盖最终数据。

**`_safe_json()` 递归序列化**（`run/sql.py:66-91`）：确保 `metadata` 和 `kwargs` 值总是 JSON 可序列化的。处理链：
```
None/str/int/float/bool → 原样
dict → {k: _safe_json(v)}
list/tuple → [_safe_json(v)]
有 model_dump() → obj.model_dump()
有 dict() → obj.dict()
最后手段 → str(obj)
```

### FeedbackRepository（`feedback/sql.py`, 280 行）

11 个方法：

```mermaid
flowchart TD
    CREATE["create() — UUID4 + 校验 rating ∈ {+1, -1}"]
    UPSERT["upsert() — SELECT then UPDATE or INSERT"]
    GET["get() — 按 feedback_id"]
    LBR["list_by_run() — (thread_id, run_id)"]
    LBT["list_by_thread() — thread_id"]
    DEL["delete() — 单条删除"]
    DBR["delete_by_run() — 删除用户对某 run 的反馈"]
    DBT["delete_by_thread() — 按所有者清空整条线程的反馈（线程删除用）"]
    LBG["list_by_thread_grouped() → {run_id: feedback_dict}"]
    LBRID["list_by_run_ids() — 批量取多 run 反馈"]
    AGG["aggregate_by_run() — SQL CASE WHEN 计数"]

    UPSERT -->|"SELECT WHERE (thread_id, run_id, user_id)"| FOUND{row 存在?}
    FOUND -->|"Yes: 原地更新 rating + comment"| COMMIT
    FOUND -->|"No: session.add(新 FeedbackRow)"| COMMIT

    AGG -->|"SELECT COUNT(*) + SUM(CASE WHEN rating=1 THEN 1 ELSE 0 END) + SUM(CASE WHEN rating=-1 THEN 1 ELSE 0 END)"| STATS["{total, positive, negative}"]
```

**`aggregate_by_run()` 的数据库端计数**（`feedback/sql.py:266-282`）：使用 SQLAlchemy `case()` + `func.sum()` + `func.coalesce()`，在 SQL 层完成正/负面反馈计数，避免应用层循环。

### 🆕 线程删除清理（sync #7，upstream #5535）

`DELETE /api/threads/{id}` 现在会在**持有 durable `delete` reservation** 的整个过程中，把该线程的持久化痕迹逐项清掉（每项都 best-effort，单项失败只 debug 日志，不打断整体删除）。仓库层的两个新入口是这次同步的实质变更：

| 仓库 | 新方法 | 语义 |
|------|--------|------|
| `RunRepository`（`run/sql.py:361`） | `delete_by_thread(thread_id, *, user_id=AUTO) -> int` | 只删 `operation_kind == "run"` 的历史 run 行；**故意不 bump run-change clock**（与单行 `delete()` 一致，也是 #5516 的规避点） |
| `FeedbackRepository`（`feedback/sql.py:190`） | `delete_by_thread(thread_id, *, user_id=AUTO) -> int` | 按所有者清空该线程全部反馈；`user_id` 沿用三态约定（`AUTO` 解析请求上下文 / 显式 id 限定所有者 / `None` 跳过所有者过滤，供 migration·CLI 用） |

两条关键约束：

1. **不能删掉正在保护本次删除的 reservation 行**。`runs` 表同时存放 durable thread-operation reservation（`checkpoint_write` / `artifact_write` / `artifact_archive` / `branch` / `delete`，由 `create_thread_operation_atomic()` 写入、`delete_thread_operation()` 释放）。因此 `delete_by_thread()` 的 WHERE 里带了 `operation_kind == "run"`——否则本次 `DELETE` 会在请求中途丢掉自己的跨 worker 互斥。历史 run 清理完，reservation 仍留到 `RunManager.reserve_thread_operation()` 退出时才释放。
2. **清理 ≠ 防复活**。这一步只删除"已存在"的行；阻止一个**已被准入**的写者在删除后重新写回状态，是另一个（尚未落地的）生命周期议题，不属于本次清理——upstream 在 `threads.py:802-804` 的注释里明确写了 "fencing already-admitted writes across thread deletion is a separate lifecycle concern"。`threads_meta.incarnation` / `mcp_tasks.thread_incarnation` 两列是为这类 generation 契约预留的 expand-phase 字段，但**目前只被写入/复制，没有任何 fencing/校验逻辑消费它**——不要把它当成已经生效的防复活机制（见上文 ThreadMetaRow）。

内存实现同步跟进：`MemoryRunStore.delete_by_thread()`（`runtime/runs/store/memory.py:218-235`）用同一规则跳过 `operation_kind != "run"` 的行（`user_id` 为 `None` 时不过滤 owner，与 SQL 侧三态一致）。

注意 `delete_by_thread` 并**不在** `RunStore` 抽象基类上（`runtime/runs/store/base.py:112` 的 `RunStore` 没有该抽象方法）：`RunRepository` 与 `MemoryRunStore` 各自实现，router 侧用 `getattr(get_run_store(request), "delete_by_thread", None)` 探测后再调用（`app/gateway/routers/threads.py:785-790`），因此第三方 `RunStore` 实现缺这个方法只是跳过、不会报错。

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

`incarnation` 不在 `ThreadMetaStore` 的接口方法签名里（`thread_meta/base.py` 未提及），它是 `create()` 产出的内部记录字段：SQL 后端 `_row_to_dict()` **不剔除**它（`thread_meta/sql.py:28-41`），由 HTTP 响应模型 `extra="ignore"` 决定不对外暴露（`threads.py:435-437`）。

**`check_access()` 的双模式语义**（`thread_meta/sql.py:182-210`）：

| 模式 | `require_existing` | 行为 | 使用场景 |
|------|-------------------|------|---------|
| Permissive | `False`（默认） | 行不存在 → `True`（向后兼容 legacy thread） | GET、list 等读取操作 |
| Strict | `True` | 行不存在 → `False`（防止对已删除 thread 的操作） | DELETE、PATCH、state-update |

**`search()` 的 metadata 过滤**（`thread_meta/sql.py:212-272`）：使用 `JsonMatch` 自定义 ColumnElement 对 `metadata_json` 列进行类型安全过滤。如果所有客户端提供的 filter key 都被拒绝（不安全字符），抛出 `InvalidMetadataFilterError` 并返回 400。

**Memory 后端的 `coerce_iso` 修复**（`thread_meta/memory.py:234-237`）：旧版 Gateway 将时间戳写为 `str(time.time())`（Unix epoch 秒），`coerce_iso()` 将这些值标准化为 ISO 8601。

## JSON 匹配系统（`json_compat.py`, 231 行）

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

## Alembic 迁移（`migrations/versions/`）

迁移链现为 **0001 → 0025**（`alembic_version.version_num` 为 VARCHAR(32)，revision id 不得超长）。

按 `down_revision` 逐文件实测（v2.1.0），实际串法是：
`0001_baseline → … → 0018_oauth_identity_pg_partial → 0019_projects → 0020_threads_meta_project_id → 0021_batch_acceptance → 0019_thread_incarnations → 0022_scheduled_occurrence_seq → 0023_run_change_seq → 0023_user_preferences → 0024_project_documents → 0025_repair_run_change_seq`（**head**，也是唯一 head）。
**数字前缀 ≠ 链顺序**：`0019_thread_incarnations.down_revision == "0021_batch_acceptance"`（`0019_thread_incarnations.py:21-22`），`0022_scheduled_occurrence_seq.down_revision == "0019_thread_incarnations"`（`0022_scheduled_occurrence_seq.py:14-15`），`0023_user_preferences.down_revision == "0023_run_change_seq"`（`0023_user_preferences.py:6-7`）——即 `0019_thread_incarnations` 挂在 `0021` 之后、`0023_user_preferences` 挂在 `0023_run_change_seq` 之后。`0023_run_change_seq.py:14-15` 的 down 是 `0022`，`0024_project_documents.py:15-16` 的 down 是 `0023_user_preferences`，`0025_repair_run_change_seq.py:34-35` 的 down 是 `0024_project_documents`。head 断言见 `backend/tests/test_migration_0025_repair_run_change_seq.py:69-70`。

下表为当前链上的 0017–0025（sync #6 新增/触及 0017–0024；sync #7 追加 **0025**）：

| revision | 内容 |
|----------|------|
| `0017_personal_access_tokens` | PAT 表（auth，#5041） |
| `0018_oauth_identity_pg_partial` | `idx_users_oauth_identity` 加 PostgreSQL 部分索引谓词 |
| `0019_projects` | Projects 工作区表（#5265） |
| `0019_thread_incarnations` | `threads_meta.incarnation` + `mcp_tasks.thread_incarnation` 可空列（#5216，expand-only；注意该 revision id 曾被早期 rollout 以不同父版本占用，本链中挂在 `0021` 之后幂等重放，见下节 forward revision） |
| `0020_threads_meta_project_id` | `threads_meta.project_id`（Projects） |
| `0021_batch_acceptance` | durable batch acceptance criteria / verdicts（subagent RFC #4651，#5289；用 `safe_add_column` 幂等加列） |
| `0022_scheduled_occurrence_seq` | 每 task occurrence 顺序 + 幂等 launch 记账 |
| `0023_run_change_seq` | `runs.change_seq` + 单例行 `run_change_clock`（稳定分页游标） |
| `0023_user_preferences` | 跨浏览器持久化的账号偏好，按 `(user_id, key)` 独立成行（表已存在则幂等跳过；#5397） |
| `0024_project_documents` | project document shelf 表（Projects Phase 2 Slice B） |
| `0025_repair_run_change_seq` | **修复**被"插队"的 `0023_run_change_seq` 留下的 schema 空洞（upstream #5517 / 修 issue #5516） |

> 编号冲突约定：多个迁移同时以 0017 生成时，先合入者保留编号，其余 rebase 时重编
> `revision`/`down_revision` 并调整 `tests/test_persistence_bootstrap*.py` 的 head 断言
> （见 `0017`/`0018` 文件内的 numbering note）。

#### 🆕 0025：为什么需要一次"修复型"迁移（sync #7）

`0023_run_change_seq` 最初被插到了**已经发布过的** `0023_user_preferences` **之前**（两者共用 0023 前缀，靠 `down_revision` 排序）。Alembic 只从数据库**已 stamp 的 revision 向前走**：任何在插入发生前就已 stamp 到 `0023_user_preferences`（或更后）的库，会把 `0023_run_change_seq` 当成"已应用的祖先"而**永不执行它**——这些库永久缺少 `run_change_clock` 表、`runs.change_seq` 列和两个游标索引，于是**所有走 `_next_change_seq()` 的写入**都会直接 `no such table: run_change_clock`：`put`、`update_status`、`start_run`、`update_model_name`、`update_run_completion`、`request_cancel`、`finalize_if_not_cancelled`、`claim_for_takeover`、`create_thread_operation_atomic`（线程删除只是其中最常被触发的一条路径）。重启也无法自愈，因为 stamp 早已 >= 0023。

`0025_repair_run_change_seq` 的修法就是**对升级经过它的库重放 0023 的同一条幂等 DDL**：

- `safe_add_column("runs", change_seq ...)`，再按 inspector 检查 `run_change_clock` 表与 `ix_runs_change_seq` / `ix_runs_user_change_seq` 缺失才建 —— 健康形状（含 0023 自己跑过的库）全部 no-op；
- `down_revision` 挂 `0024_project_documents`，downgrade 是**故意的 no-op**：schema 与已分配的 clock 位置归祖先 0023 所有，在这里 drop 会让一个 stamp 在 0024 的库重新缺 schema（恰好复现 #5516 的空洞）并丢掉游标数据；真正回退到 0023 时由 0023 自己的 downgrade 负责删。
- 配套：`RunChangeClockRow`、`UserPreferenceRow` 也被补进了 ORM 模型注册表（`persistence/models/__init__.py` 的 import + `__all__`）；此前缺的只是这份 `__init__` 清单本身（两者与 `RunRow`/`UserRow` 同模块，`Base.metadata` 早已随类定义注册，见下节 env.py 模型注册）。
- 回归测试：`backend/tests/test_migration_0025_repair_run_change_seq.py`（含 `test_migration_0024_project_documents.py` 的 head 断言调整）。

**由此固化的迁移纪律**（`persistence/migrations/AGENTS.md` 明文写入）：新 revision **必须挂在当前 head 之后**，绝不能插到已发布 revision 的前面去"重定父级"——所有 stamp 在插入点及之后的库都会把它当已应用祖先而跳过。这是本项目唯一需要"修复型迁移"来兜底的失败模式。

### 🆕 Forward revision 兼容（incarnation rollout 恢复）

早期 incarnation rollout 曾把 `0019_thread_incarnations` 盖在只有 `0018` + 两个可空 VARCHAR(32) 列的库上。
`persistence/bootstrap.py` 用常量 `_FORWARD_COMPATIBLE_REVISION = "0019_thread_incarnations"`（`bootstrap.py:129`）
加固定下限 `_CANONICAL_0019_SCHEMA_FLOOR`（`bootstrap.py:134-171`，**故意不派生自 `Base.metadata`**）识别这一形状，
`versioned` 分支先跑 `_validate_forward_schema`（`bootstrap.py:660-662`）。三种结局：

- 下限**缺失**（正是原始 0018+incarnation 形状，缺 Projects / batch-acceptance 的表列）→ `RuntimeError`
  **拒绝启动、不动 schema 与 revision**，错误里列出缺失的表/列（`bootstrap.py:388-391`）；
- 下限**通过**且该 id 在当前二进制的 known revisions 里（v2.1.0 即如此，`0019_thread_incarnations` 就在磁盘 script tree 中）→ 照常 `upgrade head`；
- 下限通过但当前二进制不认识该 id（已发布的 0020 rollback 二进制）→ warn 并跳过迁移（`bootstrap.py:688-693`）。

任何其它未知 revision、`alembic_version` 空表或多行，都 fail closed 拒绝启动（`bootstrap.py:363-364`、`:695`）。

针对这个精确形状的离线恢复流程见 [docs/database-forward-revision-recovery.md](../../../docs/database-forward-revision-recovery.md)：
停写、备份，校验 `alembic_version` 唯一行是 `0019_thread_incarnations` 且 schema 恰为"0018 + 两列"，
然后用 `DEERFLOW_RECOVERY_DATABASE_URL` + `_get_alembic_config` 先
`command.stamp(cfg, "0018_oauth_identity_pg_partial", purge=True)` 再 `upgrade head` ——
purge 只替换版本行不碰应用数据，且**不能直接 stamp 到 head**（会跳过 Projects/batch-acceptance DDL）。
回归测试：`backend/tests/test_persistence_forward_revision_compat.py`（构造原始 schema → 验证启动拒绝 →
演练恢复 → 校验 thread 读写与 incarnation 数据保留）。bootstrap 自身从不做 re-stamp。

### Hybrid bootstrap 分支（`persistence/bootstrap.py`，700 行）

`bootstrap_schema(engine, *, backend, postgres_schema="")`（`bootstrap.py:603`）在 `init_engine` 末尾调用。`_decide_state()`（`bootstrap.py:421-436`）按反射结果分三支；整个 reflect-and-act 序列在 Postgres 下走 `pg_advisory_lock`、SQLite 下走 per-engine `asyncio.Lock`（`bootstrap.py:523` / `:565` / `:590`）：

| DB 状态 | 动作（`bootstrap.py:628-698`） |
|---------|------|
| empty（无 DeerFlow 表；含只有 LangGraph checkpointer 表的新库） | `create_all` + `stamp head` |
| legacy（有 DeerFlow 表、无 `alembic_version`） | `create_all`（**仅**回填 `_BASELINE_TABLE_NAMES`）+ `stamp 0001_baseline` + `upgrade head` |
| versioned（`alembic_version` 恰好一行，且是本地已知 revision） | 若是 `0019_thread_incarnations` 先验 canonical floor，再 `upgrade head` |
| versioned + `0019_thread_incarnations` 但本地不认识该 id | 验 floor 通过后 warn 并跳过迁移 |
| versioned 但 revision 未知 / `alembic_version` 空 / 多行 | `RuntimeError` **拒绝启动** |

- `_BASELINE_TABLE_NAMES`（`bootstrap.py:198-210`，9 张：`channel_connections` / `channel_conversations` / `channel_credentials` / `channel_oauth_states` / `feedback` / `run_events` / `runs` / `threads_meta` / `users`）限制 legacy 分支的 backfill：不这么做，`create_all` 会抢建后续 revision 自己的表，让那些 revision 的 `op.create_table` 撞 `relation already exists`。有守卫测试把它钉在 `0001_baseline.upgrade()` 的实际输出上。
- 相关的另两个常量：`_BASELINE_REVISION = "0001_baseline"`（`bootstrap.py:177`）、`_BASELINE_INDEX_NAMES`（`bootstrap.py:215-249`）。
- 空库路径坚持 `create_all`：`Base.metadata` 是唯一权威 schema 源，能同时渲染 SQLite 与 Postgres（JSONB、部分索引），不必手维一份 baseline；`0001_baseline.upgrade()` 实际几乎从不执行，只作 stamp 目标 + 链根。
- 列级差异（如 `token_usage_by_model` 的历史形状）由各 `versions/*.py` 用 `migrations/_helpers.py` 的 `safe_add_column` / `safe_drop_column` 幂等处理：已存在即 no-op、形状漂移则 `logger.warning`。**新增 ORM 列/表只需加一个 revision 文件，不用改 `bootstrap.py`**——除非新 revision 引入新的 baseline 表（罕见）。

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

**明确的范围隔离**（env.py 行 1-10 的 docstring，原文）：
> ONLY manages DeerFlow's tables (runs, threads_meta, feedback, users, run_events, channel_connections, channel_credentials, channel_oauth_states, channel_conversations).

**`render_as_batch=True`**：SQLite 对 ALTER TABLE 支持有限，batch 模式通过创建新表 + 复制数据 + 重命名来模拟 ALTER（`env.py:65` 与 `:76`）。

**模型注册**（env.py 行 36-42 的 `try: import deerflow.persistence.models`）：触发所有 ORM 模型注册到 `Base.metadata`。sync #7 把 `RunChangeClockRow`（`run/model.py`，单例行 change clock）与 `UserPreferenceRow`（`user/model.py`）补进了 `models/__init__.py` 的 import + `__all__` 显式清单（upstream #5517）。注意两者此前**并非不在 `Base.metadata`**——它们与 `RunRow`/`UserRow` 同模块，import 该模块时就随类定义一并注册了，此前缺的只是这份 `__init__` 清单。如果 import 失败，Alembic 以当前已知的 metadata 继续运行。

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
- DeerFlow app 表：`Base.metadata` 里的全部 22 张（见上文「ORM Models」表）——`runs`, `run_change_clock`, `threads_meta`, `feedback`, `users`, `user_preferences`, `run_events`, `agents`, `managed_subagents`, `mcp_tasks`, `personal_access_tokens`, `projects`, `project_documents`, `scheduled_tasks`, `scheduled_task_runs`, `subagent_batches`, `subagent_batch_items`, `webhook_deliveries`, `channel_connections`, `channel_credentials`, `channel_oauth_states`, `channel_conversations`（早期文档只列到 9 张 baseline 表，已过时）
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
