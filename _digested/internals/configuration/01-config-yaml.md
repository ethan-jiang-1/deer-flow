---
title: "AppConfig — config.yaml 内部机制"
description: 'AppConfig 是一个 Pydantic BaseModel（app_config.py:224），model_config = ConfigDict(extra="allow")（app_config.py:327）意味着未知 key 自动忽略并保留。'
topics: [configuration, hot-reload, yaml-config]
verified_against: v2.2.0
last_verified: 2026-11-08
---

# AppConfig — config.yaml 内部机制

`AppConfig` 是一个 Pydantic `BaseModel`（`app_config.py:224`），`model_config = ConfigDict(extra="allow")`（`app_config.py:327`）意味着未知 key 自动忽略并保留。它是 **56** 个字段的顶层模型（`app_config.py:224` 到 `resolve_config_path` 之前，即 `app_config.py:448`）；而 `config.example.yaml` 里**实际启用**（未注释）的顶层键是 **43** 个（`config_version` + 42 个 schema 字段），`config.example.yaml` 共 3680 行。二者不等价：`plugins` / `auth` / `checkpointer` / `stream_bridge` / `subagents` / `guardrails` / `typesafe` / `circuit_breaker` / `llm_call` / `channel_connections` / `tool_progress` / `dedupe_storage` / `acp_agents` / `pii_redaction` 是已声明字段但 example 里只以注释示例出现；`config_version` 与 `uploads`、`channels` 则是 `extra="allow"` 的 schema 外键。

> 计数口径（v2.2.0 实测）：`yaml.safe_load(config.example.yaml)` 得到 43 个顶层 key；`config.example.yaml:23` 是 `config_version: 63`。v2.1.0 同一口径是 38 个 key / `config_version: 45`。

## from_file() 流水线

`AppConfig.from_file()` (`app_config.py:478`) 只做两件事：解析路径 + 读文件，真正的流水线在同文件 `_from_yaml_text()` (`app_config.py:494`)：

```
① resolve path        → AppConfig.resolve_config_path()（见下方优先级链）
② YAML parse          → yaml.safe_load(text) or {}
③ version check       → _check_config_version()（app_config.py:599）
④ env var 解析        → resolve_env_variables()（app_config.py:644）
⑤ DB defaults         → _apply_database_defaults()
⑥ load extensions     → ExtensionsConfig.from_file()，按 alias dump 后与 config.yaml 的 extensions 段合并（app_config.py:520-526）
⑦ Pydantic validate   → cls.model_validate(config_data)（app_config.py:528）
   ├─ 无 models 时只 warning，不报错（app_config.py:529-533）
   └─ _build_name_indexes() 建 name→config 索引（app_config.py:668）
⑧ ACP + singletons    → _apply_singleton_configs()（app_config.py:547）
```

**⑥ 的合并方向值得注意**：先取 `extensions_config.json` 的 `model_dump(by_alias=True)`，再用 config.yaml 里 `extensions:` 段的 `exclude_unset` dump 覆盖 —— **config.yaml 显式写了才赢**，没写就沿用 JSON。这样 config.yaml 的 extensions 字段仍然属于主配置热加载契约。

### 第③步：config_version

`_check_config_version()` (`app_config.py:599`) 从 config.yaml 读 `config_version`（整数，缺失或非数值 = 0），再沿 config.yaml 所在目录**向上最多 5 级**找 `config.example.yaml`，取其 `config_version`（找不到 example 就静默返回）。用户版本 < example 版本时只发 warning（`app_config.py:636-639`）：

```
Your config.yaml (version 45) is outdated — the latest version is 63. Run `make config-upgrade` to merge new fields into your config.
```

`make config-upgrade` 调 `scripts/config-upgrade.sh`：先按 `DEER_FLOW_ENV_FILE`（若设置）加载 dotenv（`scripts/config-upgrade.sh:35` 起），再运行内联 Python，用 `AppConfig.resolve_config_path` 而不是复制优先级链（`config/AGENTS.md` 明确要求），递归合并 example 中新的 key（不覆盖用户已有值）、更新 `config_version`、备份到 `config.yaml.bak`。

