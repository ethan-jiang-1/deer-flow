---
title: "knowledge/ 统一只读检索契约 + WeKnora 扩展 provider"
description: "2.2.0 把「只读知识库检索」从 RAGFlow/LightRAG 两个各自为政的 community 工具抽成 core 的一套 provider 中立契约：deerflow/knowledge/（capabilities、证据与引用、预算、工具面）+ deerflow/knowledge_scope.py（每轮作用域快照）+ 扩展注册口 registry.knowledge_provider()。RAGFlow 降级为兼容适配器之一，WeKnora 作为可安装扩展走同一条通用工具路径。"
topics: [tools, community, knowledge, retrieval, citations, extensions]
---

# knowledge/ 统一只读检索契约 + WeKnora 扩展 provider

> 2.2.0 新增（上游 PR #6716 phase 1「统一只读检索与来源契约」、#6904 phase 2「作用域与只读目录解耦」、#7171「Wiki 条目与实体关系独立检索工具」、#6950 phase 3 WeKnora 扩展、#7417「平台连接与层级空间」）。
> 2.1.0 的世界里，`knowledge_search` 只是 `community/ragflow` 和 `community/lightrag` 各写一版的工具；2.2.0 起，**工具名、证据形状、引用语法、字符预算、跨子 agent 转发、历史重放去重全部由 core 拥有**，provider 只负责「拿到 hit」。
> 旧的 [07-ragflow.md](07-ragflow.md) / [08-lightrag.md](08-lightrag.md) 仍在，但它们的 formatting 层已被本页的契约接管——读它们时请对着本页校正语义。

---

## 一、分层：谁拥有什么

```
deerflow/knowledge/            ← core 契约（provider 中立，禁止放配置/HTTP/资源权限）
├── contract.py                # KnowledgeCapabilities / KnowledgeSource / RetrievalHit /
│                              # RetrievalResult / KnowledgeRequestContext / 6 个 Protocol
├── providers.py               # capabilities 投影、provider 校验、配置解析、作用域能力校验、search_provider
├── sources.py                 # 证据归一、引用语法、字符预算、跨子 agent 转发、历史重放
└── tools.py                   # 3 个 StructuredTool：knowledge_search / knowledge_entries_search / entity_relations_search

deerflow/knowledge_scope.py    ← 每轮作用域快照（版本化、fail-closed、display 与 execution 分离）
deerflow/extensions/registry.py:154  registry.knowledge_provider(name, provider)

deerflow/community/ragflow/    ← 兼容适配器（provider.py + formatting.CAPABILITIES）
deerflow/community/lightrag/   ← 兼容适配器（formatting.CAPABILITIES）
examples/deerflow-extension-weknora/  ← 可安装扩展（registry.knowledge_provider("weknora", ...)）
```

`knowledge/providers.py` 的模块 docstring 把边界写死：**「No provider configuration, HTTP calls or resource permissions live here.」**（`providers.py:1-6`）。provider 的登录、凭证、租户绑定一律留在 provider 侧；core 只做「能不能问、问完的证据能不能给模型看」。

---

## 二、能力模型：`KnowledgeCapabilities`

`knowledge/contract.py:13-31`——一个 frozen Pydantic，只有 `operations: frozenset[Literal[...]]` 一个字段，默认 `frozenset({"search"})`：

| operation | 含义 |
|-----------|------|
| `search` / `sources` | 文档检索 + 可归因来源 |
| `catalog` / `documents` | 列出可检索的 dataset / 某 dataset 下的文档 |
| `dataset_filter` / `document_filter` | 支持 `selected` 作用域（按 dataset / 按文档收窄） |
| `entries_search` + `entries_dataset_filter` / `entries_document_filter` | 第三类检索：已发布的 Wiki/条目 |
| `relations_search` + `relations_dataset_filter` / `relations_document_filter` | 第四类检索：上游实体与关系 |

**「只有显式声明才算支持」**——`supports(op)` 就是集合成员判断，默认值只有 `search`，所以一个只写 `async def search()` 的最小 provider 不会意外被当作支持作用域收窄。

三档现役 capabilities（全部可在源码里直接对到）：

