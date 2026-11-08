---



title: "RAGFlow — 只读知识库检索"
description: '把 RAGFlow 当外部 RAG 知识库：operator 配置 dataset 白名单，agent 通过唯一的只读 knowledge_search 工具检索，结果格式化成带引用编号的紧凑文本。与 web_search 和内置 memory 检索都不同。'
topics: [tools, community, knowledge, rag, ragflow, retrieval]
verified_against: v2.2.0
last_verified: 2026-11-08
---

# RAGFlow — 只读知识库检索

> 同步 #5（上游 `431892e1`，#4955）新增。RAGFlow 是一个开源的 RAG（检索增强生成）知识库引擎；DeerFlow 把它当作**外部的、operator 预先建好的领域知识库**来用，只暴露一个**只读**的 `knowledge_search` 工具。DeerFlow 不持久化任何 dataset/document 元数据副本——RAGFlow 是唯一事实来源，配置的 API key 是 tenant 级作用域。

## 定位

```
community/ragflow/
├── __init__.py    # 空（无包级导出，靠 tools.py 的模块属性被 reflection 解析）
├── client.py      # 206 行：异步 httpx client + 错误层次 + 分页/文档/检索
├── formatting.py  # 190 行：CAPABILITIES + normalize_retrieval_result（新契约）
│                  #        + format_retrieval_sources（legacy 引用命名空间）
│                  #        + format_retrieval_result（纯文本）
├── provider.py    #  96 行 🆕：RAGFlowKnowledgeProvider（knowledge/ 契约兼容适配器）
├── sources.py     # 170 行 🆕：legacy #knowledge- 命名空间的预算/去重/剪枝
└── tools.py       # 658 行：两个只读 tool + 配置校验 + dataset 解析/分组/并行检索
```

> ⚠️ **行数与工具数量的更正**：v2.1.0 的 digest 写的是 `client.py ~187` / `formatting.py ~96` / `tools.py ~397`，实际 2.2.0 为 **206 / 190 / 658**（`provider.py`、`sources.py` 是新文件）。`tools.py` 变大的主要原因是它同时服务 **legacy 工具** 和 **`RAGFlowKnowledgeProvider`**（后者复用前者的 `resolve_ragflow_datasets` / `_validate_document_filters` / `_group_scoped_datasets` / `_retrieve_dataset_groups`），并新增了 `list_documents` 与文档级过滤校验。

与只读的 `web_search`/`web_fetch` 不同，RAGFlow 检索的是**私有知识库**而非公开互联网。它是纯 `httpx` 实现，无额外 SDK 依赖（不像 Tenki/E2B 需要懒加载三方 SDK）。

## client：连接 / 鉴权 / API

`RAGFlowClient`（`client.py`）是一个**无缓存、无持久状态**的直接 HTTP client——每次方法调用都新开一个 `httpx.AsyncClient` session，调用方无需管理 client 生命周期：

```python
# client.py:41-58
def __init__(self, *, base_url, api_key, timeout=30, transport=None):
    self.base_url = base_url.rstrip("/")
    self._api_key = api_key
    # _redact()：任何字符串里的 api_key 都被替换成 [REDACTED]
```

**鉴权**：所有请求带 `Authorization: Bearer {api_key}` + `Accept: application/json`，base 路径固定拼成 `{base_url}/api/v1`（`_request()`，client.py:60-110）。

**错误层次**（`client.py:13-31`）——全部归一化为可读异常：

| 异常 | 触发 |
|------|------|
| `RAGFlowError` | 基类 |
| `RAGFlowAPIError` | RAGFlow 返回合法 envelope 但 `code != 0`（携带 `code`） |
| `RAGFlowConnectionError` | 超时 / 网络层 `httpx.RequestError` |
| `RAGFlowProtocolError` | 非 2xx 但无 code、非法 JSON、非 object payload |

`_request()` 区分"错误响应带 code"（API 错误）和"错误响应无 code"（协议错误），并在所有错误消息里 `_redact` 掉 API key。

**两个 API 端点**：

| 方法 | HTTP | 作用 |
|------|------|------|
| `list_datasets(dataset_id=None)` | `GET /datasets` | 单 ID 解析或全量分页枚举 |
| `retrieve(query, *, dataset_ids, ...)` | `POST /retrieval` | 在显式 dataset 白名单上检索 chunks |

