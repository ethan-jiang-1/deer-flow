---
title: "Web Search：12 种 Provider 对比"
description: '所有 12 个 search provider 都暴露同名函数 web_search_tool，装饰为 @tool("web_search", parse_docstring=True)。都接受 query: str 参数，返回'
topics: [tools, community, external-integration]
verified_against: v2.2.0
last_verified: 2026-11-08
---

# Web Search：12 种 Provider 对比

内置 12 个 search provider 都暴露同名函数 `web_search_tool`，装饰为 `@tool("web_search", parse_docstring=True)`。都接受 `query: str` 参数，返回 JSON string。差异在可选参数、认证方式和返回格式。

> **2.2.0 变化速览**：新增 Webz（新闻检索）与 You.com（免 key 可用）两个 provider；`max_results` 的「什么算非法」抽成 `community/search_max_results.py::coerce_max_results()` 单一所有者；结果 URL 统一过 `url_safety.safe_public_result_url()`（无 DNS 的纯字符串过滤）。

## Provider 对比

### DuckDuckGo Search（默认）

- **文件：** `community/ddg_search/tools.py:181-182`（`web_search_tool`）
- **认证：** 无（使用 `ddgs` 库，免费）
- **参数：** `query: str, max_results: int = DEFAULT_MAX_RESULTS, time_range: SearchTimeRange | None = None`
- **返回格式：** `{query, total_results, results: [{title, url, content}]}`
- **配置：** `config.tool_config("web_search").model_extra["max_results"]`，并支持 `region` / `safesearch` / `backend` 覆盖工具默认值
- **2.2.0：** `max_results` 走共享 `coerce_max_results(max_results, provider="DDG Search", logger=logger)`；每条结果的 `url` 走 `safe_public_result_url(...)`
- **延迟加载：** `ddgs` 库在 `_search_text()` 内延迟导入，避免非搜索场景的启动开销

### Serper（Google Search）

- **文件：** `community/serper/tools.py:387-388`（`web_search_tool`）
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

- **文件：** `community/sofya/tools.py:141-142`（#5239）
- **认证：** config `model_extra["api_key"]` 或 env `SOFYA_API_KEY`（config 优先）→ `Authorization: Bearer`；POST `https://sofya.co/v1/search`
- **最大特点：** 返回**结果页面的内容**而非仅摘要（`search_depth: basic` 读页面 / `snippets` 只给摘要）；每个 agent 也能传 `time_range`（day/week/month/year → Sofya 的 `freshness` 参数，走共享 `SearchTimeRange` 契约）
- **返回格式：** `{query, total_results, results: [{title, url, content}]}` 包装对象；`content` = 页面内容（读取成功）或搜索摘要（fallback），按 `contents_max_characters`（默认 2000，0 = 不截断）截断，避免正常搜索被写到磁盘
- **参数：** `query: str, max_results: int | None = None`（cap 20；调用方显式传参优先于 config——其它 provider 多是 config 覆盖参数）
- **同时提供 `web_fetch`**（见 [02-web-fetch.md](02-web-fetch.md)）

### Tavily

- **文件：** `community/tavily/tools.py:52-53`（`async def web_search_tool`）
- **认证：** config `tool_config("web_search").model_extra["api_key"]`，传递给 `TavilyClient(api_key=api_key)`
- **参数：** `query: str, time_range: SearchTimeRange | None = None`（`max_results` 通过 config 控制，不作为函数参数）
- **返回格式：** `[{title, url, snippet}]` — **裸数组**，不是 `{query, total_results, results}` 包装
- **注意：** 没有 env var fallback；Tavily 同时提供 `web_fetch_tool`

### InfoQuest

- **文件：** `community/infoquest/tools.py:92-93`（`async def web_search_tool`）
- **认证：** `INFOQUEST_API_KEY` env var → `Authorization: Bearer <key>`
- **架构：** 通过 `InfoQuestClient` 类调用（`infoquest_client.py`）
- **端点：** `POST https://search.infoquest.bytepluses.com`
- **返回格式：** `[{type: "page"|"news", title, desc, snippet, url}]`
- **清洗：** `clean_results()` 提取 organic results + top stories
- **额外配置：** `search_time_range`（int，-1 禁用）
- **注意：** 同时提供 search + fetch + image search — 字节跳动内部生态

### Exa

- **文件：** `community/exa/tools.py:91-92`（`web_search_tool`）
- **认证：** config `tool_config("web_search").model_extra["api_key"]` → `Exa(api_key=api_key)`
- **参数：** `query: str`（所有配置通过 model_extra）
- **返回格式：** `[{title, url, snippet}]` — 裸数组，`snippet` = `"\n".join(result.highlights)`
- **额外配置：** `max_results`（默认 5）、`search_type`（默认 "auto"）、`contents_max_characters`（默认 1000）
- **特点：** 语义搜索，content highlight 内建

### Firecrawl