> v2.2.0 的 45→63 跨越了多次 schema 变更，其中带"语义迁移"的一步是 **v46**：当 `tools[]` 里已有 `group: knowledge` 的条目、且 `knowledge_base.enabled` 缺失时，升级把它写成 `true`（视为"升级前就已经启用"）；显式 `true`/`false` 一律保留原值。`tools[]` 里 legacy 的 provider 连接参数只有 RAGFlow `knowledge_search` 会被搬走，LightRAG 等后端保持 tool 局部设置不动。

### 第⑤步：DB defaults

```python
# app_config.py — CONFIG_FILE_DATABASE_DEFAULTS（app_config.py:76；注入逻辑 app_config.py:590-596 用 setdefault 逐键补齐）
CONFIG_FILE_DATABASE_DEFAULTS = {
    "backend": "sqlite",
    "sqlite_dir": ".deer-flow/data",
}
```

用户不写 database section 就自动走 SQLite。

### 第⑧步：singleton 传播

`_apply_singleton_configs()` (`app_config.py:548`) 把解析好的配置推到各子系统的模块级全局变量（`load_title_config_from_dict(config.title)`、`load_summarization_config_from_dict(...)`、`load_memory_config_from_dict(...)`、`load_subagents_config_from_dict(...)` 等，见 `app_config.py:552-...`）。v2.2.0 新增的 `blob_storage`（`app_config.py:556`）与 `typesafe`（`app_config.py:561`）走同一机制：`deerflow/config/blob_storage_config.py::load_blob_storage_config_from_dict`、`typesafe_config.py::load_typesafe_config_from_dict` 各自维持一个模块级单例。这一步确保 `get_memory_config()`、`get_checkpointer_config()` 等独立入口返回与 AppConfig 一致的值。如果 checkpointer config 相比上次变了，还会调用 `reset_checkpointer()` 和 `reset_store()` 回收旧对象。

`blob_storage` 还多了一道**自愈**：`get_blob_storage_config()` 在返回前若发现进程里已经加载过 AppConfig（`_app_config is not None`）就先调一次 `get_app_config()`，让签名校验触发重载——否则一个不经过 `get_app_config()` 的读者（例如决定要不要外置 tool 结果的 middleware）会在改完 YAML 后读到陈旧的 `blob_storage.enabled`。

---

## get_app_config() 缓存

`get_app_config()` (`app_config.py:798`) 维护一组模块级全局变量（`app_config.py:731-746`）：

```python
_app_config: AppConfig | None = None            # 缓存的实例
_app_config_path: Path | None = None            # 加载时的路径
_app_config_mtime: float | None = None          # 加载时的文件 mtime
_app_config_signature: _ConfigSignature | None = None  # (mtime, size, sha256) 内容指纹
_app_config_is_custom = False                   # set_app_config() 注入后置 True
_app_config_source: str | None = None           # reload_app_config(path) 钉住的绝对路径
_app_config_extensions_source: ExtensionsConfig | None = None  # extensions 快照来源
_current_app_config / _current_app_config_stack : ContextVar  # 运行时覆盖栈
```

**触发 reload 的条件**（`should_reload`，`app_config.py:825`）：路径变化、`(mtime, size, sha256)` 内容指纹变化、**或 `get_extensions_config()` 返回了新的实例**（说明 `extensions_config.json` 变了，`extensions` 快照必须跟着换）；`_app_config is None` 时首次加载。

并发语义（`_app_config_lock`，`app_config.py:730`）：
- 读、`reload_app_config()`、`reset_app_config()`、`set_app_config()` 全在同一把 `RLock` 里发布 `(revision, signature, extensions snapshot, source pin)`。
- `reload_app_config(config_path)` 会**钉住绝对路径**，之后改 cwd 不会把后续读取重定向；显式加载失败保留旧的 pin；无参 `reload_app_config()`、`reset_app_config()`、`set_app_config()` 都清 pin；环境变量/自动解析路径永不 pin。
- 每次读都要 stat + hash `config.yaml` 和 `extensions_config.json`，所以异步请求路径通过 `asyncio.to_thread` 调用（Gateway 路由与插件授权在 `app/gateway/authz.py`）。

