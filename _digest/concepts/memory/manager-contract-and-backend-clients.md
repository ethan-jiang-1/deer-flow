---
title: "Memory — Manager 契约面、工具面与后端客户端"
description: "补齐 extract-queue-persist-pipeline.md 未写的契约：MemoryManager ABC 的分层/不变量/读失败策略/单例工厂与 host hook、get_memory_tools 的 JSON 工具面、summarization 挂钩点，以及 deermem/mem0/honcho/openviking/noop 各 backend 的 client/config 初始化与失败模式。"
topics: [memory, pluggable-backend, tool-mode, failure-policy, summarization-hook, honcho, mem0, openviking]
---

# Memory — Manager 契约面、工具面与后端客户端

> 提取 / 队列 / 存储 / 驱逐 / staleness / consolidation 已在
> [extract-queue-persist-pipeline.md](extract-queue-persist-pipeline.md) 详述。本文只补它没写的三块：
> **ABC 契约面**、**`get_memory_tools` 工具面**、**`summarization_hook` 挂钩点**，以及**各 backend client/config 的初始化与失败模式**。

## MemoryManager 契约面（`manager.py`）

### 分层：tier-1 abstract / tier-2 默认 / tier-3 可选

`MemoryManager` 是 pydantic `BaseModel` 而非裸 `ABC`：字段获得校验与序列化，`ModelMetaclass` 派生自 `ABCMeta` 所以未实现的 `@abstractmethod` 在**实例化**时 `TypeError`（不是首次调用时）。`backend_config` 的 `None` 被 coerce 成 `{}`（零配置合法）；`mode` 是 `Literal["middleware","tool"]`；backend 私有依赖（storage/llm/queue…）必须是 `PrivateAttr`，在 `model_post_init` / `from_config` 里构造（`manager.py:102-160`）。

| 层级 | 成员 | 契约 |
|------|------|------|
| **tier-1 `@abstractmethod`** | `add` / `get_context` / `from_config`（classmethod） | 每个 backend 必须实现；noop 以空实现满足 |
| **tier-2 有默认** | `add_nowait`→委托 `add`；`search` / `get_memory` / `delete_memory` / `clear_memory` / `import_memory` / `export_memory`→`raise NotImplementedError`；`cancel_by_agent`→`0`；`shutdown_flush`→`True` | 不支持的 backend 继承默认，调用方 catch `NotImplementedError`（Gateway → 501） |
| **tier-3 可选钩子** | `warm()` 三态；`reload_memory` / `create_fact` / `delete_fact` / `update_fact`→raise；`on_pre_compress`→`""`；`on_turn_start`→`None`；`close()`→`None` | `warm()` 返回 `True`=成功/已缓存、`False`=尝试过但失败、`None`=无可预热（host 会打"skipping"而不是误导性的"warmed successfully"） |
| **async 占位** | `aadd` / `aget_context` / `asearch` | 默认委托同步版（无并发收益，真正的 LLM 调用仍是同步的） |

来源：`manager.py:225-576`（tier-1 230-271、tier-2 273-426、tier-3 428-576、async 511-545）。

**dead contract**：`delete_memory` 与 `export_memory` 零调用方（`/memory/export` 路由实际走 `get_memory`），保留默认 raise 只为可用性，不要求 backend 实现（`manager.py:130-136,325-333,391-399`）。

### 实例化期不变量

- `supports_search`（ClassVar）**必须与"是否真的 override 了 `search()`"一致**，否则构造期 `ValueError`——防止声明与实现漂移（override 了却忘设 flag → tool 模式被误导性拒绝；设了 flag 却没 override → 首次 `memory_search` 才 `NotImplementedError`）（`manager.py:161-172,196-223`）。
- `mode="tool"` 额外要求 `search()` 被 override（同上校验）。这解释了 noop 为何也把 `supports_search=True`：它把 `search()` override 成返回 `[]`。
- `requires_passive_writes_in_tool_mode`（ClassVar，默认 `False`）：依赖"整段对话抽取"而非 fact CRUD 的远端后端（mem0 / honcho）设为 `True`，让 tool 模式保留 `MemoryMiddleware → add()` 的被动写入（`manager.py:169-172`）。`backend_requires_passive_writes_in_tool_mode(manager_class)` 只解析类、**不构造实例**——agent 装配不会触发 backend startup 检查或网络 I/O（`manager.py:678-684`）。

