---
title: "社区工具集成全景"
description: "DeerFlow 在 `deerflow/community/` 下集成了 20+ 个外部工具 provider，覆盖 web 搜索、网页抓取、图片搜索、浏览器截图、知识库检索（RAGFlow / LightRAG）和沙箱隔离。"
topics: [tools, community, external-integration]
---

# 社区工具集成全景

DeerFlow 在 `deerflow/community/` 下集成了 20+ 个外部工具 provider，覆盖 web 搜索、网页抓取、图片搜索、浏览器截图、知识库检索（RAGFlow / LightRAG）和沙箱隔离。

## 集成矩阵

| 集成 | 类型 | 需要 API Key | Async? | 默认启用 |
|------|------|------------|--------|---------|
| **DuckDuckGo Search** | web_search | 否 | 否 | 是 |
| **Serper** | web_search | `SERPER_API_KEY` | 否 | 否 |
| **Serply** 🆕 | web_search | config `api_key` 或 `SERPLY_API_KEY` | 否 | 否 |
| **Tencent Cloud WSA** 🆕 | web_search | config `api_key` 或 `TENCENTCLOUD_WSA_APIKEY` | 否 | 否 |
| **Sofya** 🆕 | web_search + web_fetch | config `api_key` 或 `SOFYA_API_KEY` | 否 | 否 |
| **Tavily** | web_search + web_fetch | config `api_key` | 否 | 否 |
| **InfoQuest** | web_search + web_fetch + image_search | `INFOQUEST_API_KEY` | 否 | 否 |
| **Exa** | web_search + web_fetch | config `api_key` | 否 | 否 |
| **Firecrawl** | web_search + web_fetch | config `api_key`（self-host `base_url` 可免） | 否 | 否 |
| **Jina AI** | web_fetch | `JINA_API_KEY`（可选） | **是** | 是 |
| **DuckDuckGo Image** | image_search | 否 | 否 | 是 |
| **Brave Image** 🆕 | image_search | `BRAVE_API_KEY` | 否 | 否 |
| **GroundRoute** 🆕 | web_search | config `api_key` | 否 | 否 |
| **Crawl4AI** 🆕 | web_fetch | 否 | **是** | 否 |
| **fastCRW** 🆕 | web_search | config `api_key` | 否 | 否 |
| **Browserless** 🆕 | web_capture（截图） | config `api_key` | 否 | 否 |
| **SearXNG** | web_search | 否 | 否 | 否 |
| **RAGFlow** 🆕 | knowledge retrieval（知识库检索，只读） | `RAGFLOW_API_KEY`（必填） | **是** | 否 |
| **LightRAG** 🆕 | knowledge retrieval（知识库检索，只读，knowledge_search 第二 provider） | 可选（`X-API-Key`） | **是** | 否 |
| **Browser Automation** 🆕 | browser（Playwright agentic） | 否 | N/A | 否 |
| **AIO Sandbox** | sandbox | 否 | N/A | 否 |
| **BoxLite** | sandbox（micro-VM） | 否 | N/A | 否 |
| **E2B** | sandbox（云端） | `E2B_API_KEY` | N/A | 否 |
| **Tenki** 🆕 | sandbox（云端 micro-VM） | `TENKI_API_KEY` | N/A | 否 |

> **Browser Automation**（`group: browser`）：Playwright agentic 浏览器控制（`browser_navigate`/`browser_snapshot`/`browser_click`/`browser_type`/`browser_get_text`/`browser_back`/`browser_screenshot`/`browser_close`）。进程内私有 loop-affine Playwright event-loop 线程；每步返回带稳定 `[ref]` 索引的页面快照；URL SSRF 过滤；可选 `cd backend && uv sync --extra browser && uv run playwright install chromium`。`GATEWAY_WORKERS > 1` 时禁止启用（无 thread affinity）。→ 深挖见 [06-browser-automation.md](06-browser-automation.md)。

> **LightRAG**（`group: knowledge`）：`knowledge_search` 的第二 provider（#5209），与 RAGFlow 二选一（按名去重，重名保留第一条）。检索自建 LightRAG 服务（v1.4.9+）的单一索引 workspace，`POST /query/data` 纯数据检索（无 LLM 生成），`mode: naive/local/global/hybrid/mix`（默认 mix）；API key 可选（`X-API-Key`）；结果格式化成与 RAGFlow 共享形状的带 `[N]` 引用编号紧凑文本，`chunk_id`/`reference_id` 永不进模型。→ 深挖见 [08-lightrag.md](08-lightrag.md)。

> **RAGFlow**（`group: knowledge`）：只读知识库检索，唯一工具 `knowledge_search`。operator 通过 `datasets` 白名单限定作用域（省略 = 搜 tenant 可见全部）；dataset 按 `embedding_model` 分组、最多 4 组并行检索、按 rank 交错合并；结果格式化成带 `[N]` 引用编号的紧凑文本；dataset ID 永不进模型。纯 `httpx` 实现，无三方 SDK。→ 深挖见 [07-ragflow.md](07-ragflow.md)。

## Tool 装配流程

