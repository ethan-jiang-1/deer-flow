---
title: "Memory 系统 — 可插拔后端架构"
description: "DeerFlow 2.1 的 Memory 系统从单体 DeerMem 重构为可插拔后端架构，支持 middleware 和 tool 双模式，新增 consolidation 和 staleness review。"
topics: [memory, persistence, context-injection, pluggable-backend, consolidation, staleness]
---

# Memory 系统 — 可插拔后端架构

> **2.1.0 里程碑 | Breaking Changes**：Memory 从写死的 DeerMem 单体变成 `MemoryManager` ABC + 可插拔后端。只需改一行 `config.yaml` 即可切换后端，DeerFlow 核心代码无需改动。

## 架构总览

```
┌─────────────────────────────────────────────────┐
│                  config.yaml                     │
│  memory.manager_class: deermem|mem0|noop|openviking │
│  memory.mode: middleware | tool                  │
│  memory.backend_config: { ... }                  │
└─────────────────┬───────────────────────────────┘
                  │
┌─────────────────▼───────────────────────────────┐
│           MemoryManager (ABC — 10 methods)         │
│  add / add_nowait / get_context / search         │
│  get_memory / delete_memory / clear_memory       │
│  import_memory / export_memory / shutdown_flush  │
└───────┬────────────┬────────────┬──────────┬─────┘
        │            │            │          │
┌───────▼────┐ ┌─────▼────┐ ┌─────▼────┐ ┌────▼────────┐
│  DeerMem   │ │ mem0     │ │  Noop    │ │ OpenViking  │
│  (default) │ │ 平台 API │ │ (template)│ │ 远程语义检索│
│  JSON+MD   │ │ 客户端   │ │ 空实现    │ │ middleware  │
│  Markdown  │ │          │ │ 复制用    │ │ only        │
└────────────┘ └──────────┘ └──────────┘ └─────────────┘
```

### 两种运行模式

| 模式 | `memory.mode` | 行为 |
|------|--------------|------|
| **Middleware**（默认） | `middleware` | `MemoryMiddleware` 在 `after_agent` 时入队对话 → 后台 debounced LLM 提取 fact → 下次对话时注入 `<memory>` |
| **Tool**（实验性） | `tool` | 注册 `memory_search`/`add`/`update`/`delete` 工具 → 模型主动决定何时搜索、添加、更新、删除 fact |

两种模式共享 prompt 注入和 updater 后端（DeerMem 特有的是 `FileMemoryStorage` + per-user/per-agent 隔离）。OpenViking 远程后端**只支持 middleware 模式**。

---

## 可插拔后端架构

### MemoryManager ABC（10 个方法）

`packages/harness/deerflow/agents/memory/manager.py` 定义了后端无关的抽象：

| 类别 | 方法 | 说明 |
|------|------|------|
| **Write** | `add(thread_id, messages, agent_name, user_id, trace_id)` | 入队对话，debounced 异步更新 |
| | `add_nowait(thread_id, messages, agent_name, user_id)` | 立即入队（summarization 前紧急 flush） |
| **Read** | `get_context(user_id, agent_name, thread_id)` | 返回注入就绪的 memory 文本 |
| | `search(query, top_k, user_id, agent_name, category)` | 搜索匹配 fact |
| **Manage** | `get_memory(user_id, agent_name)` | 返回完整 memory document |
| | `delete_memory(user_id, agent_name)` | 删除整个 bucket |
| | `clear_memory(user_id, agent_name)` | 清空并返回空 document |
| | `import_memory(memory_data, user_id, agent_name)` | 导入 memory document |
| | `export_memory(user_id, agent_name)` | 导出 memory document |
| **Lifecycle** | `shutdown_flush(timeout)` | Graceful shutdown 时排空 pending updates |

### 后端发现机制

