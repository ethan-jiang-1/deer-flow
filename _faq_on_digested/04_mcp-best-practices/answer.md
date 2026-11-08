## 核心发现：DeerFlow 有一个专门为此设计的机制——`tool_search` 延迟加载（默认关闭），外加 2.2 新增的若干确定性收口

DeerFlow 的代码库中**已经实现了一套完整的 MCP 工具延迟发现系统**，直接回应了"大量 MCP 工具造成噪声"的问题。但这不是默认行为——需要显式开启。

> ⚠️ **2.2.0 口径更正（sync #8）**：v2.1.0 时代的这篇 FAQ 把 Skill `allowed-tools` 列为"MCP 工具过滤器"。**这个断言在 2.2.0 已不成立**——#6935 已删除 `skills/tool_policy.py`（65 行，已删除）与 `agents/middlewares/skill_tool_policy_middleware.py`（529 行，已删除），`allowed-tools` 降级为**兼容元数据**。要限制 MCP 工具现在只有这些确定路径：server `enabled` 开关、subagent `tools`/`disallowed_tools`、Layer 1 授权过滤（`authorization.enabled`）、Layer 2 `GuardrailMiddleware`（含内置 `AllowlistProvider` 的 `allowed_tools`/`denied_tools`），以及 2.2 新增的 `mcp_plugins` deny-by-default 白名单。详见下文机制 4/5。

---

## 机制 1：`tool_search` 延迟加载（Deferred Tool Loading）—— 仍然是最主要的推荐

### 设计目标

`config.example.yaml:1388-1400` 的注释说明了一切：

> "When enabled, MCP tools are not loaded into the agent's context directly. Instead, they are listed by name in the system prompt and discoverable via the `tool_search` tool at runtime. **This reduces context usage and improves tool selection accuracy when multiple MCP servers expose a large number of tools.**"

### 完整生命周期

```
Session 开始
  │
  ├─ get_available_tools() + assemble_deferred_tools() — tools.py:103, tool_search.py:302
  │     → DeferredToolCatalog 持有所有 MCP 工具（name + description + BaseTool 对象）
  │     → 但 FAKE 工具名 / schema 不进入 bind_tools
  │     → fail-closed：tool_search 开启且有 MCP 候选、却没能产出 deferred 集合时
  │       直接 RuntimeError，绝不静默绑定全量 MCP schema（tool_search.py:309-320）
  │
  ├─ DeferredToolFilterMiddleware.wrap_model_call() — deferred_tool_filter_middleware.py
  │     → 从 request.tools 中移除 deferred tool
  │     → LLM 看不到这些工具的 schema（看不到参数、类型、必填字段）
  │
  ├─ 系统 prompt 中注入 <available-deferred-tools> 块 — get_deferred_tools_prompt_section()（tool_search.py:384）
  │     → 只包含工具名字（连 description 都不列）
  │
  ├─ LLM 知道这些工具存在，但没有 schema → 调用 tool_search("github")
  │
  ├─ tool_search 执行 — build_tool_search_tool()（tool_search.py:233）
  │     → catalog.search("github") — 四种搜索模式（tool_search.py:128-172）
  │     → 返回匹配工具的完整 OpenAI function schema（排序模式最多 5 个，`select:` 精确模式不设上限）
  │     → promote 结果通过 Command 写入 graph state（catalog_hash + names）
  │
  ├─ 下一次 wrap_model_call:
  │     → 已 promote 的工具不再被过滤 → LLM 看到完整 schema
  │
  └─ LLM 可以直接调用已 promote 的工具
```

### 四种搜索模式（v2.2.0 实测）

`DeferredToolCatalog.search()` (`tool_search.py:128-172`)。排序模式硬上限 `MAX_RESULTS = 5`（`tool_search.py:44`），只有 `select:` 不设上限：

| 模式 | 语法 | 匹配逻辑 |
|------|------|---------|
| **精确选择** | `select:name1,name2` | 逗号分隔、精确匹配 name（`tool_search.py:133-139`，按名点选，不做静默截断——无上限） |
| **关键词** 🆕 | `keywords:term1 term2` | 字面词排序：先按**词覆盖度**、再按 **name 命中数**，大小写不敏感，标点保持字面（`_rank_catalog_keywords()`，`tool_search.py:175-194`） |
| **必须包含** | `+keyword rest` | name 必须包含 keyword（小写子串），rest 用 regex 对 name+description 加权排序（`tool_search.py:143-156`） |
| **通用搜索** | `任意文本` | 无前缀即 regex（非法 regex 按字面处理）：命中整个 searchable 记 1 分，额外命中 name 记 2 分，`tool_search.py:158-172` |

