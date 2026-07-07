---
title: "AppConfig — config.yaml 内部机制"
description: `AppConfig` 是一个 Pydantic `BaseModel`（`app_config.py:84`），`model_config = ConfigDict(extra="allow")` 意味着未知 key 自动忽略。
topics: [configuration, hot-reload, yaml-config]
---

# AppConfig — config.yaml 内部机制

`AppConfig` 是一个 Pydantic `BaseModel`（`app_config.py:84`），`model_config = ConfigDict(extra="allow")` 意味着未知 key 自动忽略。共 ~35 个顶层 section。

## from_file() 8 步流水线

`AppConfig.from_file()` (`app_config.py:144`) 是配置文件到运行时对象的完整流水线：

```
① resolve path    → 优先级链找到 config.yaml
② YAML parse      → yaml.safe_load()
③ version check   → 对比 config.example.yaml 的 config_version
④ env var 解析    → $VAR → os.getenv()（缺失则 raise ValueError）
⑤ DB defaults     → database section 缺失时注入 sqlite 默认值
⑥ load extensions → 读 extensions_config.json，覆盖 AppConfig.extensions 字段
⑦ Pydantic validate → model_validate() 校验所有 sub-config
⑧ propagate singletons → 推送到各子系统模块级全局变量
```

### 第③步：config_version

`_check_config_version()` (`app_config.py:226`) 从 `config.yaml` 读 `config_version`（整数，缺省 = 0），然后在上 5 级目录找 `config.example.yaml`，取其 `config_version`。用户版本 < example 版本时，发出 warning：

```
Your config.yaml (version 5) is outdated — the latest version is 19.
Run `make config-upgrade` to merge new fields into your config.
```

`make config-upgrade` 调 `scripts/config-upgrade.sh`：
- 运行内联 Python 脚本
- 执行版本特定迁移（如 v1: `src.community.*` → `deerflow.community.*`）
- 递归合并 example 中新的 key（不覆盖用户已有值）
- 更新 `config_version`，备份到 `config.yaml.bak`

### 第⑤步：DB defaults

```python
# app_config.py — _apply_database_defaults()
if "database" not in config_data:
    config_data["database"] = {"backend": "sqlite", "sqlite_dir": ".deer-flow/data"}
```

用户不写 database section 就自动走 SQLite。

### 第⑧步：singleton 传播

`_apply_singleton_configs()` (`app_config.py:188`) 把解析好的配置推到各子系统的模块级全局变量：

```python
load_title_config_from_dict(config.title)
load_summarization_config_from_dict(config.summarization)
load_memory_config_from_dict(config.memory)
load_subagents_config_from_dict(config.subagents)
load_guardrails_config_from_dict(config.guardrails)
load_checkpointer_config_from_dict(config.checkpointer)
# ... 等
```

这一步确保 `get_memory_config()`、`get_checkpointer_config()` 等独立入口返回与 AppConfig 一致的值。如果 checkpointer config 相比上次变了，还会调用 `reset_checkpointer()` 和 `reset_store()` 回收旧对象。

---

## get_app_config() 缓存

`get_app_config()` (`app_config.py:360`) 维护三个模块级全局变量：

```python
_app_config: AppConfig | None = None      # 缓存的实例
_app_config_path: Path | None = None      # 加载时的路径
_app_config_mtime: float | None = None    # 加载时的文件 mtime
```

**触发 reload 的三个条件**（`should_reload`，line 380）：
1. `_app_config is None` — 首次调用
2. `_app_config_path != resolved_path` — 路径变了（环境变量切换）
3. `_app_config_mtime != current_mtime` — 文件被编辑过

**测试注入保护：** `set_app_config()` 设 `_app_config_is_custom = True`，永久禁止 auto-reload。

---

## ContextVar 覆盖栈

除了文件缓存，还有一层 `ContextVar` 运行时覆盖（`app_config.py:336`）：

```python
push_current_app_config(override_config)   # 压入覆盖
# ... 在覆盖范围内执行 ...
pop_current_app_config()                   # 弹出
```

用于需要临时换配置的场景（如测试），`get_app_config()` 在检测到 `ContextVar` 有值时直接返回覆盖，不走文件读取。

---

## ~35 Section 速览

| Section | 类型 | 作用 |
|---------|------|------|
| `log_level` | `str` | 日志级别（仅 deerflow + app logger） |
| `token_usage` | `TokenUsageConfig` | 用量统计开关 |
| `models` | `list[ModelConfig]` | LLM 模型列表 |
| `sandbox` | `SandboxConfig` | 沙箱 provider、host bash 开关 |
| `tools` | `list[ToolConfig]` | 自定义 tool（resolve_variable 加载） |
| `tool_groups` | `list[ToolGroupConfig]` | tool 逻辑分组 |
| `skills` | `SkillsConfig` | skills 目录路径（host + container） |
| `skill_evolution` | `SkillEvolutionConfig` | agent 自我进化 skills |
| `tool_search` | `ToolSearchConfig` | 延迟 tool 加载 |
| `title` | `TitleConfig` | 自动标题生成 |
| `summarization` | `SummarizationConfig` | 上下文摘要 |
| `memory` | `MemoryConfig` | 记忆系统 |
| `agents_api` | `AgentsApiConfig` | 自定义 agent 管理 API |
| `acp_agents` | `dict[str, ACPAgentConfig]` | ACP 外部 agent |
| `subagents` | `SubagentsAppConfig` | subagent 运行时 + override |
| `guardrails` | `GuardrailsConfig` | tool 执行前授权 |
| `circuit_breaker` | `CircuitBreakerConfig` | LLM 断路器 |
| `loop_detection` | `LoopDetectionConfig` | 循环 tool call 检测 |
| `safety_finish_reason` | `SafetyFinishReasonConfig` | provider 安全过滤拦截 |
| `database` | `DatabaseConfig` | DB 后端（默认 SQLite），统一 checkpointer + Store + app repos |
| `run_events` | `RunEventsConfig` | run event 存储 |
| `checkpointer` | `CheckpointerConfig` | ⚠️ **已废弃**，改用 `database` |
| `stream_bridge` | `StreamBridgeConfig` | SSE bridge 后端（memory / redis） |
| `extensions` | `ExtensionsConfig` | MCP + skills 状态（从 JSON 合并） |
| `config_version` | int（extra） | 配置版本号（vs config.example.yaml） |
| 🆕 `logging.enhance` | | 请求 trace correlation（X-Trace-Id） |
| 🆕 `token_budget` | | Per-run token 限制（warn + hard_stop 阈值） |
| 🆕 `max_recursion_limit` | | 客户端 recursion_limit 上限（默认 1000） |
| 🆕 `tool_output` | | 超大 tool 结果磁盘持久化 + 截断 |
| 🆕 `tool_progress` | | Tool 停滞检测状态机 |
| 🆕 `read_before_write` | | 写文件前必须 read_file（默认 on） |
| 🆕 `scheduler` | | 后台 cron + 一次性任务调度 |
| 🆕 `channel_connections` | | 用户拥有的 IM 频道绑定 |
| 🆕 `auth.oidc` | | OIDC SSO（Keycloak/Google/Azure/Okta） |
| 🆕 `suggestions` | | 自动生成跟进问题建议 |

注：config version 10→19，`checkpointer` 已废弃但后向兼容。