### 读失败策略（严格读）

错误层次（`manager.py:86-99`）：

```
MemoryManagerError(RuntimeError)
├── MemoryReadError        # 必需的记忆读失败 ⇒ 调用方不得继续
├── MemoryConflictError    # 写输掉乐观并发竞争
└── MemoryCorruptionError  # 持久化数据无法安全读取
```

契约（`manager.py:251-271`）：容忍读失败的 backend 返回空串；要求记忆上下文的 backend 抛 `MemoryReadError`，并暴露 `read_failures_are_fatal`，让 **caller-owned timeout 在 backend 调用返回之前**就能保持同一策略。

两层解析，职责不同：

- `read_failures_are_fatal_for_config(backend_config)`（classmethod）**只用内存里的 config、绝不 I/O**；基类默认只看 legacy `failure_policy.read == "fail_closed"`，其余设置默认宽容，除非 backend 覆写该 resolver（`manager.py:174-194`）。
- `memory_read_failures_are_fatal(manager_class, backend_config, *, resolved_only=False)`：不构造新 manager；`resolved_only=True` 时**绝不扫描/导入 backend**，类未加载返回 `None`（调用方在自己的 bounded worker 里补完 discovery/config reload）；非法 config 与完整解析失败一律 **fail closed（`True`）**（`manager.py:971-995`）。

Gateway 映射：`MemoryConflictError` → **409** "Memory changed concurrently; reload and retry."；`MemoryCorruptionError` → **500** "Stored memory data is corrupted."；tier-2/3 默认的 `NotImplementedError` → **501**（`backend/app/gateway/routers/memory.py:126-134`）。

### 后端发现与单例工厂

- `_scan_backends()`：扫 `backends/<name>/`，子包 `__init__.py` 暴露 `MANAGER_CLASS`（且必须是 `MemoryManager` 子类）即注册，**目录名 = 后端短名 = `manager_class` 配置值**；导入失败的 backend 只 log + skip，绝不带崩工厂；结果进程内缓存，`reset_memory_manager()` 一并清空（`manager.py:580-623,998-1007`）。
- `_resolve_manager_class()`：先查短名，再按 dotted path（`pkg.mod:Cls` 或 `pkg.mod.Cls`）解析；都失败**抛 `ValueError`，绝不静默 fallback**——memory 是持久状态，静默替换 store 是数据完整性 footgun（`manager.py:626-675`）。
- `get_memory_manager()`：双重检查锁保证多线程首次竞争只建一个实例；`backend_config.storage_path` 为空 → `runtime_home()`；**相对路径按 `runtime_home()` 解析**（保持 pre-abstraction 的 base_dir 语义、不随 CWD 漂移）；"`storage_path` 是文件"的校验属 `DeerMemConfig.model_validator`（绕开工厂直接构造也会触发）（`manager.py:913-968`）。

### host hook 注入

工厂是 hook 的**提供者**，每个 backend 的 `from_config` 是**消费者**（新增 backend 不改工厂）：

| hook | 内容 |
|------|------|
| `callbacks` | `LangfuseMemoryCallbacks`：`on_memory_llm_call` 把 langfuse 元数据 merge 进 `invoke_config`；`on_memory_llm_result` 在扩展有 system-model observer 时经 `deerflow_extension_api` 派发，桥自身失败只 warn（`manager.py:701-792`） |
| `should_keep_hidden_message` | 只保留携带 human-input clarification 响应的 `hide_from_ui` 消息（其余框架内部隐藏消息丢弃）（`manager.py:795-806`） |
| `trace_context_manager` | `ensure_trace_context`（`manager.py:902-907`） |
| `host_llm_factory` | 懒建 app 默认模型的**工厂**（有自带 model 的 backend 不会白建一个默认模型）（`manager.py:809-825,891-910`） |
| `extraction_callback` | 稳定 metrics 键 `facts_extracted` / `facts_passed_confidence` / `rejected_low_confidence` / `rejected_by_scope_gate` / `scope_gate_rejections` / `token_usage`；提取拒绝率或 fact scope-gate 拒绝率 **> 60% 打 warning**（prompt / threshold 回归的可观测面）（`manager.py:828-888`） |