```
backends/
├── deermem/          ← 默认后端（JSON 概要 + Markdown fact 文件）
│   ├── __init__.py   # MANAGER_CLASS = DeerMem
│   ├── deer_mem.py   # DeerMem(MemoryManager) 实现
│   └── deermem/      # 自包含子包（可移植到其他 agent）
│       ├── config.py       # DeerMemConfig
│       ├── core/
│       │   ├── storage.py  # FileMemoryStorage（v2: fact 存 Markdown）
│       │   ├── queue.py    # debounced update queue
│       │   ├── updater.py  # LLM-based update + staleness + consolidation
│       │   ├── llm.py      # LLM 调用封装
│       │   ├── paths.py    # 路径解析
│       │   └── prompts/    # 外置 YAML 模板
│       └── ...
├── mem0/             ← 🆕 mem0 平台 API 客户端（远程）
│   ├── __init__.py   # MANAGER_CLASS = Mem0MemoryManager
│   └── client.py
├── noop/             ← 模板后端（空实现，复制即可开始新后端）
│   ├── __init__.py   # MANAGER_CLASS = NoopMemoryManager
│   ├── config.py
│   └── noop_manager.py
├── openviking/       ← 🆕 OpenViking 远程语义检索（middleware only）
│   ├── __init__.py   # MANAGER_CLASS = OpenVikingMemoryManager
│   ├── config.py     # OpenVikingConfig
│   ├── openviking_manager.py
│   └── session.py    # thread ↔ Session 确定性映射
└── <yourname>/       ← 自定义后端（drop-in）
```

工厂 `get_memory_manager()` 按 `manager_class` 配置值解析：
1. `_scan_backends()` 扫描 `backends/` 子目录，每个子包的 `__init__.py` 暴露 `MANAGER_CLASS` 属性即注册（目录名 = 后端短名）
2. 先查注册的短名（`deermem`、`mem0`、`noop`、`openviking`）
3. 再当 dotted path 解析（`pkg.mod:Cls` 或 `pkg.mod.Cls`）
4. 都解析不了 → `ValueError`（不会静默 fallback 到错误后端——memory 是持久化状态，错了就是数据完整性 bug）

Host 通过 `backend_config` dict 向后端注入：
- `storage_path` — 可写状态目录
- `tracing_callback` — LLM 调用的 Langfuse tracing
- `should_keep_hidden_message` — 过滤 `hide_from_ui` 消息
- `host_llm` — 零配置 LLM（`model_name: null` 时用 app default model）
- `trace_context_manager` — 结构化日志 trace 关联

### Breaking Changes

| 变更 | 旧行为 | 新行为 |
|------|--------|--------|
| **Config 结构** | `memory.storage_path`, `memory.max_facts`, ... 平铺在 `memory:` 下 | 迁移到 `memory.backend_config.storage_path` 等，旧字段启动时自动迁移 + warning |
| **`storage_path` 语义** | FILE 路径（如 `memory.json`） | DIRECTORY 路径；per-user memory 在 `{root}/users/{uid}/memory.json` |
| **`/memory/config` API** | 返回 DeerMem 平铺字段 | 返回 `{enabled, mode, injection_enabled, manager_class, backend_config}` |
| **`storage_class` 路径** | `deerflow.agents.memory.storage.FileMemoryStorage` | `deerflow.agents.memory.backends.deermem.deermem.core.storage.FileMemoryStorage` |
| **`storage_class` 签名** | 无参 `__init__` | 必须接受 `config` 参数 |

---

## DeerMem 后端（默认）

### 数据模型（v2：Markdown fact 文件）

**Storage v2 重构**（`storage.py` ~196 → ~1549 行）：fact 不再存在全局 JSON 的 `facts` 字段，改为**每个 fact 一个 Markdown 文件**：

```markdown
---
id: fact_01HZZZZZZZZZZZZZZZZZZZZZZZ
schemaVersion: 2
category: constraint
confidence: 0.95
user_id: alice
agent_name: agent-a
expected_valid_days: 180
createdAt: "2025-01-15T..."
source: conversation
---

# Fact Title
Project uses Python 3.12
```

