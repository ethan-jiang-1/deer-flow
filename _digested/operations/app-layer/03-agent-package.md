---
title: "Agent Package（agent 包导入/导出）"
description: "v2.2.0 新增的 `deerflow.custom-agent` v1 交换文档：把一个 custom agent 定义在部署之间搬运。哪些字段可移植、哪些必须留在原部署？导入为什么只能 create-only？"
topics: [gateway, api, agents, migration]
---

# Agent Package（agent 包导入/导出）

> 同步基线：**v2.2.0**（`58fc5bd5b`）。行号为 v2.2.0 实测（`grep -n` 核对）。
> 端点在 API 总表里的位置：[01-api-reference.md](01-api-reference.md) §1（`:44`、`:45`）与 §4（`:945`、`:946`）。本篇只讲**机制**。

v2.2.0 新增的 `deerflow.custom-agent` v1 交换文档：把一个 custom agent 定义在部署之间搬运。哪些字段可移植、哪些必须留在原部署？导入为什么只能 create-only？

## 解决什么问题

一个 custom agent 在磁盘/DB 里是一个**混合体**：既有用户写的定义（描述、工具组、技能白名单、SOUL.md），也有**属于这个部署的绑定**（GitHub 安装 ID、operator 的 `channels.github` 配置），还有**属于这个用户的运行时状态**（memory 事实、会话、凭据）。

直接复制 `config.yaml` 会三样一起搬：

- 把 `private-bot` 的 GitHub `installation_id` 搬到另一台机器 → 新机器用别人的安装身份响应 webhook；
- 把 memory 内容搬过去 → 跨用户泄漏已记住的事实；
- 把凭据搬过去 → 明文密钥落进一个 JSON 文件。

`AgentPackage` 就是为了切这一刀：**只有可移植的定义 + SOUL**，格式带版本号，两端（导出/导入）共用同一份 pydantic 模型，所以「导出什么」和「导入什么」不可能漂移。

## 数据形状

### 三个模型（`app/gateway/routers/agents.py`）

| 模型 | 行 | 说明 |
|------|----|------|
| `AgentPackageAgent(AgentCreateRequest)` | `:112-123` | 继承创建请求体，`extra="forbid"`，**新增唯一字段** `memory_enabled: bool = True`（`:123`） |
| `AgentPackage(BaseModel)` | `:126-133` | `extra="forbid"`；`format: Literal["deerflow.custom-agent"]`（`:131`）、`version: Literal[1]`（`:132`）、`agent: AgentPackageAgent`（`:133`） |
| `AgentCreateRequest` | `:77-92` | 12 个字段（见下） |

`AgentPackageAgent` 的 docstring（`:113-119`）把排除项写成了契约：

> Deliberately excludes ``github`` because its installation binding belongs to the target deployment. Runtime memory, conversations, credentials, and other user state are not part of ``AgentConfig`` and are never read while building this document.

注意最后半句 —— **不是靠 `exclude` 参数过滤，而是根本没有去读**。`_export()`（`:422-444`）只从 `AgentConfig` 取字段、只额外读 `SOUL.md`，从不触碰 memory 存储。

### 线上 JSON（序列化后）

`GET /export` 带 `response_model=AgentPackage` + `response_model_exclude_none=True`（`:409-410`），所以 `None` 字段**不出现在输出里**。一个只有名字和 SOUL 的 agent 导出后就是：

```json
{
  "format": "deerflow.custom-agent",
  "version": 1,
  "agent": {
    "name": "database-agent",
    "description": "shared backend",
    "memory_enabled": true,
    "soul": "database soul"
  }
}
```

（这正是 `tests/test_custom_agent.py:752-768` 断言的完整对象。）

字段全表 —— 也就是「可移植」的精确边界：

