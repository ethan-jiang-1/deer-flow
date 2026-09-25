---
title: "Web Fetch：6 种 URL→Markdown 管线"
description: "所有 6 个 fetch provider 都暴露同名函数 `web_fetch_tool`，装饰为 `@tool("web_fetch", parse_docstring=True)`。都接受 `url: str` 参数，返回 markd"
topics: [tools, community, external-integration]
---

# Web Fetch：6 种 URL→Markdown 管线

所有 6 个 fetch provider 都暴露同名函数 `web_fetch_tool`，装饰为 `@tool("web_fetch", parse_docstring=True)`。都接受 `url: str` 参数，返回 markdown string（截断到 4096 字符）。

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
└─────────────────────────────────────────────────────────────────────┘
```

## Provider 详情

### Jina AI（默认）

- **文件：** `community/jina_ai/tools.py:45`
- **签名：** `async def web_fetch_tool(url: str) -> str`
- **认证：** `JINA_API_KEY` env var → `Authorization: Bearer <key>`（可选——无 key 也能用但有限速）
- **端点：** `POST https://r.jina.ai/`，header `X-Return-Format: html`
- **管线：**
  1. `JinaClient.crawl()` — async HTTP POST，返回 HTML
  2. `ReadabilityExtractor.extract_article()` — 用 `readabilipy` (Mozilla Readability.js) 提取正文
  3. `Article.to_markdown()` — 用 `markdownify` 转 HTML→markdown
  4. 截断到 4096 字符
- **配置：** `timeout` 从 `config.tool_config("web_fetch").model_extra["timeout"]`，默认 10s
- **特点：** 唯一异步 fetch tool。Readability 提取失败时 fallback 到 `use_readability=False`（保留原始 HTML 结构）

### InfoQuest

- **文件：** `community/infoquest/tools.py:58`
- **签名：** `def web_fetch_tool(url: str) -> str`
- **认证：** `INFOQUEST_API_KEY` env var → `Authorization: Bearer`
- **端点：** `POST https://reader.infoquest.bytepluses.com`，body `{url, format: "HTML"}`
- **管线：** 与 Jina AI 相同——`ReadabilityExtractor` → `markdownify` → `[:4096]`
- **配置：** `fetch_time`, `timeout`, `navigation_timeout` 均可从 config 覆盖
- **特点：** 与 Jina AI 共享 `ReadabilityExtractor` 实例

### Tavily

- **文件：** `community/tavily/tools.py:43`
- **签名：** `def web_fetch_tool(url: str) -> str`
- **认证：** config `api_key` → `TavilyClient`
- **管线：** `TavilyClient.extract([url])` → `raw_content` → `f"# {title}\n\n{raw_content[:4096]}"`
- **特点：** 无本地可读性提取——Tavily 服务端完成内容提取

### Exa

- **文件：** `community/exa/tools.py:57`
- **签名：** `def web_fetch_tool(url: str) -> str`
- **认证：** config `api_key` → `Exa`
- **管线：** `Exa.get_contents([url], text={max_characters: 4096})` → `f"# {title}\n\n{text[:4096]}"`
- **特点：** Exa 服务端返回已提取的文本，无需本地管线

### Firecrawl

- **文件：** `community/firecrawl/tools.py:49`
- **签名：** `def web_fetch_tool(url: str) -> str`
- **认证：** config `api_key` → `FirecrawlApp`
- **管线：** `FirecrawlApp.scrape(url, formats=["markdown"])` → `result.markdown` → `f"# {title}\n\n{markdown[:4096]}`
- **特点：** 直接返回 markdown，无需本地转换
- **self-host 🆕：** 配置 `base_url`（如 `http://<host>:3002`）→ `FirecrawlApp(api_url=...)` 指向自建实例，无需云 API key

### Sofya 🆕

- **文件：** `community/sofya/tools.py`（#5239，与 web_search 同一模块）
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

## 关键差异

| 维度 | Jina AI | InfoQuest | Tavily | Exa | Firecrawl | Sofya 🆕 |
|------|---------|-----------|--------|-----|-----------|----------|
| **Async** | 是 | 否 | 否 | 否 | 否 | 否 |
| **API 返回** | HTML | HTML | text | text | markdown | markdown |
| **本地管线** | ReadabilityExtractor | ReadabilityExtractor | 无 | 无 | 无 | 无 |
| **截断位置** | 客户端 [:4096] | 客户端 [:4096] | 客户端 [:4096] | 服务端/客户端 | 客户端 [:4096] | 客户端 [:4096] |
| **免费层** | 有（有限速） | 否 | 否 | 否 | self-host 可免 | 否 |
| **文档格式** | HTML 页 | HTML 页 | — | — | — | 含 PDF/DOCX |

## ReadabilityExtractor（Jina AI & InfoQuest 共用）

`deerflow/utils/readability.py:58` — 共享的可读性提取管线：

```python
# 1. Mozilla Readability.js 提取正文
article = simple_json_from_html_string(html, use_readability=True)
# 2. 如果 JS 提取失败 → 保留原始 HTML 结构
if not article:
    article = simple_json_from_html_string(html, use_readability=False)
# 3. HTML → markdown
markdown = markdownify(article_html)
```

返回 `Article(title, html_content)` 对象，带 `to_markdown()` 方法。

## Async→Sync 包装

Jina AI 的 `web_fetch_tool` 是 async coroutine，但 DeerFlow 的 tool 调用链是同步的。`get_available_tools()` 中的 `_ensure_sync_invocable_tool()` 检测到 coroutine function 后，用共享 `ThreadPoolExecutor`（10 workers）包装：

```python
# tools/sync.py:38
def make_sync_tool_wrapper(async_tool):
    def sync_wrapper(**kwargs):
        if is_in_event_loop():
            return run_in_thread_pool(async_tool(**kwargs))  # 不阻塞 event loop
        else:
            return asyncio.run(async_tool(**kwargs))
    return sync_wrapper
```

在已有 event loop 的上下文中（agent 运行在 asyncio 中），包装器用线程池执行 `asyncio.run()` 来避免阻塞。