- **文件：** `community/firecrawl/tools.py:95-96`（`async def web_search_tool`）
- **认证：** config `model_extra["api_key"]` → `FirecrawlApp(api_key=api_key)`
- **参数：** `query: str`
- **返回格式：** `[{title, url, snippet}]` — `snippet` = `item.description`
- **容错：** 使用 `getattr()` with empty string fallback — 字段缺失不崩溃
- **额外配置：** `max_results`（默认 5），以 `limit` 参数传给 `client.search()`
- **self-host 🆕：** 配置 `base_url`（如 `http://<host>:3002`）即指向自建 Firecrawl 实例，可完全免云 API key（`FirecrawlApp(api_url=...)`）

### Webz 🆕

- **文件：** `community/webz/tools.py:65-66`（`async def web_search_tool`，2.2.0 新增）
- **认证：** config `model_extra["api_key"]` 或 env `WEBZ_API_KEY`（config 优先）；缺失 → `{"error": "Webz API key is missing; configure api_key or WEBZ_API_KEY"}`
- **端点是新闻、不是通用 web**：`POST https://api.webz.io/api/news/context`，`Authorization: Bearer`，body `{query, k}`，`follow_redirects=False`。docstring 明确：「This provider searches news, not the general web. Date filters do not extend the provider's available news coverage.」
- **参数是 12 个 provider 里最丰富的**：`query`（**1-750 字符且 ≤100 词**，超限直接返回错误）、`max_results`（clamp 1-100，缺省用 config 或 5）、`time_range`、`published_from`/`published_to`（`YYYY-MM-DD`，**`published_from` 优先于 `time_range`**）、`language`、`country`、`source`（映射到 Webz 的 `domain`）、`sentiment`（`positive|negative|neutral`）、`category`
- **日期校验**：`date.fromisoformat(value).isoformat() != value` 拒绝非规范写法（如 `2025-1-1`）；`published_from > published_to` 拒绝反向区间。`time_range` 只是换算成 `published_from = today - {1,7,30,365}`（UTC）
- **返回格式：** `{query, returned_results, results: [{title, url, content, published_at, source}]}`；`content` = `chunk.text` 或 `article.summary`；单条畸形结果 warn 后跳过，**有结果但全部畸形**则报 `"Webz returned an unexpected response"`
- **注意：** 与其它 provider 不同，它**不接受裸数组**——payload 必须是 `{"results": [...]}` 形状

### You.com 🆕

- **文件：** `community/youcom/tools.py:166-167`（`async def web_search_tool`，2.2.0 新增）
- **双端点、按有没有 key 选**：无 key → `https://api.you.com/v1/agents/search`（无 auth header，免费档 100 次/天）；有 `YDC_API_KEY`（或 config `api_key`）→ `https://api.you.com/v1/search` + `X-API-Key` header。docstring 强调「Endpoint and headers are always chosen together: the keyless endpoint rejects an `X-API-Key` header, so a stale key must never be sent there.」
- **参数：** `query: str, max_results: int | None = None`（缺省用 config 的 `max_results`，再缺省 5；clamp 1-100）
- **返回格式：** `[{title, url, snippet}]` 裸数组（与 Tavily/Exa/Firecrawl 同形状）。`snippet` 优先取 `snippets[]` 拼接（web hit），退回 `description`（news hit）；`web` 段在前、`news` 段在后合并后截到 `count`（`count` 是**每段**上限，所以合并后会超）
- **错误内联化**：HTTP 状态错误映射成 `{"error": "You.com API error: HTTP <n> (<hint>)", "query": ...}`，`401/402/429` 各有可执行提示（`invalid or expired YDC_API_KEY` / `credit balance depleted` / `rate limit reached — set YDC_API_KEY for higher limits`）
- **为什么是 coroutine**：模块 docstring 写明「A sync client would run the whole tool on the default executor and hold one of that pool's threads for the network round-trip, so several providers queried in parallel queued behind each other.」两处磁盘读取都挪出了事件循环——config 解析走 executor，`User-Agent`（读已安装包元数据）只在**第一次冷调用**走 executor，之后是内存缓存。回归测试：`backend/tests/blocking_io/test_youcom_search_async.py`
- **`User-Agent`**：`deerflow-harness/<version> youdotcom-integration/bytedance-deer-flow`，**只发给 You.com 主机**
- **2.2.0 复用**：`max_results` 走共享 `coerce_max_results(value, provider="You.com", ...)` 后再本地 clamp 到 100（注释：「clamping policy is deliberately per-provider」）

## 共享的 `max_results` 归一化 🆕

`community/search_max_results.py`（2.2.0 新增）把「什么算非法 `max_results`」从各 provider 里抽成单一所有者：

```python
coerce_max_results(value, *, provider: str, logger: logging.Logger, default: int = 5) -> int
```

