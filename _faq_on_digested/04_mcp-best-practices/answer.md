## 核心发现：DeerFlow 有一个专门为此设计的机制——`tool_search` 延迟加载（但默认关闭）

DeerFlow 的代码库中**已经实现了一套完整的 MCP 工具延迟发现系统**，直接回应了"大量 MCP 工具造成噪声"的问题。但这不是默认行为——需要显式开启。

---

## 机制 1：`tool_search` 延迟加载（Deferred Tool Loading）—— 这是 DeerFlow 的"最佳推荐"

### 设计目标

`config.example.yaml:1190-1204` 的注释说明了一切：

> "When enabled, MCP tools are not loaded into the agent's context directly. Instead, they are listed by name in the system prompt and discoverable via the `tool_search` tool at runtime. **This reduces context usage and improves tool selection accuracy when multiple MCP servers expose a large number of tools.**"

### 完整生命周期

```
Session 开始
  │
  ├─ get_available_tools() + assemble_deferred_tools() — tools.py:73, tool_search.py:200-219
  │     → DeferredToolCatalog 持有所有 MCP 工具（name + description + BaseTool 对象）
  │     → 但 FAKE 工具名 / schema 不进入 bind_tools
  │
  ├─ DeferredToolFilterMiddleware.wrap_model_call() — middleware:84-101
  │     → 从 request.tools 中移除 deferred tool
  │     → LLM 看不到这些工具的 schema（看不到参数、类型、必填字段）
  │
  ├─ 系统 prompt 中注入 <available-deferred-tools> 块 — prompt.py:655（占位符）+ tool_search.py:282-301
  │     → 只包含工具名字（连 description 都不列）
  │     → 例如: github_create_issue\ngithub_list_repos\n...
  │
  ├─ LLM 知道这些工具存在，但没有 schema → 调用 tool_search("github")
  │
  ├─ tool_search 执行 — tool_search.py:142-173
  │     → catalog.search("github") — 三种搜索模式
  │     → 返回匹配工具的完整 OpenAI function schema（排序模式最多 5 个，`select:` 精确模式不设上限）
  │     → promote 结果通过 Command 写入 graph state（catalog_hash + names）
  │
  ├─ 下一次 wrap_model_call:
  │     → 已 promote 的工具不再被过滤 → LLM 看到完整 schema
  │
  └─ LLM 可以直接调用已 promote 的工具
```

### 三种搜索模式

`DeferredToolCatalog.search()` (`tool_search.py:79-111`)，排序模式硬上限 `MAX_RESULTS = 5`（`tool_search.py:42`），`select:` 精确模式不设上限：

| 模式 | 语法 | 匹配逻辑 |
|------|------|---------|
| **精确选择** | `select:name1,name2` | 按逗号分隔，精确匹配 name（按名点选，不做静默截断——无上限） |
| **关键词必须** | `+keyword rest` | name 必须包含 keyword，rest 部分用 regex 对 name+description 做加权排序 |
| **通用搜索** | `任意文本` | regex 对 `{name} {description}` 匹配，name 匹配权重 2，description 权重 1，按得分排序 |

> 🔄 同步 #6（v2.1.0-rc0）：`DeferredToolRegistry` 已重构为 `DeferredToolCatalog`，promote 状态由 ContextVar 改为存入 graph state（`catalog_hash` + names，经 `Command` 提交），跨中间件/子 agent 一致。新增 PR1 MCP routing 元数据：`tool_search.auto_promote_top_k`（默认 3）可在每次模型调用前按 routing hints 自动 promote 匹配的 deferred 工具——见 `_digest/internals/mcp/`。

### 安全网

即使 LLM 绕过了 `tool_search` 直接调用一个 deferred 工具（幻觉），`DeferredToolFilterMiddleware.wrap_tool_call()` 会拦截并返回错误 `ToolMessage`，指示 agent 先用 `tool_search`。

### 配置方式

```yaml
# config.yaml
tool_search:
  enabled: true
  # 可选：routing hints 自动 promote，每次模型调用最多匹配 N 个（1..5）
  auto_promote_top_k: 3
```

### `tool_search` 的优点

- ✅ **token 效率** — MCP 工具 schema（每个可能几百 tokens）只在 LLM 主动搜索时才注入上下文
- ✅ **按需发现** — Agent 不需要一次看到全部工具，按需搜索
- ✅ **硬上限 5 个结果** — 即使搜索返回很多匹配，排序模式也只展示前 5 个（`select:` 例外）
- ✅ **graph state 隔离** — promoted 状态随 LangGraph checkpoint 持久化，每个 run/thread 独立，并发安全
- ✅ **子 agent 安全** — 修复了 issue #2884，子 agent 的 `get_available_tools()` 不会擦除主 agent 的 promotions