regex 查询有 100ms 总预算 + 单次 256 字符上限，超时抛 `ToolSearchLimitError`（提示改用 `keywords:` 或 `select:`）。

> 🔄 同步 #8：**`keywords:` 是新增的第 4 种模式**（2.1 时代只有 `select:` / `+keyword` / 裸 regex 三种，这篇 FAQ 当时把 `+keyword` 错归为"关键词必须"）。另外 #5369 把 **skill 侧**的 free-text / `+keyword` 排名也换成字面 intent 词排名——两边共享查询语法，但排名语义不同（tool_search 的标点保持字面，便于搜 `c++` 这类名字）。

> 🔄 同步 #6（v2.1.0-rc0）：`DeferredToolRegistry` 已重构为 `DeferredToolCatalog`，promote 状态由 ContextVar 改为存入 graph state（`catalog_hash` + names，经 `Command` 提交），跨中间件/子 agent 一致。`tool_search.auto_promote_top_k`（默认 3）可在每次模型调用前按 routing hints 自动 promote 匹配的 deferred 工具——见 `_digested/internals/mcp/`。

### 安全网

即使 LLM 绕过了 `tool_search` 直接调用一个 deferred 工具（幻觉），`DeferredToolFilterMiddleware.wrap_tool_call()` 会拦截并返回错误 `ToolMessage`，指示 agent 先用 `tool_search`。

### 配置方式

```yaml
# config.yaml（config.example.yaml:1395-1400）
tool_search:
  enabled: false          # 默认关闭
  # 可选：routing hints 自动 promote，每次模型调用最多匹配 N 个（1..5）
  auto_promote_top_k: 3
```

`ToolSearchConfig` 在 `config/tool_search_config.py` 里用 `clamp_auto_promote_top_k()` 把值夹到 1..5；per-tool 的 routing `auto_promote_top_k` 在 PR2 被忽略（`tool_search.py:366-367` 只打 debug 日志）。

### `tool_search` 的优点

- ✅ **token 效率** — MCP 工具 schema（每个可能几百 tokens）只在 LLM 主动搜索时才注入上下文
- ✅ **按需发现** — Agent 不需要一次看到全部工具，按需搜索
- ✅ **硬上限 5 个结果** — 即使搜索返回很多匹配，排序模式也只展示前 5 个（`select:` 例外）
- ✅ **graph state 隔离** — promoted 状态随 LangGraph checkpoint 持久化，每个 run/thread 独立，并发安全
- ✅ **子 agent 安全** — 子 agent 走同一个 `assemble_deferred_tools()`，但候选列表是**它自己已过滤/已授权**的工具（`subagents/executor.py:1533`），promotion 无法放大子方权限

### `tool_search` 的局限

- ❌ **仍然依赖 LLM 判断** — LLM 需要知道"什么时候该搜索"、"搜索什么关键词"
- ❌ **默认关闭** — 需要手动配置
- ❌ **只在 MCP 工具上生效** — `build_deferred_tool_setup()` 用 `is_mcp_tool(t)` 挑候选（`tool_search.py:293`）；config.yaml 定义的、built-in、ACP 工具都不进 catalog
- ❌ **promote 后永久可见** — 在当前 run 内，一旦 promote 就无法收回（虽然这对于大多数场景是正常行为）

---

## 机制 2：MCP Server 级别的 `enabled` 开关（2.2 起仍是"最确定"的那一层）

### 位置

`extensions_config.json` 中每个 server 的 `enabled` 字段

`backend/packages/harness/deerflow/config/extensions_config.py:218-221`（`McpServerConfig.enabled`，默认 `True`），过滤逻辑 `extensions_config.py:599`（`get_enabled_mcp_servers`）

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

### 动态修改（2.2.0 的真实端点）

`backend/app/gateway/routers/mcp.py`（`router = APIRouter(prefix="/api")`，mcp.py:46），全部 admin-only（`require_admin_user`）：