`from_config(backend_config, *, mode="middleware", **host_hooks)` 是唯一构造入口；**显式写在 `backend_config` 里的值优先**（merge 跳过已存在键）；DeerMem 装配后把 `backend_config` 还原为宿主传入的纯数据（hook 活在 `self._config`，字段保持可序列化）（`manager.py:548-567,891-910`；`deer_mem.py:161-200`）。

## 工具面：`tools.py::get_memory_tools`

`get_memory_tools()` 返回恰好 4 个 LangChain tool：`memory_search` / `memory_add` / `memory_update` / `memory_delete`；agent 工厂在 `memory.mode == "tool"` 时注册（`tools.py:240-250`）。

- **scope 解析**：`_resolve_scope(runtime)` 优先 `runtime.context["agent_name"]`，`user_id` 走 `resolve_runtime_user_id(runtime)`——选 runtime context 而非 ContextVar fallback，保证跨 request/task 边界的持久化 scope 正确（`tools.py:31-42`）。
- **返回契约是 JSON 字符串，且错误不抛异常**（工具永不带崩 run）：

| 工具 | 参数 | 成功 | 失败模式 |
|------|------|------|----------|
| `memory_search` | `query`, `category=None`, `limit=10` | `{"results":[…],"count":n}`；fact 字段 id/content/category/confidence/createdAt/source | 任意异常 → `{"error": str(exc)}`；DeerMem 侧是大小写不敏感子串匹配、`category` 精确过滤 |
| `memory_add` | `content`, `category="context"`, `confidence=0.7` | `{"fact_id":…,"status":"added"}` | 空内容 → `"empty content"`；`strip().casefold()` 快路径命中既有 fact → `"Duplicate fact"`；backend 未实现 `create_fact` → `"memory backend X does not support create_fact"`；`fact_id is None`（被 `max_facts` 容量策略驱逐）→ 专门的容量错误，**绝不返回悬空 id** |
| `memory_update` | `fact_id`, `content=None`, `category=None`, `confidence=None` | `{"fact_id":…,"status":"updated"}` | 只改提供的字段；未实现 → JSON error；`KeyError` → `"Fact not found: <id>"` |
| `memory_delete` | `fact_id` | `{"fact_id":…,"status":"deleted"}` | 未实现 → JSON error；`KeyError` → `"Fact not found: <id>"` |

来源：`tools.py:45-237`。`memory_add` 的重复检测只是**快路径**——权威检查在 backend 的 create 临界区（DeerMem 每次 revision-conflict 重试都用新快照复核），所以并发工具调用不会都写入同一内容（`tools.py:121-127`）。

- **tool 模式不经过提取安全门**：staleness 的 age/保护类别/per-cycle cap 属于自动 middleware 清理路径；tool 模式的操作者已显式 opt-in 了模型直改/直删，这是配置评审时要注意的差异（`tools.py:155-158`）。

## Summarization 挂钩点：`summarization_hook.py`

