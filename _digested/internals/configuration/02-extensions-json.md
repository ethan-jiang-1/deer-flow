---
title: "ExtensionsConfig — MCP 与 Skills 配置"
description: "`extensions_config.json` 是独立的 JSON 配置文件，管理 MCP server 连接和 skills 启用/禁用状态。与 `config.yaml` 不同，它是**可选的** — 找不到就返回空配置。"
topics: [configuration, hot-reload, yaml-config]
---

# ExtensionsConfig — MCP 与 Skills 配置

`extensions_config.json` 是独立的 JSON 配置文件，管理 MCP server 连接和 skills 启用/禁用状态。与 `config.yaml` 不同，它是**可选的** — 找不到就返回空配置。

## 数据结构

```python
class ExtensionsConfig(BaseModel):      # model_config = ConfigDict(extra="allow", populate_by_name=True)
    middlewares: list[str | ConfiguredMiddlewareSpec] = []   # extensions_config.py:398
    mcp_servers: dict[str, McpServerConfig]  # Field(alias="mcpServers")  extensions_config.py:407
    skills: dict[str, SkillStateConfig]      # extensions_config.py:412
    # mcpInterceptors 不在 schema 里，落在 model_extra：
    #   ["pkg.mod:build_interceptor", ...] 由 mcp/interceptors.py:18 的 build_mcp_tool_interceptors()
    #   在 mcp/interceptors.py:48 从 model_extra 里取，非字符串列表只警告并跳过
```

### McpServerConfig

| 字段 | 类型 | 用途 |
|------|------|------|
| `enabled` | `bool` | 开关 |
| `type` | `str` | `"stdio"` / `"sse"` / `"http"` |
| `command` | `str` | stdio: 启动命令 |
| `args` | `list[str]` | stdio: 命令参数 |
| `env` | `dict` | 注入的环境变量 |
| `url` | `str` | SSE/HTTP: 连接 URL |
| `headers` | `dict` | HTTP 头 |
| `oauth` | `McpOAuthConfig` | HTTP/SSE: OAuth2 token 流程 |
| `description` | `str` | 描述（给 LLM 看） |

`oauth` 支持 `client_credentials` 和 `refresh_token` 两种 grant，token 自动刷新。

### SkillStateConfig

```json
{
  "skills": {
    "my-custom-skill": { "enabled": true },
    "code-review": { "enabled": false }
  }
}
```

只有 `enabled: bool` 一个字段。未在 JSON 中列出的 skill 默认启用，覆盖 `public` / `custom` / `legacy` / `integrations` 四个类别（`extensions_config.py:622-626`）。

---

## 文件可选 + 宽松 env var

与 AppConfig 的两个关键差异：

```python
# ExtensionsConfig.from_file() — 找不到不报错
resolved_path = cls.resolve_config_path(config_path)
if resolved_path is None:
    return cls(mcp_servers={}, skills={})   # 空配置

# env var 解析 — 宽松模式
value = os.getenv(env_key, "")  # 不存在就是空串
```

MCP server 的 `env` 字段可能包含可选变量，缺失不应阻止进程启动。而 AppConfig 的 `$OPENAI_API_KEY` 缺失应该立即报错。

---

## 缓存策略 — 无自动 reload

```python
# extensions_config.py:642 起的模块级状态
_extensions_config: ExtensionsConfig | None = None
_extensions_config_path: Path | None = None
_extensions_config_signature: ConfigSignature | None = None   # (mtime, size, sha256)
_extensions_config_is_custom = False
```

**🔄 v2.2.0 起这里也做自动 revalidation**（`get_extensions_config()`，`extensions_config.py:883`）。v2.1.0 那次"没有 mtime 自动检测、只能手动 reload"的表述**已删除**——现行语义是：