路径：`{storage_path}/users/{user_id}/agents/{agent_name}/facts/{sha256(fact_id)[:2]}/{fact_id}.md`（SHA-256 前两位分片，保证文件分散）。

**全局 JSON**（`{base_dir}/users/{user_id}/memory.json`）只保留 `version` / `revision` / `user` / `history` 四个字段，**永不存储 facts 或 fact 索引**：

```json
{
  "version": 2,
  "revision": "...",
  "user": { "userContext": {...}, "personalContext": "...", "topOfMind": "..." },
  "history": { "recentMonths": "...", "earlierContext": "...", "longTermBackground": "..." }
}
```

默认 agent 用保留名 `__default__` 作为 fact bucket（真实 custom agent 名不在此文法内）。兼容视图：直接读全局 storage 返回 `facts: []`，而 DeerMem Manager/API 读取会返回所选 agent 的 facts。

### Fact 类别

| Category | 含义 | 示例 |
|----------|------|------|
| `preference` | 用户偏好 | "喜欢中文回复" |
| `knowledge` | 用户知识 | "熟悉 Python" |
| `context` | 上下文 | "在字节工作" |
| `behavior` | 行为模式 | "经常在晚上使用" |
| `goal` | 目标 | "想学 Rust" |
| `correction` | 用户纠正（受保护，永不过期） | "我的名字不是张三" |

### Middleware 模式工作流

```
MemoryMiddleware (after_agent)
    │  过滤消息 → 用户输入 + 最终 AI 回复
    │  捕获 user_id via get_effective_user_id()
    │  入队: manager.add(thread_id, messages, user_id=..., trace_id=...)
    ▼
MemoryQueue (debounced, 30s default)
    │  30s debounce
    │  per-thread 去重
    │  批量化处理
    ▼
MemoryUpdater (单次 LLM 调用，包含三阶段)
    │  Phase 1: Fact extraction（从对话中提取新 fact + userContext 更新）
    │  Phase 2: Staleness review（检测过期 fact，同一调用内完成）
    │  Phase 3: Consolidation（合成碎片化 fact，同一调用内完成）
    ▼
memory.json
    per-user 文件存储
    atomic write (temp file + os.replace)
```

### Tool 模式工作流

```
Agent 决定何时调用 memory 工具
    │
    ├─ memory_search(query, category, limit)
    │      → manager.search(query, top_k=limit, ...)
    │
    ├─ memory_add(content, category)
    │      → manager.create_fact(...)  [backend-internal capability]
    │
    ├─ memory_update(fact_id, content, category, confidence)
    │      → manager.update_fact(...)  [backend-internal capability]
    │
    └─ memory_delete(fact_id)
           → manager.delete_fact(...)  [backend-internal capability]
```

> **注意**：`create_fact`/`update_fact`/`delete_fact` 不在 ABC 上（是 backend-internal capability）。Gateway 通过 `hasattr(manager, "<name>")` 探测，缺失时返回 501。

---

## OpenViking 后端（远程语义检索）🆕

```yaml
memory:
  manager_class: openviking
  mode: middleware              # 只支持 middleware 模式
  backend_config:
    base_url: http://127.0.0.1:1933   # OpenViking 服务地址
    owner_user_id: alice        # 绑定单个 DeerFlow 用户到一个 OpenViking USER API key
    api_key_env: OPENVIKING_API_KEY   # 密钥走环境变量，不进配置文件
    startup_policy: fail_fast   # fail_fast | warn
    failure_policy:
      read: fail_open           # fail_open | raise
      write: log_and_drop       # log_and_drop | raise
    retrieval:
      top_k: 5
      score_threshold: 0.5
      max_injection_chars: 2000
      content_mode: ...
      injection_query: ...      # 固定注入 query
```

基于官方 `langchain-openviking` 包的**远程后端**（非裸 HTTP）。通过 `langchain-openviking==0.1.0` 的 `OpenVikingSessionRecorder`/`OpenVikingRetriever`/`OpenVikingCommitPolicy` 通信。

