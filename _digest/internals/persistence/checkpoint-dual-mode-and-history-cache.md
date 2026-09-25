---
title: "Checkpoint 双模式（full/delta）与 delta 历史缓存"
description: "`database.checkpoint_channel_mode` 把 checkpointer 分成 full（整快照 channel_values）与 delta（LangGraph DeltaChannel：哨兵 blob + 每步 writes）两种存储表示；delta 模式下额外挂一层只读历史缓存 `CachedHistorySaver`。"
topics: [persistence, checkpointer, delta-channel, cache, gateway]
---

# Checkpoint 双模式（full/delta）与 delta 历史缓存

> 本文覆盖源码：`config/database_config.py`、`runtime/checkpoint_mode.py`、`runtime/checkpoint_state.py`、`runtime/checkpoint_cache/*`、`runtime/checkpointer/cached_saver.py`、`runtime/checkpointer/{provider,async_provider}.py`、`agents/thread_state.py`（mode 适配部分）、`app/gateway/services.py`（accessor graph 缓存）、`app/gateway/deps.py`（启动冻结）。
>
> 与 [db-checkpointer-store-backends.md](db-checkpointer-store-backends.md) 的关系：那篇讲"checkpointer 选哪个后端 + 迁移"，本文讲"同一条 checkpoint 链用哪种**表示**存 + delta 模式专有的历史缓存层"。两篇都以 `make_checkpointer()` 为交汇点。

## 1. 两种 channel 表示

`database.checkpoint_channel_mode: Literal["full", "delta"]`（默认 `full`，`config/database_config.py:59` 定义类型，`:147` 定义字段）：

| 模式 | 存储内容 | 读取方 |
|------|----------|--------|
| `full` | 每个 checkpoint 存**完整** `channel_values`（LangGraph 传统行为） | 任何进程 |
| `delta` | 累积型 channel（`messages`）改用 LangGraph `DeltaChannel`：存哨兵 blob + 每步 `writes`，每 N 步落一次全量快照 | **必须**也是 delta 进程（见 §2 的 fail-closed 门） |

约束（都在字段 description 里）：

- **重启必需**：模式被编译进每个图的 channel 表，运行中不能改（`checkpoint_channel_mode` description、`runtime/checkpoint_mode.py:41-45`）。
- **同一 checkpoint 库的所有进程必须同值**——否则不同进程对同一批 thread 应用不同表示。
- **迁移方向单向**：`full → delta` 受支持；delta 进程读 legacy full checkpoint 透明兼容，反向不兼容（`checkpoint_mode.py` 模块 docstring）。

### 相关子配置

| 键 | 默认 | 语义 | 重启必需 |
|----|------|------|----------|
| `database.checkpoint_channel_mode` | `full` | `full` / `delta` | 是 |
| `database.checkpoint_delta.snapshot_frequency` | `10`（`DEFAULT_CHECKPOINT_SNAPSHOT_FREQUENCY`，`database_config.py:61`） | DeltaChannel 快照节奏：每 N 次 per-step 写落一个全量 messages 快照。越大 checkpoint 越小、物化越慢 | 是（编译进 channel 表） |
| `database.checkpoint_graph_cache.accessor_graph_max` | `64` | Gateway 侧编译态 thread-state accessor 图的进程内缓存上限（按 `(assistant, mode, cadence)` 分键） | **否**（热重载，只在淘汰检查时重读） |
| `database.checkpoint_cache.*` | 见 §4 | delta 历史缓存策略（纯性能，跨进程可不同） | 否 |

`checkpoint_graph_cache` 的读取走 `resolve_checkpoint_graph_cache_max()`（`database_config.py:45-58`）：非 plain `int >= 1` 一律回退默认值——刻意容忍测试里的 `SimpleNamespace`/`MagicMock` stub 配置。

**legacy key shim**：旧的扁平键 `checkpoint_delta_snapshot_frequency` 被 `DatabaseConfig._migrate_legacy_snapshot_frequency()`（`database_config.py:213-230` 附近的 `model_validator(mode="before")`）搬到 `checkpoint_delta.snapshot_frequency`。因为 `DatabaseConfig` 是 pydantic `extra="ignore"`，不做这个 shim 的话旧 config.yaml 会**静默**退回新的默认节奏，而不是运维选的值；显式写的嵌套键优先。