| 方法 | 路径 | 行号 |
|------|------|------|
| `PUT` | `/api/mcp/config`（整体替换） | `mcp.py:1588-1594` |
| `POST` | `/api/mcp/config/servers`（批量新增，重名拒绝） | `mcp.py:1647-1653` |
| `PUT` | `/api/mcp/config/server`（替换单个 server） | `mcp.py:1669-1675` |
| `DELETE` | `/api/mcp/config/servers/{server_name:path}` | `mcp.py:1694` |
| `PATCH` | `/api/mcp/config`（启停单个 server） | `mcp.py:1716-1722` |
| `POST` | `/api/mcp/cache/reset`（发布共享缓存代数，废弃会话池） | `mcp.py:1559-1565` |

写回是**原子 raw 配置读改写**：`_commit_mcp_config_write()`（`mcp.py:1228`）+ `_run_drained_mcp_apply()`（`mcp.py:1265`），只改目标条目、敏感值掩码保留（`_mask_server_config` `mcp.py:840` / `_merge_preserving_secrets` `mcp.py:897`），失败会 `McpReconciliationPending`（`mcp.py:1223`）对账而不是留下半截配置。

生效路径（⚠️ 与 2.1 的说法不同）：**不是** "LangGraph mtime 检测"这一条，而是 `get_available_tools()` 每次装配都走 `mcp/cache.py` 的 content-signature 检测——`get_cached_mcp_tools()`（`cache.py:1188`）比对配置文件的 `(mtime, size, sha256)` + 配置 revision + 共享 reset 标记；若**最后一个** server 被禁用，则走 `refresh_mcp_cache_if_active()`（`cache.py:1268`，调用点 `tools.py:283`）只退役旧缓存与会话，不重新初始化。2.2 的 reconciliation 是**选择性**的：只替换变更的那些 server，未变的 server 会话不重建。

> 🔄 同步 #6（v2.1.0-rc0）：MCP server 管理迁入 Settings 页，请求级 secrets 经 `mcp/context_headers.py` 注入。**同步 #8（2.2.0）新增**：`mcp_scope.py` 会话作用域键 v2（`v2:[user, thread, incarnation]`）、`lifecycle.py` 的 `mcpLifecycle` 账本（谁在引用哪些 server/transport，用于强制重绑与 OAuth token 保留期判定）、个人 MCP 连接（`mcp/user_config.py` + `post`/`PUT`/`DELETE` `/api/mcp/personal/config*`，每用户 `<user_dir>/mcp.json`，运行时名 `personal_<sha256>`）、`mcp/cache.py` 316→1407 行。详见 `_digested/internals/mcp/`。

---

## 机制 3：Subagent Tool Allowlist/Denylist —— MCP 工具可参与（仍然是确定性的）

### 位置

`backend/packages/harness/deerflow/subagents/executor.py:857-885`（`_filter_tools`）

```python
def _filter_tools(all_tools, allowed, disallowed):
    filtered = all_tools
    if allowed is not None:
        allowed_set = set(allowed)
        filtered = [t for t in filtered if t.name in allowed_set]
    if disallowed is not None:
        disallowed_set = set(disallowed)
        filtered = [t for t in filtered if t.name not in disallowed_set]
    return filtered
```

调用点在 `SubagentExecutor.__init__`（`executor.py:1037`）：`self._base_tools = _filter_tools(tools, config.tools, config.disallowed_tools)`。

### 重要：这个过滤器**对 MCP 工具生效**！

子 agent 的 `tools` allowlist 作用于**父方传入的完整工具列表**（包括 MCP 工具），在 `assemble_deferred_tools()` **之前**执行（`executor.py:1533`）。随后 Layer 1 授权过滤（`apply_tool_authorization`，`executor.py:1514-1518`）再收一道，才装配 deferred catalog。也就是说 **allowlist ∩ 授权 = 子 agent 能看到的 MCP 工具**，`tool_search` 也只在这份集合里 promote。

### 内置子 agent 默认配置（`subagents/builtins/`）