- 每次调用都重新解析路径 + 文件的 `(mtime, size, sha256)` 签名，与缓存值比较；变了就重载。理由写在 `extensions_config.py:628-641` 的注释里：多 worker / 多实例部署时，**写文件的进程通常不是随后读它的进程**，各进程共享同一个卷上的 `extensions_config.json`；写方显式 reload 自己，其它方必须靠自己发现变化。而且 local-bash 的绝对路径白名单就是从这份缓存派生的，读到陈旧副本不只是工具列表过期，而是**副本之间的安全漂移**。
- 一旦成功加载过，后续"读失败"（文件消失、被非原子覆盖写截断、内容非法）会**保留最后一次好配置**并只记一次日志；**首次加载仍抛错**，所以启动期的坏配置照样响。
- `set_extensions_config()` 注入的实例被钉住，直到 `reload_extensions_config()`（`extensions_config.py:995`）或 `reset_extensions_config()`（`extensions_config.py:1018`）。

### 手动 reload 路径

Gateway API 提供了唯一的手动更新入口：

```
PUT /api/mcp/config
  → 保存 JSON 到磁盘
  → reload_extensions_config()    # 重新加载 ExtensionsConfig
  → MCP 工具缓存 reset            # 使 MCP tool cache 失效
```

`DeerFlowClient.update_mcp_config()` 走同样的路径。

---

## MCP Tools 缓存 — 第三个缓存层

`mcp/cache.py` 有独立于 ExtensionsConfig 的缓存：

```python
_mcp_tools_cache: list[BaseTool] | None = None
_config_path: Path | None = None                          # 解析后的 extensions config 路径
_config_signature: _ConfigSignature | None = None         # (mtime, size, sha256) 内容指纹
```

```python
_server_tool_cache: dict[str, _ServerToolCacheEntry] = {}   # 按 server 名分片（cache.py:121）
_cache_initialized = False
```

`_server_tool_cache` 与扁平的 `_mcp_tools_cache` **故意分开**：某个 server 配置没变时可以直接复用它的 `BaseTool` 对象，不必重跑 discovery。

**失效检测** (`_is_cache_stale()`，`cache.py:875`)：
- 重新解析当前 extensions config 的路径 + `(mtime, size, sha256)` 内容指纹
- 与初始化时记录的值用 `!=` 比较（不是只比 mtime "大于"），因此同秒编辑、mtime 回退（对象存储/网络挂载、`git checkout`、`cp -p`）都能检出；路径变了也判 stale

**加载逻辑** (`get_cached_mcp_tools()`，`cache.py:1188`)：
1. 检查 stale → 过期则 reset
2. 已初始化 → 直接返回缓存
3. 未初始化 → 惰性初始化一次；失败只 log 并返回 `[]`（**没有**自动重试）

**Event loop 兼容** (`cache.py:1239-1254`)：
```python
try:
    loop = asyncio.get_event_loop()
except RuntimeError:
    loop = None        # 只有 get_event_loop() 才允许回落到 asyncio.run
if loop is None or loop.is_closed():
    asyncio.run(initialize_mcp_tools())
elif loop.is_running():
    with ThreadPoolExecutor() as executor:                 # 另起线程 + asyncio.run
        executor.submit(asyncio.run, initialize_mcp_tools()).result()
else:
    loop.run_until_complete(initialize_mcp_tools())
```

三条路径都确保 sync/async 调用方都能完成 MCP client 初始化。

**失败日志刻意不含异常文本**（`cache.py:1255-1261`）：配置解析会在校验前解析 `$VAR`，discovery 失败也可能带上请求 URL，所以异常消息里可能有已解析的凭据；这里只记异常**类型名**。

**🆕 关闭最后一个 MCP server 也要退役缓存**：`refresh_mcp_cache_if_active()`（`cache.py:1264`）只检查已有缓存是否陈旧、**从不惰性初始化**——从没初始化过 MCP 的进程不付任何配置哈希 / discovery 成本，而初始化过的进程仍能发现"server 全关了"并退役池化会话（`tools/tools.py` 里 `get_enabled_mcp_servers()` 为空时走这条）。

---

## Skills 启用判断

`ExtensionsConfig.is_skill_enabled()`（`extensions_config.py:607`）：

```python
def is_skill_enabled(self, skill_name: str, skill_category: str) -> bool:
    skill_config = self.skills.get(skill_name)
    if skill_config is None:
        # 未在 JSON 中列出 → 默认启用
        return skill_category in ("public", "custom", "legacy", "integrations")
    return skill_config.enabled
```

这意味着 `skills/custom/` 下的 skill 默认全部启用，除非在 `extensions_config.json` 显式禁用。