- **单用户绑定**：一个 OpenViking USER API key 绑定一个 `owner_user_id`，其他 DeerFlow 用户被拒绝（`openviking_manager.py:452`）
- **Thread ↔ Session 确定性映射**：`_session_id()` 用 SHA-256 派生；agent 名冲突/非法时生成 `df-agent-<hash>` 前缀 peer ID
- **捕获游标只存签名 hash + 计数器**，不存消息正文
- **部分写入恢复**：`OpenVikingPartialWriteError` 携带 `input_messages_consumed` 和 `commit_pending` 标记
- **与 DeerMem 差异**：不支持 tool 模式、不支持 fact CRUD（`create_fact` 等 raise `NotImplementedError`）、不支持 `get_memory`；注入 query 固定（不是格式化 fact 列表）
- 异步入口 offload 同步 SDK + cursor 文件 IO；graceful shutdown 排空活跃操作

---

## mem0 后端（平台 API）🆕

```yaml
memory:
  manager_class: mem0
  backend_config:
    base_url: https://api.mem0.ai   # 默认要求 HTTPS
    allow_insecure_http: false      # 本地开发明文 HTTP 需显式 opt-in
```

mem0 平台 API 客户端。**默认要求 HTTPS `base_url`**（请求携带 API token）；明文 HTTP 必须显式 `allow_insecure_http: true`。

---

## Storage v2 架构（DeerMem）🆕

`storage.py` 从 ~196 行重构到 ~1549 行。关键新增：

| 机制 | 说明 |
|------|------|
| **Fact 仓库 API** | `upsert_fact`/`delete_fact`/`get_fact`/`list_facts`，带**双层乐观锁**（manifest revision + fact revision） |
| **增量变更 API** | `apply_changes()` 避免全量加载-比较-写回；支持 `allow_manifest_rebase=True` 的断联变更 rebase（最多 3 次尝试） |
| **错误层次** | `MemoryStorageError` > `MemoryStorageCorruption` / `MemoryRevisionConflict` > `MemoryManifestRevisionConflict` / `MemoryFactRevisionConflict` |
| **RetrievalPort 协议** | 可插拔检索适配器（`upsert`/`remove`/`search`/`clear`/`rebuild`），默认 **FTS5 BM25**（持久 SQLite 派生索引），空值禁用走 substring fallback |
| **两阶段原子日志** | `_commit_changes_locked()` 用 prepared → committed 两阶段 + 恢复目录，崩溃可恢复 |
| **文件级缓存签名** | `(mtime_ns, size, manifest_revision)` 三元组，处理粗粒度文件系统 |
| **跨进程文件锁** | POSIX `fcntl.flock` / Windows `msvcrt.locking` |
| **v1→v2 迁移** | `_migrate_locked()` 读取旧版 JSON，fact 提取为 Markdown，迁移前 `.v1.bak` 备份 |
| **`save()` 兼容** | 保留但内部 diff 为 per-fact 操作，不重写未变动文件 |

---

## Memory Consolidation（Fact 碎片合并）

当某个 category 的 fact 数量达到 `consolidation_min_facts`（默认 8），同一次 LLM 调用中自动触发合并：

1. `_select_consolidation_candidates()` 识别碎片化类别（largest first），每周期最多 `consolidation_max_groups_per_cycle`（默认 3）组
2. LLM 决定合并哪些组，为每组生成一个合成 fact
3. `_apply_updates` 强制 guardrail：
   - 源 fact ID 必须存在且组间不重叠
   - 每组源 fact 数 ≤ `consolidation_max_sources`（默认 8）
   - 合成 fact 置信度不超过源 fact 最大值
   - 低于 `fact_confidence_threshold` 的 fact 不写入