**测试注入保护：** `set_app_config()` 设 `_app_config_is_custom = True`，永久禁止 auto-reload。

`get_app_config()` 返回前还会过一遍 `merge_managed_models(config)`（`app_config.py:841`）：把管理员在 Web 端注册的、存在加密 runtime-home 目录里的托管模型合并进模型列表。YAML 条目在重名时赢；托管模型的变更只产生新的"有效快照"，不改动正在运行的实例或显式注入的 AppConfig。**`AppConfig.from_file()` 本身仍然只读 YAML**。

---

## ContextVar 覆盖栈

`_current_app_config` 是一个 `ContextVar`（`app_config.py:749`）指向运行时覆盖：

```python
push_current_app_config(override_config)   # app_config.py:943 — 入栈当前值 + 置新值
# ... 在覆盖范围内执行 ...
pop_current_app_config()                   # app_config.py:950 — 弹出
```

用于需要临时换配置的场景（如多租户内嵌调用、测试），`get_app_config()` 在检测到 `ContextVar` 有值时直接返回覆盖，不走文件读取、也不拿锁。配套只读入口：`peek_current_app_config()` / `peek_loaded_app_config()` —— 后者返回"本进程已加载的配置"，进程从没加载过时返回 `None`，用于区分"宿主没有 config"和"宿主有 config 但现在读不到"。

---

## Auth 侧的第二条 dotenv 路径

`deerflow/env.py` 是 2.2.0 新增的 37 行小模块（`env.py:10` 的 `load_selected_env_file()`），只做一件事：若设置了 `DEER_FLOW_ENV_FILE`，就读这个文件并 `load_dotenv(stream=StringIO(contents), override=False)`；未设置则返回 `False`，调用方回落原来的 `load_dotenv()` 默认发现。调用点有三处，都写成同一模式 `if not load_selected_env_file(): load_dotenv()`：

| 调用点 | 位置 |
|---|---|
| 配置加载器 | `app_config.py:67`（`if not load_selected_env_file():` 在 `app_config.py:70`） |
| Gateway 认证 | `app/gateway/auth/config.py:60-63`（`get_auth_config()` 首次调用时加载） |
| 交互调试 CLI | `backend/debug.py:23,33` |

细节（`env.py:10-37`）：相对路径按**后端进程 cwd** 解析（不是 YAML 所在目录）；目标必须是可读的 UTF-8 普通文件，读失败抛 `ValueError`（不回显内容）；用 `utf-8-sig` 读以吞掉 Windows 记事本写的 BOM；进程里已存在的变量（包括空值）优先。若同时设置了 `PYTHON_DOTENV_DISABLED`（`1/true/t/yes/y`，大小写不敏感），**显式选择**会直接抛 `ValueError` 而不是静默忽略。完整语义见 [getting-started/05-environment.md](../../getting-started/05-environment.md)。

---

## AppConfig 顶层字段速览

