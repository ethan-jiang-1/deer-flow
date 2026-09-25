---
title: "结构化事件流：RunEventStore 与 RunJournal"
description: "DeerFlow 有一个 append-only 的 run 事件流：RunJournal 把 LangChain 回调标准化成 RunEvent，写入 RunEventStore。它是审计、回放、调试端点、subtask 卡片、workspace 审查的共同数据源。"
topics: [observability, run-events, journal, audit]
---

# 结构化事件流：RunEventStore 与 RunJournal

日志是给人 `grep` 的，事件流是给**程序**读的。DeerFlow 的 `RunEventStore` 是一份 append-only 的 run 记录，`RunJournal` 把 LangChain 回调标准化成 `RunEvent` 写进去。历史、调试、subtask、memory 审计、workspace 审查读的是同一批行的不同投影。

> RunJournal 的缓冲/刷盘/token 分桶细节 → [internals/runtime/04-journal.md](../internals/runtime/04-journal.md)。这里聚焦事件流的**契约和消费方式**。

## 事件目录（`deerflow/runtime/events/catalog.py`）

固定事件（`RunJournal` 产出）：

| event_type | category | 来源回调 |
|-----------|----------|---------|
| `run.start` | `trace` | 根 `on_chain_start()` |
| `run.end` | `outputs` | 根 `on_chain_end()` |
| `run.error` | `error` | `on_chain_error()` |
| `llm.human.input` | `message` | 首条 lead-agent 人类输入 |
| `llm.ai.response` | `message` | `on_llm_end()` |
| `llm.tool.result` | `message` | `on_tool_end()` |
| `llm.error` | `trace` | `on_llm_error()` |
| `context:memory` | `context` | `record_memory_context()` |
| `middleware:{tag}` | `middleware` | `record_middleware()` |

动态模式：`middleware:{tag}`（tag 限 1–21 字符 = `RUN_EVENT_TYPE_MAX_LENGTH`(32) − `"middleware:"`(11)，`constants.py:66`），v2.1.0 注册的 tag 全集 = `guardrail`、`loop_detection`、`safety_termination`、`skill_activation`、`skill_secrets`、`tool_promotion`、`tool_progress`（`catalog.py:79-93` 的 `MIDDLEWARE_EVENT_TAGS`）。

其它生产者：`subagent.start` / `subagent.step` / `subagent.end`（`subagents/step_events.py`，批量 `put_batch`）；`workspace_changes`（`workspace_changes.record_workspace_changes()`）。

## 信封与顺序保证

| 字段 | 含义 |
|------|------|
| `thread_id` / `run_id` | 归属 |
| `seq` | **thread 全局**严格递增（不是 run 局部） |
| `event_type` / `category` | 固定名或文档化动态模式（type ≤32 字符，category ≤16） |
| `content` | 字符串或 JSON（`run.end.content` 故意 opaque，跨后端不保证嵌套一致） |
| `metadata` | 可过滤/审计元数据 |
| `created_at` | 带时区 ISO-8601 |

后端差异：memory 保留 Python 值；JSONL/DB 经 `json.dumps(default=str)`，非 JSON 嵌套值读回为字符串。**多进程/多 worker 部署必须 `run_events.backend: db`**（JSONL 只在单进程内保证 seq）。

## 冻结契约（`contracts/run_event_stream_contract.json`，v1）

上面这些名字不是"当前实现的快照"，而是一份**跨组件冻结契约**（JSON Schema 2020-12 方言，`version: 1`）。它冻结现有 event type 与 category、描述各生产者 payload、并写明兼容规则——改运行时之前先看它。

**兼容规则**：

| 类别 | 内容 |
|------|------|
| 消费方义务 | 必须忽略未知 event type、未知信封字段、未知的可选 payload/metadata 字段（前向兼容的前提） |
| 允许的**增量**变更 | `add_event_type` / `add_optional_payload_field` / `add_optional_metadata_field` / `add_envelope_field` |
| **破坏性**变更 | 删除或改名 event type、改 category、删必填字段、改必填字段类型 |

**信封必填字段**：`thread_id` / `run_id` / `seq` / `event_type` / `category` / `content` / `metadata` / `created_at`（`record_schema.required`）。

**序列**：`scope = thread_id`、`guarantee = strictly increasing within a thread`；`jsonl_multi_process_limit` 明确写着 `JsonlRunEventStore` 只保证**单进程内**单调分配，跨进程共享写入必须用 `DbRunEventStore`。

**8 个 category**：`trace` / `message` / `outputs` / `error` / `middleware` / `context` / `subagent` / `workspace`。

**12 个冻结事件与生产者**（`events[]`）：