```
general-purpose（general_purpose.py:66-67）：tools=None（全部），
                     disallowed_tools=["task", "ask_clarification", "present_files"]
bash（bash_agent.py:46-47）：tools=["bash", "ls", "read_file", "write_file", "str_replace"]
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

## 机制 4：Skill `allowed-tools` —— ⚠️ 在 2.2.0 **已失效**（降级为兼容元数据）

### 2.1 时代的行为（历史，仅供理解迁移）

`allowed-tools` 曾在 `skills/tool_policy.py`（65 行，**已删除**，#6935）与 `agents/middlewares/skill_tool_policy_middleware.py`（529 行，**已删除**，#6935）里把并集同时应用到"模型可见性 / tool_search 结果 / 执行"三层。当时的语义是「没有 skill 声明 → 全放行；一旦有 skill 声明，未声明的 skill 贡献 0 个工具」。

### 2.2.0 的现行语义

**两个文件都已删除（#6935 `0d73798be`），`build_middlewares()` 里对 `SkillToolPolicyMiddleware` 的注册也一并移除。** `allowed-tools` 现在只是**兼容元数据**：

- 仍会被解析、仍出现在 skill catalog 指纹与 `describe_skill` 输出里（前缀固定写成 `Allowed tools (compatibility metadata, not enforced):`，`skills/describe.py:206`）；
- lead prompt 里明确写了「A skill's `allowed-tools` frontmatter is compatibility metadata carried for other agent frameworks. **It never restricts or grants tools here**」（`agents/lead_agent/prompt.py:949`）；
- `assemble_deferred_tools()` 的 docstring 同样写明它**不参与** deferred 装配（`tool_search.py:309-310`）。

所以**"skill 声明 allowed-tools 就能限定 MCP 工具"这类断言在 2.2.0 已不成立**。权限上限的唯一所有者变成「agent 组装 + 执行授权」：Layer 1 的 `authorization` provider 过滤（`apply_tool_authorization` / `tool_declarations.py`）与 Layer 2 的 `GuardrailMiddleware`（`agents/middlewares/tool_error_handling_middleware.py:452-488`）。

### 2.2.0 下想精确限定 MCP 工具，请改用

1. **Subagent `tools` / `disallowed_tools`**（机制 3）——最直接的静态白名单；
2. **`authorization.enabled`** 的 Layer 1 provider——在 deferred 装配前过滤，被拒的工具进不了 catalog；
3. **`guardrails.enabled` + `guardrails.provider`** 的 Layer 2 检查——内置 `AllowlistProvider`（`guardrails/builtin.py:13`）支持 `allowed_tools` / `denied_tools`，注意 `allowed_tools=[]` 与 `None` 语义不同（空列表 = 全拒，不是全放）。

---

## 机制 5：`tool_groups` —— **不对 MCP 工具生效（关键发现仍未变）**

### 位置

`backend/packages/harness/deerflow/tools/tools.py:145`

```python
# 只过滤 config.yaml 定义的 tools，不过滤 MCP
tool_configs = [tool for tool in config.tools if groups is None or tool.group in groups]
```

**这是最容易踩的坑。** `tool_groups` 和 `AgentConfig.tool_groups` 看起来像是一个通用的工具过滤机制，但它只作用于 `config.yaml` 的 `tools:` 部分。MCP 工具、built-in 工具、ACP 工具全都不受 `groups` 参数影响。

如果你给一个 custom agent 配置了 `tool_groups: [web]`，webs 相关的 config 定义工具会被过滤进来，但**所有 MCP 工具照样全量暴露**。

> 🔄 同步 #8：2.2 新增 `mcp_plugins` 参数（`tools.py:109`，调用 `filter_mcp_plugins()` `tools.py:303-306`），这是**唯一一个真正按 server 过滤 MCP 工具的 `get_available_tools()` 形参**，语义是 **deny-by-default 白名单**，不是"优先级提示"（`capabilities/runtime.filter_mcp_plugins`）。`include_mcp=False`（`tools.py:105`）仍然可用来整体剔除 MCP。

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

让 agent 按需发现 MCP 工具。配合 `extensions_config.json` 里每个 server 的 `description` 与 routing hints（`docs/MCP_SERVER.md` 的 "Routing Hints" 节）写好，帮助 LLM（与 `McpRoutingMiddleware`）判断何时搜索。

### 场景 B：企业自主静默执行（固定任务，已知需要哪些 MCP 工具）

**策略：** 专用 subagent 的 `tools` allowlist + `authorization` Layer 1

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

```yaml
# 2. 再叠一层执行前授权（Layer 1 过滤 + Layer 2 Guardrail 同一个 provider）
authorization:
  enabled: true
  provider: ...