### `tool_search` 的局限

- ❌ **仍然依赖 LLM 判断** — LLM 需要知道"什么时候该搜索"、"搜索什么关键词"
- ❌ **默认关闭** — 需要手动配置
- ❌ **只在 MCP 工具上生效** — config.yaml 定义的、built-in、ACP 工具不受影响
- ❌ **promote 后永久可见** — 在当前 run 内，一旦 promote 就无法收回（虽然这对于大多数场景是正常行为）

---

## 机制 2：MCP Server 级别的 `enabled` 开关

### 位置

`extensions_config.json` 中每个 server 的 `enabled` 字段

`backend/packages/harness/deerflow/config/extensions_config.py:206-209`（`McpServerConfig.enabled`），过滤逻辑 `extensions_config.py:559-565`

```python
def get_enabled_mcp_servers(self) -> dict[str, McpServerConfig]:
    return {name: config for name, config in self.mcp_servers.items()
            if config.enabled}
```

### 实际意义

这是**最粗粒度但最确定**的控制。把不需要的 MCP server 直接 disabled，它的工具就从 agent 视野里完全消失：

```json
{
  "mcpServers": {
    "github": { "enabled": true, ... },
    "postgres": { "enabled": false, ... },
    "slack": { "enabled": false, ... }
  }
}
```

**推荐：** 对于企业自主执行场景，只 enable 当前任务真正需要的 MCP server。这比依赖 LLM 选择更可靠。

### 动态修改

Gateway API 支持运行时修改：

```bash
PUT /api/mcp/config
# 写入新的 extensions_config.json
# → LangGraph mtime 检测 → 下次请求自动重载工具
```

> 🔄 同步 #6（v2.1.0-rc0）：MCP server 管理已迁入 Settings 页，对应 `backend/app/gateway/routers/mcp.py` 大改——除整体 `PUT /api/mcp/config`（mcp.py:1438）外，还提供 per-server 的 create/update/delete/enabled 状态切换（mcp.py:1340/1366/1395/1239）与工具缓存重置 `POST .../reset`（mcp.py:1417），并带敏感值掩码与 stdio 命令白名单校验。此外新增 request-scoped secrets：`mcp/context_headers.py` + `mcp/headers.py` 允许把调用方上下文中的密钥经 HTTP/SSE headers 注入 MCP 请求（不再写入磁盘配置），session pool 按 `(server_name, scope_key, owning_loop)` 键控（`mcp/session_pool.py`）。详见 `_digest/internals/mcp/`。

---

## 机制 3：Subagent Tool Allowlist/Denylist —— MCP 工具可参与

### 位置

`backend/packages/harness/deerflow/subagents/executor.py:739-766`（`_filter_tools`）

```python
def _filter_tools(tools, allowlist, denylist):
    if allowlist is not None:
        tools = [t for t in tools if t.name in allowlist]
    if denylist is not None:
        tools = [t for t in tools if t.name not in denylist]
    return tools
```

### 重要：这个过滤器**对 MCP 工具生效**！

与 `tool_groups` 不同，subagent 的 `tools` allowlist 在 `get_available_tools()` 返回**之后**应用，作用于完整的工具列表（包括 MCP 工具）。这就是你拥有的最精确的 MCP 工具过滤机制。

### 内置子 agent 默认配置

```
general-purpose: tools=None (全部), disallowed=["task", "ask_clarification", "present_files"]
bash:            tools=["bash", "ls", "read_file", "write_file", "str_replace"]
```

### Custom subagent 配置

```yaml
# config.yaml
subagents:
  custom_agents:
    github-agent:
      model: deepseek
      tools:                # MCP 工具名也可以在这里
        - github_create_issue
        - github_search_repositories
        - bash
        - read_file
```

这就创建了一个只能看到 `github_*` MCP 工具的子 agent。

**局限：** 子 agent 的 tools allowlist 只能静态配置在 `config.yaml` 中，不能在运行时动态指定。

---

## 机制 4：Skill `allowed-tools` — MCP 工具可参与

### 位置

`backend/packages/harness/deerflow/skills/tool_policy.py:28-52`（`allowed_tool_names_for_skills`）与 `tool_policy.py:54+`（`filter_tools_by_skill_allowed_tools`）

