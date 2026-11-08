# MCP 工具可见性控制：所有机制对比（v2.2.0）

| 机制 | 对 MCP 生效? | 粒度 | 确定性 | 动态? |
|------|-------------|------|--------|-------|
| **Server `enabled: false`** | ✅ | 整个 server | 100% | 可以（`PATCH /api/mcp/config`，admin-only） |
| **`tool_search.enabled`** | ✅ | 按需（LLM 搜索 / routing 自动 promote） | ~80%（依赖 LLM 判断何时搜索） | 始终动态 |
| **Subagent `tools` allowlist** | ✅ | 每个子 agent 精确列出工具名 | 100% | 静态（写在 config.yaml 里） |
| **Subagent `disallowed_tools`** | ✅ | 每个子 agent 精确列出工具名 | 100% | 静态（写在 config.yaml 里） |
| **`authorization.enabled`（Layer 1）** | ✅ | 每个工具（provider 决定） | 100% | 静态配置 + 运行时裁决 |
| **Guardrails `denied_tools` / `allowed_tools`**（`AllowlistProvider`） | ✅ | 运行时拒绝执行（Layer 2） | 100% | 静态（但运行时判断） |
| **`mcp_plugins` 白名单** 🆕 2.2 | ✅ | 按 server（deny-by-default） | 100% | 调用方传参（代码级） |
| **`include_mcp=False`** | ✅ | 全部 MCP 工具 | 100% | 代码级（实践中没用） |
| ~~**Skill `allowed-tools`**~~ | ~~✅~~ **❌** | 已删除（#6935），`tool_policy.py` 与 `skill_tool_policy_middleware.py` 均已删除，现为兼容元数据 | — | — |
| **`tool_groups`** | **❌** | 不适用（只过滤 config 的 `tools:`） | — | — |

> ⚠️ **sync #8**：v2.1.0 版本这张表把 **Skill `allowed-tools`** 列为"✅ 100% 确定"。该行在 2.2.0 已**失效**——`skills/tool_policy.py`（已删除）与 `agents/middlewares/skill_tool_policy_middleware.py`（已删除）随 #6935 `0d73798be` 移除，`SkillToolPolicyMiddleware` 不再注册进中间件链（37 → 39 条目位）。`allowed-tools` 只在 `describe_skill` 输出与 skill catalog 指纹里作为元数据存在（`skills/describe.py:206`、`agents/lead_agent/prompt.py:949`）。

---

## 推荐策略速查

| 场景 | 策略 | 确定性 |
|------|------|--------|
| 日常交互，5-10 个 MCP server | `tool_search.enabled: true` | ~80% |
| 企业自主执行，固定任务 | Subagent allowlist + `authorization` Layer 1/Layer 2 | 100% |
| 大量 MCP server，需动态选择 | `tool_search` + Server `enabled` 开关 + `select:` 语法 | ~90% |
| 按 server 整体收口（不给 LLM 看） | `enabled: false` 或 `mcp_plugins` 白名单 | 100% |
