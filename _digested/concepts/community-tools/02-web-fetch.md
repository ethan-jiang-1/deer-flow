---



title: "Web Fetch：7 种 URL→Markdown 管线"
description: '所有 7 个 fetch provider 都暴露同名函数 `web_fetch_tool`，装饰为 `@tool("web_fetch", parse_docstring=True)`。都接受 `url: str` 参数，返回 markd'
topics: [tools, community, external-integration]
verified_against: v2.2.0
last_verified: 2026-11-08
---

# Web Fetch：7 种 URL→Markdown 管线

所有 7 个 fetch provider 都暴露同名函数 `web_fetch_tool`，装饰为 `@tool("web_fetch", parse_docstring=True)`。都接受 `url: str` 参数，返回 markdown string（绝大多数截断到 4096 字符；Unbrowse 的截断常量是 `_UNBROWSE_FETCH_MAX_CHARS = 4096`，同样值）。

> **2.2.0 变化速览**：新增 Unbrowse（走 MCP `tools/call` 而不是 REST）；Jina AI 的 `web_fetch` 增加了**本地请求准入**（`request_admission`）与响应体上限等 opt-in 选项。

## Provider 管线对比

```
┌─────────────────────────────────────────────────────────────────────┐
│ Jina AI (仅异步)                                                     │
│   URL → r.jina.ai (return_format=html) → ReadabilityExtractor       │
│       → markdownify → [:4096]                                       │
├─────────────────────────────────────────────────────────────────────┤
│ InfoQuest                                                            │
│   URL → reader.infoquest.bytepluses.com (format=HTML)               │
│       → ReadabilityExtractor → markdownify → [:4096]                │
├─────────────────────────────────────────────────────────────────────┤
│ Tavily                                                               │
│   URL → TavilyClient.extract() → raw_content → [:4096]              │
├─────────────────────────────────────────────────────────────────────┤
│ Exa                                                                  │
│   URL → Exa.get_contents(text={max_characters: 4096})               │
│       → raw text → [:4096]                                           │
├─────────────────────────────────────────────────────────────────────┤
│ Firecrawl                                                            │
│   URL → FirecrawlApp.scrape(formats=["markdown"])                   │
│       → markdown → [:4096]          （self-host: base_url 免云 key）  │
├─────────────────────────────────────────────────────────────────────┤
│ Sofya 🆕                                                             │
│   URL → POST sofya.co/v1/fetch {urls:[url]}                         │
│       → 服务端 markdown → "# title\n\ncontent" → [:4096]            │
├─────────────────────────────────────────────────────────────────────┤
│ Unbrowse 🆕                                                          │
│   URL → POST unbrowse.ai/api/mcp (JSON-RPC tools/call)              │
│       invoke "unbrowse.scrape" {url, formats:["markdown"], render}  │
│       → 结构化 markdown → "# title\n\ncontent" → [:4096]            │
└─────────────────────────────────────────────────────────────────────┘
```

## Provider 详情

### Jina AI（默认）

- **文件：** `community/jina_ai/tools.py:44-45`
- **签名：** `async def web_fetch_tool(url: str) -> str`
- **认证：** `JINA_API_KEY` env var → `Authorization: Bearer <key>`（可选——无 key 也能用但有限速）
- **端点：** `POST https://r.jina.ai/`，header `X-Return-Format: html`
- **管线：**
  1. `JinaClient.crawl()` — async HTTP POST，返回 HTML
  2. `ReadabilityExtractor.extract_article()` — 用 `readabilipy` (Mozilla Readability.js) 提取正文
  3. `Article.to_markdown()` — 用 `markdownify` 转 HTML→markdown
  4. 截断到 4096 字符
- **配置：** `timeout`（默认 10）、`proxy`、`trust_env` 从 `config.tool_config("web_fetch").model_extra` 读；2.2.0 还可传 `max_retries` / `retry_budget_seconds` / `max_response_bytes` / `request_admission`（见下）
- **特点：** 唯一异步 fetch tool。Readability 提取失败时 fallback 到 `use_readability=False`（保留原始 HTML 结构）
- **配置解析不在事件循环上**：`config = (await asyncio.to_thread(get_app_config)).get_tool_config("web_fetch")`——`get_app_config()` 会 stat/hash 配置文件
- **2.2.0 新增 `request_admission`（opt-in 本地准入）**：`community/jina_ai/request_admission.py`，三个必填字段 `max_concurrent_requests`（≥1）/ `max_queue_size`（≥0）/ `max_wait_seconds`（有限正数），字段集合必须**恰好**是这三个（多一个少一个都 `ValueError`）。语义是「进程级、跨线程/跨 loop 的尝试准入」：一旦启用就对该进程后续所有 Jina 调用生效且**不可更改直到进程重启**；排队超时抛 `JinaAdmissionError("wait expired")`——文档明确它是 terminal local rejection，**不是** provider 状态也不是可重试 I/O 错误；票证只在短 threading lock 下预占容量，唤醒 future 只由持有它的 loop 触碰；**key 里不含凭证/URL/调用者身份**

