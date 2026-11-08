---



title: "Memory 系统 — 可插拔后端架构"
description: '可插拔 Memory 后端架构，支持 middleware 和 tool 双模式、5 个可插拔后端（deermem/mem0/noop/openviking/honcho）。2.1 引入 consolidation、staleness review 和 hybrid fact eviction；2.2 新增 cognitiveStyle 摘要段与 cognitive 事实类别、确定性的词法相关性排序（含 IDF 与 MMR）、以及 prescreen/signal 信号门。'
topics: [memory, persistence, context-injection, pluggable-backend, consolidation, staleness, honcho, eviction, relevance, cognitive-style]
verified_against: v2.2.0
last_verified: 2026-11-08
---

# Memory 系统 — 可插拔后端架构

> **2.1.0 里程碑 | Breaking Changes**：Memory 从写死的 DeerMem 单体变成 `MemoryManager` ABC + 可插拔后端。只需改一行 `config.yaml` 即可切换后端，DeerFlow 核心代码无需改动。

> **2.2.0 增量（非破坏性，向后兼容）**：
> 1. **`cognitiveStyle` 摘要段**——`user` 下新增第四段，「这个用户怎么思考和协作」而不是「他是谁」；注入时渲染成 `Thinking Style: ...`。旧数据无需迁移（`_normalize_memory_summaries` 自动补空段）。
> 2. **`cognitive` 事实类别**——`CORE_CATEGORIES` 从 6 个扩到 10 个。
> 3. **确定性词法相关性排序**（#4495）——`query` + `retrieval_relevance_enabled` 同时成立时，fact 先按「词法相关性 × 权重 + confidence × (1-权重)」打分，再进 guaranteed/regular 分区和 token 预算；可选 greedy-MMR 去冗余。
> 4. **prescreen / signal 信号门**——在 LLM 提取之前用确定性规则挡掉没有记忆价值的轮次（见 `manager-contract-and-backend-clients.md`）。

## 架构总览

```
┌─────────────────────────────────────────────────┐
│                  config.yaml                     │
│  memory.manager_class: deermem|mem0|noop|openviking|honcho │
│  memory.mode: middleware | tool                  │
│  memory.backend_config: { ... }                  │
└─────────────────┬───────────────────────────────┘
                  │
┌─────────────────▼───────────────────────────────┐
│           MemoryManager (ABC — 10 methods)         │
│  add / add_nowait / get_context / search         │
│  get_memory / delete_memory / clear_memory       │
│  import_memory / export_memory / shutdown_flush  │
└───────┬────────────┬────────────┬──────────┬──────────┬─────┘
        │            │            │          │          │
┌───────▼────┐ ┌─────▼────┐ ┌─────▼────┐ ┌────▼────┐ ┌───▼─────┐
│  DeerMem   │ │ mem0     │ │  Noop    │ │OpenViking│ │ Honcho  │
│  (default) │ │ 平台 API │ │ (template)│ │ 远程语义 │ │ 用户模型 │
│  JSON+MD   │ │ 客户端   │ │ 空实现    │ │ 检索     │ │ 记忆提供 │
│  Markdown  │ │          │ │ 复制用    │ │ midw only│ │ 方 #1898 │
└────────────┘ └──────────┘ └──────────┘ └──────────┘ └─────────┘
```

### 两种运行模式

| 模式 | `memory.mode` | 行为 |
|------|--------------|------|
| **Middleware**（默认） | `middleware` | `MemoryMiddleware` 在 `after_agent` 时入队对话 → 后台 debounced LLM 提取 fact → 下次对话时注入 `<memory>` |
| **Tool**（实验性） | `tool` | 注册 `memory_search`/`add`/`update`/`delete` 工具 → 模型主动决定何时搜索、添加、更新、删除 fact |

两种模式共享 prompt 注入和 updater 后端（DeerMem 特有的是 `FileMemoryStorage` + per-user/per-agent 隔离）。OpenViking 远程后端**只支持 middleware 模式**。Honcho 远程后端支持两种模式（tool 模式下保留被动写入并提供 `search`，无 fact CRUD）。

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

