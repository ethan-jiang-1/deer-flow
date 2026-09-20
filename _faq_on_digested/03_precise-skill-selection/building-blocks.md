# 精准 Skill 选择：已有积木清单

DeerFlow 中已有的可用于"精准 skill 选择"的积木（行号为 v2.1.0-rc0 = 769589e8）：

| 积木 | 位置 | 做什么 | 缺什么 |
|------|------|--------|--------|
| `DeerFlowClient.available_skills` | `client.py:189` | 直接指定 skill 列表 | 不走 HTTP，不动态切换 |
| `AgentConfig.skills` | `agents_config.py:219` | agent config 文件静态声明 | 不能 per-task 动态变 |
| `_CONTEXT_CONFIGURABLE_KEYS` | `services.py:506` | HTTP context 白名单 | 缺少 `skills` key |
| `_get_runtime_config()` | `agent.py:219` | 合并 configurable + context | 已经在读 cfg.get()，就缺 key |
| `_available_skill_names()` | `agent.py:774` | 决定可用 skill 集合 | 只读 agent_config + is_bootstrap，不读 runtime |
| `DeferredToolRegistry` | `tool_search.py` | deferred 搜索 + promote 模式（v2.1.0-rc0 重构：不再用 ContextVar，支持 `select:`/`+` 搜索） | 只用于 MCP tools，不用于 skills |
| `update_agent` tool | `update_agent_tool.py:77` | 运行时自改 skills | 下个 turn 才生效 |
| Bootstrap flow | `manager.py:2740` | 硬编码 skill 限定 | 只有一个映射 |
| `merge_run_context_overrides` | `services.py:611` | context → configurable/context | 只处理白名单内的 key |
| Channel commands | `commands.py:11` | 命令→extra_context 管道 | 只有 bootstrap 有实际逻辑 |
| `/skill-name` slash 激活（新增） | `skills/slash.py` + `SkillActivationMiddleware` | 确定性 `/skill-name 任务` 解析并注入 SKILL.md | 只覆盖行首 slash 语法 |
| `_rank_by_intent`/`_intent_score`（新增） | `skills/catalog.py:96/76` | 字面 intent 排名的 skill 搜索（#5369） | 未用于默认 `<available_skills>` 注入排序 |

> 🔄 同步 #6（v2.1.0-rc0）：`/mnt/skills` 收归 managed enabled-only projection（#4178，`skills/projection.py`），未启用 skill 在沙箱内不可见，等于在文件系统层多了一道确定性过滤积木。
