---
title: "MCP 拦截器 + 扩展配置：interceptor 链 + Gateway 写回"
description: "- `deerflow/mcp/tools.py:173-285` — `get_mcp_tools()` 工具加载"
topics: [hooks, extension, plugin-system]
---

# MCP 拦截器 + 扩展配置：interceptor 链 + Gateway 写回

**核心文件：**
- `deerflow/mcp/tools.py:173-285` — `get_mcp_tools()` 工具加载
- `deerflow/mcp/oauth.py` — OAuth interceptor
- `deerflow/config/extensions_config.py` — ExtensionsConfig 单例 + 热重载
- `deerflow/mcp/session_pool.py` — Session pool 管理

MCP（Model Context Protocol）工具是 DeerFlow 最主要的扩展入口。用户添加 MCP server → tools 出现在 agent 的工具列表中。这个过程涉及**两个进程**（Gateway API 和 LangGraph runtime）通过文件通信。

## extensions_config.json 结构

```json
{
  "mcpServers": {
    "playwright": {
      "enabled": true,
      "type": "stdio",
      "command": "npx",
      "args": ["-y", "@anthropic-ai/mcp-playwright"],
      "env": {},
      "description": "Browser automation"
    },
    "github": {
      "enabled": true,
      "type": "http",
      "url": "https://api.github.com/mcp",
      "headers": {},
      "oauth": {
        "enabled": true,
        "token_url": "https://github.com/login/oauth/access_token",
        "client_id": "$GITHUB_CLIENT_ID",
        "client_secret": "$GITHUB_CLIENT_SECRET"
      }
    }
  },
  "skills": {
    "my-skill": {"enabled": true}
  },
  "mcpInterceptors": [
    "my_package.interceptors:build_logging_interceptor"
  ]
}
```

## 跨进程配置同步管道

```
Gateway API (FastAPI, port 8001)
    │
    │  PUT /api/mcp/config
    │  → 写 extensions_config.json
    │
    ▼
[extensions_config.json 文件]
    │
    │  下次 agent run 时:
    │
    ▼
LangGraph Runtime (单独进程)
    │
    │  get_mcp_tools()
    │  → ExtensionsConfig.from_file()  ← 直接读磁盘，不用单例缓存！
    │
    ▼
MultiServerMCPClient → 新 tools 加载
```

**关键设计决策：** `get_mcp_tools()` 故意调用 `ExtensionsConfig.from_file()` 而不是 `get_extensions_config()`：

```python
# mcp/tools.py:194
# NOTE: We use ExtensionsConfig.from_file() instead of get_extensions_config()
# to always read the latest configuration from disk. This ensures that changes
# made through the Gateway API (which runs in a separate process) are immediately
# reflected when initializing MCP tools.
extensions_config = ExtensionsConfig.from_file()
```

`get_extensions_config()` 是一个 cached singleton，它不会自动检测 mtime 变化（不像 `get_app_config()`）。在同一个进程内这没问题——但 Gateway API 和 LangGraph runtime 是**不同进程**，Gateway 写回文件后，LangGraph 进程的 `get_extensions_config()` 缓存是旧的。直接读磁盘解决了这个问题。

## MCP Interceptor 链

Interceptor 是在 MCP tool 调用周围包裹的中间件。格式类似于 middleware 但更轻量：

```python
from langchain_mcp_adapters.interceptors import MCPToolCallRequest

async def my_interceptor(request: MCPToolCallRequest, handler):
    """在每个 MCP tool 调用前后执行"""
    print(f"Before: {request.name}({request.args})")
    result = await handler(request)  # 调用下一个 interceptor 或真正的 tool
    print(f"After: {request.name}")
    return result
```

### 加载流程（`mcp/tools.py:220-242`）

1. **OAuth interceptor** — 自动构建（如果 MCP server 配置了 oauth）
2. **Custom interceptors** — 从 `extensions_config.json` 的 `mcpInterceptors` 字段读取
3. **每个 interceptor 路径** → `resolve_variable(path)` → `builder()` → 检查 callable
4. **全部 interceptor 传给 `MultiServerMCPClient(tool_interceptors=...)`**

```python
tool_interceptors = []

# 1. OAuth
oauth_interceptor = build_oauth_tool_interceptor(extensions_config)
if oauth_interceptor:
    tool_interceptors.append(oauth_interceptor)

# 2. Custom
raw_paths = extensions_config.model_extra.get("mcpInterceptors", [])
for path in raw_paths:
    builder = resolve_variable(path)
    interceptor = builder()
    if callable(interceptor):
        tool_interceptors.append(interceptor)

# 3. 传给 client
client = MultiServerMCPClient(servers_config, tool_interceptors=tool_interceptors)
```

## OAuth 自动注入

配置了 `oauth` 的 HTTP/SSE MCP server 会自动获得两个阶段的认证：

1. **连接时**（`get_initial_oauth_headers()`）：获取 access token → 注入 `Authorization` header
2. **每次 tool 调用**（`build_oauth_tool_interceptor()`）：如果 token 快过期 → 自动刷新

```python
# extensions_config.json 中的 OAuth 配置
"oauth": {
    "enabled": true,
    "token_url": "https://...",
    "grant_type": "client_credentials",  # or "refresh_token"
    "client_id": "$MY_CLIENT_ID",
    "refresh_skew_seconds": 60  # 提前 60s 刷新
}
```

## Session Pool（stdio transport）

Stdio MCP server 的 session 被 pool 化（`session_pool.py`），key 为 `(server_name, thread_id)`。同一 thread 内的连续 tool call 复用同一个 MCP session。这对有状态的 MCP server（如 Playwright）至关重要——同一 browser session 跨 tool call 保持打开。

## Gateway API → 文件 → LangGraph 的完整路径

1. 用户在 Web UI 或 API 上修改 MCP 配置
2. `PUT /api/mcp/config` → `routers/mcp.py` → 写 `extensions_config.json`
3. 下次 agent run 时，`get_mcp_tools()` 调用 `ExtensionsConfig.from_file()` 从磁盘读
4. `MultiServerMCPClient` 用新配置初始化，加载新工具
5. Agent 看到更新后的工具列表

**时效性：** 不是即时的——在下一次 agent run 开始前，已经在进行的 run 继续用旧工具。这是合理的权衡：一个 run 中途换工具会导致 schema 不一致。