| `agent.*` | 来源（导出时） | 导入时如何落盘 |
|-----------|--------------|--------------|
| `name` | `agent_cfg.name`（`:429`） | 被路径参数 `?name=` 覆盖（`:387`），再 `_normalize_agent_name()` 转小写（`:390`） |
| `display_name` | `agent_cfg.display_name`（`:430`） | `_build_agent_config` 仅在为真时写入（`:257-258`）；`AgentDisplayName` 校验 ≤100 码点、拒绝控制/双向/不可见字符 |
| `description` | `agent_cfg.description`（`:431`） | 非空才写（`:259-260`） |
| `model` | `agent_cfg.model`（`:432`） | 仅由 `_apply_model_behavior` 按 `model_fields_set` 写入（见下） |
| `tool_groups` | `agent_cfg.tool_groups`（`:433`） | `is not None` 才写（`:261-262`）；**`None` 与 `[]` 语义不同**（None=全部，[]=无） |
| `knowledge_scope` | `agent_cfg.knowledge_scope`（`:435`） | 非 `None` 才写，且过 `canonicalize_knowledge_scope()`（`:263-264`） |
| `mcp_plugins` | `agent_cfg.mcp_plugins`（`:434`） | `is not None` 才写（`:265-266`） |
| `skills` | `agent_cfg.skills`（`:436`） | `is not None` 才写（`:267-268`） |
| `allowed_subagents` | `agent_cfg.allowed_subagents`（`:437`） | `is not None` 才写（`:269-270`） |
| `model_settings` | `agent_cfg.model_settings`（`:438`） | `_apply_model_behavior` → `model_dump(exclude_none=True)`（`:228`） |
| `thinking_enabled` | `agent_cfg.thinking_enabled`（`:439`） | 同上 |
| `reasoning_effort` | `agent_cfg.reasoning_effort`（`:440`） | 同上（`low\|medium\|high`） |
| `memory_enabled` | `agent_cfg.memory_enabled`（`:441`） | **只有 `False` 才写**（`:271-272`） |
| `soul` | `load_agent_soul(name, user_id) or ""`（`:424`） | 作为第三个位置参数传给 `store.create()`（`:288`） |

**不在包里的**（`AgentConfig` 有但 `AgentPackageAgent` 没有）：`github`（`agents_config.py:248`）。`extra="forbid"` 让「有人手工把 `github` 加进 JSON」变成 422 而不是静默忽略（见 §失败策略）。

### SOUL 的位置

SOUL 不是 `AgentConfig` 的字段，是独立的 `SOUL.md` 文件。导出时用 `load_agent_soul(name, user_id=user_id) or ""`（`:424`）读成字符串塞进 `agent.soul`；导入时由 `get_agent_store().create(name, config_data, body.soul, user_id=user_id)`（`:288`）写成独立的 SOUL 文档（file store 是 `SOUL.md`，SQL store 是 `AgentRow.soul` 列）。

这就是「往返」成立的前提：`soul` 在两边都是**一等字段**，不是描述文本的一部分。

## 鉴权与边界

### 四道门（按执行顺序）

| # | 门 | 导入（`:384-404`） | 导出（`:415-455`） |
|---|----|------------------|------------------|
| 1 | `@require_permission(...)` | `("agents", "write")`（`:383`） | `("agents", "read")`（`:414`） |
| 2 | `_require_agents_api_enabled()` | `:386` | `:417` |
| 3 | `_validate_agent_name(name)` | 对 `target_name`（`:388`） | 对 `name`（`:418`） |
| 4 | `_validate_model_exists(model)` | `body.agent.model`（`:389`） | —（导出的是已有配置） |

**第 1 道**：`require_permission`（`app/gateway/authz.py:953`）走网关的统一 `resource:action` 决策，与其它 agent 路由一致。PAT 调用方沿用全局规则（PAT 作用域白名单不含 agents 路由 → 403）。

**第 2 道**：`_require_agents_api_enabled()`（`:157-163`）读 `get_agents_api_config().enabled`，关闭时 **403** 且 detail 写明 `Set agents_api.enabled=true to expose agent and user-profile routes over HTTP.`。这条门把「HTTP 面整体关掉」与「权限不足」区分成两个不同来源的相同状态码。`tests/test_custom_agent.py:1242` 钉死两个 portability 端点都被这道门挡住。