| 提供方 | operations | 出处 |
|--------|-----------|------|
| RAGFlow | `search, sources, catalog, documents, dataset_filter, document_filter` | `community/ragflow/formatting.py:12` |
| LightRAG | `search, sources` | `community/lightrag/formatting.py:11` |
| WeKnora | `search, sources, catalog, documents, dataset_filter, document_filter, entries_search, entries_dataset_filter` | `examples/deerflow-extension-weknora/deerflow_extension_weknora/provider.py:80` |

注意 WeKnora **刻意不声明** `relations_search`（其 README 与 `provider.py` 都没有实现该方法）；同理它声明了 `entries_dataset_filter` 但**没有** `entries_document_filter`——Wiki 页会合并多份源文档，v0.8.3 的 search 端点无法按文档收窄，所以 `entries_search` 见到 `document_filters` 直接 `ValueError`（`provider.py:230-233`）。

### capability 投影：`operation_capabilities`

`providers.py:41-55` 把「provider 的完整能力」投影成「某一个工具实际能用到的能力」，因为三个工具共享同一个 provider：

- `search` → 取交集 `{search, sources, catalog, documents, dataset_filter, document_filter}`；
- `entries_search` / `relations_search` → 前缀剥离后重组：只要 provider 支持 `sources/catalog/documents` 就带上，支持本 operation 才加 `search`，`*_dataset_filter` / `*_document_filter` 逐条透传。

未知 operation 直接 `ValueError("Unknown knowledge retrieval operation")`。

---

## 三、provider 校验：`validate_provider`

`providers.py:58-78`——注册期（`registry.knowledge_provider` 立即调用）和运行期都会走一遍：

1. `capabilities` 必须是 `KnowledgeCapabilities`，且至少支持一个工具 operation，否则 `ValueError`；
2. 由能力反推「必须存在的方法」：`search`→`search`、`catalog`→`catalog`、`documents`→`documents`、任一 `*_filter`→`search_scoped`、`entries_search`/`relations_search`→同名方法；
3. **每个被声明的方法必须是 coroutine function**（`inspect.iscoroutinefunction`），否则 `ValueError("... requires async <method>")`；
4. `entries_dataset_filter` 但没有 `entries_search` → `ValueError("Filter capability requires its retrieval operation")`——过滤能力不能脱离它要过滤的那次检索。

这条「声明即校验」是 2.2.0 的核心防御：capabilities 是 operator 看到的配置面，也是 provider 的自我声明，声明与实现不一致必须在装配期炸，而不是等模型调用时抛 `AttributeError`。

### Protocol 面（`contract.py`）

| Protocol | 方法 | 说明 |
|----------|------|------|
| `RetrievalProvider` | `async search(query) -> RetrievalResult` | 无条件检索 |
| `ScopedRetrievalProvider` | `async search_scoped(query, *, context)` | 带作用域；**实现了它就必须在 all 作用域下也传 context** |
| `RetrievalCatalogProvider` | `async catalog(*, context, page, page_size, search)` | 目录分页 |
| `RetrievalDocumentsProvider` | `async documents(dataset_id, *, context, page, page_size, search)` | 文档分页 |
| `KnowledgeEntriesProvider` | `async entries_search(query, *, context)` | Wiki/条目 |
| `EntityRelationsProvider` | `async relations_search(query, *, context)` | 实体/关系（只返回上游证据，**禁止推断边**） |

`ScopedRetrievalProvider` 的 docstring 是一条硬约束：**「A missing/inaccessible selection must fail as a whole. Never retry a constrained request as an unconstrained search.」**——收窄失败不允许退化成全库搜。WeKnora 与 RAGFlow 的实现都遵守（WeKnora 逐条校验后统一抛 `PermissionError`，见 `provider.py:196-204`）。

`KnowledgeRequestContext`（`contract.py:93-111`）是 frozen dataclass：`user_id` / `agent_name` / `scope`。docstring 明确三件事：
- 它是**宿主身份与执行约束，不是 provider 授权**——provider 每次操作都必须自己再做权限校验；
- `scope` 是**执行态快照，display 标签永不进入 provider**；
- `agent_name` 是**当前执行者**（默认 `lead_agent`，或正在执行的子 agent 名），**不是父 assistant 名**。

---

## 四、最短路径：`search_provider`

