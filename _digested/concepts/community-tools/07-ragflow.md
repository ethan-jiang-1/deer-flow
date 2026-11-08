---
title: "RAGFlow — 只读知识库检索"
description: "把 RAGFlow 当外部 RAG 知识库：operator 配置 dataset 白名单，agent 通过唯一的只读 knowledge_search 工具检索，结果格式化成带引用编号的紧凑文本。与 web_search 和内置 memory 检索都不同。"
topics: [tools, community, knowledge, rag, ragflow, retrieval]
---

# RAGFlow — 只读知识库检索

> 同步 #5（上游 `431892e1`，#4955）新增。RAGFlow 是一个开源的 RAG（检索增强生成）知识库引擎；DeerFlow 把它当作**外部的、operator 预先建好的领域知识库**来用，只暴露一个**只读**的 `knowledge_search` 工具。DeerFlow 不持久化任何 dataset/document 元数据副本——RAGFlow 是唯一事实来源，配置的 API key 是 tenant 级作用域。

## 定位

```
community/ragflow/
├── __init__.py    # 空（无包级导出，靠 tools.py 的模块属性被 reflection 解析）
├── client.py      # ~187 行：极简异步 httpx client + 错误层次 + 分页/检索
├── formatting.py  # ~96 行：检索结果 → 带引用编号的紧凑文本
└── tools.py       # ~397 行：唯一的只读 tool + 配置校验 + dataset 解析/分组/并行检索
```

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

`format_retrieval_result()`（`formatting.py:34-96`）把 RAGFlow 原始 retrieval 响应转成**带引用编号的紧凑文本**：

- **已验证版本**：针对 RAGFlow v0.26.4 和 v0.27.0——REST 检索端点在返回前会归一化 chunk 字段（如 `kb_id` → `dataset_id`），只消费这些公开响应字段名。
- **chunks**：逐个输出 `[N] {dataset_name} / {document_name}  (score {similarity:.2f})\n{content}`；dataset ID 通过 `dataset_names_by_id` 映射回 operator 配置的名字（模型永远看不到原始 ID）。
- **doc_aggs**：接受 list 或 dict（`_document_aggregates`），`doc_id → doc_name` 映射用于补全 chunk 缺 `document_keyword` 的文档名；末尾追加 `Matched documents: name (N chunks)` 汇总。
- **截断**：每 chunk `max_chars_per_chunk`（默认 800）、整篇 `max_total_chars`（默认 8000），超限加 `… (response truncated)`；`_score()` 只在值是数字时保留相似度（bool/非数字 → None，不显示 score）。
- 空结果 → `"No relevant content found."`。

## tools：唯一的只读工具 + 配置

只暴露**一个** tool：`knowledge_search`（`tools.py:392-397`），`StructuredTool.from_function` 包装 async coroutine，`name="knowledge_search"`，`parse_docstring=True`。它**只读**——dataset 创建、上传、解析、删除都留在 RAGFlow 里，不做成 agent tool 也不做 DeerFlow API。

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

配置读取路径（`_settings_or_error`，tools.py:103-117）：`get_app_config().get_tool_config("knowledge_search")` → 未配置返回 `"Error: knowledge_search is not configured..."`；校验失败 → 通用错误；`api_key` 缺失 → 提示优先用 `$RAGFLOW_API_KEY`（`_warned` 集合保证只 warn 一次）。

## 检索执行流程

```
knowledge_search(query)
  → _settings_or_error()                # 读 tool 配置 + 校验 + api_key 必填
  → _build_client(settings)             # base_url + api_key + timeout
  → _resolve_datasets(client, settings)
      ├─ datasets is None  → list_datasets() 全量分页，去重后按 id 收进 resolved
      └─ datasets 显式     → 逐条 list_datasets(dataset_id=id) 校验
                            缺失/不可访问 → "The Nth entry ... was not found or is inaccessible"
  → _group_searchable_datasets()        # 按 embedding_model 分组；chunk_count==0 跳过
  → _retrieve_dataset_groups()          # Semaphore(4) 并发；每组一次 retrieve()
      → _merge_group_results()          # 按 rank 交错合并，page_size 全局截断
  → format_retrieval_result()           # 带引用编号紧凑文本
  → _redact_api_key()                   # 成功路径必做 API key 脱敏
```