```yaml
memory:
  backend_config:
    consolidation_enabled: false       # 开启（默认 false——consolidation 是有损的，源内容不保留，需显式 opt-in）
    consolidation_min_facts: 8         # 触发合并的最小 fact 数（3-30）
    consolidation_max_groups_per_cycle: 3  # 每周期最多合并组数（1-10）
    consolidation_max_sources: 8       # 每组最大源 fact 数（2-20）
```

---

## Staleness Review（过期清理）

每个 fact 现在有 LLM 分配的 `expected_valid_days`。同一次 LLM 调用内检测过期 fact：

1. `_select_stale_candidates()` 选超过 `expected_valid_days`（fallback `staleness_age_days`，默认 90 天）的 fact
2. 排除 `staleness_protected_categories`（默认 `["correction"]`）
3. 候选数 ≥ `staleness_min_candidates`（默认 3）时触发
4. LLM 按 `valid:Nd` 标注逐条判断：**KEEP**、**REMOVE**、或 **EXTEND**（延长 `extend_by_days` 天）
5. `_apply_updates` 硬性交叉校验：
   - **只删除 LLM 建议的 ∩ 实际候选的**
   - 保护类别和未过期 fact **永不被删除**（即使 LLM 要求）
   - 上限 `staleness_max_removals_per_cycle`（默认 10），超额保留最低置信度 fact
   - 被标记删除的 fact 不会被同一周期内的 EXTEND 复活
   - EXTEND 结果 capped 在 `staleness_max_extension_days`（默认 3650 = 10 年）

### Fact 生命周期

```
创建 → LLM 分配 expected_valid_days
         │  clamped at write: min(expected_valid_days, staleness_age_days × staleness_max_lifetime_multiplier)
         │  默认: 90 × 20 = 1800 days ≈ 5 years (creation cap)
         │
    ┌────▼────┐
    │  Active  │
    └────┬────┘
         │ 超过 expected_valid_days 后进入候选池
         ▼
    Staleness Review (同一 LLM 调用，不增加 API 开销)
         │
         ├─ KEEP    → 保持（不做任何变更）
         ├─ REMOVE  → 删除（受 per-cycle cap 限制，超过则保留最低置信度）
         └─ EXTEND  → 延长 expected_valid_days，capped at staleness_max_extension_days
```

```yaml
memory:
  backend_config:
    staleness_review_enabled: true         # 开启过期清理
    staleness_age_days: 90                 # 超过此天数才候选（fallback）
    staleness_min_candidates: 3            # 至少这么多候选才触发
    staleness_max_removals_per_cycle: 10   # 每次最多删除数
    staleness_protected_categories: [correction]  # 永不过期类别
    staleness_max_lifetime_multiplier: 20.0   # 创建时对 expected_valid_days 的倍数上限
    staleness_max_extension_days: 3650        # EXTEND 后的绝对天数上限
```

---

## Template Externalization（模板外部化）

Memory prompts 已从代码中抽离为 YAML 模板文件，放在 `backends/deermem/deermem/core/prompts/`：

| 模板文件 | 用途 |
|---------|------|
| `fact_extraction.yaml` | 从对话中提取新 fact + context 更新 |
| `staleness_review.yaml` | 过期 fact 审查 prompt |
| `consolidation.yaml` | Fact 合并 prompt |
| `memory_update.chat.yaml` | 组合上述三个阶段的完整 prompt |

---

## Per-User 隔离

```
{storage_path}/                          ← DIRECTORY（不再是 .json 文件）
└── users/
    ├── {user_id}/
    │   ├── memory.json                  # 全局概要（version/revision/user/history）
    │   └── agents/
    │       └── {agent_name}/
    │           └── facts/
    │               └── {sha256(fact_id)[:2]}/
    │                   └── {fact-id}.md  # 单 fact Markdown
    └── default/                         # 无 auth 模式
        └── memory.json
```

