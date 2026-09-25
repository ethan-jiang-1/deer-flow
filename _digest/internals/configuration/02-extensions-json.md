---
title: "ExtensionsConfig — MCP 与 Skills 配置"
description: "`extensions_config.json` 是独立的 JSON 配置文件，管理 MCP server 连接和 skills 启用/禁用状态。与 `config.yaml` 不同，它是**可选的** — 找不到就返回空配置。"
topics: [configuration, hot-reload, yaml-config]
---

# ExtensionsConfig — MCP 与 Skills 配置

`extensions_config.json` 是独立的 JSON 配置文件，管理 MCP server 连接和 skills 启用/禁用状态。与 `config.yaml` 不同，它是**可选的** — 找不到就返回空配置。

## 数据结构

```python
class ExtensionsConfig(BaseModel):          # model_config = ConfigDict(extra="allow")
    middlewares: list[str | ConfiguredMiddlewareSpec]  # config.yaml 的 extensions.middlewares 可覆盖
    mcp_servers: dict[str, McpServerConfig]  # alias: "mcpServers"
    skills: dict[str, SkillStateConfig]
    # mcpInterceptors 不在 schema 里，落在 model_extra：
    #   ["pkg.mod:build_interceptor", ...] 由 mcp/interceptors.py:47-53 解析成自定义 MCP tool 拦截器
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

只有 `enabled: bool` 一个字段。未在 JSON 中列出的 skill 默认启用（`public` / `custom` / `legacy` / `integrations` 四个类别，`extensions_config.py:567-584`）。

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
# extensions_config.py:210
_extensions_config: ExtensionsConfig | None = None  # 模块级单例

def get_extensions_config():
    if _extensions_config is None:
        _extensions_config = ExtensionsConfig.from_file()
    return _extensions_config
```

**与 AppConfig 不同：没有 mtime 自动检测。** 这是因为 extensions 不常改，且修改通过 API 进行（不是直接编辑文件）。

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

**失效检测** (`_is_cache_stale()`，`cache.py:79`)：
- 重新解析当前 extensions config 的路径 + `(mtime, size, sha256)` 内容指纹
- 与初始化时记录的值用 `!=` 比较（不是只比 mtime "大于"），因此同秒编辑、mtime 回退（对象存储/网络挂载、`git checkout`、`cp -p`）都能检出；路径变了也判 stale

**加载逻辑** (`get_cached_mcp_tools()`，`cache.py:197`)：
1. 检查 stale → 过期则 reset
2. 已初始化 → 直接返回缓存
3. 未初始化 → 惰性初始化一次；失败只 log 并返回 `[]`（**没有**自动重试）

**Event loop 兼容** (`cache.py:225-243`)：
```python
loop = asyncio.get_event_loop()
if loop.is_running():
    # 已有 running loop → 另起 ThreadPoolExecutor + asyncio.run()
else:
    loop.run_until_complete(initialize_mcp_tools())
# 取不到 loop（RuntimeError）→ asyncio.run(initialize_mcp_tools())
```

三条路径都确保 sync/async 调用方都能完成 MCP client 初始化。

---

## Skills 启用判断

`ExtensionsConfig.is_skill_enabled()` (`extensions_config.py:567`)：

```python
def is_skill_enabled(self, skill_name: str, skill_category: str) -> bool:
    skill_config = self.skills.get(skill_name)
    if skill_config is None:
        # 未在 JSON 中列出 → 默认启用
        return skill_category in ("public", "custom", "legacy", "integrations")
    return skill_config.enabled
```

这意味着 `skills/custom/` 下的 skill 默认全部启用，除非在 `extensions_config.json` 显式禁用。