关键机制（`tools.py`）：

1. **dataset 作用域**：`datasets` 省略 → 每次搜索分页枚举 tenant 可见的 dataset 目录；显式白名单 → 搜索时用 ID 过滤请求逐条校验（配置加载时**不**校验存在性）。缺失条目用**序数**（"The 2nd entry of `knowledge_search.datasets`..."，`_ordinal`）报错，指向 `config.yaml`。
2. **混合 embedding 分组**：`_group_searchable_datasets` 把剩余 dataset 按**精确的 embedding_model 标识**分组（`chunk_count==0` 的空 dataset 跳过；空 dataset 且无 embedding 元数据也跳过并 server warn）。每组各自发一次带非空 `dataset_ids` 的检索。
3. **跨组分数不可比**：不同 embedding 空间的 raw similarity 不做全局校准，所以 `_merge_group_results` **保留各组 RAGFlow 排名、按相等 rank 交错合并**，多组搜索时**隐藏 score 标签**，`page_size` 作为全局 chunk 上限。任何一组失败 → 整个 tool 调用失败（不静默丢配置范围）。
4. **并发**：`asyncio.Semaphore(_MAX_PARALLEL_RETRIEVAL_GROUPS=4)`，`asyncio.gather(..., return_exceptions=True)` 后统一 re-raise。
5. **脱敏边界**：API key 在成功路径也强制脱敏；UUID 格式的 dataset ID 只在**错误路径**脱敏（`_redact_error`，`_RAGFLOW_UUID_PATTERN`）——成功路径保留合法 checksum / trace ID 不被误替换。
6. **tool 描述**（`_tool_description`）："Search the operator-approved RAGFlow datasets and return compact, citation-numbered source chunks. Dataset IDs are never shown to the model."——明确声明 operator 白名单 + ID 不进模型。

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

| 机制 | 位置 |
|------|------|
| HTTP client + 错误层次 | `client.py:RAGFlowClient` / `_request` / `RAGFlow*Error` |
| dataset 分页 / ID 过滤 | `client.py:list_datasets`（`ids` 参数技巧） |
| 检索 | `client.py:retrieve`（POST `/retrieval`） |
| 结果格式化 | `formatting.py:format_retrieval_result` / `_truncate` / `_score` |
| 配置校验 | `tools.py:_RAGFlowRetrievalSettings` / `_settings_or_error` |
| dataset 解析/分组 | `tools.py:_resolve_datasets` / `_group_searchable_datasets` |
| 并行检索 + 合并 | `tools.py:_retrieve_dataset_groups` / `_merge_group_results` |
| 脱敏 | `tools.py:_redact_error` / `_RAGFLOW_UUID_PATTERN` |
| tool 定义 | `tools.py:knowledge_search_tool`（`StructuredTool.from_function`） |
| 配置示例 | `config.example.yaml`（tools 段 RAGFlow 注释块） |
| 测试 | `tests/test_ragflow_client.py`（257 行）/ `tests/test_ragflow_tools.py`（747 行） |

## 相关

- 装配 / 集成矩阵 / 选型 → [`00-overview.md`](00-overview.md)
- 如何添加新 provider（同目录约定）→ [`05-how-to-add-provider.md`](05-how-to-add-provider.md)
- 内置 memory 检索 → [`../memory/extract-queue-persist-pipeline.md`](../memory/extract-queue-persist-pipeline.md)
- 只读 web_fetch/web_capture 对比 → [`02-web-fetch.md`](02-web-fetch.md)