> 上表只列了 host 侧主要使用的成员。ABC 还包含 `cancel_by_agent`、`warm()`（三态）、`reload_memory`、`create_fact`/`delete_fact`/`update_fact`、`on_pre_compress`/`on_turn_start`、async 占位 `aadd`/`aget_context`/`asearch`、`close()` 与抽象 classmethod `from_config`，以及实例化期不变量与严格读（`MemoryReadError`）策略——见 [manager-contract-and-backend-clients.md](manager-contract-and-backend-clients.md)。

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
│       │   ├── eviction.py # 容量驱逐策略（confidence / hybrid-v1）
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
├── honcho/           ← 🆕 Honcho user-model 记忆提供方（远程 HTTP v3）
│   ├── __init__.py   # MANAGER_CLASS = HonchoMemoryManager
│   ├── client.py     # 最小同步 Honcho v3 HTTP 客户端（httpx）
│   ├── config.py     # HonchoConfig
│   └── honcho_manager.py
└── <yourname>/       ← 自定义后端（drop-in）
```

工厂 `get_memory_manager()` 按 `manager_class` 配置值解析：
1. `_scan_backends()` 扫描 `backends/` 子目录，每个子包的 `__init__.py` 暴露 `MANAGER_CLASS` 属性即注册（目录名 = 后端短名）
2. 先查注册的短名（`deermem`、`mem0`、`noop`、`openviking`、`honcho`）
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

**Storage v2 重构**（2.2.0 实测 `storage.py` = **2297 行**）：fact 不再存在全局 JSON 的 `facts` 字段，改为**每个 fact 一个 Markdown 文件**：

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

### 全局 JSON 的 `user` 段：2.2.0 多出 `cognitiveStyle`

`create_empty_memory()`（`storage.py:97-118`）的 `user` 段现在是**四**个 summary section：

```python
"user": {
    "workContext":     {"summary": "", "updatedAt": ""},
    "personalContext": {"summary": "", "updatedAt": ""},
    "topOfMind":       {"summary": "", "updatedAt": ""},
    "cognitiveStyle":  {"summary": "", "updatedAt": ""},   # ← 2.2.0 新增（:107）
},
```

`history` 段仍是三段（`recentMonths` / `earlierContext` / `longTermBackground`）。归一化器 `_normalize_memory_summaries()`（`storage.py:162-179`）用同一个元组驱动：

```python
("user", ("workContext", "personalContext", "topOfMind", "cognitiveStyle")),   # :167
("history", ("recentMonths", "earlierContext", "longTermBackground")),
```

**向后兼容的做法**：先 `copy.deepcopy(empty[section_name])` 得到完整骨架，再把旧数据里已知的 section 逐个走 `_normalize_context_section()`（保留扩展字段），最后**对四个已知 key 再归一化一遍**（缺失的补空）。所以一份 2.1 时期的 `memory.json` 读进来就有空的 `cognitiveStyle`，不需要迁移脚本；`DOCUMENT_VERSION = "2.0"` 也没变。

**注入侧**（`prompt.py:550-552`）：

```python
cognitive_style = user_data.get("cognitiveStyle", {})
if cognitive_style.get("summary"):
    user_sections.append(f"Thinking Style: {_escape_summary(cognitive_style['summary'])}")