## 2. 进程冻结、元数据标记与 fail-closed 门（`runtime/checkpoint_mode.py`，146 行）

三个全局规则：

1. **进程冻结（freeze）**
   - `freeze_checkpoint_channel_mode(mode)`：首次调用写入进程级 `_frozen_checkpoint_channel_mode`；之后传不同值抛 `CheckpointModeReconfigurationError`（"restart-required and cannot change in a running process"）。
   - `freeze_checkpoint_snapshot_frequency(int)` 是同构的节奏冻结；`<= 0` 抛 `ValueError`。
   - `frozen_checkpoint_channel_mode()` / `frozen_checkpoint_snapshot_frequency()` 供"模式已定"的路径读取；`resolve_checkpoint_snapshot_frequency(explicit)` 的解析顺序是 **显式参数 → 进程冻结值 → 配置默认**。
   - 冻结点：Gateway 启动 `app/gateway/deps.py:450`；嵌入式 `client.py:226`；lead agent 构建 `agents/lead_agent/agent.py:825-833`（`requested_mode` 与已冻结值不一致时由 freeze 抛错）。

2. **checkpoint 元数据标记**（`inject_checkpoint_mode`）
   - 标记只写**一份**：`metadata["deerflow_checkpoint_channel_mode"] = "delta"`（`CHECKPOINT_MODE_METADATA_KEY`）。full 模式**移除**该键——因此契约是"**absence = full**"。
   - 同时把模式写进 `config.configurable["__deerflow_checkpoint_channel_mode"]`（`INTERNAL_CHECKPOINT_MODE_KEY`），供图构建期使用。
   - `checkpoint_metadata_uses_delta()` 判定时为**兼容旧数据**也接受"存在 `counters_since_delta_snapshot` 且含 `messages`"这一形态；`checkpoint_tuple_uses_delta()` / `state_snapshot_uses_delta()` 是 tuple / `StateSnapshot` 两个入口的薄包装。
   - 节奏（`snapshot_frequency`）**故意不写进元数据**：模式标记的 absence 契约和 full→delta 迁移语义不能被节奏值改变（`freeze_checkpoint_snapshot_frequency` docstring）。

3. **fail-closed 门**（full 进程碰到 delta thread 必须报错，而不是把空/残缺 state 当成真的用）
   - `raise_if_snapshot_incompatible(snapshot, mode)`：在 `get_state`/`get_state_history` 返回的 `StateSnapshot` 上检查，读路径只多一次 checkpoint fetch（marker 就在 `snapshot.metadata`）。危险的是**静默使用**空 state，所以调用方拿不到它。
   - `raise_if_checkpoint_tuple_incompatible(tuple, mode)`：暴露原始 metadata 前的门。
   - `ensure_checkpoint_mode_compatible()` / `aensure_checkpoint_mode_compatible()`：**写前**门（写不能撤销，所以事先查 `get_tuple`/`aget_tuple`）。delta 模式直接 return（新写没有 legacy 兼容问题）。
   - 违规统一抛 `CheckpointModeMismatchError`，消息固定为 "Thread requires delta mode; materialize and convert its checkpoints before using full mode."

## 3. 唯一的状态读写咽喉：`CheckpointStateAccessor`（`runtime/checkpoint_state.py`，209 行）

delta checkpoint **不存完整 `channel_values`**，直接读 saver 只会看到哨兵值。所以 `CheckpointStateAccessor` 被定义为**所有 thread checkpoint-state 读写的唯一入口**：它绑定"一个编译好的图（携带 mode 匹配的 channel schema）+ checkpointer + 冻结 mode"，每次操作都注入 mode 标记、过兼容门。