- `bool` 一律拒绝（`True` 是 `int` 子类，裸 `int(value)` 会静默变成 1）；
- 非整除 `float` 拒绝（`int(3.5)` 会静默截断 YAML 里写错的值）；
- 越界 float（如未加引号的 `max_results: .inf`）触发 `OverflowError`，也在这里兜住；
- 整除 float（`4.0`）**是合法的**，且**不设上限**——「Deliberately *not* decided here: whether an otherwise-valid value has an upper bound」；
- `logger` 是**参数而不是模块级**：调用方传自己的 logger，warning 的 `record.name` 才会保留来源模块。

现役使用者：`ddg_search` / `image_search` / `fastcrw` / `firecrawl` / `sofya` / `serply` / `serper` / `tencent_wsa` / `brave` / `groundroute` / `youcom`。**Exa**（自己的整数 helper）、**SearXNG**（内联校验）、**Tavily**（透传配置值）仍各自归一化——`tests/test_search_max_results_single_owner.py` 只跟踪已知的 helper/内联模式，不证明任意 provider 的语义。

## 结果 URL 的 SSRF 过滤（2.2.0 强化）

`community/url_safety.py:14` 的 `safe_public_result_url(value)` 是**纯字符串层面**的过滤，`docstring` 明确它「without doing DNS or network I/O」，且「Downloaders must still check the resolved address at connection time.」

它拦的东西（`:14-50`）：

1. 非 `http`/`https`、无 netloc、无 host → 返回 `""`；
2. host 先做 IDNA 点号归一化（`\u3002`/`\uff0e`/`\uff61` → `.`，`:11` 的 `_IDNA_DOT_TRANSLATION`）+ 小写 + 去尾点，**防止全角点把 IP 字面量伪装成域名**；
3. 命中 `_BLOCKED_HOSTNAMES = {"localhost", "metadata.google.internal"}` 或以 `.localhost` 结尾 → `""`；
4. IPv4 字面量解析前先过 `_decode_result_ipv4()`（`:53`）——**识别十进制/八进制/十六进制**写法（`0x7f.1`、`0177.0.0.1` 之类），然后复用 `is_blocked_address()`；
5. IPv6 额外拆 embedded IPv4：`ipv4_mapped`、`sixtofour`、`64:ff9b::/96` NAT64 前缀，以及「裸 32 位整数塞在 IPv6 低位」这种写法。

`is_blocked_address()` 在 2.2.0 里补了 `not address.is_global`（`:97-107`）——single flag 漏掉的特殊用途网段（最典型是 `100.64.0.0/10` 共享地址空间）现在也会被拦。

现役使用者（`grep safe_public_result_url`）：`ddg_search` / `serper` / `serply` / `tencent_wsa` / `sofya` / `tavily` / `exa` / `firecrawl` / `fastcrw` / `groundroute` / `brave` / `image_search` / `searxng` / `webz` / `youcom` / `infoquest_client`。

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
| Webz 🆕 | `time_range` | 换算成 `published_from = today - 1/7/30/365`；显式 `published_from` 优先 |

Serply / Tencent WSA / Firecrawl 等不支持。docstring 统一措辞："Use only when the request requires recent results"——让模型只在需要新近性时才传。InfoQuest 的 `search_time_range: 10`（int 分钟数配置项）是更早的独立机制，与此契约无关。

## 返回格式的不一致性

这是 12 个 provider 之间最大的差异——调用方需要注意：

| 格式 | Provider |
|------|----------|
| `{query, total_results, results: [{title, url, content}]}` | DDG, Serper, Serply, Sofya |
| `{query, returned_results, results: [{title, url, content, published_at, source}]}` | Webz 🆕 |
| `[{title, url, snippet}]` | Tavily, Exa, Firecrawl, You.com 🆕 |
| `[{type, title, desc, snippet, url}]` | InfoQuest |

DDG/Serper/Serply/Sofya/Webz 返回包装对象（含 metadata），其余 provider 返回裸数组。字段名也不统一：DDG/Serper/Serply/Sofya/Webz 用 `content`，Tavily/Exa/Firecrawl/You.com 用 `snippet`，InfoQuest 两者都有，Tencent WSA 用 `snippet` 且外层带 `request_id`。**注意 Webz 的计数键是 `returned_results`**（本页条数），不是 `total_results`。

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
| Webz 🆕 | config `api_key` 或 env `WEBZ_API_KEY` | `Authorization: Bearer` |
| You.com 🆕 | config `api_key` 或 env `YDC_API_KEY`（**可缺省**） | `X-API-Key` header（仅在有 key 时，且只配 keyed 端点） |

Serply/Tencent WSA/Sofya/Webz/You.com 都采用 **config 优先、env fallback** 的模式。Serply/Tencent WSA/Sofya 在 key 缺失时首次调用 warn 一次（`_api_key_warned` 集合）后返回结构化 JSON 错误；**Webz 每次都返回错误文本**（不做 warn 去重）；**You.com 缺 key 不是错误**——它降级到免 key 端点。Tavily/Exa 仍只从 config 读取；InfoQuest 只从环境变量读取。Firecrawl 走 self-host `base_url` 时可以完全不需要 key。
