# 精准 Skill 选择：已有积木清单

DeerFlow 中已有的可用于"精准 skill 选择"的积木：

| 积木 | 位置 | 做什么 | 缺什么 |
|------|------|--------|--------|
| `DeerFlowClient.available_skills` | `client.py:116` | 直接指定 skill 列表 | 不走 HTTP，不动态切换 |
| `AgentConfig.skills` | `agents_config.py:49` | agent config 文件静态声明 | 不能 per-task 动态变 |
| `_CONTEXT_CONFIGURABLE_KEYS` | `services.py:124` | HTTP context 白名单 | 缺少 `skills` key |
| `_get_runtime_config()` | `agent.py:51` | 合并 configurable + context | 已经在读 cfg.get()，就缺 key |
| `_available_skill_names()` | `agent.py:356` | 决定可用 skill 集合 | 只读 agent_config + is_bootstrap，不读 runtime |
| `DeferredToolRegistry` | `tool_search.py:39` | ContextVar 隔离 + promote 模式 | 只用于 MCP tools，不用于 skills |
| `update_agent` tool | `update_agent_tool.py:71` | 运行时自改 skills | 下个 turn 才生效 |
| Bootstrap flow | `manager.py:936` | 硬编码 skill 限定 | 只有一个映射 |
| `merge_run_context_overrides` | `services.py:139` | context → configurable/context | 只处理白名单内的 key |
| Channel commands | `commands.py:11` | 命令→extra_context 管道 | 只有 bootstrap 有实际逻辑 |