**第 3 道**：`_validate_agent_name()`（`:136-149`）用 `AGENT_NAME_PATTERN = re.compile(r"^[A-Za-z0-9-]+$")`（`:37`），失败 **422**，detail 里带正则原文。注意这条拒绝**也覆盖 `?name=` 参数**（导入时校验的是 `target_name`，不是包里的名字），所以重命名目标同样受约束。

**第 4 道**：`_validate_model_exists()`（`:166-186`）只对**导入**生效。它在 `get_app_config().get_model_config(model)` 为 `None` 时抛 **422**（`f"Unknown model '{model}'. Use a model name defined under models: in config.yaml."`），但有两处刻意放宽：

- `model` 为 `None`/空 → 直接返回（`:178-179`，表示「用全局默认」）；
- `get_app_config()` 本身抛异常时只 `logger.warning(...)` 并返回（`:180-184`）—— 注释的理由是 *"the runtime still falls back to the default for an unknown model"*，宁可放过也不让裸部署（没有 `config.yaml`）写不进去。

这条校验让一个**跨部署的包**大概率在目标机器上失败 —— 这是**有意的**：模型名是部署本地的东西（见 §与相邻机制的关系）。

### owner 作用域

两边都用 `user_id = get_effective_user_id()`（`:391`、`:420`），并把它显式传给 store 调用（`load_agent_config(..., user_id=)`、`load_agent_soul(..., user_id=)`、`store.create(..., user_id=)`）。

结果是 **owner-scoped**：同一个包，alice 导入一次、bob 导入一次，落在两个独立的目录里，互相不可见也不冲突。`tests/test_custom_agent.py:732-750` 直接 patch `get_effective_user_id` 成 `alice`/`bob`，断言两次都 201 且 `tmp_path/users/alice/agents/shared-agent/SOUL.md` 与 `.../bob/...` 各自存在。

掉用 `get_effective_user_id` 而不是「从包里读 `owner`」是关键：包是**内容**，不是**身份**。任何人拿到的包，导入后都归**导入者**。

### source/target 名字不同

导入时 `target_name = name or body.agent.name`（`:387`）。也就是说：

- 不带 `?name=` → 用包里的名字；
- 带 `?name=research-lead-copy` → 落地为 `research-lead-copy`，**包本身不被修改**（不是原地 replace 再导入）。

`tests/test_custom_agent.py:670-675` 从 `research-lead` 导出后导入成 `research-lead-copy`，断言响应是 `{**payload, "name": "research-lead-copy", "knowledge_scope": None}` —— 注意两个差异：`name` 被替换，`knowledge_scope` 因为导入的是 `/export` 的输出（无该键）而落成 `None`。

前端对应的 API 调用在 `frontend/src/core/agents/api.ts:93-...`（`importAgentPackage(agentPackage, name?)` → `POST /api/agents/import?name=`），hook 在 `frontend/src/core/agents/hooks.ts:95-108`（成功后 `invalidateQueries(["agents"])`）。导出在 `frontend/src/components/workspace/agents/agent-card.tsx:139-152`：拿 JSON 做 Blob，文件名 `${agent.name}.deerflow-agent.json`。

## 失败策略

### 导入（`:393-404`）

```python
try:
    return await _persist_new_agent(body.agent, normalized_name, user_id, memory_enabled=body.agent.memory_enabled)
except AgentExistsError:
    raise HTTPException(409, f"Agent '{normalized_name}' already exists")
except Exception as e:
    logger.error("Failed to import agent '%s' (%s)", normalized_name, type(e).__name__, exc_info=True)
    raise HTTPException(500, "Failed to import agent")
```

| 状态码 | 来源 | 例子 |
|--------|------|------|
| **422**（请求校验） | `AgentPackage` / `AgentPackageAgent` / `AgentCreateRequest` 的 pydantic 校验 | 缺 `format`、`version=2`、`format="unknown"`、`agent` 里多一个 `github` 键、名字 `"bad name"`（`test_custom_agent.py:699-713` 的 6 个参数化用例） |
| **403** | `_require_agents_api_enabled` 或 `require_permission` | API 关闭；无 `agents:write` |
| **422**（业务） | `_validate_agent_name` / `_validate_model_exists` | 非法名字；模型未配置 |
| **409** | `AgentExistsError` | 同名 agent 已存在 |
| **500** | 其它任何异常 | store 故障、Soul 写失败 |