- `memory_flush_hook(event: SummarizationEvent)` 是薄入口：门只做 `get_memory_config().enabled` + `event.thread_id`；然后 `user_id = resolve_runtime_user_id(event.runtime)`，调 `get_memory_manager().add_nowait(event.thread_id, list(event.messages_to_summarize), agent_name=event.agent_name, user_id=user_id)`。**过滤、human/AI 校验、correction/reinforcement 检测全在 backend 内**（`summarization_hook.py:11-28`）。
- 注册条件在 summarization middleware 构建期：`memory.enabled and not skip_memory_flush`。`skip_memory_flush` 由 lead/custom agent 的 agent 级 memory opt-out 与"subagent 内部 turn 不写父 thread 的 durable memory"分别设置（hook 以 `thread_id` 为键，而 subagent 共享 parent `thread_id`，若不跳过会把 Task 消息与中间轮写进父 thread 记忆）（`agents/middlewares/summarization_middleware.py:935-946,1010-1014`）。
- 语义差异：`add_nowait` 与普通 `add` 不同——它带 `bypass_watermark=True` 并立刻（0 延迟）调度处理，所以 summarization 移除消息前捕获的子集不会让 updater 的 conversation watermark 回退（见下 queue 契约）。

## 各 backend 的 client / config 初始化与失败模式

### DeerMem（默认）：`llm.py` / `queue.py` / `prompt.py` / `retrieval.py`

- **LLM 构建降级**：`build_llm(model_config)` 在 model 为空或 `init_chat_model` 失败（provider/api_key/base_url 配错）时返回 `None` 并打 WARNING——不崩启动；后果是**抽取禁用、CRUD/读/搜索照常、update 在运行时抛底层错误**。`host_llm`（工厂注入的 app 默认模型）优先于 `build_llm(model)`，所以零配置 `model: null` 仍能抽取（`backends/deermem/deermem/core/llm.py:29-64`；`deer_mem.py:132-136`）。
- **构造期 fail fast**：显式 `prompts_dir` 会在 `model_post_init` 立刻校验 global 模板（staleness / consolidation / memory_update），让配置错误在启动暴露而不是"静默丢更新"；per-agent override 只能在首次使用时校验（`deer_mem.py:142-158`）。
- **队列背压契约**（`queue.py`）：深度达到 `queue_max_depth` 后，**新的非信号普通更新被拒绝**（抛 `QueueFull`），但 **signal-bearing 更新与 emergency（bypass）flush 永远准入**——前者捕获重要记忆，后者捕获即将被 summarization 移除的消息，两者都不能等下一轮重喂；同 key 更新是合并（不增长深度）。DeerMem 自己 catch `QueueFull` → log + drop，让背压退化为"本轮跳过"，而不是穿透 `MemoryMiddleware.after_agent` 破坏 run；被 drop 的更新下一轮会被重喂（watermark 未推进）（`queue.py:34-41,180-188`；`deer_mem.py:222-239`）。
- **debounce key 含 `bypass_watermark`**：emergency flush 与普通更新**共存而非替换**同 `(thread,user,agent)` 的 pending 普通更新，否则会丢掉普通更新尚未抽取的尾部；signal 取并集（`queue.py:64-70,158-204`）。
- **`flush_sync(timeout)` 处理两处竞态**：(1) 先 join 已在跑的 `_process_queue` worker——否则 `flush()` 看到 `_processing=True` 会 no-op 并谎报成功，而 worker 正拿着已出队的 context 做同步 LLM 调用，进程退出即丢；(2) 真正排空放 daemon 线程并用 `Event.wait` 做硬超时（LLM 调用不可中断）。**只有"队列空 + 无 worker + flush 未抛"才返回 `True`**。shutdown drain 跳过条目间 0.5s 限速 sleep，把预算花在 LLM 调用上（`queue.py:309-394`）。
- **`cancel_by_agent` scope**：只匹配仍在 `_items` 里的 pending context；已被 in-flight worker 取走的一律不动（中断 LLM 调用属于 durable outbox 的职责）。`user_id=None` 只匹配 legacy 无用户根，**不表示"所有用户"**；`all_agents=True` 忽略 `agent_name`，取消该 user scope 内所有 agent bucket（`queue.py:403-446`；ABC 上的同一契约见 `manager.py:350-378`）。
- **检索策略**（`retrieval.py`）：FTS5 查询四段式——advanced 语法（AND/OR/NOT/NEAR/短语/前缀/分组）直接透传 MATCH；自然语言用 jieba（可选 extra `memory-zh`）分词、每个 token 加引号后 OR 连接（防标点变成 FTS5 运算符/语法错误）；advanced 报错则退回 tokenized OR；仍失败返回空。排序 `BM25 × 时间衰减 + confidence × 0.2`；`scope_user`/`scope_agent`/`category` 是 SQL 侧精确过滤（`retrieval.py:63-101,308-416`）。SQLite 连接 `check_same_thread=False` + `RLock` 串行化所有变更调用，WAL + `busy_timeout=30000`；**外部调用者不得绕过公开 API 直接碰 `self._conn`**（`retrieval.py:103-123`）。
- **`PromptConfigurationError`**：模板缺失/渲染变量不齐是专用构造期错误类型（`prompt.py:20`）；自定义 prompts_dir 必须带同样的 classification 字段，旧模板会让抽取写入 fail closed（详见 [extract-queue-persist-pipeline.md](extract-queue-persist-pipeline.md) 的近重复门与分类门）。