`list_datasets` 的两个关键设计（client.py:112-158）：

- **单 ID 用 `ids` 参数而非 `id`**：RAGFlow 的单数 `id` 过滤对"不可访问/缺失的 dataset"返回泛化的 `DATA_ERROR`，无法与其它 provider 故障区分；而 `ids` 过滤对不可访问 ID 返回**成功的空列表**，让调用方能把它归类为"missing binding"，同时保留所有真实 API 错误。
- **分页**：`page_size=100`，最多 `_MAX_DATASET_PAGES=100` 页；用 `total`（fallback `total_datasets`）判断是否收完，页数超限或提前中断都抛 `RAGFlowProtocolError`。

`retrieve()` 强制**非空 dataset 白名单**（`dataset_ids` 至少一个非空 ID，否则 `ValueError`），请求体是 RAGFlow 的检索参数：`question` / `dataset_ids` / `page_size` / `similarity_threshold` / `vector_similarity_weight` / `top_k`。

## formatting：结果格式化

`formatting.py` 在 2.2.0 里是**三层**，只有第三层是 v2.1.0 描述的那个函数：

| 层 | 符号 | 位置 | 产出 | 谁用 |
|----|------|------|------|------|
| capabilities | `CAPABILITIES` | `formatting.py:12` | `{search, sources, catalog, documents, dataset_filter, document_filter}` | 注册期校验 / provider 投影 |
| 新契约 | `normalize_retrieval_result()` | `:14` | `RetrievalResult`（`KnowledgeSource` **不带 locator**） | `RAGFlowKnowledgeProvider`、通用工具 |
| legacy 富证据 | `format_retrieval_sources()` | `:116` | `(text, artifact)`，引用 ID = `{uuid4}-{n}`，命名空间 `#knowledge-` | legacy `knowledge_search` 工具 |
| legacy 纯文本 | `format_retrieval_result()` | `:46` | 带 `[N]` 的紧凑文本（无 artifact） | 直接调用 `knowledge_search()` 时 |

### 新契约层：`normalize_retrieval_result`

`formatting.py:14-31`。逐 chunk 取 `content`（strip 后非空才保留，两端截到 100_000）、`title` 取 `document_keyword` 或 `doc_aggs` 里的 `doc_name`（strip 后截 500）；只有 title 非空才构造 `KnowledgeSource(provider="ragflow", title=..., excerpt=..., dataset_name=...)`——**不打 url、不打 page**，所以 `KnowledgeSource.id` 是内容哈希而非 provider ID。`score` 只保留有限 float（`_score()` 对 `bool`/不可解析值返 None）。

### legacy 富证据层：`format_retrieval_sources`（v2.1.0 未记录）

`formatting.py:116-190`，返回 `(text, {"knowledge_sources": {"version": 1, "sources": [...]}})`：

- **只保留可核验的 locator**：`dataset_id` / `document_id` / `chunk_id` 三个都必须是 1-256 字符的非空字符串，且 `dataset_id` 必须在 `dataset_names_by_id` 里——「Incomplete or out-of-scope locators must not become verified sources.」缺一个就整条跳过；
- **重要修正：dataset/document 的名字放在引用标签之外**——header 由三段拼成：citation 标记（标签是序号 `n`）+ 链接目标 `#knowledge-<uuid>-<n>` + ` dataset_name / document_name` + 换行，注释原话「Keep untrusted names outside the Markdown label to avoid link injection.」v2.1.0 的描述把 `[N] {dataset_name} / {document_name}` 当成唯一格式，实际上**这条路径的编号是 `[citation:N]` 形式**；
- 引用 ID = `f"{uuid4().hex}-{n}"`——**每次调用都变**，这正是 2.2.0 新契约改用内容哈希的原因；
- 预算：`remaining` 从 `max_total_chars` 递减，每条的 `allowance = min(max_chars_per_chunk, remaining - len(header) - 分隔符)`，`allowance < 1` 就 break；最多 100 个 chunk；
- `redact` 回调（默认 `str`，RAGFlow 传 `lambda v: redact_secret(v, api_key)`）作用于 dataset 名、document 名和正文；
- `pages` 从 `chunk["positions"][:100]` 提取（只收 1..1_000_000 的 int），`truncated` 标记 excerpt 是否被截；
- **一条 source 都没有时**退回 `format_retrieval_result()` 并返回 `None` artifact——「Legacy/incomplete provider responses still yield useful readable text.」