**409 是「绝不覆盖」的证据**：`_persist_new_agent` 只调 `store.create()`（`:288`），从不调 `store.update()`。两个 store 都在**底层**保证这一点：

- `FileAgentStore.create`（`persistence/agents/file.py:128-151`）：先查 `agent_dir.exists() or paths.agent_dir(name).exists()` → `AgentExistsError`；`mkdir(exist_ok=False)` 抛 `FileExistsError` 也转成 `AgentExistsError`；写失败时 `shutil.rmtree` 清理残留目录。
- `SqlAgentStore.create`（`persistence/agents/sql.py:143-161`）：依赖 `UNIQUE(user_id, name)`，`IntegrityError` → `AgentExistsError`。

所以 **check-then-write 的竞态也被 store 兜住**，路由不需要额外加锁。`test_custom_agent.py:719-729` 断言冲突后原 agent 的 `soul` 仍是 `"original"`。

### 导出（`:446-455`）

| 状态码 | 来源 |
|--------|------|
| **403** | API 关闭 / 无 `agents:read` |
| **422** | `_validate_agent_name` |
| **404** | `load_agent_config` / `load_agent_soul` 抛 `FileNotFoundError` → `f"Agent '{normalized_name}' not found"` |
| **500** | 其它 |

导出**没有** `?name=` 参数，也没有「导出别人的 agent」的入口：名字先 `_normalize_agent_name` 转小写，`load_agent_config(name, user_id=get_effective_user_id())` 走 owner 作用域，所以别人的同名 agent 表现为 **404**（而不是 403）—— 与 agent 详情端点一致的「不暴露存在性」策略。

### 500 文案

两处 500 都是**固定文本**（`"Failed to import agent"` / `"Failed to export agent"`），原始异常只进日志且**只打类型名**（`:403`、`:451`）。原因与 `routers/AGENTS.md` 的通用规则一致：store 异常可能带宿主路径。

## 为什么是 create-only

三条独立理由，缺一条都不够：

1. **安全性**：包是**外部输入**（用户可以把任意 JSON 贴进导入框）。如果导入 = upsert，任何拿到别人包的人都能用它**覆盖**自己的 agent —— 表面无害，但 agent 的 `tool_groups`/`mcp_plugins`/`skills` 是**工具授权面**，一次导入就能把一个 agent 从「只读」扩到「全部工具」。create-only 让「导入」这个动作永远不会改变既有 agent 的能力。
2. **可预测性**：409 是显式的，调用方知道需要换名字；upsert 会让「我点了导入」产生不可见的差异（字段合并、`None` vs 缺失、`model_settings` 子字段继承）。
3. **实现简单**：`_persist_new_agent` 与 `POST /api/agents` **共用同一个函数**（`:282-293`）。create-only 让这两条路径完全等价，不需要为导入单独设计合并语义。

## 写排空：取消不会丢写

普通创建与导入共用 `_persist_new_agent`，它把落盘包在 `run_drained_write("Create agent", _create_agent, (AgentExistsError,))`（`:293`）里。

`run_drained_write`（`app/gateway/persistent_writes.py:18-47`）：同步函数 → `asyncio.to_thread` → `await_drained`。三条性质：

- **排队中的写不会被 cancel**：客户端断连触发的 handler cancel 不会取消一个还没开始的写线程（裸 `asyncio.to_thread` 会）；
- **已开始的写会跑完**：handler 被取消后仍等到 worker 结束；
- **失败不丢**：`expected_errors=(AgentExistsError,)` 原样上抛（handler 还连着时映射成 409），其它异常记一条**只带类型**的日志。

`tests/test_agents_router_write_drain.py` 把这个契约钉死：