| event_type | category | 生产者 |
|-----------|----------|--------|
| `run.start` | trace | `RunJournal.on_chain_start(parent_run_id=None)` |
| `run.end` | outputs | `RunJournal.on_chain_end(parent_run_id=None)` |
| `run.error` | error | `RunJournal.on_chain_error()` |
| `llm.human.input` | message | `on_chat_model_start()`，仅首条被持久化的 lead-agent `HumanMessage` |
| `llm.ai.response` | message | `on_llm_end()` |
| `llm.tool.result` | message | `on_tool_end()`，对 `ToolMessage` 或 `Command(update.messages[])` |
| `llm.error` | trace | `on_llm_error()` |
| `context:memory` | context | `record_memory_context()`（由 DynamicContextMiddleware 触发） |
| `subagent.start` | subagent | `subagent_run_event(task_started)` |
| `subagent.step` | subagent | `subagent_run_event(task_running)` |
| `subagent.end` | subagent | `subagent_run_event(task_completed\|task_failed\|task_cancelled\|task_timed_out)` |
| `workspace_changes` | workspace | `workspace_changes.record_workspace_changes()` |

**动态模式**：只有 `middleware:{tag}` 一个，`event_type` 长度 12–32（`^middleware:` 前缀 + tag），`tag` 长度 1–21；**7 个已知 tag** = `guardrail` / `loop_detection` / `safety_termination` / `skill_activation` / `skill_secrets` / `tool_promotion` / `tool_progress`（与 `catalog.py` 的 `MIDDLEWARE_EVENT_TAGS` 一一对应）。`content` 必填 `name` / `hook` / `action` / `changes`。

**legacy 别名**：`ai_message` → 规范化名 `llm.ai.response`，状态是 `read-only compatibility`（当前 runtime **不**再产出），按 category 的消息投影与 last-visible-AI 查询（含 `/messages/page`）仍识别这个历史名——所以判"最后一条 AI 消息"时两种写法都要覆盖。

## 读取契约与分页边界（`events/store/base.py`）

所有读取方法都按 `seq` **升序**返回；下面的默认值即抽象签名默认值。

| 方法 | 默认 limit | 边界语义 |
|------|-----------|---------|
| `list_messages(thread_id, *, before_seq, after_seq, user_id=AUTO)` | 50 | 只含 `category="message"`；`before_seq` = seq < 游标的**最后** limit 条；`after_seq` = seq > 游标的**最初** limit 条；都不给 = **最新** limit 条（仍升序） |
| `list_messages_by_run(thread_id, run_id, *, before_seq, after_seq)` | 50 | 同窗口语义，但限定单 run |
| `list_events(thread_id, run_id, *, event_types, task_id, limit=500, after_seq, user_id=AUTO)` | 500 | 单 run 全类别；`task_id` 匹配 `metadata["task_id"]`，DB 在 LIMIT **之前**用 SQL JSON 探针过滤（`db.py:364`，issue #3779），所以单 task 翻页不被 run 级 limit 截断；只有前向 `after_seq` |
| `find_latest_ai_message_run_ids(thread_id, message_ids, *, user_id=AUTO)` | 每页 1000 | 反向分页的 **complete-or-error** 契约：空输入不碰存储直接返回 `{}`；整页无法形成安全推进的 `seq` 游标时抛 `IncompleteMessageRunLookupError`（`base.py:23-24`）而非静默漏；调用方只能在**正常返回**后把 miss 当"不存在"的证据 |
| `get_message_seqs(thread_id, identities, *, user_id=AUTO)` | — | 每个 identity 取**最早** seq（重复持久化的消息保留首次位置）；未持久化的 identity 直接缺席，不是错误 |
| `get_last_visible_ai_seq_by_run(thread_id, run_ids, *, user_id=AUTO)` | — | 每个 run 最后一条非 `middleware:` 的 AI 消息 seq（`llm.ai.response`，兼容旧的 `ai_message`） |
| `put_if_absent(...)` | — | run 内按 `event_type` 的幂等单例，返回 `(record, created)`；检查与写入必须与普通写者串行（见下节） |

接口不对称（v2.1.0 源码）：抽象签名里 `count_messages()`（`base.py:242`）与 `list_messages_by_run()`（`base.py:210`）**没有** `user_id`，只有 `DbRunEventStore` 的 override 额外接受它——这两个方法不能对任意后端统一传 owner 过滤。

## 🆕 变更串行域（mutation fence）与删除签名（sync #7，upstream #5535）

事件存储的所有**线程级变更**共享一个串行域：`put` / `put_batch` / `put_if_absent` / `delete_by_thread` / `delete_by_run`。

| 层 | 手段 |
|----|------|
| 进程内 | 每线程 `asyncio` 锁（`_get_write_lock()`，另有 weak registry + 引用 pin 防 release/acquire 竞态） |
| PostgreSQL 跨进程 | 事务级 advisory lock `pg_advisory_xact_lock(hashtext(thread_id))`，由 `DbRunEventStore._acquire_thread_mutation_fence()` 取；写路径经 `_max_seq_for_thread()` 内部调用它，两个 delete 直接调用（`db.py:524` / `558`）。只读方法（`list_*`）不取 |
| SQLite | 无跨进程 fence，依赖上面的进程内锁（故多实例部署要求 Postgres） |
| JSONL | 自己的 `_run_mutation` 提供等价保证 |