- Middleware 模式：`user_id` 在 enqueue 时通过 `get_effective_user_id()` 捕获
- Tool 模式：`user_id` 从 `ToolRuntime.context` 通过 `resolve_runtime_user_id(runtime)` 解析
- 自定义 agent 定义也在同一布局下
- **v1→v2 迁移**：首次读取自动迁移（`storage.py` 的 `_migrate_locked()`），迁移前做 `.v1.bak` 备份。也可用主动 CLI：`python scripts/migrate_memory_markdown.py --all-users --dry-run`（幂等、按用户继续）

---

## Token Counting

两种策略，由 `memory.token_counting` 控制：

| 策略 | 说明 |
|------|------|
| `tiktoken`（默认） | `cl100k_base` 精确计数。懒加载+缓存。失败后 600s cooldown。正在加载时并发调用者 fallback 到 char（不阻塞更多线程） |
| `char` | 零网络依赖。CJK 感知估算：非 CJK `//4`，CJK `//2` |

---

## Guaranteed Categories

`guaranteed_categories`（默认 `["correction"]`）中的 fact 走独立 token 预算（`guaranteed_token_budget`，默认 500），放在 Facts 块最前面，不被普通 fact 挤出。

---

## Shutdown Flush

`manager.shutdown_flush(timeout)` 在 Gateway graceful shutdown 时排空 pending 更新。每个 pending item 做一次 LLM 调用（不可中断），所以需要 hard timeout。Gateway lifespan 在 channels/scheduler 停止后调用，超时值必须适配 K8s `terminationGracePeriodSeconds`。

---

## Run-Level Memory Identity

每次 Gateway run 带有有效 memory block 时，会对 `<memory>` wrapper 的 HumanMessage.content 取 SHA256 hash，通过 `RunJournal` 记录 `context:memory` event。后续 runs 和 checkpoint-based branches 复用 frozen message 而不重新加载 memory。

---

## 配置速查

```yaml
memory:
  enabled: true
  injection_enabled: true
  mode: middleware           # middleware | tool
  manager_class: deermem     # deermem | mem0 | noop | openviking | <custom>
  shutdown_flush_timeout_seconds: 30
  backend_config:
    # ── Storage ──
    storage_path: ""         # 空 = runtime_home()；DIRECTORY（不是文件！）
    max_facts: 100
    fact_confidence_threshold: 0.7
    max_injection_tokens: 2000
    # ── Queue ──
    debounce_seconds: 30
    # ── Token Counting ──
    token_counting: tiktoken  # tiktoken | char
    guaranteed_categories: [correction]
    guaranteed_token_budget: 500
    # ── Staleness ──
    staleness_review_enabled: true
    staleness_age_days: 90
    staleness_min_candidates: 3
    staleness_max_removals_per_cycle: 10
    staleness_protected_categories: [correction]
    staleness_max_lifetime_multiplier: 20.0
    staleness_max_extension_days: 3650
    # ── Consolidation ──
    consolidation_enabled: false       # 默认 false（有损操作，需显式 opt-in）
    consolidation_min_facts: 8
    consolidation_max_groups_per_cycle: 3
    consolidation_max_sources: 8
    # ── Model ──
    model:
      model: null            # null = 用 app default model
      provider: openai
      api_key: null
      base_url: null
      temperature: null
```

## API 接口

| 操作 | endpoint |
|------|----------|
| 获取记忆 | `GET /api/memory` |
| 强制重载 | `POST /api/memory/reload` |
| 清空记忆 | `DELETE /api/memory` |
| 创建 Fact | `POST /api/memory/facts` |
| 删除 Fact | `DELETE /api/memory/facts/{id}` |
| 更新 Fact | `PATCH /api/memory/facts/{id}` |
| 导出 | `GET /api/memory/export` |
| 导入 | `POST /api/memory/import` |
| 配置 | `GET /api/memory/config` |
| 状态 | `GET /api/memory/status` |

---
> **See also:** [MemoryConfig source](../../../backend/packages/harness/deerflow/config/memory_config.py) · [MemoryManager ABC](../../../backend/packages/harness/deerflow/agents/memory/manager.py) · [Backend README](../../../backend/packages/harness/deerflow/agents/memory/backends/README.md)
