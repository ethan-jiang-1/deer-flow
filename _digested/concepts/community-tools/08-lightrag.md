---
title: "LightRAG — 只读知识库检索（knowledge_search 的第二 provider）"
description: "LightRAG 是 knowledge_search 工具的第二 provider（与 RAGFlow 二选一）：operator 配置自建 LightRAG 服务地址，agent 通过同一个只读 knowledge_search 工具检索，结果格式化成与 RAGFlow 共享形状的带引用编号紧凑文本。"
topics: [tools, community, knowledge, rag, lightrag, retrieval]
---

# LightRAG — 只读知识库检索（knowledge_search 的第二 provider）

> 同步 #6（上游 `431892e1..769589e8`，#5209）新增。与 [07-ragflow.md](07-ragflow.md) 的 RAGFlow 定位相同：把**外部、operator 预先建好的私有知识库**变成一个**只读**的 `knowledge_search` 工具；DeerFlow 不持久化任何索引/文档元数据副本。

## 与 RAGFlow 的关系：同一个工具，两个 provider

`knowledge_search` 是 DeerFlow 侧固定的工具名；RAGFlow 和 LightRAG 都是它的实现，通过 `use:` 指向不同模块切换：

| 维度 | RAGFlow | LightRAG |
|------|---------|----------|
| use 路径 | `deerflow.community.ragflow.tools:knowledge_search_tool` | `deerflow.community.lightrag.tools:knowledge_search_tool` |
| 检索作用域 | tenant 内多个 dataset，operator 用 `datasets` 白名单圈定 | 部署的**单一索引 workspace**（LightRAG 无 dataset 目录，不做 binding 解析） |
| 检索端点 | `POST {base_url}/api/v1/retrieval` | `POST {base_url}/query/data`（**无 LLM 生成**，纯数据检索） |
| 检索策略 | 相似度阈值 + 向量权重 + top_k | `mode`: naive / local / global / hybrid / **mix**（默认，随 LightRAG 自身默认） |
| 认证 | `Authorization: Bearer`（**必填**） | `X-API-Key` header（**可选**——无鉴权的部署可省略） |
| 要求版本 | 针对 v0.26.4 / v0.27.0 校验 | **v1.4.9+**（响应 envelope 和引用字段从 v1.4.9 起） |
| 额外依赖 | 纯 httpx | 纯 httpx |

**二选一**：由于 tool 装配**按名去重、先到先得**，config.yaml 的 tools 列表里 `name: knowledge_search` 出现两次时只有第一条生效——只配置一个，且把它放在想要的位置。

## 结构

```
community/lightrag/
├── __init__.py    # 空
├── client.py      # ~170 行：极简异步 httpx client + 错误层次 + POST /query/data
├── formatting.py  # ~89 行：检索结果 → 带引用编号的紧凑文本
└── tools.py       # ~164 行：只读 tool + Pydantic 配置校验
```

纯 `httpx` 实现，无三方 SDK 依赖（与 RAGFlow 一致，不像 Tenki/E2B 懒加载 SDK）。

## client：连接 / 鉴权 / API

`LightRAGClient`（`client.py`）与 RAGFlowClient 同一设计：**无缓存、无持久状态**，每次调用新开 `httpx.AsyncClient` session。API key（如有）作为 **`X-API-Key`** 请求头发送——这是 LightRAG 文档的唯一 API key 认证形式；所有错误消息先经 `_redact()` 脱敏。

**错误层次**（`client.py`）：

| 异常 | 触发 |
|------|------|
| `LightRAGError` | 基类 |
| `LightRAGAPIError` | 服务端给出了可读失败（`message` / FastAPI `detail`，含 pydantic 校验列表） |
| `LightRAGConnectionError` | 超时（含精确秒数）/ 网络层 `httpx.RequestError` |
| `LightRAGProtocolError` | 非 JSON / 非 object payload / 无可读消息的非 2xx |

**版本探测是显式的**（对 v1.4.9 之前的 LightRAG 很友好）：

- `/query/data` 返回 **404** → `"check base_url or upgrade LightRAG to v1.4.9 or newer"`（区分配错地址和版本太老）
- 响应是 v1.4.8 的扁平 `{entities, relationships, chunks, metadata}`（无 `status: "success"` envelope）→ `"LightRAG server response predates v1.4.9"`
- 只有 v1.4.9+ 的 `status/data` envelope 和带 `reference_id` 引用的 chunk 字段被消费（字段名对照过 LightRAG v1.5.7 源码）

`query_data(query, *, mode, top_k, chunk_top_k=None)` 是唯一方法：`POST /query/data`，body `{query, mode, top_k[, chunk_top_k]}`。该端点**不做 LLM 生成**，恒返回 entities/relationships/chunks/references——正是只读工具想要的形状。`mode` 只接受 `naive/local/global/hybrid/mix`；LightRAG 原生还支持 `bypass`（跳过索引直接让 LLM 回答），**被刻意排除**——那会架空检索工具。

