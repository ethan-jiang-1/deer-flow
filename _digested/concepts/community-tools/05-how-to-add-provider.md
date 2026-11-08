---
title: "如何添加新的 Tool Provider"
description: '一步一步指南：创建一个新的社区工具 provider，从目录结构到 config.yaml 注册，含认证模式。'
topics: [tools, community, integration, howto]
verified_against: v2.2.0
last_verified: 2026-11-08
---

# 如何添加新的 Tool Provider

## 目录结构

```
deerflow/community/{provider_name}/
├── __init__.py     # 导出 tool 函数
└── tools.py        # @tool 装饰的函数
```

`__init__.py` 是可选的，但推荐——让 `resolve_variable()` 可以直接 import 你的模块。

## 步骤

### 1. 创建 tool 函数

```python
# deerflow/community/my_provider/tools.py
from langchain.tools import tool

@tool("web_search", parse_docstring=True)
def web_search_tool(query: str) -> str:
    """Search the web for the given query.

    Args:
        query: The search query string.

    Returns:
        JSON string with search results.
    """
    # 你的实现
    results = my_api.search(query)
    return json.dumps({"query": query, "results": results})
```

**关键规则**：
- `@tool` 的 name（`"web_search"`）会被用于去重——如果另一个 provider 也注册了 `web_search`，`get_available_tools()` 按名字去重，先匹配的生效
- 返回字符串（LLM 看到 ToolMessage content），可以是 JSON 或纯文本
- 函数签名中的参数就是 LLM function-calling schema

### 2. 读取 API key

两种模式，参考现有 provider 任选其一：

**模式 A：从 config.yaml 读（推荐）**
```python
from deerflow.config import get_app_config

@tool("web_search", parse_docstring=True)
def web_search_tool(query: str) -> str:
    cfg = get_app_config().tool_config("web_search")
    api_key = cfg.model_extra.get("api_key")  # ToolConfig.extra="allow" 透传任意字段
    ...
```

**模式 B：从环境变量读**
```python
import os
api_key = os.getenv("MY_PROVIDER_API_KEY")
```

**模式 C（较新，Serply/Sofya/Tencent WSA 采用）🆕：config 优先、env fallback**
```python
def _get_api_key(tool_name: str) -> str | None:
    config = get_app_config().get_tool_config(tool_name)
    if config is not None:
        api_key = (config.model_extra or {}).get("api_key")
        if isinstance(api_key, str) and api_key.strip():
            return api_key.strip()
    return os.getenv("MY_PROVIDER_API_KEY") or None
```

配合 `_api_key_warned: set[str]` 集合，key 缺失时每个 tool 名只 warn 一次，然后返回结构化 JSON 错误（如 `{"error": "...", "query": ...}`）而不是裸文本——模型能解析失败原因。

### 3. 注册到 config.yaml

```yaml
tools:
  # 注释掉旧的 provider
  # - name: web_search
  #   use: deerflow.community.tavily.tools:web_search_tool

  # 启用新的 provider
  - name: web_search
    group: web
    use: deerflow.community.my_provider.tools:web_search_tool
    api_key: $MY_PROVIDER_API_KEY  # ToolConfig.extra="allow" 透传
    max_results: 10                # 任意额外字段
```

**注意**：一次只能有一个 `web_search` 生效（按名字去重）。注释掉旧的，取消注释新的。

### 4. 验证

```bash
# 启动后检查 tool 是否注册
curl http://localhost:8001/api/models  # 确认 agent 可用

# 用 DeerFlowClient 测试
python -c "
from deerflow.client import DeerFlowClient
c = DeerFlowClient()
print(c.chat('用 web_search 搜索 Python 3.13 新特性'))
"
```

### 2.5 复用两个共享所有者（2.2.0 起应做的）

新增 provider 前先看这两个模块，别复制粘贴它们的逻辑：

**`community/search_max_results.py`** —— `max_results` 的归一化单一所有者

```python
from deerflow.community.search_max_results import coerce_max_results

count = coerce_max_results(
    max_results, provider="My Provider", logger=logger, default=5,
)
```

它替你处理三件容易写错的事：`bool`（`True` 是 `int` 子类，裸 `int()` 会变 1）、非整除 `float`（会被静默截断）、越界 float 的 `OverflowError`。**上限故意不在这里决定**——clamp 策略是 per-provider 的（You.com 在这里拿到值后再自己 `min(..., 100)`）。传自己的 `logger`，别让它用模块级 logger（否则 warning 的 `record.name` 会指向共享模块）。

**`community/provider_credentials.py`** —— 凭证规则的单一所有者

| 函数 | 用途 |
|------|------|
| `resolve_api_key(raw)` | 统一「config 优先」的取值与 `.strip()` / 空串判定 |
| `redact_secret(value, secret)` | 把日志/错误里出现的密钥替换成 `[REDACTED]` |
| `reject_url_userinfo(value)` | 拒绝 `https://user:pass@host`，错误文本 `URL_USERINFO_ERROR = "base_url must not contain username or password information"` |

`jsonify` / `webz` / `youcom` 等 2.2.0 新 provider 都用它；如果你要写自己的「config 优先、env fallback」，请直接调 `resolve_api_key()` 而不是再抄一遍上面的模式 C。

**另外**：结果 URL 一律过 `community/url_safety.py::safe_public_result_url()`（纯字符串、无 DNS），别把 provider 返回的原始 URL 直接交给模型。

## 返回格式