| 方法 | 行为 |
|------|------|
| `bind(graph, checkpointer, *, store=None, mode="full")` | 把 checkpointer/store 挂到图上，返回 accessor |
| `get` / `aget` | `graph.get_state()` 后过 `raise_if_snapshot_incompatible` |
| `get_metadata` / `aget_metadata` | 只读 checkpoint metadata，**不物化 channel state**（走 `checkpointer.get_tuple` + tuple 门） |
| `history` / `ahistory` | 逐条过门；`limit <= 0` 返回空列表；手工截断到 `limit`（不信任底层实现） |
| `update` / `aupdate` | 先过写前门，再 `graph.update_state()` |

配套的**只读图 introspection**（供调用方回退到 schema 集合，stub accessor 返回 `None`）：

- `graph_state_schema(graph)`：`StateGraph.schemas` 的第一项（state schema 先于 input/output 注册）。
- `graph_writable_channels(graph)`：排除 Pregel 内部 channel（`__*`）与分支 fan-in（`branch:*`）后的用户可见 channel 名集合。
- `graph_reducer_channels(graph)`：走 reducer 合并的 channel——经典 reducer（`BinaryOperatorAggregate`）与 delta channel（`DeltaChannel`）都在内，两者在任何模式下都需要 `Overwrite` 包装才能做替换式写。

`build_state_mutation_graph(as_node, mode, state_schema=None, *, snapshot_frequency=None)` 编译一个**只做状态变更的图**：单节点、entry = finish、`_finish_state_mutation` 返回 `{}`。用途是整块状态替换（rollback restore、context compaction）：它复用 agent 图的 checkpoint 机制，但**不调度任何 pending 节点**，所以写出的 head 保持 idle。`as_node` 必填（`update_state(as_node=...)` 要求节点已注册）；`state_schema` 应传**该 thread 的有效 schema**——base `ThreadState` 回退不认识自定义 middleware 贡献的 channel，写未知 channel 会被**静默丢弃**。回退路径自己按 `显式 → 冻结 → 默认` 解析 delta 节奏，因为显式传入的 `state_schema` 身份里已带节奏。

实际调用点（契约的验收面）：`runtime/runs/worker.py`（resume/rollback 用 `build_state_mutation_graph("checkpoint_resume"|"rollback_restore", ...)`，`:2316` / `:2381`）、`client.py:727`、`runtime/context_compaction.py`。

**accessor 图的进程内缓存**（`app/gateway/services.py:1032-1075`）：accessor 操作从不执行图节点或 middleware，所以 per-request 差异（user/model/skills）不影响物化语义，编译图按 `(assistant_id, mode, snapshot_frequency)` 稳定。`_state_accessor_graph_cache` 每次命中都**重新校验 factory 与 app_config 的身份**（`is` 比较），所以打补丁的 factory 立即生效、config.yaml 热重载（重建 AppConfig 对象）不会命中旧图；缓存的旧引用会拖住旧 config，identity 复用无法造假命中。缓存满时整体 clear，上限由 `database.checkpoint_graph_cache.accessor_graph_max` 决定并**每次淘汰判断都重读**；构建走 `KeyedLockTable` 按同一 key 串行化。

## 4. delta 专属：只读历史缓存（`runtime/checkpoint_cache/`）

**为什么可以永不失效（正确性论证，写在 `cached_saver.py` 模块 docstring 与 `checkpoint_cache/base.py` 里）**：一个 checkpoint 的 delta 历史是其**已封闭祖先链**的纯函数——LangGraph 契约排除了目标自身的 pending writes，parent link 在创建时固定，祖先的 writes 在子节点出现后即封闭。因此按 `(thread, ns, checkpoint_id, channel)` 分键的条目是**不可变**的：无需 invalidation，共享后端在多进程间天然一致。

### 4.1 键与契约（`checkpoint_cache/base.py`，80 行）

```python
CACHE_FORMAT_VERSION = 1
make_history_key(key_prefix, thread_id, checkpoint_ns, checkpoint_id, channel) -> str
#   f"{key_prefix}:{thread_id}:{sha256(ns \x00 checkpoint_id \x00 channel)[:24]}"
thread_key_stem(key_prefix, thread_id) -> f"{key_prefix}:{thread_id}:"
```

`thread_id` 保持可读（运维排障），其余分量用 `\x00` 分隔后哈希，避免含 `:` 的 namespace 产生歧义键。