共享的 `truncate` 来自 `deerflow.knowledge.sources`（`formatting.py:9`），不再是模块私有实现。

### legacy 纯文本层：`format_retrieval_result()`（`formatting.py:46-112`）把 RAGFlow 原始 retrieval 响应转成**带引用编号的紧凑文本**：

- **已验证版本**：针对 RAGFlow v0.26.4 和 v0.27.0——REST 检索端点在返回前会归一化 chunk 字段（如 `kb_id` → `dataset_id`），只消费这些公开响应字段名。
- **chunks**：逐个输出 `[N] {dataset_name} / {document_name}{score_suffix}\n{content}`；`score_suffix` 为 `"  (score 0.82)"`（两位小数），无法解析为有限 float 时**整段省略**而不是打 `nan`；dataset ID 通过 `dataset_names_by_id` 映射回 operator 配置的名字（模型永远看不到原始 ID），缺映射时为 `"Unknown dataset"`，文档名缺失为 `"Unknown document"`。
- **doc_aggs**：接受 list 或 dict（`_document_aggregates`，`formatting.py:33-40`），`doc_id → doc_name` 映射用于补全 chunk 缺 `document_keyword` 的文档名；末尾追加 `Matched documents: name (N chunks)` 汇总（`count` 非 int 或为 bool 时显示 `?`，单数走 `1 chunk`）。
- **截断**：每 chunk `max_chars_per_chunk`（默认 800）、整篇 `max_total_chars`（默认 8000）；整篇超限时保留 `max_total_chars - len(marker)` 前缀、`rstrip()` 后拼 `… (response truncated)`；若预算连标记本身都放不下，直接返回标记的前 N 字符。`_score()` 只在值可解析为 float 时保留相似度（bool → None）。
- 空结果 → `"No relevant content found."`。

## tools：唯一的只读工具 + 配置

暴露**两个** tool（v2.1.0 只记了一个）：

| tool | 定义位置 | `response_format` | 说明 |
|------|---------|-------------------|------|
| `knowledge_search` | `tools.py:631` | `content_and_artifact` 🆕 | 唯一检索入口 |
| `list_knowledge_bases` | `tools.py:653` | 默认（纯文本） | 列出可访问 KB **名字**，永不含 dataset UUID（`tools.py:594` 起） |

`knowledge_search` 经 `_knowledge_search_entrypoint(query, runtime)`（`tools.py:624`）调用 `knowledge_search(query, runtime=..., _source_artifact=artifact)`——**`metadata={"knowledge_capabilities": CAPABILITIES.model_dump(mode="json")}`**（`tools.py:637`）是 2.2.0 加的：装配期用这个元数据把 tool 声明的能力交给 `knowledge/providers.py` 校验，不需要 import RAGFlow。

两者都**只读**——dataset 创建、上传、解析、删除都留在 RAGFlow 里，不做成 agent tool 也不做 DeerFlow API。

**配置**从 `config.yaml` 的 tool 条目 `model_extra` 读入，经 `_RAGFlowRetrievalSettings` Pydantic 模型校验（`tools.py:36-75`）：

```yaml
tool_groups:
  - name: knowledge

tools:
  - name: knowledge_search
    group: knowledge
    use: deerflow.community.ragflow.tools:knowledge_search_tool
    base_url: http://localhost:9380   # Docker/K8s 下必须从 Gateway 容器可达
    api_key: $RAGFLOW_API_KEY
    datasets:                          # 可选 operator 白名单；省略 = 搜 tenant 可见的所有 dataset
      - 0123456789abcdef0123456789abcdef
    timeout: 30
    page_size: 8
    similarity_threshold: 0.2
    vector_similarity_weight: 0.3
    top_k: 256
    max_chars_per_chunk: 800
    max_total_chars: 8000
```

设置字段与默认值（`_RAGFlowRetrievalSettings`）：

| 字段 | 默认 | 约束 |
|------|------|------|
| `datasets` | `null`（全量） | 显式 `[]` 非法；每 ID 1–256 字符、去重、≤100 个 |
| `base_url` | `http://localhost:9380` | 禁止含 username/password（`_reject_url_userinfo`） |
| `api_key` | 必填 | `SecretStr`；缺失 → tool 直接返回错误 |
| `timeout` | 30 | (0, 600] |
| `page_size` | 8 | [1, 100] |
| `similarity_threshold` | 0.2 | [0, 1] |
| `vector_similarity_weight` | 0.3 | [0, 1] |
| `top_k` | 256 | [1, 1024] |
| `max_chars_per_chunk` | 800 | [1, 100000] |
| `max_total_chars` | 8000 | [1, 1000000] |