```python
def filter_tools_by_skill_allowed_tools(tools, skills):
    allowed = allowed_tool_names_for_skills(skills)
    if allowed is None:
        return tools  # 没有 skill 声明 allowed-tools → 全部放行
    return [t for t in tools if t.name in allowed]
```

### Skill SKILL.md 中的声明

```markdown
---
name: github-workflows
description: GitHub automation workflows
allowed-tools:
  - github_create_issue
  - github_search_repositories
  - read_file
  - write_file
---
```

当这个 skill 被加载时，agent 只能看到 `allowed-tools` 中列出的工具。**MCP 工具可以出现在这个列表中。**

### 与 skill 选取的组合

回顾 Q1-Q3：skill 选取本身不可靠。但如果**你通过 Embedded Client 的 `available_skills` 参数或 agent config 的 `skills:` 字段精确指定了 skill**，那么该 skill 的 `allowed-tools` 就会成为有效的 MCP 工具过滤器。

---

## 机制 5：`tool_groups` —— **不对 MCP 工具生效（关键发现）**

### 位置

`backend/packages/harness/deerflow/tools/tools.py:105`（groups 过滤行；`get_available_tools()` 在 tools.py:73）

```python
# 只过滤 config.yaml 定义的 tools，不过滤 MCP
tool_configs = [tool for tool in config.tools
                if groups is None or tool.group in groups]
```

**这是最容易踩的坑。** `tool_groups` 和 `AgentConfig.tool_groups` 看起来像是一个通用的工具过滤机制，但它只作用于 `config.yaml` 的 `tools:` 部分。MCP 工具、built-in 工具、ACP 工具全都不受 `groups` 参数影响。

如果你给一个 custom agent 配置了 `tool_groups: [web]`，webs 相关的 config 定义工具会被过滤进来，但**所有 MCP 工具照样全量暴露**。

---

## 综合对比

详见 [comparison-matrix.md](comparison-matrix.md)。

---

## 推荐策略（按场景）

### 场景 A：日常交互使用（5-10 个 MCP server）

**策略：** 启用 `tool_search`

```yaml
tool_search:
  enabled: true
```

让 agent 按需发现 MCP 工具。配合 system prompt 中每个 server 的 description 写好（`extensions_config.json` 中 `description` 字段），帮助 LLM 判断何时搜索。

### 场景 B：企业自主静默执行（固定任务，已知需要哪些 MCP 工具）

**策略：** 组合使用 Subagent allowlist + Skill allowed-tools

```yaml
# 1. 创建专用 subagent，精确指定它需要的 MCP 工具
subagents:
  custom_agents:
    deploy-agent:
      tools:
        - bash
        - read_file
        - write_file
        - github_create_release     # MCP 工具
        - github_upload_asset       # MCP 工具
```

```markdown
# 2. 或者创建 skill，用 allowed-tools 限定
---
name: github-release
allowed-tools:
  - github_create_release
  - github_upload_asset
  - read_file
  - write_file
---
```

然后通过 `agent_name` context key 调用这个 agent，或者通过 `available_skills` 指定这个 skill。这是**最确定性**的 MCP 工具选择方式。

### 场景 C：大量 MCP server，需要动态选择

**策略：** 三层组合

1. **`tool_search.enabled: true`** — 默认延迟加载
2. **Server `enabled` 开关** — 通过 Gateway API 按需开关不需要的 server
3. **`select:` 语法** — 在初始消息中精准 promote 所需工具

对于"长城任务"MD 文件场景，可以在任务文件开头注入一段：

```
在开始之前，请先调用 tool_search 加载以下工具：
tool_search("select:github_create_release,github_upload_asset,k8s_deploy")
```

这样初始就 promote 了任务需要的 MCP 工具，避免 LLM 自己去猜。

---

## 关键限制和注意事项

### 1. `tool_groups` 不对 MCP 生效（再次强调）

这是最反直觉的。如果你习惯了用 `tool_groups` 组织工具，要记住 MCP 工具在这个机制之外。

### 2. 没有 MCP server 分组/标签机制

`extensions_config.json` 中 MCP server 是扁平的 map，不能分组、不能打标签。组织方式只能靠 `enabled` 开关 + server 命名规范 + `description` 字段。

### 3. MCP 工具在初始化时全部加载