两个 Protocol：

| 接口 | 方法 | 说明 |
|------|------|------|
| `CheckpointHistoryCache`（异步） | `aget_many` / `aset_many` / `adelete_thread(key_prefix, thread_id)` / `stats()` / `aclose()` | delta 模式 + Gateway/async 路径 |
| `SyncCheckpointHistoryCache`（同步） | `get_many` / `set_many` / `delete_thread` / `stats()` | 内嵌/TUI 路径，**只有 memory 后端** |

**唯一的删除 API 是 thread 级**，且它存在的理由是**数据生命周期**而不是正确性：源 checkpoint 被擦除时（thread 删除、租户下线、GDPR 式擦除），该 thread 的缓存历史载荷必须一起消失，而不是留到 LRU 淘汰或 TTL 过期。

`CheckpointCacheStats`：`hits` / `misses` / `evictions` / `entries`（`.as_dict()`）。统计里若出现 `compose_hits` / `full_walks`，那是 `CachedHistorySaver` 自己合并进去的（见 §4.4）。

### 4.2 后端

| 后端 | 类 | 特性 |
|------|----|------|
| memory（默认） | `MemoryCheckpointHistoryCache` | 进程内 `OrderedDict` LRU，命中路径**零序列化**；copy-on-read/write（`writes` 列表新拷、`seed` 共享且从不原地改）；`enabled = max_entries > 0`，`max_entries=0` 即全关 |
| redis | `RedisCheckpointHistoryCache` | `MGET`/`pipeline(transaction=False)` + `SETEX`；值用下游 saver 的 `serde.dumps_typed/loads_typed`，`tag + \x00 + payload` 拼一字节串；`ttl_seconds=0` 显式关闭过期（只靠 redis maxmemory）；`adelete_thread` 用 `SCAN(match=stem+"*", count=500)` + `UNLINK` |

redis 后端的**降级策略**（性能开关不能变成可用性开关）：

- `mget` 抛 `RedisError` → 记 warning、当全 miss 返回（`misses += len(keys)`），**从不**让请求失败。
- 写失败 → 记 warning 跳过，下次读重算。
- 线程清理失败 → 记 warning，残留条目靠 TTL 兜底（源数据已删，所以**从不 raise**）。
- redis 是可选 extra：client 与 `RedisError` 都惰性 import，缺包时报带安装命令的 `ImportError`（`REDIS_INSTALL`）。

### 4.3 工厂与部署身份（`checkpoint_cache/provider.py`，101 行）

`make_checkpoint_cache(app_config, *, serde)` 是 async context manager，镜像 `make_stream_bridge` 的"config → env fallback → memory"形状：

- `config is None` / `type == "memory"` / `max_entries == 0` → memory 后端。**`max_entries == 0` 用"禁用的 memory 后端"统一表达关闭**，于是包装层不需要任何 `None` 检查。
- `type == "redis"` → `RedisCheckpointHistoryCache`，URL 解析顺序 **`config.redis_url` → `DEER_FLOW_CHECKPOINT_CACHE_REDIS_URL` → `REDIS_URL` → `redis://localhost:6379/0`**。
- 其它值 `ValueError`。

键前缀（多部署共享一个 Redis 时防串味）：

```python
checkpoint_cache_db_hash(db_config)   # 只取 host:port/database（postgres）、checkpointer_sqlite_path（sqlite）、"memory"
checkpoint_cache_key_prefix(app_config)
#   config.key_prefix 优先，否则 f"ckpt-hist:v{CACHE_FORMAT_VERSION}:{db_hash}"
```

`_stable_postgres_identity()` 刻意**不哈希原始 URL**：凭据轮换会让缓存命名空间整体变化（冷缓存 + 直到 TTL 的孤儿键），而数据库（以及所有缓存历史）其实没变。URL 解析失败回退原始字符串（仍按部署稳定），且 identity 计算**永不**让配置加载失败。

### 4.4 包装器 `CachedHistorySaver`（`runtime/checkpointer/cached_saver.py`，328 行）