`providers.py:157-186` 是三个工具共用的一次调用骨架：

1. `operation_capabilities(provider.capabilities, operation)`；没有 `search` → `ValueError("Knowledge retrieval operation is unavailable")`；
2. 有 scope 就 `validate_scope_capabilities(scope, capabilities)`（见下节）；`mode == "disabled"` → `ValueError("Knowledge search is disabled for this turn")`；
3. 组 `KnowledgeRequestContext(user_id=..., agent_name=..., scope=canonical)`；
4. 选方法：`search` → `search_scoped`；`entries_search`/`relations_search` → 同名方法；否则退回无条件 `search(query)`；
   - 有 `selected` scope 但 provider 没有 `search_scoped` → `ValueError("Knowledge provider cannot apply the selected scope")`（**绝不静默忽略选择**）；
5. **返回值二次校验**：`RetrievalResult.model_validate(result.model_dump())`——「Validate provider values before they can become model-visible evidence.」

### 作用域能力校验：`validate_scope_capabilities`

`providers.py:146-155`：先把 scope 过一遍 `execution_scope()`；没有 `search` → `"Knowledge retrieval is unavailable"`；`mode == "selected"` 时要求 `dataset_filter`，并**只在真有 `document_filters` 时**才要求 `document_filter`。这让「只支持 dataset 级的 provider」和「也支持文档级收窄的 provider」共存，而不必给前者塞一个空实现。

### 多工具交叉：`get_knowledge_capabilities`

`providers.py:104-144` 处理一个容易忽略的场景：**同一轮里配了多个知识工具**。它取每个已配置工具的 capability 交集；并且**只要出现两种以上不同 provider 身份**，就砍掉 `{catalog, documents, dataset_filter, document_filter}`，只留下「全开 / 全关」：

> 「Different provider registrations have no shared resource-ID namespace; their combination supports all/disabled only. Never reinterpret selected IDs.」

理由很实在：RAGFlow 的 dataset UUID、WeKnora 的 `wk1_...` 哈希 ID 互不兼容，把一方的 ID 塞给另一方只能靠猜。配置非法时（工具指向未注册 provider 或 provider 未声明该 operation）记一条 error 日志但错误文本对模型脱敏：`"Invalid knowledge tool configuration; check operator logs"`。

---

## 五、证据：`KnowledgeSource` 与引用语法

`contract.py:34-61`——一个 hit 的可归因来源：

| 字段 | 约束 |
|------|------|
| `provider` | 1-100 字符 |
| `title` | 1-500，`str_strip_whitespace` |
| `excerpt` | 1-100_000 |
| `dataset_name` | 可选，≤500 |
| `url` | 可选 `HttpUrl`，**validator 拒绝带 username/password 的 URL** |
| `page` | 可选，`strict=True` 的整数，`1 ≤ page ≤ 2^53-1` |
| `id` | **计算字段**：`sha256(json([provider, title, excerpt, dataset_name, url, page]))[:32]` |

`id` 的计算属性是整套引用稳定性的支点：同一个 provider 返回同一段证据 → 同一个 ID，**与调用次序、总预算、provider 内部 chunk ID 全部无关**。docstring 对此写得很硬：「Titles and optional locators are provider evidence, **never inferred links, page numbers, or local reference ordinals**. IDs expose no provider internals.」——所以 WeKnora 拿不到可信页码时选择**留空**而不是从 chunk offset 反推（`provider.py:243-245`）。

### 引用文本：`sources.py::citation`

`knowledge/sources.py:63-66`：

```python
title = source.title.replace("\\", "\\\\").replace("[", "\\[").replace("]", "\\]").replace("\n", " ")
return "[citation:" + title + "]" + "(#knowledge-source-" + source.id + ")"   # 原源码为 f-string
```

标签先转义再插入——provider 返回的标题是不可信输入，不转义就能构造 Markdown 链接注入。最终语义是「**只允许复制给定的 `[citation:Title]` + `#knowledge-source-<32 位十六进制 ID>`，不要自己发明或重编号**」，这句话被写进了三个通用工具的 description（`knowledge/tools.py:81-86`）。

