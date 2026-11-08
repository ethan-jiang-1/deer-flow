# MCP 工具管理：五种机制详解（v2.2.0 口径）

> ⚠️ **sync #8 更正**：机制 4（Skill `allowed-tools`）在 v2.2.0 **已失效**——`skills/tool_policy.py`（已删除）与 `agents/middlewares/skill_tool_policy_middleware.py`（已删除）随 #6935 移除，`allowed-tools` 降级为兼容元数据。下面按现行源码改写，并补上 2.2 新增的确定性路径。

## 机制 1：`tool_search` 延迟加载（Deferred Tool Loading）

DeerFlow 的"最佳推荐"——但不默认开启。完整生命周期见 [answer.md](answer.md)。

配置（`config.example.yaml:1395-1400`）：
```yaml
# config.yaml
tool_search:
  enabled: true
  auto_promote_top_k: 3   # 1..5，由 clamp_auto_promote_top_k() 夹取
```

装配入口 `assemble_deferred_tools()`（`tools/builtins/tool_search.py:302`）：**fail-closed**——开启且有 MCP 候选却没产出 deferred 集合时直接 `RuntimeError`，不会静默绑定全量 MCP schema。搜索语法四种：`select:a,b`（无上限）、`keywords:...` 🆕、`+kw rest`、裸 regex；排序模式上限 `MAX_RESULTS = 5`（`tool_search.py:44`）。

## 机制 2：MCP Server 级别的 `enabled` 开关

最粗粒度但最确定。通过 `extensions_config.json` 控制：
```json
{"mcpServers": {"github": {"enabled": true}, "postgres": {"enabled": false}}}
```
过滤点是 `ExtensionsConfig.get_enabled_mcp_servers()`（`config/extensions_config.py:599`），字段定义在 `extensions_config.py:218-221`。

2.2.0 的管理面（全部 admin-only，`app/gateway/routers/mcp.py`）：
- `PUT /api/mcp/config`（mcp.py:1588）整体替换；`POST /api/mcp/config/servers`（mcp.py:1647）批量新增；`PUT /api/mcp/config/server`（mcp.py:1669）单条替换；`DELETE /api/mcp/config/servers/{name}`（mcp.py:1694）；`PATCH /api/mcp/config`（mcp.py:1716）启停。
- `POST /api/mcp/cache/reset`（mcp.py:1559）发布共享缓存代数，让共享配置目录下的所有 worker 下次使用时重载。

生效路径：`get_cached_mcp_tools()`（`mcp/cache.py:1188`）按 resolved-path + `(mtime,size,sha256)` content-signature + 配置 revision + 共享 reset 标记判断失效；2.2 是**选择性 reconciliation**（只换变更的 server）。最后一个 server 被禁用时改走 `refresh_mcp_cache_if_active()`（`mcp/cache.py:1268`，调用点 `tools/tools.py:283`）只退役旧缓存与会话。

> 🔄 同步 #6（v2.1.0-rc0）：MCP server 管理迁入 Settings 页，request-scoped secrets 经 `mcp/context_headers.py` 注入。
> 🔄 同步 #8（2.2.0）：`mcp/cache.py` 316→1407 行；新增 `mcp_scope.py`（95 行，会话作用域键 v2 `v2:[user,thread,incarnation]`）、`lifecycle.py` 的 `mcpLifecycle` 账本、个人 MCP 连接（`/api/mcp/personal/config*`）。

## 机制 3：Subagent Tool Allowlist/Denylist

**对 MCP 工具生效。** 在 `config.yaml` 的 subagent 配置中指定：
```yaml
subagents:
  custom_agents:
    github-agent:
      tools: [github_create_issue, github_search_repositories, bash, read_file]
      disallowed_tools: [bash]
```
实现 `_filter_tools()`（`subagents/executor.py:857-885`），在 `SubagentExecutor.__init__` 里对父方传入的工具集先应用（`executor.py:1037`），之后才做 Layer 1 授权（`apply_tool_authorization`，`executor.py:1514`）与 deferred 装配（`executor.py:1533`）。

内置子 agent（`subagents/builtins/`）：`general-purpose`（`tools=None` 继承全部；`disallowed_tools=["task","ask_clarification","present_files"]`，`general_purpose.py:66-67`）、`bash`（仅 `bash/ls/read_file/write_file/str_replace`，`bash_agent.py:46-47`）。

## 机制 4：Skill `allowed-tools` —— ⚠️ 2.2.0 已失效（兼容元数据）

```markdown
---
name: github-workflows
allowed-tools: [github_create_issue, read_file, write_file]
---
```

**2.1 时**：skill 被精确加载（slash 激活或 loaded）后，`allowed-tools` 会收窄工具集。
**2.2.0 起**：`skills/tool_policy.py`（已删除）与 `agents/middlewares/skill_tool_policy_middleware.py`（已删除）随 #6935 移除，`allowed-tools` **永不过滤、授予或拒绝任何工具**——它只被保留为兼容元数据（`describe_skill` 里前缀写成 `Allowed tools (compatibility metadata, not enforced):`，`skills/describe.py:206`；lead prompt 原文见 `agents/lead_agent/prompt.py:949`）。`assemble_deferred_tools()` 的 docstring 同样声明它不参与 deferred 装配（`tool_search.py:309-310`）。

**要限制 MCP 工具，改用**：subagent `tools`/`disallowed_tools`（机制 3）、`authorization.enabled` 的 Layer 1 provider、或 `guardrails.enabled` + 内置 `AllowlistProvider(allowed_tools=..., denied_tools=...)`（`guardrails/builtin.py:13`，注意 `[]` 表示全拒而非全放）。

## 机制 5：`tool_groups`（⚠️ 不对 MCP 生效）

`config.yaml` 中 `tool_groups` 和 `AgentConfig.tool_groups` 只过滤 `config.yaml` 的 `tools:` 部分（`tools/tools.py:145`），**不作用于 MCP 工具**。这是最容易踩的坑。

🆕 **2.2 的正解**：`get_available_tools(mcp_plugins=[...])`（`tools.py:109` → `tools.py:303-306` 调 `filter_mcp_plugins()`）是唯一按 server 过滤 MCP 工具的形参，语义是 **deny-by-default 白名单**（不是优先级提示）；`include_mcp=False`（`tools.py:105`）可整体剔除 MCP。
