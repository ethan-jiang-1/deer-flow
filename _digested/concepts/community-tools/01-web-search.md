---
title: "Web Search：9 种 Provider 对比"
description: "所有 9 个 search provider 都暴露同名函数 `web_search_tool`，装饰为 `@tool("web_search", parse_docstring=True)`。都接受 `query: str` 参数，返回 "
topics: [tools, community, external-integration]
---

# Web Search：9 种 Provider 对比

所有 9 个 search provider 都暴露同名函数 `web_search_tool`，装饰为 `@tool("web_search", parse_docstring=True)`。都接受 `query: str` 参数，返回 JSON string。差异在可选参数、认证方式和返回格式。

## Provider 对比

### DuckDuckGo Search（默认）

- **文件：** `community/ddg_search/tools.py:56`
- **认证：** 无（使用 `ddgs` 库，免费）
- **参数：** `query: str, max_results: int = 5`
- **返回格式：** `{query, total_results, results: [{title, url, content}]}`
- **配置：** `config.tool_config("web_search").model_extra["max_results"]`
- **延迟加载：** `ddgs` 库在 `_search_text()` 内延迟导入，避免非搜索场景的启动开销

### Serper（Google Search）

- **文件：** `community/serper/tools.py:32`
- **认证：** `SERPER_API_KEY` env var，或 config `model_extra["api_key"]`
- **HTTP：** 同步 `httpx.Client.post()` → `https://google.serper.dev/search`
- **Header：** `X-API-KEY: <key>`（非标准 Bearer）
- **返回格式：** 同 DDG — `{query, total_results, results: [{title, url, content}]}`（从 Serper 的 `link`→`url`, `snippet`→`content` 映射）
- **优先级：** config `api_key` > 环境变量 `SERPER_API_KEY`

### Serply 🆕

- **文件：** `community/serply/tools.py`（#5023）
- **认证：** config `model_extra["api_key"]` 或 env `SERPLY_API_KEY`（config 优先）
- **HTTP：** 同步 `httpx.Client.get()` → `https://api.serply.io/v1/{path}/`，header `X-Api-Key` + `User-Agent: deerflow`
- **一个 key 三个垂直**：`vertical` 配置切换端点与响应键 — `search`（默认，`results`）/ `news`（`entries`）/ `scholar`（`articles`），即 Google SERP、Google News、Google Scholar
- **返回格式：** `{query, total_results, results: [{title, url, content}]}` 包装对象；news 额外带 `published`/`source`，scholar 额外带 `authors`/`cited_by`/`pdf_url`（summary HTML 会被 strip 标签 + unescape 成纯文本）
- **参数：** `query: str, max_results: int = 5`（cap 100）；额外配置 `vertical`、`gl`、`hl`（原样透传）
- **注意：** news feed 服务端忽略 `num`，客户端再截一次 `[:max_results]`

### Tencent Cloud WSA 🆕

- **文件：** `community/tencent_wsa/tools.py`（#5057）
- **认证：** config `model_extra["api_key"]` 或 env `TENCENTCLOUD_WSA_APIKEY`（config 优先）→ `Authorization: Bearer`。**不能用**腾讯云 SecretId/SecretKey，要 WSA 控制台的服务 API key
- **HTTP：** 同步 `httpx.Client.post()` → `https://api.wsa.cloud.tencent.com/SearchPro`，响应走 `{Response: {Pages: [...]}}` envelope（含 `RequestId`，会透传到输出和错误里）
- **返回格式：** `{query, total_results, results: [{title, url, snippet, date?, site?, score?}], request_id?}`；`Pages` 官方 schema 是 JSON 字符串数组，代码同时兼容对象数组
- **参数：** `query: str, max_results: int = 5`（1–50）；额外配置 `mode`（0=web / 1=VR / 2=mixed，**缺省不传**——腾讯默认自然网页结果，不会隐式请求 VR/mixed）
- **Cnt 请求技巧：** 腾讯默认响应 10 条；`max_results > 10` 时按 10 的倍数向上取整请求 `Cnt`（该选项需要支持 Cnt 的腾讯套餐），≤10 则干脆不传
- **注意：** 不支持 time_range（无原生时间过滤）

### Sofya 🆕

- **文件：** `community/sofya/tools.py`（#5239）
- **认证：** config `model_extra["api_key"]` 或 env `SOFYA_API_KEY`（config 优先）→ `Authorization: Bearer`；POST `https://sofya.co/v1/search`
- **最大特点：** 返回**结果页面的内容**而非仅摘要（`search_depth: basic` 读页面 / `snippets` 只给摘要）；每个 agent 也能传 `time_range`（day/week/month/year → Sofya 的 `freshness` 参数，走共享 `SearchTimeRange` 契约）
- **返回格式：** `{query, total_results, results: [{title, url, content}]}` 包装对象；`content` = 页面内容（读取成功）或搜索摘要（fallback），按 `contents_max_characters`（默认 2000，0 = 不截断）截断，避免正常搜索被写到磁盘
- **参数：** `query: str, max_results: int | None = None`（cap 20；调用方显式传参优先于 config——其它 provider 多是 config 覆盖参数）
- **同时提供 `web_fetch`**（见 [02-web-fetch.md](02-web-fetch.md)）

### Tavily

- **文件：** `community/tavily/tools.py:18`
- **认证：** config `tool_config("web_search").model_extra["api_key"]`，传递给 `TavilyClient(api_key=api_key)`
- **参数：** `query: str`（`max_results` 通过 config 控制，不作为函数参数）
- **返回格式：** `[{title, url, snippet}]` — **裸数组**，不是 `{query, total_results, results}` 包装
- **注意：** 没有 env var fallback；Tavily 同时提供 `web_fetch_tool`