**与 RAGFlow legacy 命名空间并存**：`community/ragflow/sources.py` 里的 `budget_source_artifact` 仍产出 `#knowledge-<uuid>-<n>` 形式的旧 ID（provider 固定 `"ragflow"`，ID 正则 `[a-f0-9]{32}-[1-9][0-9]{0,2}`）。两条路径不会混：走 `ragflow.tools:knowledge_search_tool` 是旧格式，走 `deerflow.knowledge.tools:knowledge_search_tool` + `provider: ragflow` 是新格式。

### 预算：`format_result`

`knowledge/sources.py:68-107`，签名 `format_result(result, *, max_chars_per_chunk=800, max_total_chars=8000)`：

1. **最多 100 个 hit**（第 101 个只置 `truncated` 后 break，与 artifact 读取器和委派账本的上限对齐）；
2. `content` 先 `strip()` 再按 `max_chars_per_chunk` 截断（截断标记 `…`）；
3. **证据必须来自这个 hit**：`source.excerpt != hit.content.strip()` 时直接丢 source——适配器不能把另一段文本挂到这条证据上；
4. 只剩一个截断标记（`content == "…"` 且原始内容更长）时也丢 source——「A truncation marker alone is not retrieved evidence.」；
5. 然后**用截断后的 `content` 重建 `KnowledgeSource`**——模型看到的 excerpt 与 artifact 里的 excerpt 逐字一致；
6. 每条 header 是 `[N] ` + 该条 citation，无 source 时是 `[N] Unattributed content`；
7. **放不下就整条丢弃**（不是切一半）：`len(entry) > remaining` → `truncated` + break。注释给出的理由：「keeps the stable source identity independent of total budget」——如果切开，`excerpt` 会随预算变化，ID 也就跟着变；
8. 末尾按剩余预算补 `TRUNCATION_MARKER = "… (response truncated)"`；全空则给 `"No relevant content found."`。

返回 `(text, artifact)`，artifact 由 `source_artifact()`（`sources.py:57-58`）构造：

```python
{"knowledge_sources_version": 1, "knowledge_sources": [source.model_dump(mode="json", exclude_none=True), ...]}
```

`ARTIFACT_VERSION = 1` 是硬门：`sources_from_messages()` 只认 `type(artifact["knowledge_sources_version"]) is int and == 1` 的消息（`sources.py:123`）。

### 三个防篡改/防泄漏小工具

| 函数 | 位置 | 作用 |
|------|------|------|
| `redact_strings(value, secret)` | `sources.py:15-24` | 递归替换字符串里的密钥，**归一化之前**做，text 和 artifact 都不泄漏 |
| `strip_source_artifact(artifact)` | `sources.py:27-32` | 只剥服务端所有的证据键（`knowledge_sources` / `knowledge_sources_version` / `retrieval_sources`），用于不可信的写回 |
| `prune_sources(content, artifact)` | `sources.py:35-52` | 预算变换后**只保留模型仍看得到的证据**：把正文里指向已消失 ID 的 citation 降级成纯标签，artifact 同步重算 |

`prune_sources` 的正则是 `\[citation:((?:\\.|[^\]\\])*)\]\(#knowledge-source-([a-f0-9]{32})\)`——只匹配新命名空间的 32 位十六进制 ID，不会误伤旧格式。

### 重放与委派：`sources_from_messages` / `forward_sources`

- `sources_from_messages(messages)`（`sources.py:110-140`）：只扫 `type == "tool"` 消息（原生 `ToolMessage` 或序列化 dict），逐条 `KnowledgeSource.model_validate` 失败即跳过，并要求 **`raw["id"] == source.id` 且 `source.excerpt in content` 且 `#knowledge-source-{id}` 出现在正文里**——三条同时成立才认。按 ID 去重后保留最后 100 条。docstring：「Accept native and serialized ToolMessages, **never assistant claims**.」
- `forward_sources(report, raw_sources, *, max_total_chars=8000)`（`sources.py:143-155`）：子 agent 的报告 + 父侧收到的来源，只保留「报告正文里真的引用过的」那些，拼成 `"{report}\n\nKnowledge evidence:\n{evidence}"` 再走一次 `format_result` 与 `prune_sources`。没有任何证据时报告也会被 `prune_sources(report, source_artifact([]))` 洗一遍（把悬空 citation 降级）。

---

## 六、工具面：`knowledge/tools.py`

