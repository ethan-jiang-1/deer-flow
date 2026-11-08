# 精准 Skill 选择：已有积木清单

DeerFlow 中已有的可用于"精准 skill 选择"的积木（行号为 **v2.2.0** 实测，2.1 时代的旧行号已重核）：

| 积木 | 位置 | 做什么 | 缺什么 |
|------|------|--------|--------|
| `DeerFlowClient.available_skills` | `client.py:221`（签名）、`:442-449`（Layer 1 过滤后使用） | 直接指定 skill 列表 | 不走 HTTP，不动态切换 |
| `AgentConfig.skills` | `agents_config.py:221` | agent config 文件静态声明 | 不能 per-task 动态变 |
| `_CONTEXT_CONFIGURABLE_KEYS` | `services.py:880-895` | HTTP context 白名单 | 缺少 `skills` key（2.2 仍是那 10 个） |
| `_get_runtime_config()` | `agent.py:219-226` | 合并 configurable + context | 已经在读 cfg.get()，就缺 key |
| `_available_skill_names()` | `agent.py:812-817` | 决定可用 skill 集合 | 只读 agent_config + is_bootstrap，不读 runtime |
| Layer 1 skill 授权过滤（新增） | `authz/skill_filter.py`，调用点 `agent.py:1041-1047`、`client.py:442-449` | 用 `skill` 策略再收窄可用集 | 只收窄 visibility，不改工具 |
| `DeferredToolCatalog` | `tool_search.py:113` | deferred 搜索 + 随图状态 promote（无 ContextVar，支持 `select:`/`+` 搜索）；docstring "pure search, no mutation" | 只用于 MCP tools，不用于 skills |
| `update_agent` tool | `update_agent_tool.py:78-82` | 运行时自改 skills | 下个 turn 才生效 |
| Bootstrap flow | `manager.py:3730-3735` + `agent.py:812-817` | 硬编码 skill 限定 | 只有一个映射 |
| `merge_run_context_overrides` | `services.py:1005` | context → configurable/context | 只处理白名单内的 key |
| Channel commands | `commands.py:11-24` | 命令→extra_context 管道 | 只有 bootstrap 有实际逻辑 |
| `/skill-name` slash 激活 | `skills/slash.py:39,54` + `SkillActivationMiddleware`（`skill_activation_middleware.py:118,318-355`） | 确定性 `/skill-name 任务` 解析并注入 SKILL.md | 只覆盖行首 slash 语法；**2.2 起不再联动工具集** |
| `_rank_by_intent`/`_intent_score` | `skills/catalog.py:96/76` | 字面 intent 排名的 skill 搜索（#5369） | 未用于默认 `<available_skills>` 注入排序 |
| 权限上限（Layer 1 + Layer 2，新增） | `authz/tool_filter.py:25-33`（`apply_tool_authorization`）、`authz/provider.py:86`、`authz/adapter.py:27` | 决定模型能看到/能调用哪些**工具** | 是「限制」积木，不是「选择」积木 |

> 🔄 同步 #6（v2.1.0-rc0）：`/mnt/skills` 收归 managed enabled-only projection（#4178，`skills/projection.py`），未启用 skill 在沙箱内不可见，等于在文件系统层多了一道确定性过滤积木。

> 🔄 同步 #8（v2.2.0）：**要从这张表里划掉的积木**——skill 的 `allowed-tools` 曾是一种「选了 skill 就锁定工具集」的能力，2.2 已把它降级为兼容元数据：**已删除** `skills/tool_policy.py`（65 行，含 `filter_tools_by_skill_allowed_tools()`）与 `agents/middlewares/skill_tool_policy_middleware.py`（529 行），`build_middlewares()` 的注册也一并移除（上游 #6935 / `0d73798be`）。现行语义是：skill 选择只决定 skill 可见性/激活，**工具上限归 agent 组装 + 执行授权所有**（上表最后一行）。另外 2.2 新增的 Layer 1 skill 授权过滤是本表里唯一「你没点名、但能在运行时继续收窄 skill 集」的积木——做精准选择方案时别忽略它，它可能直接把你设计的集合再砍一刀。
