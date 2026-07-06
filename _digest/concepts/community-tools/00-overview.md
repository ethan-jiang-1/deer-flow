---
title: "社区工具集成全景"
description: "DeerFlow 在 `deerflow/community/` 下集成了 9 个外部工具 provider，覆盖 web 搜索、网页抓取、图片搜索和沙箱隔离。"
topics: [tools, community, external-integration]
---

# 社区工具集成全景

DeerFlow 在 `deerflow/community/` 下集成了 9 个外部工具 provider，覆盖 web 搜索、网页抓取、图片搜索和沙箱隔离。

## 集成矩阵

| 集成 | 类型 | 需要 API Key | Async? | 默认启用 |
|------|------|------------|--------|---------|
| **DuckDuckGo Search** | web_search | 否 | 否 | 是 |
| **Serper** | web_search | `SERPER_API_KEY` | 否 | 否 |
| **Tavily** | web_search + web_fetch | config `api_key` | 否 | 否 |
| **InfoQuest** | web_search + web_fetch + image_search | `INFOQUEST_API_KEY` | 否 | 否 |
| **Exa** | web_search + web_fetch | config `api_key` | 否 | 否 |
| **Firecrawl** | web_search + web_fetch | config `api_key` | 否 | 否 |
| **Jina AI** | web_fetch | `JINA_API_KEY`（可选） | **是** | 是 |
| **DuckDuckGo Image** | image_search | 否 | 否 | 是 |
| **AIO Sandbox** | sandbox | 否 | N/A | 否 |

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
├─ Google 搜索结果质量 → Serper (需 SERPER_API_KEY)
├─ 需要 search + fetch 一体化 → Tavily / Exa / Firecrawl / InfoQuest
│   ├─ Tavily → 简洁 API，AI 优化搜索结果
│   ├─ Exa → 语义搜索，支持内容高亮
│   ├─ Firecrawl → 搜索 + scrape markdown 一体化
│   └─ InfoQuest → 字节跳动内部，中文场景优化
└─ 需要 search + fetch + image search → InfoQuest

需要 web fetch (URL→markdown)?
├─ 免费/零配置 → Jina AI (r.jina.ai，无需 key 但有频率限制)
├─ 需要高质量可读性提取 → Jina AI 或 InfoQuest (都走 ReadabilityExtractor)
├─ 已有 search provider → Tavily/Exa/Firecrawl 都自带 fetch
└─ 格式需求 → Firecrawl 直接返回 markdown（无需本地转换）

需要 image search?
├─ 免费 → DDG Image Search
└─ 付费/中文场景 → InfoQuest Image Search (需 INFOQUEST_API_KEY)
```

## 源码索引

| 目录 | 文件 |
|------|------|
| `community/ddg_search/` | `__init__.py`, `tools.py` |
| `community/serper/` | `__init__.py`, `tools.py` |
| `community/tavily/` | `tools.py` |
| `community/infoquest/` | `infoquest_client.py`, `tools.py` |
| `community/exa/` | `tools.py` |
| `community/firecrawl/` | `tools.py` |
| `community/jina_ai/` | `jina_client.py`, `tools.py` |
| `community/image_search/` | `__init__.py`, `tools.py` |
| `community/aio_sandbox/` | `__init__.py`, `aio_sandbox.py`, `aio_sandbox_provider.py`, `backend.py`, `local_backend.py`, `remote_backend.py`, `sandbox_info.py` |
| Tool 装配 | `tools/tools.py` → `get_available_tools()` |
| Async 包装 | `tools/sync.py` → `make_sync_tool_wrapper()` |
| Readability 提取 | `utils/readability.py` → `ReadabilityExtractor` |