三个 `StructuredTool`（`response_format="content_and_artifact"`），共用 `execute_knowledge_search()`（`tools.py:37-73`）：

| 工具名 | operation | description 摘要 |
|--------|-----------|------------------|
| `knowledge_search` | `search` | "Search accessible document evidence." |
| `knowledge_entries_search` | `entries_search` | "Search accessible published Wiki and knowledge entries." |
| `entity_relations_search` | `relations_search` | "Search upstream entities and relations. **Returned paths may be incomplete; absence does not disprove a relation.**" |

三条 description 都追加同一句：「Within this turn's scope. Cite only supplied `[citation:Title]` + `#knowledge-source-<32 位十六进制 ID>` links exactly; never invent source locators or relations.」

执行序（`execute_knowledge_search`）：

1. 空 query → `"Error: query must not be empty."`；
2. `context[KNOWLEDGE_SCOPE_RUNTIME_KEY]`（即 `"__knowledge_scope_execution"`）取执行态 scope；`mode == "disabled"` → `"Error: Knowledge search is disabled for this turn."`；
3. `app_config` 优先用 runtime context 里的实例，否则 `get_app_config()`；`resolve_run_extensions(context)` 拿到本轮生效的扩展（**逐轮解析**，不是全局）；
4. 有 scope 时先用 `get_knowledge_capabilities()` 校验**本轮配置整体**能否执行这个收窄；
5. `resolve_knowledge_provider(..., tool_name=...)` → `search_provider(...)`；
6. 三种错误出口，全部脱敏：
   - `PermissionError` → `"Error: The selected knowledge scope is not accessible."`
   - 其它 `Exception` → 只记 `type(exc).__name__`，返回 `"Error: Knowledge retrieval failed; check the provider and selected scope."`
   - 注释：「Provider exceptions may contain credentials or resource identifiers.」

**执行者身份**由 `_execution_agent_name(context, config)`（`tools.py:22-34`）解析：`context["is_subagent"] is True` → 用 `agent_id`；否则 `context["agent_name"]`，再退 `configurable.agent_name`，最后 `"lead_agent"`。差别在**子 agent 用自己配置的名字，而不是父 assistant 的名字**——这一条直接决定了 WeKnora 的 `agent_names` 绑定是否对子 agent 生效。

---

## 七、作用域：`deerflow/knowledge_scope.py`（194 行）

版本化的「这一轮能查哪些知识」快照，三个 mode：

| mode | 允许的字段 | 语义 |
|------|-----------|------|
| `all` | 无 | 全开（= provider 自己的可见范围） |
| `selected` | `dataset_ids`、`document_filters`、`display` | 收窄；**至少一个 dataset ID** |
| `disabled` | 无 | 本轮关闭知识检索 |

上限（`knowledge_scope.py:14-22`）：`MAX_KNOWLEDGE_SCOPE_BYTES = 64KiB`、`MAX_DATASET_IDS = 100`、`MAX_DOCUMENT_IDS = 1000`、`MAX_ID_CODEPOINTS = 256`、`MAX_DISPLAY_DATASETS = 20`、`MAX_DISPLAY_DOCUMENTS = 50`。

校验链（`KnowledgeScope._validate_and_normalize`）：
- `all`/`disabled` **不得**携带任何选择或 display，违者 `ValueError`；
- `selected` 必须有 dataset IDs；每个 dataset 至多一个 document filter；filter 的 `dataset_id` 必须在选中集合内；文档 ID 总数 ≤ 1000；
- display 只能引用已选中的 dataset / 已 filter 的文档，且 display 文档数 ≤ 50；
- 最后按 `_canonical_dict()` 序列化（`ensure_ascii=False, sort_keys=True, separators=(",", ":")`）检查 ≤ 64KiB。

三个对外函数：
- `canonicalize_knowledge_scope(value)` → 稳定 JSON 安全表示（含 display）；
- `execution_scope(value)`（`:179`）→ **剥掉 display 后的执行态**，「Runtime consumers must use execution_scope」——display 块是不可信的历史渲染数据；
- `strip_message_knowledge_scope(message)`（`:186`）→ 复制一条 LangChain 消息并剥掉 `knowledge_scope` 与 `__knowledge_scope_execution` 两个 additional_kwargs 键。