## formatting：结果格式化

`format_retrieval_result()`（`formatting.py`）与 RAGFlow 的同名函数**共享输出形状**：

- chunks 逐个输出 `[N] {file_path}\n{content}`（缺 `file_path` 的 chunk 通过 `references[].reference_id → file_path` 映射补全；仍无则标 `Unknown document`）
- **内部标识符永不出现在输出里**：`chunk_id` 和响应局部的 `reference_id` 完全不进格式化文本，引用一律用 operator 可读的 `file_path` 标注
- **entities 和 relationships 被刻意丢弃**：只保留 mode 已排序好的文档 chunk 文本，保持输出紧凑并维持与 RAGFlow 一致的引用形状
- 末尾追加 `Matched documents: {doc} (N chunks), ...` 汇总
- 截断：每 chunk `max_chars_per_chunk`（默认 800）、整篇 `max_total_chars`（默认 8000），超限加 `… (response truncated)`
- 空结果 → `"No relevant content found."`

## tools：配置

`knowledge_search_tool` = `StructuredTool.from_function(coroutine=...)`，`name="knowledge_search"`，工具描述明确 "Internal identifiers are never shown to the model"。配置从 `get_app_config().get_tool_config("knowledge_search")` 的 `model_extra` 读入，经 `_LightRAGRetrievalSettings` Pydantic 校验（`base_url` 同样禁止携带 username/password）：

```yaml
tool_groups:
  - name: knowledge

tools:
  # 注意：与 RAGFlow 的 knowledge_search 二选一——重名保留第一条
  - name: knowledge_search
    group: knowledge
    use: deerflow.community.lightrag.tools:knowledge_search_tool
    base_url: http://localhost:9621  # Docker: 用 backend 容器可达的 URL
    api_key: $LIGHTRAG_API_KEY       # 仅对无鉴权的可信内网服务器省略
    mode: mix                        # naive / local / global / hybrid / mix（默认 mix）
    timeout: 30
    top_k: 60
    chunk_top_k: 8                   # 可选；省略用服务端默认
    max_chars_per_chunk: 800
    max_total_chars: 8000
```

设置字段与默认值（`_LightRAGRetrievalSettings`）：

| 字段 | 默认 | 约束 |
|------|------|------|
| `base_url` | `http://localhost:9621` | 禁止含 username/password（`_reject_url_userinfo`） |
| `api_key` | `None`（合法） | `SecretStr`；**允许缺失**——LightRAG 可无鉴权运行，空白值视为未配置 |
| `mode` | `mix` | naive / local / global / hybrid / mix（`bypass` 被排除） |
| `timeout` | 30 | (0, 600] |
| `top_k` | 60 | [1, 1000]（对齐服务端 `MAX_QUERY_TOP_K = 1000`，不自造更紧上限） |
| `chunk_top_k` | `None`（服务端默认） | [1, 1000] |
| `max_chars_per_chunk` | 800 | [1, 100000] |
| `max_total_chars` | 8000 | [1, 1000000] |

## 执行流程

```
knowledge_search(query)
  → _settings_or_error()      # 读 tool 配置 + 校验；未配置/校验失败 → 通用错误
  → _build_client(settings)   # base_url + 可选 api_key + timeout
  → client.query_data(...)    # POST /query/data（无 LLM 生成，单一 workspace，无 binding 解析）
  → format_retrieval_result() # 带引用编号紧凑文本（丢弃 entities/relationships）
  → _redact_api_key()         # 成功路径也强制 API key 脱敏
  └─ 异常 → _tool_error()     # APIError/ConnectionError/ProtocolError 各给可读消息，均脱敏
```

与 RAGFlow 相比刻意**简化掉**的部分：无 dataset 目录/白名单、无 embedding 分组并行、无 rank 交错合并——LightRAG 部署只有一个索引 workspace，一次请求即可。

## 源码索引

| 机制 | 位置 |
|------|------|
| HTTP client + 错误层次 + 版本探测 | `client.py:LightRAGClient` / `_request` / `query_data` |
| 结果格式化 + 引用映射 | `formatting.py:format_retrieval_result` / `_reference_file_paths` |
| 配置校验 | `tools.py:_LightRAGRetrievalSettings` / `_settings_or_error` |
| tool 定义 | `tools.py:knowledge_search_tool`（`StructuredTool.from_function`） |
| 配置示例 | `config.example.yaml`（tools 段 LightRAG 注释块） |
| 测试 | `backend/tests/test_lightrag_client.py` / `backend/tests/test_lightrag_tools.py` |

## 相关

- 同一工具的第一 provider（对比表在此）→ [`07-ragflow.md`](07-ragflow.md)
- 装配 / 集成矩阵 / 选型 → [`00-overview.md`](00-overview.md)
- 内置 memory 检索 → [`../memory/extract-queue-persist-pipeline.md`](../memory/extract-queue-persist-pipeline.md)
