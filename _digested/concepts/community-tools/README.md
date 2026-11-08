---
title: "Community Tools — 外部工具集成"
description: "DeerFlow 通过 `community/` 目录集成了 25+ 个第三方工具 provider，覆盖 web 搜索、网页抓取、图片搜索、浏览器自动化、截图、只读知识库检索（统一 knowledge/ 契约 + RAGFlow/LightRAG 兼容适配器 + WeKnora 扩展）和沙箱。这些是 Agent 连接外部世界的主要通道。"
type: index
---

# Community Tools — 外部工具集成

DeerFlow 通过 `community/` 目录集成了 25+ 个第三方工具 provider，覆盖 web 搜索、网页抓取、图片搜索、浏览器自动化、截图、只读知识库检索（统一 `knowledge/` 契约 + RAGFlow/LightRAG 兼容适配器 + WeKnora 扩展）和沙箱。这些是 Agent 连接外部世界的主要通道。

**回答的核心问题**：12 种 web_search provider 有什么区别？web_fetch 怎么把网页转成 LLM 可读的文本？AioSandbox 的 Docker/K3s 适配是怎么做的？Browser Automation 怎么让 agent 操作真实浏览器？RAGFlow / LightRAG / WeKnora 怎么把外部私有知识库变成只读的 `knowledge_search` 工具，2.2.0 的 `knowledge/` 契约又统一了什么？

> **约束：不修改项目源代码。** 本 `_digested/` 下所有内容仅作研究记录。详见 [根 README](../README.md)。

## 阅读顺序

| 文件 | 内容 |
|------|------|
| **00-overview.md** | 全景：25+ 个集成在 tool 装配中的位置、provider 选择决策树、对比矩阵 |
| **01-web-search.md** | 12 种 search provider：DDG、Tavily、Serper、Serply、Tencent WSA、Sofya、Exa、Firecrawl、InfoQuest、GroundRoute、fastCRW、SearXNG 外加 2.2.0 新增 Webz / You.com 的差异与选型；共享 `coerce_max_results` 与原生 recency filters |
| **02-web-fetch.md** | 7 种 fetch provider：Jina AI、Exa、InfoQuest、Firecrawl（self-host）、Sofya、Unbrowse（2.2.0 新增）的 URL-to-markdown 管线 |
| **03-image-search.md** | DDG / Brave / InfoQuest 图片搜索的返回格式与 vision model 对接 |
| **04-aio-sandbox.md** | AioSandboxProvider 深入：Docker 容器管理、Apple Container 探测、LRU 淘汰、K3s provisioner 模式、2.2.0 新增的容器隔离（`quarantine.py`） |
| **05-how-to-add-provider.md** | 如何添加新的 tool provider：目录结构、tool 函数、认证、config.yaml 注册、测试；2.2.0 起还覆盖**知识库 provider**（`registry.knowledge_provider`）的注册路径 |
| **06-browser-automation.md** | Browser Automation 深入：Playwright 会话、loop-affine 线程、`[ref]` 快照、SSRF 过滤；2.2.0 新增的 `egress.py` 出网守卫 |
| **07-ragflow.md** | RAGFlow 深入：只读 `knowledge_search`、dataset 白名单、embedding 分组并行检索、引用编号格式化、与 memory 检索的区别；2.2.0 起它同时是 `RAGFlowKnowledgeProvider` 兼容适配器 |
| **08-lightrag.md** | LightRAG 深入：`knowledge_search` 第二 provider（与 RAGFlow 二选一）、`/query/data` 只读检索、mode 五档、v1.4.9+ 版本探测、X-API-Key 可选认证 |
| **09-knowledge-abstraction.md** 🆕 | `deerflow/knowledge/` 统一只读检索契约：capabilities、稳定 source ID 与引用语法、字符预算、跨子 agent 转发、`knowledge_scope.py` 作用域快照、`registry.knowledge_provider()` 注册口，以及 WeKnora 可安装扩展 provider |

## 关键问题

- 9 种 web_search 怎么选？→ `01-web-search.md` 对比矩阵
- web_fetch 怎么把任意网页变成 markdown？→ `02-web-fetch.md` 转换管线
- AioSandbox 的 Docker 和 K3s 模式有什么区别？→ `04-aio-sandbox.md`
- 这些 tool 是怎么注入到 Agent Loop 的？→ `00-overview.md` 装配流程
- 为什么 AioSandbox 放在 community/ 而不是 sandbox/？→ `04-aio-sandbox.md`
- 怎么让 agent 操作真实浏览器并拿到稳定的元素句柄？→ `06-browser-automation.md`
- RAGFlow 的 `knowledge_search` 和内置 memory 检索有什么区别？→ `07-ragflow.md`
- RAGFlow 和 LightRAG 怎么选、怎么切换？→ `08-lightrag.md`（对比表）
- 2.2.0 之后一个知识库 provider 要满足什么契约、引用 ID 为什么稳定、作用域怎么收窄？→ `09-knowledge-abstraction.md`
- 新 provider（Webz / You.com / Unbrowse / Jsonify / WeKnora）怎么接入？→ `00-overview.md` 矩阵 + `05-how-to-add-provider.md`