| 测试 | 行 | 钉住什么 |
|------|----|---------|
| `test_agent_persistent_writes_route_through_write_drain` | `:55` | 调用顺序 `["Create agent", "Create agent", "Update agent", "Update user profile", "Delete agent"]` —— 普通创建与导入**都**用 `"Create agent"` 这个 action 名，且 `get_agent`（读）不经过 drain |
| `test_agent_import_drains_started_store_write_across_repeated_cancellation` | `:77` | 用 `threading.Event` 把 `store.create()` 卡住 → 连续 cancel 两次 → task 仍未结束 → 放行后 `await` 抛 `CancelledError`，但 agent 确实落盘（`soul == "imported soul"`、`memory_enabled is False`） |
| `test_agent_creation_drains_store_write_across_repeated_cancellation` | `:118` | 普通创建同契约 |
| `test_agent_update_logs_lost_worker_failure_after_cancellation` | `:192` | 失败类型名 `OSError` 出现在 `app.gateway.persistent_writes` 日志里，且 `worker-secret` **不**出现在日志 |

最后两条合起来是「`memory_enabled=False` 真的穿过了 drain」的证据 —— 导入路径没有丢掉 `AgentPackageAgent` 独有的那个字段。

## 与相邻机制的关系

| 相邻机制 | 关系 |
|---------|------|
| `POST /api/agents`（创建，`:496-529`） | **同一个** `_persist_new_agent`，同一个 409/500 映射；区别只在导入多一层 `AgentPackage` 校验和 `?name=` 覆盖 |
| `PUT /api/agents/{name}`（更新，`:532`） | 与导入**刻意无关**。更新走 `preserve_non_managed_fields(..., new_tool_groups=...)`（见 `routers/AGENTS.md`）；导入永远不调用它，因为导入不更新已有记录 |
| `get_agent_store()`（`deerflow/persistence/agents/`） | 唯一落盘抽象（file / SQL 两个后端）。两条路径都只调 `.create()` / `.get()`，所以换后端不影响 portability —— `test_custom_agent.py:752-778` 用真实 `SqlAgentStore` 跑一遍完整往返 |
| `load_agent_config` / `load_agent_soul` | 导出侧的读入口，均带 `user_id=`；`load_agent_config(name=None)` 返回 `None`（默认 agent 不是 custom agent 记录） |
| `config.yaml -> agents_api.enabled` | 整个 agent/user-profile HTTP 面的开关，portability 端点也在其内 |
| GitHub 事件驱动 agent | `github:` 块属于 `AgentConfig` 但**不可移植**；它由 operator/用户在目标部署手工写回，不是导入的一部分 |
| Memory（DeerMem） | `memory_enabled` 只是个**布尔开关**（`agents_config.py:244`，默认 `True`）；memory **内容**从不进入包 |
| 模型配置（`config.yaml models:` 或托管模型） | `_validate_model_exists` 用有效配置校验 `agent.model`。跨部署搬包时最可能踩的坑：目标机器没有同名模型 profile → 422 |

## 版本演化契约

`format` 与 `version` 都是 `Literal`（`:131-132`），这是刻意的:

- `format: Literal["deerflow.custom-agent"]` + `version: Literal[1]` = **单版本声明**。README 里如果要求「向前兼容」，现在**没有**：一个 v2 文档在 v2.2.0 上直接 422（`test_custom_agent.py:706`）。
- 想加兼容性就得把 `version: Literal[1]` 换成 `int` + 版本分派，并且**保留 v1 的语义**；在那之前，加字段就必须同时改 `AgentPackageAgent` 与前端 `frontend/src/core/agents/types.ts:46-50` 的 `AgentPackage` 接口，并考虑 `extra="forbid"` 会让「旧版后端读新版包」直接失败（而不是忽略未知字段）。

`extra="forbid"` 在这个设计里是**安全特性**：它把「有人在包里夹带 `github` 安装绑定」从「静默忽略」变成「显式 422」，同时防止未来字段被旧后端静默丢弃后再被新后端读到 `null`。