`CachedHistorySaver(inner, cache, *, key_prefix)` 是**任何** `BaseCheckpointSaver` 的 read-through delta-history 包装：

- 构造时 `self.serde = inner.serde`（实例属性遮蔽基类默认 `JsonPlusSerializer`）。
- `__getattr__` 兜住 saver 特有的额外属性（如 `AsyncSqliteSaver.setup`）并转发给 inner；基类**具体定义**的方法都显式转发（`get_tuple`/`list`/`put`/`put_writes`/`get_next_version` + async 孪生），所以 `__getattr__` 只在基类没定义时才触发。
- **唯一被覆写的行为是 delta channel history**（`aget_delta_channel_history` / `get_delta_channel_history`）；其余读写原样透传。

算法（`_aresolve` / `_resolve_sync`，`_COMPOSE_MAX_DEPTH = 8`）：

1. 取目标 tuple；`cache.enabled == False` 或 tuple 不存在 → 直接走 inner（"对所有条目都 miss 再 compose"严格比原始 walk 更费）。
2. 按 channel 建键、批量 `aget_many`；命中进 `found`，未命中进 `missing`。
3. 未命中的按 **compose** 解析：沿 `parent_config` 递归——父的 `channel_values[channel]` 存在 → 记 `compose_hits`，返回 `{writes: 父的该 channel writes, seed: 父值}`；否则查父的历史缓存，仍 miss 且 depth 未耗尽就再递归；**depth 归零**（冷链）则退化为对**那一层**做**一次** inner fast-path walk（`_full_walks += 1`，2 条 SQL），而不是逐祖先 tuple 爬。
4. 每一层 compose 结果都回写缓存（暖前沿跟着 run 走），最终 `entry = {writes: 父历史.writes + 本层writes, seed: 继承}`。
5. 返回时对每个 channel 兜底 `{"writes": []}`。

为什么需要递归 compose：真实 run 每个 super-step 会创建多个 checkpoint，只有一部分被物化成 target，于是父节点通常是**未预热**的中间 checkpoint（实测：500 步 sqlite run 上单层 compose 命中 0）。稳态下递归约 2 层就能落到已预热的祖先。

删除/生命周期语义（**这是容易写错的部分**）：

| inner 操作 | 包装层行为 |
|-----------|-----------|
| `delete_thread` / `adelete_thread` | 转发后 `purge` 该 thread 全部缓存条目 |
| `prune` / `aprune` | 转发后对每个 thread `purge`——prune **重写**这些 thread 的链，不能让缓存历史指向已删祖先或 prune 前的链 |
| `delete_for_runs` / `adelete_for_runs` | **只转发，不清缓存**：run 级删除无法廉价映射回 thread；条目**仍然是正确的**（封闭链论证不受其它链影响），残留保留由 LRU/TTL 兜底。代码注释明确 "No in-tree callers today" |
| `copy_thread` / `acopy_thread` | 只转发（新 thread 自会重新预热） |
| `stats()` | 后端 stats 合并 `compose_hits` / `full_walks` |

**同步/异步约束**：同步 `get_delta_channel_history` 自带 `get_many`/`set_many` 检查，缺失就抛 `TypeError("sync get_delta_channel_history requires a SyncCheckpointHistoryCache (memory backend)")`。这解释了 §5 里"同步 provider 拒绝 redis"。

## 5. 接线：`make_checkpointer()` 什么时候包缓存

两处 provider 都按"**有效模式 = 进程冻结值 or `database.checkpoint_channel_mode`**"判断，只有 `delta` 才包：