## 源文件索引

| 组件 | 路径 |
|------|------|
| DDG 搜索 | `packages/harness/deerflow/community/ddg_search/` |
| Tavily 搜索 | `packages/harness/deerflow/community/tavily/` |
| Serper 搜索 | `packages/harness/deerflow/community/serper/` |
| Exa 搜索/抓取 | `packages/harness/deerflow/community/exa/` |
| Firecrawl 搜索/抓取 | `packages/harness/deerflow/community/firecrawl/` |
| InfoQuest 搜索/抓取/图片 | `packages/harness/deerflow/community/infoquest/` |
| Jina AI 抓取 | `packages/harness/deerflow/community/jina_ai/` |
| 图片搜索 | `packages/harness/deerflow/community/image_search/` |
| Brave Image 🆕 | `packages/harness/deerflow/community/brave/` |
| GroundRoute 🆕 | `packages/harness/deerflow/community/groundroute/` |
| Crawl4AI 🆕 | `packages/harness/deerflow/community/crawl4ai/` |
| fastCRW 🆕 | `packages/harness/deerflow/community/fastcrw/` |
| Browserless 🆕 | `packages/harness/deerflow/community/browserless/` |
| SearXNG | `packages/harness/deerflow/community/searxng/` |
| **RAGFlow** 🆕 | `packages/harness/deerflow/community/ragflow/`（只读知识库检索） |
| **LightRAG** 🆕 | `packages/harness/deerflow/community/lightrag/`（只读知识库检索，knowledge_search 第二 provider） |
| **knowledge/ 契约** 🆕 | `packages/harness/deerflow/knowledge/`（contract/providers/sources/tools）+ `knowledge_scope.py`（2.2.0 统一只读检索抽象） |
| **WeKnora 扩展** 🆕 | `examples/deerflow-extension-weknora/`（可安装扩展，注册 `knowledge_provider("weknora", ...)`） |
| **Serply** 🆕 | `packages/harness/deerflow/community/serply/`（Google 搜索 + News/Scholar 垂直） |
| **Webz** 🆕 | `packages/harness/deerflow/community/webz/`（Webz.io News Search，2.2.0 新增） |
| **You.com** 🆕 | `packages/harness/deerflow/community/youcom/`（无 key 走 `/v1/agents/search`，有 `YDC_API_KEY` 走 `/v1/search`，2.2.0 新增） |
| **Sofya** 🆕 | `packages/harness/deerflow/community/sofya/`（整页内容搜索 + markdown fetch） |
| **Tencent Cloud WSA** 🆕 | `packages/harness/deerflow/community/tencent_wsa/`（腾讯云 Web Search API） |
| **search_time_range** 🆕 | `packages/harness/deerflow/community/search_time_range.py`（共享 recency filter 契约） |
| **search_max_results** 🆕 | `packages/harness/deerflow/community/search_max_results.py`（`coerce_max_results()`：ddg/image/fastcrw/firecrawl/youcom 共用的 max_results 归一化） |
| **Unbrowse** 🆕 | `packages/harness/deerflow/community/unbrowse/`（MCP `unbrowse.scrape` 网页转 markdown，2.2.0 新增） |
| **Jsonify** 🆕 | `packages/harness/deerflow/community/jsonify/`（只读 dataset rows 工具，URL 即凭证，2.2.0 新增） |
| **provider_credentials** 🆕 | `packages/harness/deerflow/community/provider_credentials.py`（`resolve_api_key` / `redact_secret` / `reject_url_userinfo` 单一所有者） |
| **Browser Automation** 🆕 | `packages/harness/deerflow/community/browser_automation/`（Playwright agentic session） |
| AIO 沙箱 | `packages/harness/deerflow/community/aio_sandbox/` |
| BoxLite 沙箱 | `packages/harness/deerflow/community/boxlite/` |
| E2B 沙箱 | `packages/harness/deerflow/community/e2b_sandbox/` |
| **Tenki 沙箱** 🆕 | `packages/harness/deerflow/community/tenki/`（云 micro-VM，懒加载 SDK） |
| Warm pool 共享生命周期 | `packages/harness/deerflow/community/warm_pool_lifecycle.py` |
| URL 安全校验 | `packages/harness/deerflow/community/url_safety.py` |
| Tool 装配入口 | `packages/harness/deerflow/tools/tools.py:get_available_tools()` |