```

与 `Work:` / `Personal:` / `Current Focus:` 并列，同一个 `_escape_summary` 转义。**空的 `cognitiveStyle` 不产生任何文本**——不会出现空行或占位。

**提取侧**：`memory_update.chat.yaml` 要求模型在四个 section 之间分工（`:42` / `:92` / `:111` 提到 `cognitiveStyle`），并把「稳定的推理方式、回答结构与协作习惯」归到这里；类别枚举与每个 section 的取舍规则以 `memory_update.chat.yaml` 的 prompt 正文为唯一权威（`fact_extraction.yaml` 只负责初始提取；更新路径走 chat 模板）。

### Fact 类别

`CORE_CATEGORIES`（`storage.py:52`）在 2.2.0 是 **10 个**，不是 6 个：

```python
CORE_CATEGORIES = frozenset({
    "preference", "correction", "context", "goal", "behavior",
    "cognitive", "identity", "constraint", "decision", "other",
})
```

| Category | 含义 | 示例 |
|----------|------|------|
| `preference` | 用户偏好 | "喜欢中文回复" |
| `correction` | 用户纠正（受保护，永不过期） | "我的名字不是张三" |
| `context` | 上下文（**缺省值**） | "在字节工作" |
| `goal` | 目标 | "想学 Rust" |
| `behavior` | 行为模式 | "经常在晚上使用" |
| `cognitive` 🆕 | 稳定的推理/表达/协作习惯 | "先要结论再要细节" |
| `identity` 🆕 | 身份事实 | "name: 张三" |
| `constraint` 🆕 | 硬约束（`expected_valid_days` 常用） | "不能用 GPL 依赖" |
| `decision` 🆕 | 已做的决定 | "选了 Postgres 而不是 MySQL" |
| `other` + `categoryExtension` | 非核心标签的旧写法 | `category: other` + `categoryExtension: hobby` |

**`knowledge` 不在这个集合里**——v2.1.0 digest 里列的 `knowledge` 类别早已不存在于 `CORE_CATEGORIES`；用户知识现在落在 `context` 或 `identity`。

类别归一化的两条规则（`_normalize_category`，`storage.py:247-260`）：

1. `raw_category = fact.get("category", "context")`，非字符串抛 `ValueError("fact.category must be a string")`，空串回落 `"context"`；
2. **`categoryExtension` 只在 `category == "other"` 时保留**，否则丢弃——注释说清了原因：旧构建把非核心标签停在 `other` + extension 里，一旦标签被原生存储（包括一条旧 `other`+extension 被更新成真实类别），残留字段就会与 Gateway 文档语义矛盾。

迁移期还有 `_category_comparison_key()`（`storage.py:262+`）：把 `("other", <label>)` 折叠成 `(<label>, None)` 再比较，这样「Markdown 已提交但旧 JSON 未删除」的中断迁移在重试时仍认得自己的结果；真正不同的标签之间仍然不等。

prompt 模板 `deermem/core/prompts/fact_extraction.yaml` 的类别枚举在 `:12`，`cognitive` 的说明在 `:21`：

> `cognitive: Stable reasoning, response-structure, and collaboration habits`

`_normalize_legacy_import_fact()`（`storage.py:123`）负责把导入的旧 fact 走同一套归一化。

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

> **注意**：`create_fact`/`update_fact`/`delete_fact` 是 ABC 上的 **tier-3 可选钩子**，默认 `raise NotImplementedError`——**不是** `hasattr` 探测。调用方直接调用并 catch `NotImplementedError`，Gateway 的 `_unsupported_501` 把它映射成 501（`manager.py:428-494`；`app/gateway/routers/memory.py:133-165`）。完整分层与不变量见 [manager-contract-and-backend-clients.md](manager-contract-and-backend-clients.md)。

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

- **单用户绑定**：一个 OpenViking USER API key 绑定一个 `owner_user_id`，其他 DeerFlow 用户被拒绝（`openviking_manager.py:459-460`）
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

## Honcho 后端（user-model 记忆提供方）🆕

```yaml
memory:
  manager_class: honcho
  mode: middleware              # 也支持 tool 模式（实现 search，无 fact CRUD）
  backend_config:
    base_url: http://localhost:8000   # 自托管 Honcho v3；hosted 用 https
    # api_key: $HONCHO_API_KEY        # hosted Honcho；明文 HTTP + api_key 需 allow_insecure_http: true
    workspace_prefix: deerflow-u-     # 每个 user 一个隔离 workspace
    # workspace_overrides: {}         # 按 raw user_id 精确映射到自定义 workspace
    # user_peer_overrides: {}         # 按 raw user_id 映射到自定义 peer 名
    assistant_peer: deerflow          # AI 消息写入的 peer
    timeout_seconds: 10.0
    connect_timeout_seconds: 3.0
    message_char_limit: 8000          # add() 单条消息截断上限
    max_injection_chars: 6000         # get_context() 注入文本截断上限
    allow_insecure_http: false        # 明文 HTTP + api_key 需显式 true
    failure_policy:
      read: fail_open                 # fail_open | fail_closed
