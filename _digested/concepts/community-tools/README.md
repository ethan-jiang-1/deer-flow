---
title: "Community Tools — 外部工具集成"
description: "25+ 个第三方 provider：web 搜索、网页抓取、图片搜索、浏览器自动化、只读知识库与沙箱。"
type: index
topics: [tools, integration, knowledge, provider]
---

# Community Tools — 外部工具集成

> **定位**：Agent 连接外部世界的通道。`deerflow/community/` 下 25+ 个 provider 怎么选、怎么调、怎么注册，以及 2.2.0 把只读知识库检索统一成 `knowledge/` 契约之后的接法。给选 provider、加 provider、排查外部调用失败的人。
> **边界**：不覆盖装配顺序与同名去重（见 [builtin-tools](../builtin-tools/README.md)），不覆盖沙箱抽象、租约与隔离（见 [sandbox](../sandbox/README.md)），不覆盖 MCP server 的会话与鉴权（见 [internals/mcp](../../internals/mcp/README.md)）。

## 阅读路径

1. **先看**：[00-overview.md](00-overview.md) — 25+ 集成在 tool 装配中的位置、provider 选择决策树与对比矩阵。
2. **再看**：[01-web-search.md](01-web-search.md) — 12 种 search provider（含 2.2 新增的 Webz / You.com）的差异与选型。
3. **深入**：[09-knowledge-abstraction.md](09-knowledge-abstraction.md) — `knowledge/` 契约：capabilities、稳定 source ID 与引用语法、字符预算、作用域快照。

## 本篇目

| 文件 | 主题 | 深度 |
|---|---|---|
| [00-overview.md](00-overview.md) | 全景：装配位置、provider 决策树与对比矩阵 | 概览 |
| [01-web-search.md](01-web-search.md) | 12 种 search provider 的接口、结果形态、recency / max_results 契约 | 深入 |
| [02-web-fetch.md](02-web-fetch.md) | 7 种 URL → Markdown 抓取管线（含 Unbrowse、Jina 准入） | 深入 |
| [03-image-search.md](03-image-search.md) | DDG / Brave / InfoQuest 图片搜索与 `view_image` 对接 | 概览 |
| [04-aio-sandbox.md](04-aio-sandbox.md) | AioSandboxProvider：Docker / Apple Container / K3s、LRU、`quarantine.py` | 深入 |
| [05-how-to-add-provider.md](05-how-to-add-provider.md) | 新增 provider：目录、tool 函数、认证、注册与测试（含知识库 provider） | 概览 |
| [06-browser-automation.md](06-browser-automation.md) | Playwright agentic 会话：`[ref]` 快照、loop-affine 线程、SSRF 与 `egress.py` | 深入 |
| [07-ragflow.md](07-ragflow.md) | RAGFlow：dataset 白名单、分组并行检索、引用编号、与 memory 检索的区别 | 深入 |
| [08-lightrag.md](08-lightrag.md) | LightRAG：`/query/data` 只读检索、mode 五档、版本探测、与 RAGFlow 二选一 | 深入 |
| [09-knowledge-abstraction.md](09-knowledge-abstraction.md) | `knowledge/` 统一契约 + `knowledge_scope` + WeKnora 扩展 provider | 深入 |

## 速览

- **覆盖面**：12 个 web_search、7 个 web_fetch、3 个 image_search（DDG / Brave / InfoQuest），加浏览器自动化、4 个沙箱 provider（AIO / BoxLite / E2B / Tenki）与 2 个只读知识库（RAGFlow / LightRAG，二选一）。
- **共享契约**：`provider_credentials.py`（`resolve_api_key` / `redact_secret` / `reject_url_userinfo` 的单一所有者）、`search_time_range.py`（recency filter）、`search_max_results.py`（`coerce_max_results()`）、`url_safety.py`、`warm_pool_lifecycle.py`；同处 `backend/packages/harness/deerflow/community/`。
- **2.2.0 新增**：Webz、You.com、Unbrowse、Jsonify、WeKnora，以及 `deerflow/knowledge/` 契约（contract / providers / sources / tools）与 `knowledge_scope.py`。
- **注册两条路**：普通工具经 `config.yaml` 的 `tools[]` 选 provider、装配后同名暴露；知识库 provider 还可走 `registry.knowledge_provider()`（见 05 与 09）。

## 宪章与约定

- 本目录无独立宪章；研究纪律沿用 [根 README](../../README.md)（不修改源码、`main` 只镜像上游、笔记只落在 `ethan`）。
- 每个 provider 的源码目录与函数锚点写在对应分册正文（如 `community/ddg_search/tools.py`、`community/ragflow/`），README 不再维护逐条清单。

## 相关目录

- [builtin-tools/](../builtin-tools/README.md) — 这些工具在总装配顺序里的位置与去重规则。
- [sandbox/](../sandbox/README.md) — AIO / BoxLite / E2B / Tenki 在统一抽象下的位置与租约。
- [internals/mcp/](../../internals/mcp/README.md) — MCP 工具的会话池、OAuth 与缓存失效。
- [projects/](../projects/README.md) — 项目 document shelf 与知识库检索的分工。