### mem0：`config.py` / `client.py` / `mem0_manager.py`

- 配置解析 **fail fast**，未知键直接 `ValueError`（只有 host 注入的 `storage_path` / `should_keep_hidden_message` 被接受并忽略——持久状态的配置 typo 不能静默回默认）：`failure_policy: {read: fail_open|fail_closed, write: log_and_drop|raise}`、`startup_policy: fail_fast|tolerate`、`top_k ∈ [1,1000]`、`score_threshold ∈ [0,1]`、`max_injection_chars > 0`、`timeout_seconds` 有限且 >0、`api_key_env` 非空、`base_url` 必须是绝对 http(s) URL，**明文 http 携带 API key 时必须显式 `allow_insecure_http: true`**（`backends/mem0/config.py:26-118`）。API key 从环境变量读，缺失抛错（`config.py:120-125`）。
- 初始化：`model_post_init` 建 `Mem0Config` + `Mem0Client`；`from_config` 在 `startup_policy == "fail_fast"` 时用 **`ping()` 做鉴权探测**——列一个永远空的哨兵 user bucket（`__deerflow_startup_check__`），证明 key 可用而不触碰真实数据；`tolerate` 推迟到首次使用（`mem0_manager.py:83-103`；`client.py:122-128`）。
- 客户端错误层次：`Mem0APIError`（传输 / 4xx / 5xx）、`Mem0AuthError`（401）；空 body 返回 `{}`；JSON 解析失败抛 `Mem0APIError`（`client.py:16-59`）。
- **读写策略落地**：`_read_or_fallback`——`fail_open` 只 log + 返回 fallback，`fail_closed` 抛 `MemoryReadError`；`_write_or_drop`——`log_and_drop` 只 log（at-most-once），`raise` 抛 `MemoryManagerError`（`mem0_manager.py:116-133`）。`read_failures_are_fatal_for_config` 由 `Mem0Config` 解析得到，不落 I/O。
- 语义：identity 1:1（`user_id→user_id`、`agent_name→agent_id`、`thread_id→run_id`）；filters 至少需要一个 entity id，否则读返回 `""`/`[]`、clear/delete 是 no-op；`add` 是 fire-and-forget（mem0 服务端异步抽取，response 的 event_id 不轮询）；`get_context` 注入"最近 top_k 条"，**按条目边界截断**（放不下整条的跳过、靠后的短条目仍可能入内），全部超预算时返回空并 warning，绝不注入半条；`category` 搜索翻译成 `{"categories": {"contains": category}}`；`supports_search=True` + `requires_passive_writes_in_tool_mode=True`（`mem0_manager.py:29-114,136-282`）。
- `close()` 关 HTTP 连接池（`mem0_manager.py:105-107`）。

### Honcho：`config.py` / `client.py` / `honcho_manager.py`