```

Honcho 是 RFC #1898 里的 **user 维度记忆提供方**：专管长期用户建模、偏好、跨会话 working representation，与面向 project/task 的后端互补。本后端是**远程 HTTP 适配器**（`honcho/client.py` 用裸 `httpx` 打 Honcho v3 REST API，peer/session 服务端 get-or-create，所有调用幂等；后续可换官方 `honcho-ai` SDK，路线同 OpenViking 的 custom-HTTP → 官方适配器）。

- **零 LLM 调用**：ingestion 只是写明文消息，Honcho 服务端自带的 deriver 异步做 fact 提取与 representation 构建，DeerFlow 侧不发任何 LLM 请求（`honcho_manager.py:1-8`）
- **多用户隔离（fail closed）**：每个操作按 `user_id` 解析 workspace——`workspace_overrides` 精确匹配，否则 `workspace_prefix + _stable_id(user_id)`。`_stable_id` = `sanitize_id(raw)[:48]` + `-` + 8 位 SHA-256 后缀：因为 `sanitize_id` 会把连续非法字符折叠成一个 `-`（`"user.name@x"` 与 `"user-name@x"` 都折叠成 `"user-name-x"`），裸清洗结果有碰撞风险；哈希后缀让默认派生路径碰撞抵抗。`workspace_overrides`/`user_peer_overrides` 按**未清洗的 raw key** 匹配；共享同一 workspace 的用户共享一个 search 索引（`search` 无 peer filter）。缺失 `user_id` fail closed：写变 no-op、读返回空，绝不落到共享 fallback workspace
- **写入（`add`）**：`human` → `user_peer`、`ai`/`AIMessageChunk` → `assistant_peer`，每条截断到 `message_char_limit`；session id = `df-` + `_stable_id(thread_id)`（避免 `"t.1"`/`"t-1"` 这类裸清洗会合并的 thread 碰撞）
- **读取**：`get_context()` 返回 `working_representation`（`max_conclusions=25`）截断到 `max_injection_chars`；`search()` 走 Honcho 的 workspace 级 `/search`；`get_memory()` 返回 DeerMem 形状最小视图（`facts: []` + `user.workContext.summary` = representation）
- **failure_policy.read**：默认 `fail_open`（log + 空结果）；`fail_closed` 把召回失败包装成 `MemoryManagerError` 抛出（`_read_or_fallback` 门，镜像 mem0）。写失败只 log 不抛。**同步 #6（#4726）**：failure policy 从"文档约定"变为"逐后端强制"——manager 层统一收口读失败路径（含超时处理移出饱和 executor），mem0/openviking/deermem 各自补齐策略行为测试（`test_memory_manager_interface.py` +135 行）
- **Agent 删除即取消缓冲提取（#5123，同步 #6）**：agent 被删除或 clear 时，排队中的 extraction 不再跑完——`manager.py` + deermem `queue.py` 增加按 agent 取消入口（`test_memory_cancel_by_agent.py`），避免已删 agent 继续消耗后台提取资源
- **异步 offload**：`aadd`/`aget_context`/`asearch` 通过 `asyncio.to_thread` 把同步 httpx IO 移出事件循环
- **配置校验（fail fast，构造期）**：`timeout_seconds`/`connect_timeout_seconds` 必须有限且 >0；`message_char_limit`/`max_injection_chars` 必须 >0（`text[:n]` 的 n≤0 是空串或负切片，不是长度上限）；`api_key` 走明文 HTTP 而未开 `allow_insecure_http` 直接报错（`config.py:53-73`）

**模式支持**：middleware（默认）与 tool 都支持。`supports_search=True`；Honcho 无 fact CRUD（`create_fact`/`update_fact`/`delete_fact` 不支持），故 `requires_passive_writes_in_tool_mode=True`——tool 模式下仍保留 `MemoryMiddleware → add()` 的被动写入喂 deriver，`search()` 提供 tool 模式期望的 query 检索（`honcho_manager.py:97-104`，与 mem0 相同理由）。

**与其他后端定位差异**：

| 后端 | 记忆维度 | LLM 位置 | fact CRUD | 模式 |
|------|---------|---------|-----------|------|
| **DeerMem**（默认） | project/task + user，本地 | DeerFlow 侧 updater LLM | 完整（含 staleness/consolidation） | middleware + tool |
| **mem0** | 平台托管 | 平台侧（stateless HTTP，无队列/缓存） | 无（保留被动写入） | middleware + tool |
| **OpenViking** | 语义检索（远程） | 平台侧 SDK | 无 | middleware only |
| **Honcho** | **user 模型（远程）** | **服务端 deriver** | **无** | **middleware + tool** |

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

## Hybrid Fact Eviction（hybrid-v1 事实驱逐）🆕

DeerMem 的容量驱逐集中在 `deermem/core/eviction.py`，一个纯函数、确定性、可解释的策略层。`select_facts_for_capacity()` 在 fact 快照超 `max_facts` 时挑选保留/驱逐哪些 fact，**不修改快照**，只返回决策。两种策略：

| 策略 | 评分 | 说明 |
|------|------|------|
| `confidence`（默认） | 只用 `confidence` | 精确保留历史 ranking |
| `hybrid-v1`（opt-in） | 0.65×confidence + 0.25×confirmationFreshness + 0.10×accessHeat | 三个有界信号加权 |

### 三个有界信号（均 clamp 到 [0,1]）

| 分量 | 计算 | 关键参数 |
|------|------|---------|
| `confidence` | fact 的 `confidence`（缺省 0.5） | — |
| `confirmationFreshness` | 显式确认的新鲜度：`lastConfirmedAt` 的指数半衰期衰减 `2^(-elapsed/half_life)`；无 `lastConfirmedAt` 时退回 `createdAt` 并**减半**（创建比显式确认证据弱） | `eviction_confirmation_half_life_days`（90） |
| `accessHeat` | 查询访问热度：`accessHeat` 侧车按访问半衰期衰减后 `log1p(heat)/log(9)` 归一化 | `eviction_access_half_life_days`（30） |

权重默认 0.65/0.25/0.10，**必须求和 = 1.0**（`config.py:323-325` 校验，违反即构造期 `ValueError`）。

### Correction 保留槽

`hybrid-v1` 在 `max_facts` 内预留 `min(eviction_correction_reserved_max, ceil(max_facts × eviction_correction_reserved_fraction))` 个槽给 `category == "correction"` 的 fact（默认 10% / 最多 10），使存储上限与 guaranteed correction 注入对齐。**只预留实际存在的最少 correction 数**，未用槽立即回到普通竞争（`eviction.py:210-217`）。

### 决策流程

1. 每个 fact 算分 → `FactEvictionScore{value, components}`（`components` 保留三分量，可解释）
2. `len(facts) <= max_facts` 时直接全保留（不驱逐）
3. 否则按 `(-score, 原始 index)` 稳定排序，先锁 correction 槽，再按排名取满 `max_facts`
4. 返回 `FactEvictionDecision{kept, evicted, scores, policy, reserved_correction_slots}`；`evicted` 是**仅元数据**记录（id/category/score/components），不落原文

### 元数据采集与 shadow mode

- 确认/访问元数据**仅在 `hybrid-v1` 或 shadow 模式激活时收集**。`accessHeat` 侧车只由 `DeerMem.search()` 命中的 fact 递增（`get_context()` 从不递增），侧车放在 agent 的 `.metadata/` 目录，不污染 canonical Markdown 的时间戳/revision；`confidence` 策略的容量选择不读侧车
- `lastConfirmedAt`/`confirmationCount` 只被 `_apply_updates` 更新，且需**确定性消息处理同时检测到 reinforcement**：批量级检测（当前抽取批次最后 6 条过滤消息中匹配到 human 消息）+ LLM 提供的 fact ID 绑定；重复抽取、prompt injection、单纯 search 都不算确认
- `fact_eviction_shadow_enabled: true` 时，`confidence` 策略照常执行，同时算 hybrid 分数并把它与 confidence-only 的分歧写进仅元数据的驱逐审计（`eviction_audit_max_entries` 上限）

```yaml
memory:
  backend_config:
    fact_eviction_policy: confidence        # confidence | hybrid-v1
    fact_eviction_shadow_enabled: false
    eviction_confidence_weight: 0.65        # 三权重之和必须 = 1.0
    eviction_confirmation_weight: 0.25
    eviction_access_weight: 0.10
    eviction_confirmation_half_life_days: 90
    eviction_access_half_life_days: 30
    eviction_correction_reserved_fraction: 0.10
    eviction_correction_reserved_max: 10
    eviction_audit_max_entries: 200
