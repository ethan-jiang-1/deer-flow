---
title: "Web Search：6 种 Provider 对比"
description: "所有 6 个 search provider 都暴露同名函数 `web_search_tool`，装饰为 `@tool("web_search", parse_docstring=True)`。都接受 `query: str` 参数，返回 "
topics: [tools, community, external-integration]
---

# Web Search：6 种 Provider 对比

所有 6 个 search provider 都暴露同名函数 `web_search_tool`，装饰为 `@tool("web_search", parse_docstring=True)`。都接受 `query: str` 参数，返回 JSON string。差异在可选参数、认证方式和返回格式。

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

## 返回格式的不一致性

这是 6 个 provider 之间最大的差异——调用方需要注意：

| 格式 | Provider |
|------|----------|
| `{query, total_results, results: [{title, url, content}]}` | DDG, Serper |
| `[{title, url, snippet}]` | Tavily, Exa, Firecrawl |
| `[{type, title, desc, snippet, url}]` | InfoQuest |

DDG/Serper 返回包装对象（含 metadata），其余 provider 返回裸数组。字段名也不统一：DDG/Serper 用 `content`，Tavily/Exa/Firecrawl 用 `snippet`，InfoQuest 两者都有。

## web_search 只能启用一个的原因

`get_available_tools()` 做**按名去重**——config.yaml 中先出现的 `name: web_search` 胜出，后续同名 tool 被丢弃。所有 provider 都注册为 `name="web_search"`，所以只能激活一个。要换 provider：注释掉当前的，取消注释目标 provider。

## 认证方式对比

| Provider | 密钥来源 | 传递方式 |
|----------|---------|---------|
| DDG | 无 | — |
| Serper | env `SERPER_API_KEY` 或 config `api_key` | `X-API-KEY` header |
| Tavily | config `api_key` | SDK constructor |
| InfoQuest | env `INFOQUEST_API_KEY` | `Authorization: Bearer` |
| Exa | config `api_key` | SDK constructor |
| Firecrawl | config `api_key` | SDK constructor |

Tavily/Exa/Firecrawl 的密钥只从 config 读取——不 fallback 到环境变量。Serper 支持两种来源。InfoQuest 只从环境变量读取。