- **async**（`runtime/checkpointer/async_provider.py:216-256`，Gateway/FastAPI lifespan 路径）：`_select_inner_checkpointer()` 按 `legacy checkpointer: 段 → 统一 database: 段 → 默认 InMemorySaver` 选内层 saver，然后 `async with make_checkpoint_cache(app_config, serde=saver.serde) as cache: yield CachedHistorySaver(saver, cache, key_prefix=checkpoint_cache_key_prefix(app_config))`。
- **sync**（`runtime/checkpointer/provider.py:165-193`，CLI/内嵌/TUI 路径）：`mode == "delta"` 且 `database.checkpoint_cache.type == "redis"` → 直接 `ValueError("database.checkpoint_cache.type 'redis' is not supported on the sync checkpointer path (TUI/embedded); use 'memory'.")`；否则包同一个 `CachedHistorySaver`，但缓存**是模块级单例**（`_checkpointer_cache` / `_checkpointer_cache_prefix`），而不是每次调用新建：
  - **容量或命名空间变化时重建**（`_max_entries != cache_config.max_entries` 或 `_checkpointer_cache_prefix != key_prefix`）——旧前缀下的条目不可达、也不再被 thread purge 覆盖，所以必须整体换掉。
  - `checkpointer_context()` 路径上不持 `_checkpointer_lock` 重赋该单例是**刻意**的：竞态最坏结果是两个 wrapper 各拿一份新 memory cache，last writer wins，而缓存是纯性能的。
  - 这也解释了 sync 只支持 memory 后端：缓存本来就是进程内的。

**注意**：`checkpoint_cache` 是**纯性能**配置——"never frozen, never required to match across processes"；改它不需要重启，不同 worker 用不同后端/容量也是安全的（条目不可变，共享后端天然一致）。

## 6. mode 适配状态 schema（`agents/thread_state.py`）

delta 模式下 `messages` channel 必须是 `DeltaChannel`，所以 schema 要按 mode 重建：

| 函数 | 行为 |
|------|------|
| `get_thread_state_schema(mode, snapshot_frequency=None)` | `full` → 静态 `ThreadState`；`delta` → `_delta_thread_state_schema(freq)` |
| `_delta_thread_state_schema(freq)`（`@cache` 按节奏分键） | 默认节奏返回静态 `DeltaThreadState`（**保持既有类型检查的身份**）；非默认节奏基于 `ThreadState` 的 `get_type_hints` 造 `TypedDict(f"DeltaThreadState_f{freq}")`，只把 `messages` 换成 `delta_messages_field(freq)` |
| `adapt_state_schema_for_mode(schema, mode, freq)` | 把**任意** schema 适配到 mode；full 原样返回 |
| `_adapt_state_schema_for_delta(schema, freq)`（`@cache`） | 同上但针对传入 schema，类名形如 `Delta{module}_{name}_f{freq}` |
| `normalize_middleware_state_schemas(middleware, mode, freq)` | delta 下 `copy.copy` 每个带 `state_schema` 的 middleware，替换为适配后的 schema（不动原对象） |

解析节奏统一走 `resolve_checkpoint_snapshot_frequency()`（显式 → 冻结 → 默认），见 §2。

delta 的 messages reducer 是 `merge_message_writes`（见 `agents/AGENTS.md` 的契约段）：先归一化当前消息状态一次，然后按带消息 ID 位置索引的顺序折叠写入，并做延迟 tombstone 压缩；必须保持 `add_messages` 的**全部**公开语义（重复 ID、替换位置、removal 错误、`REMOVE_ALL_MESSAGES`、null 写错误、缺失 ID 分配顺序），靠差分测试钉住。**不能**直接用 LangGraph 私有的 `_messages_delta_reducer`——它同样是线性的，但故意省略了这些公开语义。

## 7. 边界与常见误解

- delta 模式下**不允许**绕过 `CheckpointStateAccessor` 直接读 saver 的 `channel_values`——那不是"读到旧值"，而是读到哨兵/残缺值。
- full 进程读 delta thread 会**报错而不是降级**；要迁移必须显式物化并转换 checkpoint。
- `snapshot_frequency` 不进元数据，所以不同节奏的 checkpoint 之间**没有**可检测的标记差异——只能靠"所有进程同值"这一运维约束。
- 缓存**永不需要 invalidation**；`adelete_thread` 是生命周期 API，不是正确性 API。
- `delete_for_runs` 后会留下该 run 的缓存条目（受 LRU/TTL 约束），这是**有意**的，不是 bug。
- `checkpoint_graph_cache.accessor_graph_max` 可以热改；`checkpoint_channel_mode` / `checkpoint_delta.snapshot_frequency` 不可以。