```
config.yaml tools:              importlib reflection           dedup by name
  ├─ name: web_search   →  resolve_variable(cfg.use)  ┐
  ├─ name: web_fetch    →  resolve_variable(cfg.use)  │
  ├─ name: image_search →  resolve_variable(cfg.use)  │
  ├─ name: ls           →  resolve_variable(cfg.use)  ├→ config tools (优先)
  ├─ name: bash         →  resolve_variable(cfg.use)  │
  └─ ...                                              ┘
                                                      ┐
builtins:                                             │
  ├─ present_file_tool                                ├→ builtin tools
  ├─ ask_clarification_tool                           │
  └─ view_image_tool (if supports_vision)             ┘
                                                      ┐
extensions_config.json:                               │
  └─ mcpServers → MCP tools (by name, mtime cache)    ├→ MCP tools (去重)
                                                      ┘
config.yaml:                                          ┐
  └─ acp_agents → invoke_acp_agent tool               ├→ ACP tools (去重)
                                                      ┘
                                                      ↓
                                              get_available_tools()
```

关键机制：
1. **Reflection 加载**：`config.yaml` 中 `use: deerflow.community.ddg_search.tools:web_search_tool` → `import_module` + `getattr` → tool callable
2. **按名去重**：同名 tool 先到先得——config.yaml 中先列出的优先。这就是"只能有一个 web_search"的原因
3. **Async→Sync 包装**：如果 community tool 是 async coroutine（如 Jina AI），`_ensure_sync_invocable_tool()` 用共享 `ThreadPoolExecutor`（10 workers）包装为同步 callable
4. **ToolConfig.extra="allow"**：`ToolConfig` Pydantic model 允许任意额外字段（`api_key`, `max_results`, `timeout` 等），各 tool 运行时通过 `config.tool_config("web_search").model_extra` 读取

## Provider 选择决策树

```
需要 web search?
├─ 免费/零配置 → DDG (ddg_search)
├─ Google 搜索结果质量 → Serper (需 SERPER_API_KEY) / Serply 🆕 (需 SERPLY_API_KEY，
│   同一 key 覆盖 Google News/Scholar 垂直：vertical: search/news/scholar)
├─ 国内/中文场景 → Tencent Cloud WSA 🆕 (需 TENCENTCLOUD_WSA_APIKEY，1-50 条，mode 0/1/2)
├─ 搜索返回整页内容 → Sofya 🆕 (需 SOFYA_API_KEY，search_depth: basic 读页面)
├─ 需要 search + fetch 一体化 → Tavily / Exa / Firecrawl / InfoQuest
│   ├─ Tavily → 简洁 API，AI 优化搜索结果
│   ├─ Exa → 语义搜索，支持内容高亮
│   ├─ Firecrawl → 搜索 + scrape markdown 一体化
│   └─ InfoQuest → 字节跳动内部，中文场景优化
└─ 需要 search + fetch + image search → InfoQuest

需要 web fetch (URL→markdown)?
├─ 免费/零配置 → Jina AI (r.jina.ai，无需 key 但有频率限制)
├─ 需要高质量可读性提取 → Jina AI 或 InfoQuest (都走 ReadabilityExtractor)
├─ 已有 search provider → Tavily/Exa/Firecrawl 都自带 fetch；Sofya 🆕 也同时提供
├─ 需要处理 PDF/DOCX 链接 → Sofya 🆕 (服务端转 markdown)
└─ 格式需求 → Firecrawl 直接返回 markdown（无需本地转换）

需要 image search?
├─ 免费 → DDG Image Search
└─ 付费/中文场景 → InfoQuest Image Search (需 INFOQUEST_API_KEY)

需要检索私有知识库（RAG，非公开互联网）?
├─ 多 dataset + 白名单/相似度阈值 → RAGFlow → knowledge_search（需 RAGFLOW_API_KEY + datasets 白名单）
└─ 自建图 RAG、单 workspace、检索策略切换 → LightRAG 🆕 → knowledge_search（与 RAGFlow 二选一）
   （注意：与内置 memory 检索不同——两者接的都是 operator 建好的领域知识库，
     memory 记的是从对话里提取的 per-user fact。见 07-ragflow.md / 08-lightrag.md）
```

## 源码索引

| 目录 | 文件 |
|------|------|
| `community/ddg_search/` | `__init__.py`, `tools.py` |
| `community/serper/` | `__init__.py`, `tools.py` |
| `community/serply/` 🆕 | `__init__.py`, `tools.py` |
| `community/tencent_wsa/` 🆕 | `__init__.py`, `tools.py` |
| `community/sofya/` 🆕 | `__init__.py`, `tools.py` |
| `community/lightrag/` 🆕 | `__init__.py`, `client.py`, `formatting.py`, `tools.py` |
| `community/search_time_range.py` 🆕 | 共享 recency filter 契约（day/week/month/year → 各 provider 映射） |
| `community/tavily/` | `tools.py` |
| `community/infoquest/` | `infoquest_client.py`, `tools.py` |
| `community/exa/` | `tools.py` |
| `community/firecrawl/` | `tools.py` |
| `community/jina_ai/` | `jina_client.py`, `tools.py` |
| `community/image_search/` | `__init__.py`, `tools.py` |
| `community/aio_sandbox/` | `__init__.py`, `aio_sandbox.py`, `aio_sandbox_provider.py`, `backend.py`, `local_backend.py`, `remote_backend.py`, `sandbox_info.py`, `ownership/`（跨实例租约） |
| `community/browser_automation/` | `__init__.py`, `session.py`, `tools.py` |
| `community/ragflow/` | `__init__.py`, `client.py`, `formatting.py`, `tools.py` |
| `community/tenki/` | `__init__.py`, `provider.py`, `sandbox.py` |
| Tool 装配 | `tools/tools.py` → `get_available_tools()` |
| Async 包装 | `tools/sync.py` → `make_sync_tool_wrapper()` |
| Readability 提取 | `utils/readability.py` → `ReadabilityExtractor` |