## 测试地图

| 测试 | 文件:行 | 覆盖 |
|------|---------|------|
| `test_agent_package_round_trip_preserves_portable_behavior` | `test_custom_agent.py:641` | 往返：**逐字节相等**的包体、`Content-Disposition` 头、`?name=` 改名 |
| `test_agent_package_excludes_runtime_state_and_operator_github_binding` | `:677` | 手工往 `config.yaml` 塞 `memory_enabled: false` + `github:` 块 + 写 `memory.json` → 导出里只有 `memory_enabled: false`，**没有** `github`、没有 `memory`、没有 `"secret"` |
| `test_agent_package_import_rejects_unsupported_or_unsafe_documents` | `:714`（参数化表 `:698-713`） | 6 个畸形包全 422，且 agent 列表仍为空 |
| `test_agent_package_import_conflicts_explicitly_and_never_overwrites` | `:719` | 409 且原有 `soul` 不变 |
| `test_agent_package_import_is_scoped_to_current_user` | `:732` | alice/bob 各自 201，目录互不重叠 |
| `test_agent_package_round_trip_uses_configured_store_abstraction` | `:752` | 真实 SQL store 往返；断言导出对象**精确等于** 4 键 |
| `test_agent_portability_routes_return_403` | `:1242` | `agents_api.enabled=false` → 导入/导出都 403 |
| `test_agent_persistent_writes_route_through_write_drain` | `test_agents_router_write_drain.py:55` | drain 调用顺序（含导入） |
| `test_agent_import_drains_started_store_write_across_repeated_cancellation` | `:77` | 重复 cancel 下写仍完成，`memory_enabled=False` 生效 |

## 陷阱清单

1. **`None` ≠ `[]`**。`tool_groups` / `skills` / `mcp_plugins` / `allowed_subagents` 的 `None` 表示「继承全部」，`[]` 表示「一个都不要」（`agents_config.py:215-232`）。导入时 `_build_agent_config` 用 `is not None` 判断（`:261-270`），所以 `[]` **会**被写进配置 —— 这是特性，别「顺手改成真值判断」。
2. **`response_model_exclude_none=True` 只在导出侧**。导入的响应是 `AgentResponse`（`response_model=AgentResponse`，`:378`），没有 exclude，所以 `knowledge_scope: null` 会出现（`test_custom_agent.py:675` 正是这么断言的）。
3. **`memory_enabled` 只在 `False` 时落盘**（`:271-272`），与 `AgentConfig` 的默认值 `True`（`agents_config.py:244`）配对，保证「未设置」与「显式开启」在磁盘上不可区分 —— YAML 保持最小。
4. **`_apply_model_behavior` 用 `model_fields_set` 而非值**（`:208-228`）。导入的 `model`/`model_settings`/`thinking_enabled`/`reasoning_effort` 只有在包**真的带了**这个键时才写；`existing is None`（导入路径）时未带就是「不写」。所以「包里省略 `thinking_enabled`」与「包里写 `thinking_enabled: false`」是两件事。
5. **`?name=` 也必须过名字校验**（`_validate_agent_name(target_name)`，`:388`），并且**大小写不敏感冲突**：`_normalize_agent_name` 转小写后 409 判断用的是转小写后的名字，所以导入 `Foo` 与已有 `foo` 冲突。
6. **导出不带 `?name=`，也不带版本协商**。想导出旧版本格式，现在没有入口。
7. **500 文案固定、日志只打类型**：`logger.error("Failed to import agent '%s' (%s)", normalized_name, type(e).__name__, exc_info=True)`（`:403`）。`exc_info=True` 意味着**堆栈**进日志 —— 堆栈里可能有路径，但不会进响应体。
8. **`AgentPackage` 与 `AgentPackageAgent` 都 `extra="forbid"`**，但 `AgentCreateRequest` **没有**（`:77-92` 无 `model_config`）。所以普通创建请求多带一个未知键会被 pydantic 默认忽略，而同一个键放进包里就是 422。这是两端唯一的宽严差异，别把它当成 bug 修。
