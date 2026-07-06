# MCP 工具可见性控制：所有机制对比

| 机制 | 对 MCP 生效? | 粒度 | 确定性 | 动态? |
|------|-------------|------|--------|-------|
| **Server `enabled: false`** | ✅ | 整个 server | 100% | 可以（Gateway API PUT） |
| **`tool_search.enabled`** | ✅ | 按需（LLM 搜索） | ~80%（依赖 LLM 判断何时搜索） | 始终动态 |
| **Skill `allowed-tools`** | ✅ | 每个 skill 声明白名单 | 100%（如果 skill 被精确选中） | 静态（写在 SKILL.md 里） |
| **Subagent `tools` allowlist** | ✅ | 每个子 agent 精确列出工具名 | 100% | 静态（写在 config.yaml 里） |
| **Subagent `disallowed_tools`** | ✅ | 每个子 agent 精确列出工具名 | 100% | 静态（写在 config.yaml 里） |
| **Guardrails `denied_tools`** | ✅ | 运行时拒绝执行 | 100% | 静态（但运行时判断） |
| **`tool_groups`** | **❌** | 不适用 | — | — |
| **`include_mcp=False`** | ✅ | 全部 MCP 工具 | 100% | 代码级（实践中没用） |

---

## 推荐策略速查

| 场景 | 策略 | 确定性 |
|------|------|--------|
| 日常交互，5-10 个 MCP server | `tool_search.enabled: true` | ~80% |
| 企业自主执行，固定任务 | Subagent allowlist + Skill allowed-tools | 100% |
| 大量 MCP server，需动态选择 | `tool_search` + Server `enabled` 开关 + `select:` 语法 | ~90% |
