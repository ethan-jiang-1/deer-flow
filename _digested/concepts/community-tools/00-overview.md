---
title: "社区工具集成全景"
description: "DeerFlow 在 `deerflow/community/` 下集成了 25+ 个外部工具 provider，覆盖 web 搜索、网页抓取、图片搜索、浏览器截图、只读知识库检索（统一 `knowledge/` 契约 + RAGFlow/LightRAG/WeKnora）和沙箱隔离。"
topics: [tools, community, external-integration]
---

# 社区工具集成全景

DeerFlow 在 `deerflow/community/` 下集成了 25+ 个外部工具 provider，覆盖 web 搜索、网页抓取、图片搜索、浏览器截图、只读知识库检索（统一 `knowledge/` 契约 + RAGFlow/LightRAG/WeKnora）和沙箱隔离。

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
| **Webz** 🆕 | web_search | config `api_key` 或 `WEBZ_API_KEY` | **是** | 否 |
| **You.com** 🆕 | web_search | 可选（`YDC_API_KEY`，缺省走免 key 端点） | **是** | 否 |
| **Crawl4AI** 🆕 | web_fetch | 否 | **是** | 否 |
| **Unbrowse** 🆕 | web_fetch | `UNBROWSE_API_KEY`（必填） | **是** | 否 |
| **Jsonify** 🆕 | data（只读 dataset rows） | dataset serve URL（URL 即凭证，operator 配） | **是** | 否 |
| **fastCRW** 🆕 | web_search | config `api_key` | 否 | 否 |
| **Browserless** 🆕 | web_capture（截图） | config `api_key` | 否 | 否 |
| **SearXNG** | web_search | 否 | 否 | 否 |
| **RAGFlow** 🆕 | knowledge retrieval（知识库检索，只读） | `RAGFLOW_API_KEY`（必填） | **是** | 否 |
| **LightRAG** 🆕 | knowledge retrieval（知识库检索，只读，knowledge_search 第二 provider） | 可选（`X-API-Key`） | **是** | 否 |
| **WeKnora** 🆕 | knowledge retrieval（可安装扩展，走通用 `knowledge_search` + `provider: weknora`） | `WEKNORA_API_KEY`（env 名由 `api_key_env` 指定） | **是** | 否 |
| **Browser Automation** 🆕 | browser（Playwright agentic） | 否 | N/A | 否 |
| **AIO Sandbox** | sandbox | 否 | N/A | 否 |
| **BoxLite** | sandbox（micro-VM） | 否 | N/A | 否 |
| **E2B** | sandbox（云端） | `E2B_API_KEY` | N/A | 否 |
| **Tenki** 🆕 | sandbox（云端 micro-VM） | `TENKI_API_KEY` | N/A | 否 |

> **Browser Automation**（`group: browser`）：Playwright agentic 浏览器控制（`browser_navigate`/`browser_snapshot`/`browser_click`/`browser_type`/`browser_get_text`/`browser_back`/`browser_screenshot`/`browser_close`）。进程内私有 loop-affine Playwright event-loop 线程；每步返回带稳定 `[ref]` 索引的页面快照；URL SSRF 过滤；可选 `cd backend && uv sync --extra browser && uv run playwright install chromium`。`GATEWAY_WORKERS > 1` 时禁止启用（无 thread affinity）。→ 深挖见 [06-browser-automation.md](06-browser-automation.md)。

> **LightRAG**（`group: knowledge`）：`knowledge_search` 的第二 provider（#5209），与 RAGFlow 二选一（按名去重，重名保留第一条）。检索自建 LightRAG 服务（v1.4.9+）的单一索引 workspace，`POST /query/data` 纯数据检索（无 LLM 生成），`mode: naive/local/global/hybrid/mix`（默认 mix）；API key 可选（`X-API-Key`）；结果格式化成与 RAGFlow 共享形状的带 `[N]` 引用编号紧凑文本，`chunk_id`/`reference_id` 永不进模型。→ 深挖见 [08-lightrag.md](08-lightrag.md)。