`KnowledgeRequestContext.scope` 收到的永远是 `execution_scope()` 的产物（`providers.py:174`、`tools.py:50`、`provider.py:186`），所以 provider 那一侧根本没有 display 可读。

---

## 八、注册口与"第三种工具"的配置形状

`extensions/registry.py:154-164`：

```python
def knowledge_provider(self, name: str, provider: Any) -> bool:
    if not isinstance(name, str) or not re.fullmatch(r"[a-z][a-z0-9_-]{0,63}", name) or name in {"ragflow", "lightrag"}:
        raise ValueError("Invalid or reserved knowledge provider name")
    validate_provider(provider)
    if any(existing == name for _, (existing, _) in self._knowledge_providers):
        raise ValueError("Duplicate knowledge provider name")
```

三条限制：名字文法 `[a-z][a-z0-9_-]{0,63}`、**`ragflow` 与 `lightrag` 是保留名**（它们是内置兼容适配器，不允许被扩展顶替）、同名不可重复注册。注册即校验（`validate_provider`），所以一个 capability 与实现不一致的扩展在 install 期就失败，不会半注册。

### tool 配置如何绑定 provider

通用工具靠 `tools:` 条目上的 **`provider:` 额外字段**选人（`ToolConfig.extra="allow"`）：

```yaml
tool_groups:
  - name: knowledge
tools:
  - name: knowledge_search
    group: knowledge
    use: deerflow.knowledge.tools:knowledge_search_tool
    provider: weknora          # ← 指向 registry 注册名
```

`_registered_provider()`（`providers.py:127-136`）只认 `use` 命中 `GENERIC_KNOWLEDGE_TOOLS` 的条目，再按 `model_extra["provider"]` 在 `get_loaded_extensions().knowledge_providers` 里找同名的那个。`_configured_tools()`（`providers.py:81-101`）则同时接受三种 `use`：两个 legacy 路径 + 通用路径，并按工具名（`knowledge_search` / `knowledge_entries_search` / `entity_relations_search`）归类。

`resolve_knowledge_provider()`（`providers.py:139-149`）目前**只特判 ragflow**（`RAGFlowKnowledgeProvider(app_config)`，因为它的配置来自 `knowledge_search` 工具自身的 extra），其余全部走注册表；找不到 → `LookupError("Knowledge provider is not configured")`。LightRAG 没有 provider.py，它的 legacy 工具直接自己跑检索（见 [08-lightrag.md](08-lightrag.md)）。

---

## 九、RAGFlow 兼容适配器：`community/ragflow/provider.py`（96 行）

`RAGFlowKnowledgeProvider`（`provider.py:19-96`）是「老工具能力 + 新契约」的桥：

- `capabilities = CAPABILITIES`（`formatting.py:12`，含 `catalog`/`documents`/两个 filter）；
- `__init__(app_config)` **不做 I/O**（注释：「Construction performs no I/O; credentials remain in the adapter.」），配置解析失败 → `LookupError("Knowledge retrieval is not configured")`；
- `search` / `search_scoped` 都落到 `_search(query, scope)`：scope 先过 `validate_scope_capabilities`，`selected` 时把 `dataset_ids` 传给 `resolve_ragflow_datasets`，再 `_validate_document_filters` → `_group_scoped_datasets` → `_retrieve_dataset_groups`（与 legacy 工具复用同一批内部函数）；
- **范围不可用一律 `PermissionError("Knowledge scope is unavailable")`**——不区分「不存在」和「无权限」，避免把资源存在性泄漏给模型；
- 结果 `normalize_retrieval_result(redact_strings(result, key), dataset_names_by_id=...)`，**不带 locator**（不打 url/page）；
- `catalog()`：`selectable = bool(embedding_model) and chunk_count != 0`；
- `documents()`：`selectable = run == "DONE" and chunk_count > 0`；配了 `datasets` 白名单而请求的 `dataset_id` 不在其中 → `FileNotFoundError("Knowledge base not found")`。

**两条输出路径**（legacy 工具 `knowledge_search()`，`tools.py:512-591`）：传了 `_source_artifact`（新工具入口）就走 `format_retrieval_sources`（旧 `#knowledge-` 命名空间）；artifact 为空时退回 `normalize_retrieval_result` + 共享 `format_result`（新 `#knowledge-source-` 命名空间）。不传 artifact（直接调用）就走 `format_retrieval_result` 纯文本。