进程内锁的生命周期：`DbRunEventStore._get_write_lock()` 每次调用都把当前 generation 重新 pin 到 `_write_lock_pins`（`db.py:47-56`）；`delete_by_thread()` 在删除完成后只 `pop` 掉 pin 让该线程 retire，**不**直接从 weak registry 删条——`asyncio.Lock.release()` 会在排队 waiter 恢复前清掉 `locked()`，直接删会在 handoff 窗口把同一线程劈成两代锁（`db.py:532-539`）。`delete_by_run()` 故意保留 pin，因为线程仍然活着（`db.py:549-553`）。

这样删除**无法**与一个已被准入的写者交错、在 `count` 与 `commit` 之间落进行——否则会"复活"一个刚被删掉的线程。

**删除签名统一为 owner-scoped**：`delete_by_thread(thread_id, *, user_id=AUTO)` / `delete_by_run(thread_id, run_id, *, user_id=AUTO)` 遵循与读方法相同的三态约定（`user_context.resolve_user_id()`：`AUTO` 解析请求上下文，**无上下文时抛 `RuntimeError`**；显式 id 限定所有者；`None` 关掉所有者过滤，供 migration/CLI）。DB 后端按 `user_id` 过滤行；memory 与 JSONL 的存储本身不按用户分区，**接受该参数只为接口一致性并忽略它**。Gateway 侧对第三方（legacy）`RunEventStore` 实现做了兼容：用 `inspect.signature` 判断能否传 `user_id`，只有签名支持时才带（无法 inspect 或后端内部抛出的 `TypeError` **不会**触发重试）。

**这是串行化，不是 incarnation fence**：一个在删除**之前**就已准入的变更，仍可能在删除之后才真正执行。阻止旧 incarnation 复活需要独立的 durable generation 契约——`threads_meta.incarnation` 列在 v2.1.0 已存在（migration `0019`），但没有任何 fencing 逻辑消费它。

**注意**：删除后该线程的 `seq` **从 1 重新开始**——DB store 的 `put` 用 `seq = (max_seq or 0) + 1`（`db.py:204`），memory 与 JSONL 在删除时清掉各自进程内的 `_seq_counters`（`memory.py:225`、`jsonl.py:443`），所以下一条事件重新取得 seq=1。被删线程的事件流不再可读（这正是目的：`GET /threads/{id}/messages` 不能读回已删线程的历史）。

## 消费方式（读同一批行的不同投影）

| 消费者 | 读取路径 |
|--------|---------|
| 前端线程历史 | `GET /api/threads/{id}/messages/page` → `list_messages()`，过滤 middleware 行、subagent AI 响应、被替代的 regenerate run |
| 单 run 消息 | thread-scoped / stateless `GET .../runs/{rid}/messages` → `list_messages_by_run()` |
| **调试/审计端点** | `GET /api/threads/{id}/runs/{rid}/events?event_types=&task_id=&limit=&after_seq=` → `list_events()` |
| 历史 subtask 卡片 | run-events 端点按 `task_id` 过滤 `subagent.step` |
| Memory 审计 | 过滤 `context:memory`，比 `content_sha256`（全文不重复进事件存储） |
| Workspace 审查 | `GET /api/threads/{id}/runs/{rid}/workspace-changes` → 最新 `workspace_changes` |

**调试端点**是生产排障的入口：`event_types` 过滤（如 `context:memory`、`run.error`、`middleware:guardrail`），`task_id` 翻 subagent 步，`after_seq` 前向游标翻页。

## token/成本不靠读事件行

`RunJournal` 在回调触发时**累计**用量，worker 把聚合写进 `RunRow`。不要从事件行反推 token 汇总。

## 已知缺口（契约 `known_gaps[]`）

契约文件把 6 个缺口连同状态一起冻结了（下面是逐条中文对照；状态原文见 `contracts/run_event_stream_contract.json`）：

| id | 状态 | 含义 |
|----|------|------|
| `mixed-event-name-separators` | frozen for compatibility | 事件名混用点号/冒号/裸词（`run.start` / `context:memory` / `workspace_changes`），**为兼容而冻结**；将来要统一必须走版本化迁移或双写期 |
| `tool-call-intent` | not first-class | tool call 意图内嵌在 `llm.ai.response.content.tool_calls`，不是一级事件；`llm.tool.result` 只记录返回的消息，**丢失或超时的 tool result 可能没有任何 outcome 事件** |
| `terminal-run-status` | split source of truth | `run.end` 只是根图完成标记（恒 `success`）；`RunRow.status`（success/error/interrupted/timeout）才是权威，worker 丢失可能不留终端事件 |
| `run-end-backend-serialization` | backend-dependent opaque payload | `run.end.content` 故意 opaque：memory 保留嵌套 Python 值，JSONL/DB 把非 JSON 原生值字符串化——跨后端不保证嵌套一致 |
| `middleware-coverage` | partial | loop-detection / deferred-tool promotion / tool-progress 事件覆盖 lead agent 与普通 task-tool subagent 运行；**durable batch subagent 不覆盖** |
| `run-scoped-observation-context` | manual wiring | journal 归属、token 计账、外部 tracing metadata 仍在多个 LLM 调用点**手工挂接** |

另有一条不属于"缺口"但消费方必须知道的设计事实：外部 Langfuse/LangSmith 是**并行**的 callback 管线，不读事件行，只靠 trace metadata 关联。
