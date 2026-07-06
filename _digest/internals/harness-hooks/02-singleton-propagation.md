---
title: "单例传播：AppConfig → 12 个子配置的推送链"
description: "**核心文件：** `deerflow/config/app_config.py:188-211`"
topics: [hooks, extension, plugin-system]
---

# 单例传播：AppConfig → 12 个子配置的推送链

**核心文件：** `deerflow/config/app_config.py:188-211`

`get_app_config()` 返回的是 `AppConfig` 这个 Pydantic model。但 DeerFlow 的各个子系统不直接持有 `AppConfig` 引用——每个子系统有自己的**模块级单例**。当 `AppConfig` 被重载时，它负责把新值推送到所有子配置单例。

## 推送链

`AppConfig._apply_singleton_configs()` 把同一个 `AppConfig` 字段分发到 10 个子配置单例：

```python
@classmethod
def _apply_singleton_configs(cls, config, acp_agents):
    load_title_config_from_dict(config.title.model_dump())
    load_summarization_config_from_dict(config.summarization.model_dump())
    load_memory_config_from_dict(config.memory.model_dump())
    load_agents_api_config_from_dict(config.agents_api.model_dump())
    load_subagents_config_from_dict(config.subagents.model_dump())
    load_tool_search_config_from_dict(config.tool_search.model_dump())
    load_guardrails_config_from_dict(config.guardrails.model_dump())
    load_checkpointer_config_from_dict(config.checkpointer.model_dump() if ...)
    load_stream_bridge_config_from_dict(config.stream_bridge.model_dump() if ...)
    load_acp_config_from_dict({name: agent.model_dump() for ...})

    # 特殊：checkpointer 变了 → 连带 reset store
    if previous_checkpointer_config != config.checkpointer:
        reset_checkpointer()
        reset_store()
```

## 每个子配置的三函数模式

以 `guardrails_config.py` 为例：

```python
_guardrails_config: GuardrailsConfig | None = None  # 模块级单例

def load_guardrails_config_from_dict(data: dict) -> GuardrailsConfig:
    """由 AppConfig._apply_singleton_configs() 调用"""
    global _guardrails_config
    _guardrails_config = GuardrailsConfig.model_validate(data)
    return _guardrails_config

def get_guardrails_config() -> GuardrailsConfig:
    """各子系统读取"""
    global _guardrails_config
    if _guardrails_config is None:
        _guardrails_config = GuardrailsConfig()  # 默认值
    return _guardrails_config

def reset_guardrails_config() -> None:
    """测试清理"""
    global _guardrails_config
    _guardrails_config = None
```

这 10 个子配置单例分布在：
- `deerflow/config/guardrails_config.py`
- `deerflow/config/memory_config.py`
- `deerflow/config/title_config.py`
- `deerflow/config/summarization_config.py`
- `deerflow/config/agents_api_config.py`
- `deerflow/config/subagents_config.py`
- `deerflow/config/tool_search_config.py`
- `deerflow/config/checkpointer_config.py`
- `deerflow/config/stream_bridge_config.py`
- `deerflow/config/acp_config.py`

## Checkpointer/Store 的级联重置

checkpointer 和 store 是两个**runtime 单例**（不是配置单例）。它们从 checkpointer config 派生：

```python
if previous_checkpointer_config != config.checkpointer:
    reset_checkpointer()   # → 下次 get_checkpointer() 重新创建
    reset_store()          # → 下次 get_store() 重新创建
```

比较用的是 `__eq__`（Pydantic model 的字段级相等），而不是 `is`（对象标识）。所以如果 checkpointer config 内容没变（比如只改了 `title.enabled`），checkpointer 和 store 不会被重置。

测试 `test_get_app_config_keeps_persistence_runtime_singletons_when_checkpointer_unchanged` 验证了这一点：改 `title.enabled` 不会重置 checkpointer；删除 checkpointer section 会。

## 热生效 vs 重启生效

### 热生效（下一条消息生效）

这些字段通过 `get_app_config()` → 子配置单例 → 在每轮 agent step 中读取：

| 字段 | 生效路径 |
|------|----------|
| `models[*].max_tokens` | `factory.py` `create_chat_model()` 读取 |
| `summarization.*` | `SummarizationMiddleware` 每轮检查 |
| `title.*` | `TitleMiddleware` 在首次交换后触发 |
| `memory.*` | `MemoryMiddleware` 检查 `get_memory_config().enabled` |
| `subagents.*` | `SubagentLimitMiddleware` 检查 `max_concurrent_subagents` |
| `tools[*]` | `get_available_tools()` 从 `AppConfig.tools` 读取 |
| `guardrails.*` | `GuardrailMiddleware` 检查 `get_guardrails_config().enabled` |
| `token_usage.*` | `TokenUsageMiddleware` 条件加入链 |
| `loop_detection.*` | `LoopDetectionMiddleware` 条件加入链 |
| system prompt | 每次构建 agent 时重新生成 |

### 必须重启

| 字段 | 为什么必须重启 |
|------|----------------|
| `database.*` | `init_engine_from_config()` 在 `langgraph_runtime()` 启动时执行一次；SQLAlchemy engine 持有连接池 |
| `checkpointer.*` | `make_checkpointer()` 在启动时绑定一次；但 config 热重载时如果 checkpointer 变化会 reset |
| `run_events.*` | `make_run_event_store()` 在启动时选择 memory vs SQL 实现 |
| `stream_bridge.*` | `make_stream_bridge()` 在启动时构造 bridge 对象一次 |
| `sandbox.use` | `get_sandbox_provider()` 缓存 provider 单例；新类路径只在进程重启时生效 |
| `log_level` | `apply_logging_level()` 仅在 `app.py` startup 调用一次；`get_app_config()` 返回新的 `AppConfig` 不会重新触发 |
| `channels.*` | `start_channel_service()` 在启动时调用一次；运行中的 IM 通道不会因为 config 变化而重建 |

### 例外：checkpointer 热重载的边界

checkpointer 在 `_apply_singleton_configs()` 中有特殊处理——如果 checkpointer config 变化，会 `reset_checkpointer()` + `reset_store()`。但这**不是真正完整的热重载**：对于那些已经打开、正在运行的 agent run，它们的 checkpointer 和 store 是在 run 开始时获取的，不会感知到中途的 reset。只有新的 run 会使用新的 checkpointer/store。

## 验证失败不污染

最重要的安全保障：`_apply_singleton_configs()` 在 `AppConfig.from_file()` 中被调用，而 `from_file()` 先构造完整的 Pydantic model 再做传播。如果 Pydantic 验证失败（比如 `title.enabled` 类型不对），`from_file()` 本身就会抛异常——`_apply_singleton_configs()` 根本不会被调用，所有子配置单例保持旧值不变。

```python
@classmethod
def from_file(cls, config_path=None):
    ...
    result = cls.model_validate(config_data)       # ← Pydantic 验证在这里
    acp_agents = cls._validate_acp_agents(...)
    cls._apply_singleton_configs(result, acp_agents)  # ← 传播在这里
    return result
```

测试 `test_get_app_config_does_not_mutate_singletons_when_reload_validation_fails` 直接验证了这一点：写入非法 YAML → `get_app_config()` 抛异常 → 所有子配置单例、checkpointer、store 全部不变。
