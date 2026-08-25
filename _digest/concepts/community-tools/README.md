---
title: "Community Tools — 外部工具集成"
description: "DeerFlow 通过 `community/` 目录集成了 15+ 个第三方工具 provider，覆盖 web 搜索、网页抓取、图片搜索、浏览器自动化、截图、知识库检索（RAGFlow）和沙箱。这些是 Agent 连接外部世界的主要通道。"
type: index
---

# Community Tools — 外部工具集成

DeerFlow 通过 `community/` 目录集成了 15+ 个第三方工具 provider，覆盖 web 搜索、网页抓取、图片搜索、浏览器自动化、截图、知识库检索（RAGFlow）和沙箱。这些是 Agent 连接外部世界的主要通道。

**回答的核心问题**：6 种 web_search provider 有什么区别？web_fetch 怎么把网页转成 LLM 可读的文本？AioSandbox 的 Docker/K3s 适配是怎么做的？Browser Automation 怎么让 agent 操作真实浏览器？RAGFlow 怎么把外部私有知识库变成只读的 `knowledge_search` 工具？

> **约束：不修改项目源代码。** 本 `_digest/` 下所有内容仅作研究记录。详见 [根 README](../README.md)。

## 阅读顺序

| 文件 | 内容 |
|------|------|
| **00-overview.md** | 全景：15+ 个集成在 tool 装配中的位置、provider 选择决策树、对比矩阵 |
| **01-web-search.md** | 6 种 search provider：DDG、Tavily、Serper、Exa、Firecrawl、InfoQuest 的差异与选型 |
| **02-web-fetch.md** | 4 种 fetch provider：Jina AI、Exa、InfoQuest、Firecrawl 的 URL-to-markdown 管线 |
| **03-image-search.md** | DDG / InfoQuest 图片搜索的返回格式与 vision model 对接 |
| **04-aio-sandbox.md** | AioSandboxProvider 深入：Docker 容器管理、Apple Container 探测、LRU 淘汰、K3s provisioner 模式 |
| **05-how-to-add-provider.md** 🆕 | 如何添加新的 tool provider：目录结构、tool 函数、认证、config.yaml 注册、测试 |
| **06-browser-automation.md** 🆕 | Browser Automation 深入：Playwright 会话、loop-affine 线程、`[ref]` 快照、SSRF 过滤 |
| **07-ragflow.md** 🆕 | RAGFlow 深入：只读 `knowledge_search`、dataset 白名单、embedding 分组并行检索、引用编号格式化、与 memory 检索的区别 |

## 关键问题

- 6 种 web_search 怎么选？→ `01-web-search.md` 对比矩阵
- web_fetch 怎么把任意网页变成 markdown？→ `02-web-fetch.md` 转换管线
- AioSandbox 的 Docker 和 K3s 模式有什么区别？→ `04-aio-sandbox.md`
- 这些 tool 是怎么注入到 Agent Loop 的？→ `00-overview.md` 装配流程
- 为什么 AioSandbox 放在 community/ 而不是 sandbox/？→ `04-aio-sandbox.md`
- 怎么让 agent 操作真实浏览器并拿到稳定的元素句柄？→ `06-browser-automation.md`
- RAGFlow 的 `knowledge_search` 和内置 memory 检索有什么区别？→ `07-ragflow.md`

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
| **Browser Automation** 🆕 | `packages/harness/deerflow/community/browser_automation/`（Playwright agentic session） |
| AIO 沙箱 | `packages/harness/deerflow/community/aio_sandbox/` |
| BoxLite 沙箱 | `packages/harness/deerflow/community/boxlite/` |
| E2B 沙箱 | `packages/harness/deerflow/community/e2b_sandbox/` |
| **Tenki 沙箱** 🆕 | `packages/harness/deerflow/community/tenki/`（云 micro-VM，懒加载 SDK） |
| Warm pool 共享生命周期 | `packages/harness/deerflow/community/warm_pool_lifecycle.py` |
| URL 安全校验 | `packages/harness/deerflow/community/url_safety.py` |
| Tool 装配入口 | `packages/harness/deerflow/tools/tools.py:get_available_tools()` |