---

## 十、WeKnora：可安装扩展 provider

代码不在 core 里，在 `examples/deerflow-extension-weknora/`（**只读示例目录**，通过 `make extension-install SOURCE=...` 安装）：

```
examples/deerflow-extension-weknora/
├── deerflow_extension_weknora/
│   ├── __init__.py   # 13 行：@extension(api="0.2.7", name="weknora") → registry.knowledge_provider("weknora", WeKnoraProvider(dict(config)))
│   ├── config.py     # 62 行：Settings / Space / native_id()
│   └── provider.py   # 294 行：WeKnoraProvider
├── README.md         # 安装、配置、授权模型、验证步骤
└── VALIDATION.md     # 一个真实 Ollama bge-m3 部署的验证记录
```

上游依据：API 映射对着 **WeKnora v0.8.3**（commit `3e22822c1d2397be730c458c7539d0eb8c113a24`）核对，其它版本需重新验证。

### 配置形状（`config.py`）

```yaml
plugins:
  - use: deerflow_extension_weknora:install
    enabled: true
    required: true
    config:
      timeout: 30          # 1-120
      match_count: 8       # 1-100，strict int
      spaces:              # 1-20 条，(base_url, tenant_id) 不得重复
        - base_url: https://weknora.example.com
          tenant_id: "42"                # ^[1-9][0-9]{0,19}$
          api_key_env: WEKNORA_API_KEY   # 只写环境变量名，不写 key
          user_ids: ["<deerflow-user-id>"]     # 必填，精确匹配
          agent_names: ["lead_agent", "researcher"]   # 可选，精确匹配执行者
          knowledge_base_ids: ["..."]                 # 可选，≤100；空列表被拒（≠全开）
```

`Space` 的校验值得抄：`base_url` 不得带 username/password/query/fragment；身份绑定必须**非空且无首尾空格**（「nonblank exact host identities」）；`knowledge_base_ids` 逐项过 `native_id()`（`[A-Za-z0-9_-]{1,256}`，先挡掉路径语法再拼 URL）。

### 连接与授权（`provider.py`）

- `_bindings(context)`（`:84-95`）：按 `context.user_id ∈ space.user_ids` 且（`agent_names is None` 或 `context.agent_name ∈ agent_names`）选 binding；每个 binding 从 `os.getenv(api_key_env)` 现读 key，缺 key 或含控制字符 → `RuntimeError`；**一个都没匹配上 → `PermissionError("No WeKnora space is bound to this user and executing agent")`**（fail-closed，没有默认/通配绑定）。
- `_request()`（`:97-127`）：**每次请求新建 `httpx.AsyncClient`**（「prevents tenant/credential mutation across users and event loops」），`follow_redirects=False`（绝不带着特权凭证跟随跳转），`X-API-Key` + `X-Tenant-ID` 头，`httpx.AsyncClient` 本身经 `asyncio.to_thread` 构造（SSL trust 加载不在事件循环上）；401/403 → `PermissionError`，404 → `FileNotFoundError`，非 200 → `RuntimeError("WeKnora request failed")`；**响应体上限 4 MiB**（`_MAX_RESPONSE_BYTES`）；`httpx.HTTPError | ValueError` 统一转成 `"WeKnora request failed or returned invalid JSON"`，`from None` 丢掉原始异常——「No raw body, URL, request headers or credential-bearing cause.」
- 信封：默认要求 `payload["success"] is True` 且有 `data`；Wiki 检索走 `envelope=False`（它不是统一信封）。
- **ID 空间**：`_Dataset.id = "wk1_" + sha256(json([base_url.rstrip("/"), tenant_id, native_id]))`（68 字符）。注释点明设计约束：「Recomputed from authorized catalogs; no reverse-map database, truncation, key material or ambiguous concatenation. **Key rotation preserves IDs.**」——换 API key 不会让用户已选中的 dataset 失效，只有换 endpoint/tenant 才会。

### 检索（`search_scoped`，`:183-253`）