`get_mcp_tools()` 会连接**所有 enabled** 的 MCP server，不管 `tool_search` 是否开启。延迟加载只影响**是否暴露给 LLM**，不影响连接成本（connection overhead 仍然存在）。

### 4. 不能手动预 promote（但已有自动 promote）

没有外部 API 可以在 agent run 开始前手动 promote 特定 MCP 工具；`promote` 只能由 `tool_search` 调用（或 routing 中间件自动触发）。对于自主执行场景，可在初始消息中指导 agent 调用 `tool_search("select:...")`。

> 🔄 同步 #6（v2.1.0-rc0）：新增 `build_mcp_routing_middleware()`（tool_search.py:239-280）——server/tool 配置中的 PR1 routing hints 可在每次模型调用前自动 promote 匹配的 deferred 工具（上限 `auto_promote_top_k`，默认 3），部分缓解了"必须靠 LLM 主动搜索"的问题。

### 5. MCP 工具文件系统冲突

DeerFlow 文档明确警告：**不要添加 MCP filesystem server**。DeerFlow 内置的 `ls`/`read_file`/`write_file`/`str_replace` 已经提供了 thread-scoped 文件访问，MCP filesystem server 的路径语义不同，会导致 LLM 工具选择行为不稳定。

---

## 结论

**DeerFlow 对 MCP 工具噪声问题有清晰的设计回应：`tool_search` 延迟加载。** 这是代码库中能找到的、经过完整测试（610 行 `test_tool_search.py` + 391 行 promotion 回归测试）的机制。但它默认关闭，且仍然是 LLM 自主选择模式（决定何时搜索、搜什么）。

对于"企业自主静默执行"场景，**最务实的方案是将 MCP 工具纳入 subagent allowlist 或 skill allowed-tools 中**。这是两个**对 MCP 工具确定生效**的过滤机制，不需要依赖 LLM 判断。缺点是不能动态指定——需要预先在配置文件中声明。

如果两者结合——`tool_search` 做延迟加载 + subagent/skill 做确定性过滤——就能同时解决 context 效率和选择精度问题。

---

## 相关 digest 笔记

- `_digest/harness-hooks/04-agent-middleware-hooks.md` — DeferredToolFilterMiddleware 在中间件链中的位置
- `_digest/harness-hooks/06-mcp-interceptors.md` — MCP 拦截器链 + Gateway API 写回机制
- `_digest/middleware/03-catalog.md` — 18 middleware 目录
- `_faq_on_digested/precise-skill-selection/` — Q3: 自主执行中的精准 skill 选择（subagent allowlist, skill allowed-tools）
- `_faq_on_digested/skill-selection-accuracy/` — Q1: skill 选取精度问题

Sources:
- DeerFlow 源码: `deerflow/tools/builtins/tool_search.py:42-301` — `DeferredToolCatalog` + `tool_search` + prompt section（Registry→Catalog 重构，promote 状态入 graph state）
- DeerFlow 源码: `deerflow/agents/middlewares/deferred_tool_filter_middleware.py:29-119` — 中间件过滤
- DeerFlow 源码: `deerflow/tools/tools.py:73, 105` — `get_available_tools()` 中 groups 只过滤 config 工具 + deferred 装配（`assemble_deferred_tools`）
- DeerFlow 源码: `deerflow/config/tool_search_config.py` — `ToolSearchConfig(enabled=False, auto_promote_top_k=3)`
- DeerFlow 源码: `deerflow/agents/lead_agent/prompt.py:655` + `deerflow/tools/builtins/tool_search.py:282-301` — `<available-deferred-tools>` 注入
- DeerFlow 源码: `deerflow/subagents/executor.py:739-766` — subagent tool allowlist/denylist
- DeerFlow 源码: `deerflow/skills/tool_policy.py:28-66` — skill `allowed-tools` 过滤
- DeerFlow 源码: `deerflow/config/extensions_config.py:206-209, 559-565` — server `enabled` 过滤
- DeerFlow 源码: `backend/app/gateway/routers/mcp.py:1110-1444` — Settings 页 MCP server 管理 API（同步 #6 大改）
- DeerFlow 源码: `deerflow/mcp/context_headers.py` / `deerflow/mcp/headers.py` / `deerflow/mcp/session_pool.py` — request-scoped header secrets 与 loop 键控 session pool
- DeerFlow 文档: `backend/docs/MCP_SERVER.md` — MCP filesystem server 警告
- DeerFlow 配置: `config.example.yaml:1190-1204` — tool_search 配置说明（含 `auto_promote_top_k`）