配置读取路径（`_settings_or_error`，tools.py:119-137），2.2.0 里它被包在 `await asyncio.to_thread(...)` 中调用（`tools.py:533`），因为配置解析会 stat/hash 文件。同一批内部函数被 `provider.py` 以 `resolve_ragflow_retrieval_settings`（`tools.py:318`）和 `build_ragflow_retrieval_client`（`tools.py:325`）两个公开别名复用。：`get_app_config().get_tool_config("knowledge_search")` → 未配置返回 `"Error: knowledge_search is not configured..."`；校验失败 → 通用错误；`api_key` 缺失 → 提示优先用 `$RAGFLOW_API_KEY`（`_warned` 集合保证只 warn 一次）。

## 检索执行流程

```
knowledge_search(query, *, knowledge_scope, runtime, _source_artifact)
  → 解析作用域 🆕：knowledge_scope 参数 > runtime.context[KNOWLEDGE_SCOPE_RUNTIME_KEY]
      canonicalize_knowledge_scope() → execution_scope()；mode=disabled → 直接拒
  → _settings_or_error()                # 读 tool 配置 + 校验 + api_key 必填（在 to_thread 里）
  → _build_client(settings)             # base_url + api_key + timeout
  → _resolve_datasets(client, settings, requested_dataset_ids=作用域选中的 ID)
      ├─ datasets is None  → list_datasets() 全量分页，去重后按 id 收进 resolved
      └─ datasets 显式     → 逐条 list_datasets(dataset_id=id) 校验
                            缺失/不可访问 → "The Nth entry ... was not found or is inaccessible"
  → [_validate_document_filters()]      # 仅 selected 模式：逐文档核对归属与可检索状态
  → _group_scoped_datasets()            # 按 embedding_model + 文档过滤集合分组
  → _retrieve_dataset_groups()          # Semaphore(4) 并发；每组一次 retrieve()
      → _merge_group_results()          # 按 rank 交错合并，page_size 全局截断
  → 两条输出路径（看调用者）
      ├─ _source_artifact 非 None → format_retrieval_sources()（legacy #knowledge- 命名空间）
      │      artifact 为空时退回 normalize_retrieval_result() + knowledge.sources.format_result()
      └─ 否则                      → format_retrieval_result()（纯文本，无 artifact）
  → redact_secret(..., api_key)         # 成功路径必做 API key 脱敏
```

关键机制（`tools.py`）：

1. **dataset 作用域**：`datasets` 省略 → 每次搜索分页枚举 tenant 可见的 dataset 目录；显式白名单 → 搜索时用 ID 过滤请求逐条校验（配置加载时**不**校验存在性）。缺失条目用**序数**（"The 2nd entry of `knowledge_search.datasets`..."，`_ordinal`）报错，指向 `config.yaml`。
2. **混合 embedding 分组**：`_group_searchable_datasets` 把剩余 dataset 按**精确的 embedding_model 标识**分组（`chunk_count==0` 的空 dataset 跳过；空 dataset 且无 embedding 元数据也跳过并 server warn）。每组各自发一次带非空 `dataset_ids` 的检索。
3. **跨组分数不可比**：不同 embedding 空间的 raw similarity 不做全局校准，所以 `_merge_group_results` **保留各组 RAGFlow 排名、按相等 rank 交错合并**，多组搜索时**隐藏 score 标签**，`page_size` 作为全局 chunk 上限。任何一组失败 → 整个 tool 调用失败（不静默丢配置范围）。
4. **并发**：`asyncio.Semaphore(_MAX_PARALLEL_RETRIEVAL_GROUPS=4)`，`asyncio.gather(..., return_exceptions=True)` 后统一 re-raise。
5. **脱敏边界**：API key 在成功路径也强制脱敏；UUID 格式的 dataset ID 只在**错误路径**脱敏（`_redact_error`，`_RAGFLOW_UUID_PATTERN`）——成功路径保留合法 checksum / trace ID 不被误替换。
6. **tool 描述**（`_tool_description`，`tools.py:615`）：「Search the operator-approved RAGFlow datasets and return compact, citation-numbered source chunks. If knowledge_search.datasets is omitted, all datasets accessible to the configured RAGFlow API key are searched. Dataset IDs are never shown to the model. When citing results, copy the supplied `[citation:N]` links exactly; do not invent or renumber source links.」——明确声明 operator 白名单、ID 不进模型，以及 **2.2.0 起引用必须原样复制**。
7. **文档级收窄**（`_validate_document_filters`，`tools.py:340`）：仅 `selected` 模式下 `knowledge_scope.document_filters` 非空时执行，逐条向 RAGFlow 核对文档是否属于已选 dataset 且处于可检索状态；单次请求文档 ID 上限 `_MAX_DOCUMENT_IDS_PER_REQUEST = 100`（`tools.py:35`）。