虽然格式自由，但大多数 provider 返回 `{query, total_results, results: [{title, url, snippet}]}`。保持与其他 provider 一致有助于 LLM 在切换 provider 时行为可预测。

## 加一个「知识库 provider」（2.2.0 新路径）🆕

知识库检索不再需要写新工具——core 已经提供了三个通用 `StructuredTool`，provider 只需要实现**契约**并注册。完整契约详见 [09-knowledge-abstraction.md](09-knowledge-abstraction.md)，这里是上手清单。

### 1. 实现契约方法（全部必须是 `async`）

```python
from deerflow.knowledge.contract import KnowledgeCapabilities, RetrievalResult

class MyKnowledgeProvider:
    capabilities = KnowledgeCapabilities(operations=frozenset({"search", "sources"}))

    async def search(self, query: str) -> RetrievalResult: ...
    # 需要 selected 作用域时再加：
    async def search_scoped(self, query: str, *, context) -> RetrievalResult: ...
    # 需要目录/文档列表时再加：
    async def catalog(self, *, context, page, page_size, search): ...
    async def documents(self, dataset_id, *, context, page, page_size, search): ...
```

**声明即校验**：`validate_provider()` 会用 `inspect.iscoroutinefunction` 逐个检查你声明的方法，同步方法直接 `ValueError`；声明了 `entries_dataset_filter` 却没有 `entries_search` 也会 `ValueError("Filter capability requires its retrieval operation")`。

### 2. 在扩展里注册

```python
from deerflow.extensions.registry import registry   # 或对应 API

registry.knowledge_provider("myprov", MyKnowledgeProvider(config))
```

名字必须匹配 `[a-z][a-z0-9_-]{0,63}`，**`ragflow` / `lightrag` 是保留名**，同名重复注册抛 `ValueError`。找不到该注册口时（旧宿主）示例扩展的做法是抛 `RuntimeError("This host does not support knowledge provider registration")`——别静默降级。

### 3. 在 config.yaml 里挂到通用工具

```yaml
tool_groups:
  - name: knowledge
tools:
  - name: knowledge_search
    group: knowledge
    use: deerflow.knowledge.tools:knowledge_search_tool
    provider: myprov
```

三个通用工具名与操作的对应：`knowledge_search` → `search`、`knowledge_entries_search` → `entries_search`、`entity_relations_search` → `relations_search`。

### 4. 三条硬性纪律

1. **`ScopedRetrievalProvider` 收窄失败必须整体失败**——「Never retry a constrained request as an unconstrained search.」不可访问的选择抛 `PermissionError`，绝不退化成全库搜。
2. **证据只放真实的 locator**——标题、URL、页码都是 provider 证据，拿不到就**留空**，不要从 chunk offset 反推页码，也不要编造 URL。
3. **授权在 provider 里做**——`KnowledgeRequestContext` 只是宿主身份与执行约束，不是授权；每个操作都要自己校验。

参考实现：`community/ragflow/provider.py`（96 行，最小兼容适配器）与 `examples/deerflow-extension-weknora/deerflow_extension_weknora/provider.py`（294 行，含多租户绑定、条目检索与分页）。

## 测试

```python
# tests/community/test_my_provider.py
from deerflow.community.my_provider.tools import web_search_tool

def test_web_search_returns_results():
    result = web_search_tool.invoke({"query": "test"})
    assert len(result) > 0

def test_empty_query_handled():
    result = web_search_tool.invoke({"query": ""})
    assert result is not None  # 不应崩溃
```

## 现有 Provider 参考

| Provider | 文件 | 认证 | 返回格式 |
|----------|------|------|---------|
| Tavily | `community/tavily/tools.py` | env var | `{query, results: [...]}` |
| DuckDuckGo | `community/ddg_search/tools.py` | 无 | `{query, total_results, results: [...]}` |
| Serper | `community/serper/tools.py` | env var | `{query, total_results, results: [...]}` |
| Brave | `community/brave/tools.py` | env var | `{query, results: [...]}` |
| SearXNG | `community/searxng/tools.py` | config | `{query, results: [...]}` |
| Serply 🆕 | `community/serply/tools.py` | config 优先 + env fallback | `{query, total_results, results: [...]}` |
| Sofya 🆕 | `community/sofya/tools.py` | config 优先 + env fallback | `{query, total_results, results: [...]}` |
| Tencent WSA 🆕 | `community/tencent_wsa/tools.py` | config 优先 + env fallback | `{query, total_results, results: [...], request_id?}` |
| LightRAG 🆕 | `community/lightrag/tools.py` | `StructuredTool`（async），api_key 可选 | 带引用编号纯文本 |
| Webz 🆕 | `community/webz/tools.py` | config 优先 + env fallback | `{query, returned_results, results: [...]}`（新闻） |
| You.com 🆕 | `community/youcom/tools.py` | 可选 key（缺省走免 key 端点） | `[{title, url, snippet}]` |
| Unbrowse 🆕 | `community/unbrowse/tools.py` | env / config，**MCP JSON-RPC** | `# title\n\nmarkdown` |
| Jsonify 🆕 | `community/jsonify/tools.py` | dataset serve URL 即凭证 | `StructuredTool`（只读 dataset rows） |
| RAGFlow provider 🆕 | `community/ragflow/provider.py` | `RAGFLOW_API_KEY` | `RetrievalResult`（新契约） |
| WeKnora 🆕 | `examples/deerflow-extension-weknora/` | `api_key_env` 指定的 env | `RetrievalResult`（新契约，可安装扩展） |

源码路径：`deerflow/community/{provider}/tools.py`