1. `search()` 无条件版本**直接拒**：`raise PermissionError("WeKnora retrieval requires a trusted KnowledgeRequestContext")`——WeKnora 必须在有上下文时才能检索；
2. scope 缺省视为 `{"mode": "all"}`；`disabled` 或空 query → `ValueError`；
3. **先把所有受约束资源验完再搜**：`selected` 里每个 dataset 的每个 document 都走 `_document()`（详情端点复核 `id`、`knowledge_base_id` 从属关系、`_searchable` 状态），任何一个不过 → `PermissionError`，**没有部分成功、没有退化成不带 filter 的重试**；
4. 逐个 dataset 发 `POST /api/v1/knowledge-bases/{native_id}/hybrid-search`，body `{"query_text", "match_count", "skip_context_enrichment": True}`，若该 dataset 有文档 filter 再加 `knowledge_ids`；
   - 为什么用 KB 绑定的端点而不是全局 `/knowledge-search`：注释写得很清楚——KB 绑定端点认可受限 key 并能与文档 ID 求交；全局端点对受限 key 会拒绝 `knowledge_ids`，而在那里混用 base/document 目标是**并集**语义，会悄悄放宽检索范围；
5. 每条结果再用 `_document()` 复核（`SearchResult` 不带 `knowledge_base_id`，所以即使不过滤也要验从属）；filter 之外的证据 → `PermissionError`；
6. `title` 取 `knowledge_title` / `knowledge_filename` / 详情 `title|file_name`，空则 **source 为 None**（不编造标题）；`content` 上限 100_000 字符；**不打 url/page**（v0.8.3 没有可信页码或公开文档 URL）；`score` 只接受有限 `float | int`；
7. 全局 ≤100 hits。

### 条目检索（`entries_search`，`:255-294`）

- 只看 `wiki_enabled`（`base["capabilities"]["wiki"] is True`）的 KB；
- 请求 `GET /api/v1/knowledgebase/{native_id}/wiki/search?q=&limit=`，`envelope=False`；
- **空结果的 ≤4 关键词重试**：首轮用整句 query，若成功但 0 条，就把它 split 后（≥2 字符、去重、排除整句本身）的术语逐个再问，最多 4 个——注释解释了原因：「Wiki search is lexical, unlike document hybrid search. A model's space-separated keyword combination can miss a matching title.」且**只在同一个 KB 内重试**，不放宽范围；
- 只要 `status == "published"` 的页；按 `(title, content)` 去重；KB 不匹配 → `PermissionError`；
- `document_filters` 非空 → `ValueError("Wiki retrieval does not support document filters")`（能力表里本来就只有 `entries_dataset_filter`）。

`relations_search` **完全没有实现**，也不声明——所以 `entity_relations_search` 在 WeKnora 栈上会被 `get_knowledge_capabilities()` 判为配置非法（provider 未声明该 operation → `ValueError`，日志里能看到具体 tool/provider/operation）。

---

## 十一、这套抽象解决的四个老问题

| 问题 | 2.1.0 | 2.2.0 |
|------|-------|-------|
| 每种知识库都要写一个工具 | Ragflow/LightRAG 各一版 tools.py，输出格式各自演化 | 一个通用工具 + `provider:` 字段；格式/预算/引用全在 core |
| 引用 ID 不稳定 | 每次调用生成 `uuid4` 前缀（`format_retrieval_sources`）或本地序号 | `sha256(证据内容)[:32]`，跨调用、跨预算、跨重放稳定 |
| 选择的知识库可能被静默忽略 | 工具自己解释自己的 scope | `selected` + 无 `search_scoped` → 硬报错；收窄失败不退化为全库搜 |
| 子 agent 拿到的证据无法回溯 | 只有文本 | artifact 携带版本化来源，`forward_sources` 只转发正文引用过的那些 |

---

> **See also:** [07-ragflow.md](07-ragflow.md) · [08-lightrag.md](08-lightrag.md) · [05-how-to-add-provider.md](05-how-to-add-provider.md) · [knowledge contract source](../../../backend/packages/harness/deerflow/knowledge/contract.py) · [knowledge scope source](../../../backend/packages/harness/deerflow/knowledge_scope.py) · [WeKnora 扩展 README](../../../examples/deerflow-extension-weknora/README.md)