| Section | 类型 | 作用 |
|---------|------|------|
| 🆕 `lead_prompt_overlay` | `PromptOverlay` | operator 拥有的字面 `prepend`/`append`，包在组装好的 lead system prompt 外侧；subagent 侧对应 `subagents.agents.<name>.prompt_overlay`，DeerMem 侧是 `memory.backend_config.prompt_prepend/prompt_append` |
| `log_level` | `str` | 日志级别（仅 deerflow + app logger），**重启生效** |
| `logging` | `LoggingConfig` | trace id 是否进日志、什么格式（`logging.enhance`），**重启生效** |
| `token_usage` | `TokenUsageConfig` | 用量统计开关 |
| `token_budget` | `TokenBudgetConfig` | Per-run token 限制（warn + hard_stop 阈值） |
| `recursion_limit` / `max_recursion_limit` | `int` | run 的 super-step 默认上限（100）/ 服务端硬上限（1000），每次 run 实时读 |
| `models` | `list[ModelConfig]` | LLM 模型列表：`use` 类路径、`supports_thinking`/`supports_vision`、🆕 `aliases`、🆕 `reasoning:` 契约、`request_admission` |
| `knowledge_base` 🆕 | `KnowledgeBaseConfig` | 仅 `enabled` / `scope_selection_enabled` 两个 flag，门控 `knowledge` 组工具与选择器；provider 连接参数不在这一层 |
| `tool_groups` | `list[ToolGroupConfig]` | tool 逻辑分组（web / file:read / file:write / bash / browser / knowledge） |
| `tools` | `list[ToolConfig]` | 自定义 tool（resolve_variable 加载） |
| `sandbox` | `SandboxConfig` | 沙箱 provider、host bash 开关、`ownership` lease 存储、`network` 出网管控，**重启生效** |
| `skills` | `SkillsConfig` | skills 目录路径（host + container），`container_path` 单独**重启生效** |
| `skill_scan` / `skill_evolution` | | 原生 skill 安全扫描 / agent 自演化 |
| `tool_output` | `ToolOutputConfig` | 超大 tool 结果磁盘持久化 + 截断 |
| 🆕 `tool_artifacts` | `ToolArtifactConfig` | tool-artifact handle 注册表（issue #4676） |
| 🆕 `pii_redaction` | `PiiRedactionConfig` | 模型上下文里的确定性 PII 脱敏（issue #3190） |
| `tool_search` | `ToolSearchConfig` | 延迟 tool 加载 |
| `suggestions` / `input_polish` | | 追问建议 / 发送前改写 |
| `loop_detection` | `LoopDetectionConfig` | 循环 tool call 检测 |
| `read_before_write` | | 写文件前必须读 |
| `projects` | `ProjectsConfig` | 项目工作区：instructions 字节上限、document shelf 索引渲染上限、回收站保留天数 |
| `safety_finish_reason` | | provider 安全过滤拦截 |
| `uploads` | （extra） | 上传大小限制 + 文档自动转换 |
| `subagent_runtime` / `subagent_batches` | | 进程级准入 / 持久化批调度，**重启生效** |
| `verification` / `guardrails` / `circuit_breaker` / `llm_call` | | 收据与 judge / tool 执行前授权 / LLM 断路器 / LLM 并发上限 |
| `acp_agents` | `dict[str, ACPAgentConfig]` | ACP 外部 agent |
| `subagents` | `SubagentsAppConfig` | subagent 运行时 + override |
| 🆕 `typesafe` | `TypeSafeConfig` | 所有 TypeSafe(Jev) 消费者共享的连接/模型/超时默认值；严格模式校验 |
| `authorization` | `AuthorizationConfig` | 可插拔授权 provider（RBAC 等） |
| `agents_api` | `AgentsApiConfig` | 自定义 agent 管理 API |
| `summarization` / `title` / `memory` / `task_continuity` | | 摘要 / 标题 / 可插拔记忆（5 个后端）/ 任务笔记 |
| 🆕 `blob_storage` | `BlobStorageConfig` | 内容寻址 blob 存储（`enabled`/`backend`/`backend_config`），默认关、无生产者 |
| `database` / `checkpointer` / `run_events` / `agent_storage` / `dedupe_storage` | | 统一数据库 / 已废弃的 legacy checkpointer / run 事件 / agent 定义 / 入站去重，**重启生效** |
| `scheduler` / `mcp_tasks` | | 定时任务 / 长时 MCP 任务，**重启生效**（`scheduler.recursion_limit` 例外） |
| 🆕 `deployment` | `DeploymentConfig` | `multi_instance` 声明：多 Gateway 实例共享同一 DB 时的启动门禁开关，**重启生效** |
| `run_ownership` | | 跨进程 run 租约，**重启生效** |
| `stream_bridge` / `plugins` / `channel_connections` / `channels.leader_lease` | | SSE 桥 / 打包扩展 / 用户 IM 绑定 / IM 传输 leader lease，**重启生效** |
| `auth` | `AuthConfig` | `local`（含 🆕 `throttle_storage`）与 `oidc` |

注：当前 `config_version` = **63**（`config.example.yaml:23`）。历史（用 git 逐个锚点核对）：初始锚点 `162fb214` = 10 → `4915b5e` = 19 → `cd34a1a5` = 28 → `e5c62cab` = 33 → `431892e1`（锚点 #5）= **36** → `v2.1.0` = **45** → `v2.2.0` = **63**（sync #7）。`checkpointer` 已废弃但后向兼容（统一由 `database` 接管）。