### InfoQuest

- **文件：** `community/infoquest/tools.py:104-105`
- **签名：** `def web_fetch_tool(url: str) -> str`
- **认证：** `INFOQUEST_API_KEY` env var → `Authorization: Bearer`
- **端点：** `POST https://reader.infoquest.bytepluses.com`，body `{url, format: "HTML"}`
- **管线：** 与 Jina AI 相同——`ReadabilityExtractor` → `markdownify` → `[:4096]`
- **配置：** `fetch_time`, `timeout`, `navigation_timeout` 均可从 config 覆盖
- **特点：** 与 Jina AI 共享 `ReadabilityExtractor` 实例

### Tavily

- **文件：** `community/tavily/tools.py:96-97`
- **签名：** `def web_fetch_tool(url: str) -> str`
- **认证：** config `api_key` → `TavilyClient`
- **管线：** `TavilyClient.extract([url])` → `raw_content` → `f"# {title}\n\n{raw_content[:4096]}"`
- **特点：** 无本地可读性提取——Tavily 服务端完成内容提取

### Exa

- **文件：** `community/exa/tools.py:134-135`
- **签名：** `def web_fetch_tool(url: str) -> str`
- **认证：** config `api_key` → `Exa`
- **管线：** `Exa.get_contents([url], text={max_characters: 4096})` → `f"# {title}\n\n{text[:4096]}"`
- **特点：** Exa 服务端返回已提取的文本，无需本地管线

### Firecrawl

- **文件：** `community/firecrawl/tools.py:131-132`
- **签名：** `def web_fetch_tool(url: str) -> str`
- **认证：** config `api_key` → `FirecrawlApp`
- **管线：** `FirecrawlApp.scrape(url, formats=["markdown"])` → `result.markdown` → `f"# {title}\n\n{markdown[:4096]}`
- **特点：** 直接返回 markdown，无需本地转换
- **self-host 🆕：** 配置 `base_url`（如 `http://<host>:3002`）→ `FirecrawlApp(api_url=...)` 指向自建实例，无需云 API key

### Sofya 🆕

- **文件：** `community/sofya/tools.py:200-201`（#5239，与 web_search 同一模块）
- **签名：** `def web_fetch_tool(url: str) -> str`
- **认证：** config `model_extra["api_key"]` 或 env `SOFYA_API_KEY`（config 优先）→ `Authorization: Bearer`
- **端点：** `POST https://sofya.co/v1/fetch`，body `{"urls": [url]}`
- **管线：** Sofya 服务端完成提取并返回 **markdown** → `f"# {title}\n\n{content[:4096]}"`
- **特点：** 官方注释称同时处理 PDF、DOCX 等文档格式；单个 URL 失败时返回 `result.error`；与 web_search 共用 `_sofya_post` / `_response_results` 辅助函数和 60s 超时
- **配置示例**（`config.example.yaml`）：

```yaml
  # Web fetch tool (uses Sofya, requires SOFYA_API_KEY)
  # Returns the page as markdown. Also handles PDF, DOCX and other documents.
  # NOTE: Only one web_fetch provider can be active at a time.
  # - name: web_fetch
  #   group: web
  #   use: deerflow.community.sofya.tools:web_fetch_tool
  #   # api_key: $SOFYA_API_KEY
```

### Unbrowse 🆕

- **文件：** `community/unbrowse/tools.py:160-161`（`def web_fetch_tool(url: str) -> str`，2.2.0 新增）
- **认证：** env `UNBROWSE_API_KEY` 或 config `api_key`（config 优先，`_get_api_key`）；缺失 → `Error: UNBROWSE_API_KEY is not configured`，并首次 warn 一次
- **它不是 REST 抓取器，而是 MCP 客户端**：`POST https://unbrowse.ai/api/mcp`，body 是标准 JSON-RPC
  ```json
  {"jsonrpc": "2.0", "id": 1, "method": "tools/call",
   "params": {"name": "unbrowse.scrape", "arguments": {"url": ..., "formats": ["markdown"], "render": "auto"}}}
  ```
  header：`Authorization: Bearer <key>` + `Content-Type: application/json` + `Accept: application/json`；超时 `_UNBROWSE_TIMEOUT = 90`