```

> ⚠️ 2.1 时代的"用 SKILL.md 的 `allowed-tools` 兜底"已**不可用**（机制 4）：文件已删除，`allowed-tools` 不再收窄工具集。

### 场景 C：大量 MCP server，需要动态选择

**策略：** 三层组合

1. **`tool_search.enabled: true`** — 默认延迟加载
2. **Server `enabled` 开关** — `PATCH /api/mcp/config` 按需启停（admin-only），或 `POST /api/mcp/cache/reset` 刷新 discovery
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

这是最反直觉的。如果你习惯了用 `tool_groups` 组织工具，要记住 MCP 工具在这个机制之外。要按 server 过滤请用 `mcp_plugins`（deny-by-default 白名单）。

### 2. 没有 MCP server 分组/标签机制

`extensions_config.json` 中 MCP server 是扁平的 map，不能分组、不能打标签。组织方式只能靠 `enabled` 开关 + server 命名规范 + `description` / routing hints。

### 3. MCP 工具在初始化时全部加载

`get_cached_mcp_tools()`（`cache.py:1188`）会连接**所有 enabled** 的 MCP server（含当前用户的个人连接），不管 `tool_search` 是否开启。延迟加载只影响**是否暴露给 LLM**，不影响连接成本（connection overhead 仍然存在）。2.2 的选择性 reconciliation 只减少"配置变更导致的重新发现"，不减少首次发现成本。

### 4. 不能手动预 promote（但已有自动 promote）

没有外部 API 可以在 agent run 开始前手动 promote 特定 MCP 工具；`promote` 只能由 `tool_search` 调用（或 `McpRoutingMiddleware` 自动触发）。对于自主执行场景，可在初始消息中指导 agent 调用 `tool_search("select:...")`。

> 🔄 同步 #8：`McpRoutingMiddleware` 的注册条件更严了——`build_mcp_routing_middleware()`（`tool_search.py:341`）要求 `deferred_setup.catalog_hash` 非空、且有 `mode == "prefer"` 的 routing hint，否则返回 `None`，链上就没有这一条。装配顺序不变量由 `assert_mcp_routing_before_deferred_filter()` 强制（`agents/lead_agent/agent.py:699-700`）。

### 5. MCP 工具文件系统冲突

DeerFlow 文档明确警告：**不要添加 MCP filesystem server**（`backend/docs/MCP_SERVER.md` 的 "Filesystem MCP Servers" 节）。DeerFlow 内置的 `ls`/`read_file`/`write_file`/`str_replace` 已经提供了 thread-scoped 文件访问，MCP filesystem server 的路径语义不同（且不发布 per-thread MCP roots、不映射 `/mnt/user-data/...`），会导致 LLM 工具选择行为不稳定。

### 6. 🆕 2.2：长任务工具不再是"一次同步调用"

声明了 `task_toolsets` 的 server，其 `submit` 工具会被换成 durable 包装器：`tools.py:925`（`_configure_task_tools_for_server`）**隐藏** `status_tool` / `cancel_tool`，submit 立即返回本地 task ID，真正的轮询在 Agent 循环之外的 `McpTaskService` 里跑。对"工具噪声"而言这是好消息（模型少看到两个工具），但要注意：`list_background_tasks` / `cancel_background_task` 只在 task runtime 可用时才进工具集，且后台 poll 跑在 run 之外、没有请求级 secrets。详见 `_digested/internals/mcp/durable-tasks.md`。

### 7. 🆕 2.2：会话作用域按「用户 + 线程 + incarnation」隔离

`mcp_scope.mcp_session_scope_key()`（`mcp_scope.py:31`）产出 `v2:[user, thread, incarnation]` 编码；incarnation 为 NULL 的历史行仍用 legacy `user:thread`。同一线程删掉重建（换 incarnation）后，旧任务既不会出现在 `/api/threads/{id}/mcp-tasks` 列表里，也不能被详情/取消命中。

---

## 结论

**DeerFlow 对 MCP 工具噪声问题有清晰的设计回应：`tool_search` 延迟加载，且 2.2.0 把它做成了 fail-closed。** 但它默认关闭，且仍然是 LLM 自主选择模式（决定何时搜索、搜什么）。

对于"企业自主静默执行"场景，**2.2.0 下最务实的方案是把 MCP 工具纳入 subagent `tools` allowlist，再叠上 `authorization` 的 Layer 1/Layer 2 检查**。v2.1 时代推荐的"skill allowed-tools"兜底已经**随 #6935 删除而失效**——它现在只是兼容元数据，不再过滤任何工具。

如果两者结合——`tool_search` 做延迟加载 + subagent allowlist/授权做确定性过滤——就能同时解决 context 效率和选择精度问题。

---

## 相关 digest 笔记

- `_digested/internals/mcp/README.md` — MCP 深度索引（session pool / OAuth / 缓存 / 个人连接 / durable task）
- `_digested/internals/mcp/durable-tasks.md` — durable task 子系统（`app/mcp_tasks/service.py` 1731 行、租约令牌、incarnation）
- `_digested/internals/mcp/session-pool-oauth-cache-invalidation.md` — 缓存失效 / 选择性 reconciliation / 作用域键 v2
- `_digested/concepts/skills-tools/skill-md-and-tool-assembly.md` — `allowed-tools` 2.2 新语义（专节）
- `_digested/internals/middleware/03-catalog.md` — 39 middleware 条目位（`SkillToolPolicyMiddleware` 已下线）
- `_faq_on_digested/03_precise-skill-selection/` — Q3: 自主执行中的精准 skill 选择
- `_faq_on_digested/01_skill-selection-accuracy/` — Q1: skill 选取精度问题

Sources（v2.2.0 源码实测）:
- `deerflow/tools/builtins/tool_search.py:44, 128-172, 233, 278-320, 341` — `MAX_RESULTS`、`DeferredToolCatalog.search`、`build_tool_search_tool`、`build_deferred_tool_setup` / `assemble_deferred_tools`（fail-closed）、`build_mcp_routing_middleware`
- `deerflow/agents/middlewares/deferred_tool_filter_middleware.py` — 中间件过滤（162 行）
- `deerflow/agents/middlewares/mcp_routing_middleware.py` — 自动 promote（160 行）
- `deerflow/tools/tools.py:103-145, 252-306` — `get_available_tools()` 签名、groups 只过滤 config 工具、MCP + 个人连接 + `mcp_plugins`
- `deerflow/config/tool_search_config.py:9, 22-34` — `ToolSearchConfig(enabled=False, auto_promote_top_k=3)` + clamp 1..5
- `deerflow/subagents/executor.py:857-885, 1037, 1514-1533` — subagent allow/deny → Layer 1 授权 → deferred 装配
- `deerflow/subagents/builtins/general_purpose.py:66-67` / `bash_agent.py:46-47` — 内置子 agent 工具集
- `deerflow/config/extensions_config.py:218-221, 599` — server `enabled` + `get_enabled_mcp_servers`
- `deerflow/mcp/cache.py:1188, 1268`（1407 行）— `get_cached_mcp_tools` / `refresh_mcp_cache_if_active`
- `deerflow/mcp_scope.py:31, 52, 82`（95 行）— 会话作用域键 v2 / `mcp_scope_belongs_to_thread` / `runtime_thread_incarnation`
- `deerflow/mcp/tools.py:925-986` — `_configure_task_tools_for_server`（隐藏 status/cancel、替换 submit）
- `deerflow/guardrails/builtin.py:13-31` — `AllowlistProvider(allowed_tools, denied_tools)`
- `deerflow/agents/lead_agent/prompt.py:949` — 「allowed-tools 是兼容元数据」的 lead prompt 原文
- **已删除（#6935）**：`deerflow/skills/tool_policy.py`（65 行）、`deerflow/agents/middlewares/skill_tool_policy_middleware.py`（529 行）
- `backend/app/gateway/routers/mcp.py:46, 840, 897, 1223-1265, 1559-1716` — Settings 页 MCP 管理 API 与 raw 配置读改写
- DeerFlow 文档: `backend/docs/MCP_SERVER.md` — filesystem server 警告、Routing Hints、Durable Background Tasks
- DeerFlow 配置: `config.example.yaml:1385-1400` — tool_search 配置说明（含 `auto_promote_top_k`）