## 🆕 v2.2.0 新增 section 速查

| Section | 类别 | 关键事实 |
|---|---|---|
| `blob_storage` | 新模块 `blob_storage_config.py` | 三个 host 共享字段 `enabled`(false) / `backend`(local_fs) / `backend_config`({})。`backend` 可以是 `storage/backends/<name>/` 里暴露 `STORE_CLASS` 的目录名，也可以是 `module.Class` / `module:Class`。工厂在 `get_blob_store()` 时解析，**解析失败直接抛错**（fail-fast）而不是悄悄换后端。`local_fs` 读 `backend_config.root`，空则 `{runtime_home}/blobs`。example 注释明确：**还没有生产者迁移过来**，不设这个 key 行为完全不变 |
| `knowledge_base` | `knowledge_base_config.py`（15 行） | `model_config = ConfigDict(validate_default=True)`；`enabled: false`、`scope_selection_enabled: false`（仅自定义 agent 聊天，且只在生效的 `knowledge_search` 是内置 RAGFlow 工具时才显示选择器）。真正的门控在 `tools/tools.py:155-157`：`enabled` 不为真时把 `tool.group == "knowledge"` 的条目全部剔除 |
| `typesafe` | `typesafe_config.py` | `model_config = ConfigDict(strict=True)`。7 个可选项：`api_key` / `api_key_env`(默认 `TYPESAFE_API_KEY`) / `base_url`(默认 `https://api.typesafe.ai`) / `model` / `timeout` / `deadline_seconds` / `max_attempts` / `retry_backoff`。优先级：消费者 `config` > 本块 > 内置默认（`deerflow.typesafe.connection.resolve_connection`）。严格模式的理由：lax 模式会把 `max_attempts: true` 静默读成 `1`，而同样的值写在 `guardrails.provider.config` 里会被拒 |
| `deployment` | `deployment_config.py` | 只有一个字段 `multi_instance: false`；等价环境变量 `DEER_FLOW_MULTI_INSTANCE`（空 / `0` / `false` / `no` / `off` 算"未声明"）。声明为真后 startup 强制要求 `database.backend: postgres`、`run_events.backend: db`、`run_ownership.heartbeat_enabled: true`、Redis stream bridge，并拒绝 `sandbox.ownership.type: memory`、进程内 browser 工具、未开 `scheduler.multi_instance` 的 scheduler、以及"有非 GitHub IM 频道却 `channels.leader_lease.enabled: false`"。理由：`GATEWAY_WORKERS`/`WEB_CONCURRENCY` 只数单进程树的 uvicorn worker，K8s `replicas > 1` 每 Pod 一个 worker，门禁完全看不见 |
| `openai_decisions`（**不是** YAML section） | `deerflow/openai_decisions/client.py` | 任务清单里的 "openai_decisions 配置块" 实为**另一种后端实现**，不是独立 section：它是 TypeSafe 接口的姊妹适配器（issue #7005），复用 `TypeSafeClient` 的传输层（鉴权/重试/退避/预算/有界且不解码的 body 读取），只换 wire：`POST /v1/decisions`、`question` 形态为 `predicate`。默认 `base_url: https://api.openai.com`、`api_key_env: OPENAI_API_KEY`。配置仍写在三个消费者槽位里（`guardrails.provider.use` / `memory.prescreen.use` / `memory.signal_classification.use`），见 `config.example.yaml:3320-3345` 的 Option 4b 注释 |

## 🆕 其它值得单独记的行为