```

---

## 🆕 Near-Duplicate Fact Gate（v2.1.0-rc0，#5254）

写侧的**确定性近重复合并门**（`deermem/core/updater.py`，opt-in）：

```yaml
fact_dedup_enabled: false                    # 默认关
fact_dedup_similarity_threshold: 0.85        # 有界 token-Jaccard 相似度下限
```

- 只作用于 **NEW facts**（write 侧）：新提取的 fact 与已有 fact 相似度 ≥ 阈值时**合并进旧 fact**而非追加
- 门只对**完整的分类 fact** 生效：`scope=user`、`durability=durable`、`authority=descriptive` 三字段齐全才参与（`_FACT_CLASSIFICATION_FIELDS` 校验）
- 被提议 removal 的目标 fact **排除**在近重复合并之外——避免"一边要删一边又被合并"的循环
- 纯确定性（token-Jaccard），无 LLM 调用；测试 `test_memory_fact_dedup.py`（317 行）

## 🆕 Agent 级 Memory 禁用（#5167）

Custom agent 配置可整体关闭 memory（`memory_enabled: false`）：不注入记忆上下文、不注册 memory tools、`skip_memory_flush`——agent 的内部 turn 完全不写 durable memory。Subagent 本就继承 parent `thread_id` 不 flush，此开关面向 lead/custom agent。

## 🆕 Hybrid Eviction 评估基建（#4810）

可复现的混合驱逐评估（eval 框架 + 数据集），验证 `hybrid-v1` 评分相对纯 `confidence` 的保留质量——调参时不必靠线上观察。

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

两种策略，由 `memory.backend_config.token_counting` 控制（旧写法 `memory.token_counting` 会被自动迁移进 `backend_config` 并告警，`memory_config.py:180-215`）：

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

## 🆕 确定性词法相关性排序（2.2.0）

2.1 的注入顺序**只看 confidence**。2.2 增加了「当前这轮问的是什么」这一维——但仍**不用 embedding、不用网络**：`deermem/core/relevance.py`（259 行）是一套纯词法的打分 / IDF / MMR 排序器。

### 开关与接线

| 层 | 位置 | 作用 |
|----|------|------|
| 配置 | `deermem/config.py:117` `retrieval_relevance_enabled`（默认关） | 总开关 |
| 配置 | `:129` `retrieval_relevance_weight`（默认 0.5） | 相关性在混合分里的权重 |
| 配置 | `:135` `retrieval_diversity_weight` | greedy-MMR 的重复惩罚权重 |
| 调用方 | `deer_mem.py:313-356` `get_context(..., query=...)` | 算 `corpus_idf` 并把三个参数传给 formatter |
| 注入器 | `prompt.py:469-480` `format_memory_for_injection(..., query, relevance_weight, diversity_weight, idf)` | 在 guaranteed/regular 分区**之前**排序 |

`get_context` 只有在 `retrieval_relevance_enabled and query.strip()` 且 `retrieval_relevance_weight > 0` 时才建 IDF——**先取该 user/agent 的 fact 全集**（分区之前）`build_idf([tokenize(content) ...])`，与 `search` 用的是同一个有界分词器。

### `lexical_relevance` 的算法（`relevance.py:117-146`）

```
containment = query ⊂ content 或 content ⊂ query
matched_weight = total_weight = 1.0 if containment else 0.0
for token in dict.fromkeys(query_tokens):        # 同一 token 只算一次
    weight = idf.get(token, 1.0) ** 2
    total_weight += weight
    if token in content_tokens
       or (len(token) >= 4 and 存在 content_token 使 一方是另一方的前缀):
        matched_weight += weight