### InfoQuest

- **文件：** `community/infoquest/tools.py:46`
- **认证：** `INFOQUEST_API_KEY` env var → `Authorization: Bearer <key>`
- **架构：** 通过 `InfoQuestClient` 类调用（`infoquest_client.py`）
- **端点：** `POST https://search.infoquest.bytepluses.com`
- **返回格式：** `[{type: "page"|"news", title, desc, snippet, url}]`
- **清洗：** `clean_results()` 提取 organic results + top stories
- **额外配置：** `search_time_range`（int，-1 禁用）
- **注意：** 同时提供 search + fetch + image search — 字节跳动内部生态

### Exa

- **文件：** `community/exa/tools.py:17`
- **认证：** config `tool_config("web_search").model_extra["api_key"]` → `Exa(api_key=api_key)`
- **参数：** `query: str`（所有配置通过 model_extra）
- **返回格式：** `[{title, url, snippet}]` — 裸数组，`snippet` = `"\n".join(result.highlights)`
- **额外配置：** `max_results`（默认 5）、`search_type`（默认 "auto"）、`contents_max_characters`（默认 1000）
- **特点：** 语义搜索，content highlight 内建

### Firecrawl

- **文件：** `community/firecrawl/tools.py:17`
- **认证：** config `model_extra["api_key"]` → `FirecrawlApp(api_key=api_key)`
- **参数：** `query: str`
- **返回格式：** `[{title, url, snippet}]` — `snippet` = `item.description`
- **容错：** 使用 `getattr()` with empty string fallback — 字段缺失不崩溃
- **额外配置：** `max_results`（默认 5），以 `limit` 参数传给 `client.search()`
- **self-host 🆕：** 配置 `base_url`（如 `http://<host>:3002`）即指向自建 Firecrawl 实例，可完全免云 API key（`FirecrawlApp(api_url=...)`）

## 原生 recency filters 🆕

同步 #6（#5099）抽出共享契约 `community/search_time_range.py`：

```python
type SearchTimeRange = Literal["day", "week", "month", "year"]
```

支持 time_range 参数的 provider 及各自映射：

| Provider | 参数 | 服务端映射 |
|----------|------|-----------|
| DuckDuckGo | `time_range` | `DDGS_TIMELIMIT_BY_TIME_RANGE` → `d/w/m/y`（且会自动选用支持 timelimit 的 backend） |
| Brave | `time_range` | `BRAVE_FRESHNESS_BY_TIME_RANGE` → `pd/pw/pm/py` |
| SearXNG | `time_range` | 透传 `time_range` |
| Tavily | `time_range` | 透传 `time_range` |
| Sofya 🆕 | `time_range` | → `freshness` |

Serply / Tencent WSA / Firecrawl 等不支持。docstring 统一措辞："Use only when the request requires recent results"——让模型只在需要新近性时才传。InfoQuest 的 `search_time_range: 10`（int 分钟数配置项）是更早的独立机制，与此契约无关。

## 返回格式的不一致性

这是 9 个 provider 之间最大的差异——调用方需要注意：

| 格式 | Provider |
|------|----------|
| `{query, total_results, results: [{title, url, content}]}` | DDG, Serper, Serply, Sofya |
| `[{title, url, snippet}]` | Tavily, Exa, Firecrawl |
| `[{type, title, desc, snippet, url}]` | InfoQuest |

DDG/Serper/Serply/Sofya 返回包装对象（含 metadata），其余 provider 返回裸数组。字段名也不统一：DDG/Serper/Serply/Sofya 用 `content`，Tavily/Exa/Firecrawl 用 `snippet`，InfoQuest 两者都有，Tencent WSA 用 `snippet` 且外层带 `request_id`。

## web_search 只能启用一个的原因

`get_available_tools()` 做**按名去重**——config.yaml 中先出现的 `name: web_search` 胜出，后续同名 tool 被丢弃。所有 provider 都注册为 `name="web_search"`，所以只能激活一个。要换 provider：注释掉当前的，取消注释目标 provider。

## 认证方式对比

| Provider | 密钥来源 | 传递方式 |
|----------|---------|---------|
| DDG | 无 | — |
| Serper | env `SERPER_API_KEY` 或 config `api_key` | `X-API-KEY` header |
| Serply 🆕 | config `api_key` 或 env `SERPLY_API_KEY` | `X-Api-Key` header |
| Tencent WSA 🆕 | config `api_key` 或 env `TENCENTCLOUD_WSA_APIKEY` | `Authorization: Bearer` |
| Sofya 🆕 | config `api_key` 或 env `SOFYA_API_KEY` | `Authorization: Bearer` |
| Tavily | config `api_key` | SDK constructor |
| InfoQuest | env `INFOQUEST_API_KEY` | `Authorization: Bearer` |
| Exa | config `api_key` | SDK constructor |
| Firecrawl | config `api_key`（self-host 可免） | SDK constructor（`api_url` 指向自建实例） |

🆕 三个新 provider 都采用 **config 优先、env fallback** 的模式，且 key 缺失时首次调用 warn 一次（`_api_key_warned` 集合）后返回结构化 JSON 错误。Tavily/Exa 仍只从 config 读取；InfoQuest 只从环境变量读取。Firecrawl 走 self-host `base_url` 时可以完全不需要 key。