> **WeKnora**（`group: knowledge`，2.2.0 新增）：**可安装扩展**（`examples/deerflow-extension-weknora`），不写在 `community/` 里，而是通过 `registry.knowledge_provider("weknora", WeKnoraProvider(...))` 注册到扩展注册表，再用通用 `knowledge_search` 工具 + `provider: weknora` 接上。能力集为 `search/sources/catalog/documents/dataset_filter/document_filter/entries_search/entries_dataset_filter`——**刻意不声明** `relations_search`，`entries_search` 也**拒绝** `document_filters`（Wiki 页合并多份源文档，v0.8.3 的 search 端点无法按文档收窄）。授权靠 operator 写的 `spaces` 绑定（`user_ids` 精确匹配 + 可选 `agent_names` 精确匹配**当前执行者**），绑定不到就 `PermissionError` fail-closed。→ 深挖见 [09-knowledge-abstraction.md](09-knowledge-abstraction.md#十weknora可安装扩展-provider)。

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
4. **ToolConfig.extra="allow"**：`ToolConfig` Pydantic model 允许任意额外字段（`api_key`, `max_results`, `timeout`, 以及 2.2.0 起知识库工具的 `provider:` 等），各 tool 运行时通过 `config.tool_config("web_search").model_extra` 读取
5. **知识库工具的 provider 选择**（2.2.0 新增）：`use: deerflow.knowledge.tools:knowledge_search_tool` 只是「通用入口」，真正干活的是同一 `ToolConfig` 上的 `provider:` 字段——`knowledge/providers.py:127` 的 `_registered_provider()` 按这个名字去扩展注册表里找实例。`ragflow` / `lightrag` 是**保留名**，不能通过扩展顶替（`extensions/registry.py:157`）

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
├─ 自建图 RAG、单 workspace、检索策略切换 → LightRAG 🆕 → knowledge_search（与 RAGFlow 二选一）
└─ WeKnora 部署（含 Wiki 条目 + 多租户空间）→ WeKnora 扩展 🆕 → 通用 knowledge_search + provider: weknora
   （注意：与内置 memory 检索不同——这些接的都是 operator 建好的领域知识库，
     memory 记的是从对话里提取的 per-user fact。见 07-ragflow.md / 08-lightrag.md / 09-knowledge-abstraction.md）

需要读托管表格/爬取型 dataset（非网页、非知识库）?
└─ Jsonify 的只读 dataset rows 工具（URL 即凭证，永不由模型传入）
```

## 源码索引

| 目录 | 文件 |
|------|------|
| `community/ddg_search/` | `__init__.py`, `tools.py` |
| `community/serper/` | `__init__.py`, `tools.py` |
| `community/serply/` 🆕 | `__init__.py`, `tools.py` |
| `community/tencent_wsa/` 🆕 | `__init__.py`, `tools.py` |
| `community/sofya/` 🆕 | `__init__.py`, `tools.py` |
| `community/lightrag/` 🆕 | `__init__.py`, `client.py`, `formatting.py`（`CAPABILITIES = search+sources`）, `tools.py` |
| `knowledge/` 🆕 | `contract.py`, `providers.py`, `sources.py`, `tools.py`（2.2.0 统一只读检索契约） |
| `knowledge_scope.py` 🆕 | 版本化作用域快照（`canonicalize_knowledge_scope` / `execution_scope` / `strip_message_knowledge_scope`） |
| `community/search_time_range.py` 🆕 | 共享 recency filter 契约（day/week/month/year → 各 provider 映射） |
| `community/search_max_results.py` 🆕 | `coerce_max_results()`（ddg_search / image_search / fastcrw / firecrawl / youcom 共用；Booleans 与非整除 float 一律拒绝而非强转） |
| `community/provider_credentials.py` 🆕 | 凭证规则单一所有者：`resolve_api_key()` / `redact_secret()` / `reject_url_userinfo()` |
| `community/url_safety.py` | `safe_public_result_url()`（无 DNS 的结果 URL 过滤）、`validate_public_http_url()`、`validate_delegated_backend_url()` |
| `community/webz/` 🆕 | `__init__.py`, `tools.py` |
| `community/youcom/` 🆕 | `__init__.py`, `tools.py` |
| `community/unbrowse/` 🆕 | `__init__.py`, `tools.py` |
| `community/jsonify/` 🆕 | `__init__.py`, `tools.py` |
| `community/tavily/` | `tools.py` |
| `community/infoquest/` | `infoquest_client.py`, `tools.py` |
| `community/exa/` | `tools.py` |
| `community/firecrawl/` | `tools.py` |
| `community/jina_ai/` | `jina_client.py`, `tools.py` |
| `community/image_search/` | `__init__.py`, `tools.py` |
| `community/aio_sandbox/` | `__init__.py`, `aio_sandbox.py`, `aio_sandbox_provider.py`, `backend.py`, `local_backend.py`, `remote_backend.py`, `sandbox_info.py`, `ownership/`（跨实例租约）, `quarantine.py` 🆕（容器隔离/回收） |
| `community/browser_automation/` | `__init__.py`, `session.py`, `tools.py`, `egress.py` 🆕（出网守卫） |
| `community/ragflow/` | `__init__.py`, `client.py`, `formatting.py`, `tools.py`, `provider.py` 🆕（`RAGFlowKnowledgeProvider` 兼容适配器）, `sources.py` 🆕（legacy `#knowledge-` 命名空间预算） |
| `community/tenki/` | `__init__.py`, `provider.py`, `sandbox.py` |
| Tool 装配 | `tools/tools.py` → `get_available_tools()` |
| Async 包装 | `tools/sync.py` → `make_sync_tool_wrapper()` |
| Readability 提取 | `utils/readability.py` → `ReadabilityExtractor` |