## v2.2.0：`RAGFlowKnowledgeProvider` 兼容适配器

`provider.py`（96 行）让 RAGFlow 以**新契约**（见 [09-knowledge-abstraction.md](09-knowledge-abstraction.md)）的形式被通用 `knowledge_search` 工具使用，同时不重写任何检索逻辑：

```python
class RAGFlowKnowledgeProvider:
    capabilities = CAPABILITIES          # formatting.py:12
    def __init__(self, app_config):      # 无 I/O；配置解析失败 → LookupError
    async def search(self, query):                          # → _search(query, None)
    async def search_scoped(self, query, *, context):        # → _search(query, context.scope)
    async def catalog(*, context, page, page_size, search)
    async def documents(dataset_id, *, context, page, page_size, search)
```

要点：

- **构造不做 I/O**——注释「Construction performs no I/O; credentials remain in the adapter.」，配置解析失败抛 `LookupError("Knowledge retrieval is not configured")`（由 `knowledge/providers.py` 转成对模型脱敏的配置错误）；
- **`_search()` 的失败语义统一成 `PermissionError("Knowledge scope is unavailable")`**——dataset 解析失败、文档过滤校验失败都走这一条，**不区分「不存在」与「无权限」**，避免向模型泄漏资源存在性；`groups` 为空时返回空 `RetrievalResult()` 而不是错误；
- `_search()` 内部**自己再调一次** `validate_scope_capabilities`（`provider.py:36`）——不信任调用方已校验过；
- 结果统一 `normalize_retrieval_result(redact_strings(result, key), dataset_names_by_id=redact_strings(...))`——**先脱敏再归一化**，text 与 artifact 两条路径都不会带出 API key；
- **`catalog()`**（`provider.py:56`）：全量解析 dataset 目录后按 `search` 做 casefold 子串过滤，再在内存里切片分页；`selectable = bool(item.embedding_model) and item.chunk_count != 0`——与 legacy `_group_searchable_datasets` 的跳过条件一致，所以「目录里能不能选」与「选了能不能搜到」不会互相打脸；
- **`documents()`**（`provider.py:66`）：先查 operator 白名单（`settings.datasets is not None and dataset_id not in settings.datasets` → `FileNotFoundError("Knowledge base not found")`），再 `list_documents(dataset_id, params=[page, page_size, keywords?])`；`data["docs"]` 不是 list → `RAGFlowProtocolError("Invalid document list")`；`total` 非非负 int 时退回 `len(items)`；`selectable = document["run"] == "DONE" and chunk_count > 0`。

配置方式（`config.yaml`）——把 `use` 指向**通用**工具再加 `provider: ragflow`：

```yaml
tools:
  - name: knowledge_search
    group: knowledge
    use: deerflow.knowledge.tools:knowledge_search_tool
    provider: ragflow
    base_url: http://localhost:9380
    api_key: $RAGFLOW_API_KEY
```

注意 `provider: ragflow` 是**保留名**——`extensions/registry.py:157` 拒绝扩展注册同名 provider，这个名字只由 `knowledge/providers.py:139` 的 `resolve_knowledge_provider()` 特判（它从 `knowledge_search` 的 tool extra 里构造 `RAGFlowKnowledgeProvider`）。

## 与 memory 检索的区别

两者都是"检索"，但定位、数据来源、生命周期完全不同：