- **`render` 三档**：`auto`（默认）/ `never`（只走纯 HTTP）/ `always`（强制云浏览器）；不支持的值 warn 后回落 `auto`（`_resolve_render`）
- **结果解包的两条路径**：优先 `result.structuredContent` 的 dict；否则把 `result.content[].text` 拼起来再 `json.loads`。任一步不是预期形状 → `Error: Unbrowse returned an unexpected response format`
- **错误分层**：HTTP 状态错误 → `Unbrowse API error: HTTP <n>`；JSON-RPC `error` 字段 → `Unbrowse error: <message>`（截 500 字符）；`result.isError` → 同样报 `Unbrowse error:`。所有错误日志的文本截 500 字符，不把完整响应打出去
- **页面级失败但仍有内容**：`metadata.statusCode ∈ [400,599]` 时把 `Warning: target page responded with HTTP <n> (final URL: ...)` 放在正文前；`finalUrl` 会先过 `_strip_url_userinfo()`（剥 `user:pass@`，不可解析则整段丢弃——「Never echo raw credentials when parsing the authority fails.」）
- **返回：** `# {title}\n\n{markdown}`，`title` 缺省 `"Untitled"`；空内容 → `Error: No content found`

## 关键差异

| 维度 | Jina AI | InfoQuest | Tavily | Exa | Firecrawl | Sofya 🆕 | Unbrowse 🆕 |
|------|---------|-----------|--------|-----|-----------|----------|-------------|
| **Async** | 是 | 否 | 否 | 否 | 否 | 否 | 否 |
| **协议** | REST | REST | SDK | SDK | SDK | REST | **MCP JSON-RPC** |
| **API 返回** | HTML | HTML | text | text | markdown | markdown | markdown |
| **本地管线** | ReadabilityExtractor | ReadabilityExtractor | 无 | 无 | 无 | 无 | 无 |
| **截断位置** | 客户端 [:4096] | 客户端 [:4096] | 客户端 [:4096] | 服务端/客户端 | 客户端 [:4096] | 客户端 [:4096] | 客户端 [:4096] |
| **免费层** | 有（有限速） | 否 | 否 | 否 | self-host 可免 | 否 | 否 |
| **文档格式** | HTML 页 | HTML 页 | — | — | — | 含 PDF/DOCX | HTML 页（可强制云浏览器渲染） |

## ReadabilityExtractor（Jina AI & InfoQuest 共用）

`deerflow/utils/readability.py:197`（`class ReadabilityExtractor`，`extract_article()` 在 `:198`）— 共享的可读性提取管线：

```python
# 1. Mozilla Readability.js 提取正文
article = simple_json_from_html_string(html, use_readability=True)
# 2. 如果 JS 提取失败 → 保留原始 HTML 结构
if not article:
    article = simple_json_from_html_string(html, use_readability=False)
# 3. HTML → markdown
markdown = markdownify(article_html)
```

返回 `Article(title, html_content, url=None)` 对象（`:55`），带 `to_markdown(including_title=True)` 方法（`:63`）。传入 `url` 时先做 `_resolve_html_urls(html, url)`（`:109`）把相对链接补成绝对链接。

## Async→Sync 包装

Jina AI 的 `web_fetch_tool` 是 async coroutine，但 DeerFlow 的 tool 调用链是同步的。`get_available_tools()` 中的 `_ensure_sync_invocable_tool()` 检测到 coroutine function 后，用共享 `ThreadPoolExecutor`（10 workers）包装：

```python
# tools/sync.py:38
def make_sync_tool_wrapper(coro: Callable[..., Any], tool_name: str) -> Callable[..., Any]: ...
```

它还负责把 `RunnableConfig` 参数注入回 coroutine（`invoke_acp_agent` 这类配置敏感工具依赖这一点），并明确**不伪造动态函数签名**——一个用户可见参数恰好叫 `config` 的异步工具会与 LangChain 注入的 `config` 撞名，此时应改名或扩展这个 helper。

在已有 event loop 的上下文中（agent 运行在 asyncio 中），包装器用线程池执行 `asyncio.run()` 来避免阻塞。
