---
title: "MCP 深度解析 — Session Pool、OAuth、缓存"
description: "- `deerflow/mcp/cache.py` (159 行) — 惰性初始化、mtime 缓存失效"
topics: [mcp, tools, protocol-integration]
---

# MCP 深度解析 — Session Pool、OAuth、缓存

## 相关文件

- `deerflow/mcp/cache.py` (159 行) — 惰性初始化、mtime 缓存失效
- `deerflow/mcp/oauth.py` (151 行) — OAuth TokenManager、双检查锁、header 注入
- `deerflow/mcp/session_pool.py` (199 行) — 持久会话池、LRU 淘汰、跨线程安全
- `deerflow/mcp/client.py` (69 行) — 传输类型路由、服务器配置构建
- `deerflow/mcp/tools.py` (~50 行) — 通过 MultiServerMCPClient 加载工具

## MCP 工具生命周期全景

```mermaid
flowchart TD
    CONFIG[extensions_config.json] -->|mtime 变化检测| CACHE{get_cached_mcp_tools}
    CACHE -->|缓存命中| TOOLS[返回工具列表]
    CACHE -->|缓存过期/为空| BUILD[build_servers_config]

    BUILD --> SPAWN[MultiServerMCPClient.spawn_servers]
    SPAWN --> TOOLS2[get_tools]

    subgraph Session Pool
        SPAWN --> POOL[MCPSessionPool]
        POOL -->|范围: server_name, scope_key| SCOPE[stateful sessions]
        POOL -->|LRU 256 条| EVICT[淘汰 old sessions]
        POOL -->|跨线程 Lock| LOCK[threading.Lock]
    end

    subgraph OAuth
        SPAWN --> OAUTH[OAuthTokenManager]
        OAUTH -->|缓存 token| TOK[每个 server 的 token]
        OAUTH -->|自动刷新| REFRESH[refresh_skew_seconds 窗口]
        OAUTH -->|双检查锁| DCL[防止并发刷新]
    end

    TOOLS2 -->|工具去重| DEDUP[seen_names 集合]
    DEDUP -->|缓存结果| CACHE2[更新缓存]
    CACHE2 --> TOOLS3[返回工具]
```

## Session Pool (`session_pool.py`)

### 为什么需要持久会话

部分 MCP 服务器是**有状态的**：
- Playwright MCP 在工具调用之间维护浏览器状态
- 数据库 MCP 保持连接池

无会话池的情况下，每个请求都会创建/销毁 MCP 连接，丢失状态并产生不必要的开销。

### 设计

```python
class MCPSessionPool:
    _sessions: dict[tuple[str, str], Any]  # (server_name, scope_key) → session
    _lock: threading.Lock                   # async + sync 路径安全
    _max_size: int = 256                    # LRU 上限
```

- **范围键** `scope_key` 通常为 `thread_id` — 同一线程的工具调用复用同一会话
- **LRU 淘汰** — 当会话数超过 256 时，最久未使用的被关闭
- **跨事件循环处理** — 如果会话属于不同的事件循环（在 asyncio 下），会话会被替换而不是崩溃
- **`close_all_sync()`** — 跨事件循环边界优雅关闭
- **每范围 close** — `close_scope(scope_key)` 用于线程清理

### 线程安全

`threading.Lock` 保护所有变更操作。此选择的原因：
1. 工具调用在 `asyncio.to_thread` 中运行（离开主事件循环）
2. MCP 客户端方法可能是同步的
3. 简单的 `asyncio.Lock` 会导致跨线程数据竞争

## OAuth Token 管理 (`oauth.py`)

### 支持的授权类型

| 授权类型 | `grant_type` | 说明 |
|---------|-------------|------|
| `client_credentials` | `"client_credentials"` | 无需刷新 token |
| `refresh_token` | `"refresh_token"` | 初始 token + 自动刷新 |

### Token 生命周期

```mermaid
sequenceDiagram
    participant TOOL as Tool Call
    participant TM as OAuthTokenManager
    participant CACHE as Token Cache
    participant AUTH as Auth Server
    participant MCP as MCP Server

    TOOL->>TM: build_oauth_tool_interceptor(server_name)
    TM->>CACHE: get cached token
    CACHE-->>TM: token (可能过期)

    alt 无 token 或已过期
        TM->>AUTH: POST /token (client_credentials or refresh_token)
        AUTH-->>TM: {access_token, refresh_token, expires_in}
        TM->>CACHE: 更新缓存
    else 未过期但在 refresh_skew_seconds 内
        TM->>AUTH: POST /token (refresh_token)
        AUTH-->>TM: 新 token
        TM->>CACHE: 更新缓存
    end

    TM-->>TOOL: interceptor function
    TOOL->>MCP: Authorization: Bearer {token}
```

### 关键设计细节

- **refresh_skew_seconds** — 如果 token 在 skew 窗口内过期，主动刷新以避免竞态
- **双检查锁定模式** (`_lock` + `_refresh_locks[server]`) — 防止多个并发工具调用同时刷新同一 token
- **`get_initial_oauth_headers()`** — 用于 MCP 连接设置，与 tool 调用授权分离

## 缓存失效 (`cache.py`)

### 惰性初始化

`get_cached_mcp_tools()` 使用惰性加载模式：

```python
_cache: dict | None = None
_cache_mtime: float = 0

async def get_cached_mcp_tools():
    if _cache is None or _is_cache_stale():
        await _init_cache()
    return _cache
```

### mtime 过期检测

`_is_cache_stale()` 比较 `extensions_config.json` 的 `os.path.getmtime()` 与缓存的 mtime。

### 异步安全初始化

在活跃事件循环内调用 `get_cached_mcp_tools()` 时：
1. 检查 `asyncio.get_event_loop()`
2. 如果循环正在运行但不在异步上下文中 → 使用 `ThreadPoolExecutor` 回退
3. 如果已经在异步上下文中 → 直接调用异步初始化

### 重置集成

`reset_mcp_tools_cache()` 在以下时机被调用：
- 通过 Gateway API 更新 MCP 配置
- `DeerFlowClient.update_mcp_config()`
- 会话池关闭

## 工具加载 (`tools.py`)

`get_mcp_tools()` 流：

```
1. 构建 server params（传输类型路由：stdio/sse/http）
2. 构建拦截器（OAuth header 注入）
3. 实例化 MultiServerMCPClient
4. 调用 client.get_tools() → 返回 List[StructuredTool]
```

所有 MCP 工具都包装为标准 LangChain `StructuredTool` 对象，与 DeerFlow 工具注册管道完全兼容。

## 传输类型

| 类型 | `type` 值 | 示例 |
|------|----------|------|
| **stdio** | `"stdio"` | 本地命令：`command: python`, `args: [-m, my_mcp]` |
| **SSE** | `"sse"` | 远程 SSE：`url: https://mcp.example.com/sse` |
| **HTTP** | `"http"` | 远程 HTTP：`url: https://mcp.example.com/mcp` |

OAuth 支持目前仅用于 `sse` 和 `http` 传输类型。