return sqrt(matched_weight / total_weight)
```

四个刻意选择：

1. **IDF 平方**——高频词（"的"、"the"）几乎不贡献分数，稀有词主导匹配；
2. **重复不能冒充覆盖**——`dict.fromkeys` 去重 + 用「匹配权重 / 完整查询权重」的**范数比**，所以不需要再 clip，部分匹配仍能在 blend 里保持竞争力；
3. **前缀匹配必须 ≥ 4 字符**（`_PREFIX_MATCH_MIN_CHARS = 4`，`:39`）且要求「一个完整 token 是另一个的前缀」——共享 4 个字符只用来缩小候选集，不直接记分（注释：「Sharing four characters only narrows the candidate set.」）；
4. **token 化对中日韩友好**：`_WORD_RE = r"[a-zA-Z0-9_]+|[\u3400-\u4dbf\u4e00-\u9fff]+"`（`:35`）——CJK 整段当一个 token，所以中文 fact 的匹配是子串级而非单字级。

**有界性**：`_TEXT_CHAR_BUDGET = 4096`（`:43`）截断输入文本、`_SIMILARITY_TOKEN_BUDGET = 128`（`:42`）限制 token 数——注入路径是热路径，不能因为一条超长 fact 拖慢每轮。

### 混合分与排序

`score_facts(facts, query, *, relevance_weight=0.5, idf=None)`（`:159-192`）：

```python
combined = relevance_weight * relevance + (1.0 - relevance_weight) * confidence
```

- `relevance_weight <= 0` **短路**成旧的 confidence-only 排序，不算任何相关性；
- `confidence` 走 `_coerce_confidence()`（`:149-156`）：非有限值 → 0，最后 clamp 到 [0,1]；
- 返回 `(score, fact)` 列表，**不修改输入**。

`iter_diversify(scored, *, similarity_weight)`（`:219-246`）是**惰性 greedy-MMR**：

- `similarity_weight <= 0` 时原序 yield，零开销；
- 否则每条 fact 只 tokenize 一次，每次选中后**只更新一次** penalty：`penalty = max(penalty, Jaccard(picked, candidate))`；
- 调整分 = `score - similarity_weight * penalty`；相等时保留输入序（稳定）；
- **惰性**的意义写在 docstring 里：「Consumers can stop at their result or token budget without ranking the rest.」——token 预算消费者随时可以停，不必全量排序。

`prompt.py` 侧的对应结构是 `_rank_pool()`（`:614-619`）：`relevance_ordered` 为真时先 `sorted(...)` 再 `iter_diversify(...)`，否则退回 `sorted(pool, key=_confidence_key)`。**两个预算池（guaranteed / regular）各自独立排序**，但共享同一份 `scores` 和 `idf`——所以「被 guarantee 的 fact」和「竞争主预算的 fact」不会用两套尺子。

### 与检索/注入的关系

| 场景 | 是否走相关性排序 |
|------|-----------------|
| middleware 注入（有当前 query） | ✅ 排序后再按 token 预算挑选 |
| tool 模式注入 | ❌ 只注入全局 summary，facts 在 `memory_search` 后面 |
| 无 query（如后台 consolidation 读取） | ❌ 沿用 confidence 序（`query=None` 即旧行为） |
| `memory_search` 工具 | 取决于 `retrieval_relevance_enabled`：开 → `_relevance_search`（`deer_mem.py:458-486`，全 scope 竞争 + 自己的 `build_idf`）；关 → `_fts5_search` 失败后退 `_substring_search`（`:388-396`） |

**它是「确定性」的**：同样的 fact 集合 + 同样的 query + 同样的配置，排序结果始终一致——这是与 embedding 检索最重要的区别，也是它能放进热路径的前提。

---

## 配置速查

```yaml
memory:
  enabled: true
  injection_enabled: true
  mode: middleware           # middleware | tool
  manager_class: deermem     # deermem | mem0 | noop | openviking | honcho | <custom>
  shutdown_flush_timeout_seconds: 30
  backend_config:
    # ── Storage ──
    storage_path: ""         # 空 = runtime_home()；DIRECTORY（不是文件！）
    max_facts: 100
    fact_confidence_threshold: 0.7
    # ── Eviction（hybrid-v1 事实驱逐）──
    fact_eviction_policy: confidence      # confidence | hybrid-v1
    fact_eviction_shadow_enabled: false
    eviction_confidence_weight: 0.65      # 三权重之和必须 = 1.0
    eviction_confirmation_weight: 0.25
    eviction_access_weight: 0.10
    eviction_confirmation_half_life_days: 90
    eviction_access_half_life_days: 30
    eviction_correction_reserved_fraction: 0.10
    eviction_correction_reserved_max: 10
    eviction_audit_max_entries: 200
    max_injection_tokens: 2000
    # ── Retrieval（2.2.0 🆕）──
    retrieval_adapter: fts5              # fts5 | ""（关闭）| 点路径工厂（RetrievalPort）
    retrieval_index_path: ""             # 空 = {storage_path}/.retrieval；多 Gateway 必须指实例本地盘
    retrieval_relevance_enabled: false   # 开则 search 绕过 adapter，全 scope 词法排序
    retrieval_relevance_weight: 0.5      # 0.0 = 只看 confidence；1.0 = 只看相关性
    retrieval_diversity_weight: 0.0      # greedy-MMR 重复惩罚，0 = 不去冗余
    fact_dedup_enabled: false            # 近重复门（#5252），默认关
    fact_dedup_similarity_threshold: 0.7 # 仅 fact_dedup_enabled 时生效，范围 [0.5, 1.0]
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

## 🆕 Retrieval 相关的四个警告

来自 `deermem/config.py` 的字段描述，都是容易踩的坑：

1. **`retrieval_relevance_enabled: true` 会让 `search` 绕过 `retrieval_adapter`**——包括 FTS5 和自定义工厂。索引仍然照常建（`retrieval_index_path` 仍有效），但搜索不再走它。要么用 adapter，要么用 relevance，不要指望两者叠加。
2. **`retrieval_index_path` 在多 Gateway 共享 `storage_path` 时必须指实例本地盘**——「SQLite WAL is unsupported on network filesystems, and peers would rebuild or delete each other's index.」索引本身是可重建的派生数据。
3. **`retrieval_adapter: ""` 是「显式关闭」**，与「未配置（默认 fts5）」不同；关闭后搜索退回 `_substring_search`。
4. **`fact_dedup_*` 是写侧的门，`retrieval_relevance_*` 是读侧的门**，互不依赖。近重复门**不作用于 correction 替换和 proposed removal targets**——那两类被显式排除，否则纠正会被合并掉。

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