- 构造期校验：`timeout_seconds` / `connect_timeout_seconds` 有限且 >0；`message_char_limit` / `max_injection_chars` > 0（负数会变成 Python 负切片而非长度上限）；`api_key` + 明文 http 必须显式 `allow_insecure_http: true`；`workspace_overrides` / `user_peer_overrides` 的**空值直接报错**（空串会静默回落默认派生、YAML null 会字符串化成 id `"None"`）（`backends/honcho/config.py:24-88`）。
- **不做连通性探测**：`from_config` 只做配置校验——"暂时不可达的 Honcho 不能阻塞 Gateway 启动"，读失败按 `failure_policy.read` 降级；`read_failures_are_fatal_for_config` 由 config 的 `read_fail_closed` 得到（`honcho_manager.py:110-130`）。
- 客户端：裸 httpx 打 Honcho v3 REST；peers/sessions 是服务端 get-or-create ⇒ 每次调用幂等；非 2xx / 传输错误 → `HonchoRequestError`，非 JSON 响应也抛错（`client.py:18-71`）。
- 身份：`workspace_overrides` 精确匹配 **raw（未清洗）key**，否则 `workspace_prefix + _stable_id(user_id)`；`_stable_id = sanitize_id(raw)[:48] + "-" + sha256(raw)[:8]`——`sanitize_id` 会把连续非法字符折叠成单个 `-`（`"user.name@x"` 与 `"user-name@x"` 同形），哈希后缀让默认派生路径碰撞抵抗；session id = `df-` + `_stable_id(thread_id)`（同理避免 `t.1`/`t-1` 合并）；**缺 `user_id` fail closed**：写变 no-op、读返回空，绝不落共享 fallback workspace（`honcho_manager.py:75-139`）。
- `close()` 关连接池（`client.py:35-36`）。

### OpenViking：`config.py`

- 配置校验（构造期 fail fast）：已移除的自定义 HTTP 字段（`connect_timeout_seconds`/`max_connections`/`max_keepalive_connections`/`max_retries`/`pool_timeout_seconds`/`read_timeout_seconds`/`write_timeout_seconds`）与 `auth_mode`/`account`（trusted 模式不再支持，必须 USER API key + `owner_user_id`）直接报错；未知字段统一列出并报错；`owner_user_id` 非空、USER API key 必须能从 `api_key_env` 读到；`default_peer_id` 必须匹配 `^[a-z0-9][a-z0-9_-]{0,63}$` 且**不得以保留前缀 `df-agent-` 开头**；明文 HTTP 仅允许 localhost / `openviking`（除非显式 opt-in）；`timeout_seconds` 有限 >0；`retrieval.top_k ∈ [1,100]`、`score_threshold ∈ [0,1]`、`max_injection_chars ∈ [256,100000]`、`content_mode ∈ {auto,abstract,overview,read}`、`injection_query` 非空；`startup_policy ∈ {fail_fast,warn}`；`failure_policy.read ∈ {fail_open,raise}`、`write ∈ {log_and_drop,raise}`；`max_seen_message_ids ∈ [16,10000]`（`backends/openviking/config.py:49-143`）。

### noop：`config.py` / `noop_manager.py`

- 模板后端：`supports_search=True` 且 `search()` override 成返回 `[]`（满足不变量）；`add` / `add_nowait` / `get_context` / `search` 全空实现；`get_memory` 返回最小 `{"facts": []}`（Gateway 用默认值补全 version/lastUpdated/user/history）；`delete_memory` / `export_memory` **继承默认 raise**（dead contract）；`shutdown_flush` 直接 `True`；`from_config` 忽略所有 host hooks（`backends/noop/noop_manager.py:63-189`）。
- 新 backend 的落地步骤，以及**"整个 backend 目录里唯一允许的 `from deerflow` import 是 ABC 契约行"**的可移植性金律在 `backends/noop/config.py:1-34` 与 `noop_manager.py:13-38`（与 [extract-queue-persist-pipeline.md](extract-queue-persist-pipeline.md) 的后端发现机制互补）。

---
> **See also:** [extract-queue-persist-pipeline.md](extract-queue-persist-pipeline.md) · [MemoryManager source](../../../backend/packages/harness/deerflow/agents/memory/manager.py) · [memory tools source](../../../backend/packages/harness/deerflow/agents/memory/tools.py) · [summarization hook source](../../../backend/packages/harness/deerflow/agents/memory/summarization_hook.py)