| 维度 | RAGFlow（本文件） | DeerFlow 内置 memory |
|------|------------------|---------------------|
| 数据来源 | operator 预先在 RAGFlow 建好的**领域知识库**（私有文档） | 从**对话中自动提取**的 per-user/per-agent fact |
| 写入方 | 只有 RAGFlow（DeerFlow 只读） | MemoryUpdater 后台 LLM 提取 + consolidation/staleness |
| 作用域 | tenant 级 API key + dataset 白名单，全 deployment 共享 | per-user、per-agent 隔离（`users/{uid}/agents/{name}/facts/`） |
| 触发 | agent 主动调 `knowledge_search` tool | middleware 自动注入 `<memory>`，或 tool 模式 `memory_search` |
| 检索后端 | RAGFlow 的 embedding/相似度检索 | DeerMem 默认 FTS5 BM25（或 mem0/OpenViking 远程） |
| 结果 | 引用编号 chunks（原文片段 + 相似度） | 结构化 fact（标题 + category + confidence） |

一句话：**RAGFlow 是"接入外部领域知识"，memory 是"记住这次会话里关于用户的长期事实"**。详见 [`../memory/extract-queue-persist-pipeline.md`](../memory/extract-queue-persist-pipeline.md)。

## 源码索引

| 机制 | 位置（2.2.0 实测行号） |
|------|------|
| HTTP client + 错误层次 | `client.py:36` `RAGFlowClient` / `:60` `_request` / `:16-33` `RAGFlow*Error` |
| dataset 分页 / ID 过滤 | `client.py:112` `list_datasets`（`ids` 参数技巧）、`:160` `list_documents` 🆕 |
| 检索 | `client.py:174` `retrieve`（POST `/retrieval`） |
| 能力声明 | `formatting.py:12` `CAPABILITIES` |
| 新契约归一化 | `formatting.py:14` `normalize_retrieval_result` |
| legacy 富证据格式化 | `formatting.py:116` `format_retrieval_sources` 🆕 |
| legacy 纯文本格式化 | `formatting.py:46` `format_retrieval_result` / `:33` `_document_aggregates` / `:42` `_score` |
| legacy 预算/去重/剪枝 | `sources.py` 🆕（`#knowledge-` 命名空间） |
| **兼容适配器** | `provider.py:19` `RAGFlowKnowledgeProvider`；`:28` `search` / `:31` `search_scoped` / `:34` `_search` / `:56` `catalog` / `:66` `documents` |
| 配置校验 | `tools.py:54` `_RAGFlowRetrievalSettings` / `:119` `_settings_or_error` / `:318` `resolve_ragflow_retrieval_settings` |
| dataset 解析/分组 | `tools.py:260` `_resolve_datasets` / `:331` `resolve_ragflow_datasets` / `:340` `_validate_document_filters` / `:387` `_group_scoped_datasets` |
| 并行检索 + 合并 | `tools.py:474` `_retrieve_dataset_groups` / `:427` `_merge_group_results` / `:227` `_bounded_gather` |
| 脱敏 | `tools.py:110` `_redact_error` / `:33` `_RAGFLOW_UUID_PATTERN` |
| 作用域读取 | `tools.py:505` `_runtime_knowledge_scope`（读 `KNOWLEDGE_SCOPE_RUNTIME_KEY`） |
| tool 定义 | `tools.py:512` `knowledge_search()` / `:624` `_knowledge_search_entrypoint` / `:631` `knowledge_search_tool` / `:594` `list_knowledge_bases` / `:653` `list_knowledge_bases_tool` |
| 配置示例 | `config.example.yaml`（tools 段 RAGFlow 注释块） |
| 测试 | `tests/test_ragflow_client.py`（322 行）/ `tests/test_ragflow_tools.py`（1321 行）——行数为 v2.1.0 记录，2.2.0 未复核 |

## 相关

- 装配 / 集成矩阵 / 选型 → [`00-overview.md`](00-overview.md)
- 如何添加新 provider（同目录约定）→ [`05-how-to-add-provider.md`](05-how-to-add-provider.md)
- 内置 memory 检索 → [`../memory/extract-queue-persist-pipeline.md`](../memory/extract-queue-persist-pipeline.md)
- 只读 web_fetch/web_capture 对比 → [`02-web-fetch.md`](02-web-fetch.md)
- **统一 `knowledge/` 契约（capabilities / 证据 / 预算 / 作用域）** → [`09-knowledge-abstraction.md`](09-knowledge-abstraction.md)