- **`sandbox.ownership`**（`config.example.yaml:1851-1897` 注释示例）：跨实例容器所有权（issue #4206）。单 Gateway 用 `memory`；多实例/负载均衡必须 `type: redis`（`redis_url` / `renewal_interval_seconds` / `ttl_multiplier`（≥2）/ `key_prefix`）。Redis ownership 是 fail-closed 的：拿不到所有权就不发沙箱。Docker Compose 已经设置了 `DEER_FLOW_STREAM_BRIDGE_REDIS_URL`，据此推断多实例并自动启用 redis ownership。
- **`auth.local.throttle_storage`**（`auth_config.py:81` `resolve_login_throttle_storage`）：`auto`（默认）/`memory`/`db`。`auto` 在 `database.backend` 为 `sqlite`/`postgres` 时用共享 `login_throttle` 表；`db` 在 `database.backend: memory` 时降级为进程内计数并 WARNING；配置的数据库引擎不可用时**拒绝启动**。该字段**重启生效**，而 `max_login_attempts` / `lockout_seconds` 仍是实时读。
- **`channels.leader_lease`**（`channel_leader_lease_config.py:35`）：`channels` 段不是 AppConfig schema 字段，但其中 `leader_lease` 子块由这个模块校验，`extra="forbid"`（拼错 key 会直接报错）。`enabled` 默认 `"auto"`：多进程信号（`GATEWAY_WORKERS`/`WEB_CONCURRENCY` > 1、`deployment.multi_instance: true`、`DEER_FLOW_MULTI_INSTANCE=1`）出现时自动开启，单实例不动；`lease_seconds`（默认 30，`ge=3`，每 `lease_seconds // 3` 秒续约）、`grace_seconds`（默认 10，`ge=0`）。**重启生效**。
- **`models[].reasoning:`**（issue #5073，`model_config.py:106` `ReasoningCapabilities`）：mapping 形态才启用契约（`thinking: unsupported|optional|required`、`on_disable_request: keep_enabled|reject`、`dialect: auto|openai_extra_body|anthropic|vllm_chat_template|ollama|none`、`history: preserve|clear`、`effort.{values,default,aliases,path}`）。启用后 `supports_thinking` / `supports_reasoning_effort` 由它推导；矛盾组合在 `ModelConfig` 校验期就失败（`required` 配 `when_thinking_disabled`、`default` 不在 `values` 里、自定义 `effort.path` 旁边还留着 `reasoning_effort` 等）。boolean / level-string 形态的 `reasoning`（Ollama 的 `true`/`false`、gpt-oss 的 `low|medium|high`）仍然是原生 provider 参数，原样透传。
- **`models[].aliases`**（`model_config.py:140`）：最多 16 个字符串，用于在聊天里按别名选中该模型。与 `reasoning.effort.aliases`（把 DeerFlow 通用档位映射到 provider 值）是两件事。

## 🆕 Feature Gating

`GET /api/features` — 运行时特性门控端点（`app/gateway/routers/features.py:104` `list_features`），响应模型 `FeaturesResponse`（`features.py:85`）现在有 **8** 个字段：

| 字段 | 子字段 | 数据源 |
|---|---|---|
| `agents_api` | `enabled` | `config.agents_api.enabled`（实时读） |
| `browser_control` | `enabled` | `browser_capability(config)` |
| `mcp_tasks` | `enabled` | `app.state.mcp_tasks_available`（启动期能力，不是热加载值） |
| `subagent_batches` | `enabled`（`worker_running` 的兼容别名）/ `repository_available` / `worker_running` / `max_running` | `app.state.subagent_batches_available`、`app.state.subagent_batch_repo`、`configured_subagent_max_running()` |
| `conversation_references` | `enabled` / `max_references` | `conversation_references_enabled(config)`（走 `get_config`，开工具不用重启）+ `MAX_CONVERSATION_REFERENCES` |
| 🆕 `knowledge_base` | `scope_selection_enabled` | 要求 `knowledge_base.enabled` **且** `scope_selection_enabled` **且** 有目录/数据集过滤能力 |
| 🆕 `scheduled_tasks` | `available` / `running` / `tool_enabled` / `min_interval_seconds` / `group_notifications` | 仓库存在性、`service.is_running`、`scheduler_tools_enabled(config)`、`scheduler.min_once_delay_seconds`、`channel_connections.enabled` |
| 🆕 `thread_activity` | `available` | `thread_activity_available(request.app.state)`（只有 SQL 持久化时才有读仓库） |

模式不变：config.yaml 定义 flag → Gateway 端点暴露 → 前端 `useQuery` 读取 → UI 条件渲染；但**启动期能力（`app.state.*`）必须如实报告"实际起来了什么"**，而不是热加载后的 config 值 —— 否则前端会去调一个本进程根本没注册的路由。
