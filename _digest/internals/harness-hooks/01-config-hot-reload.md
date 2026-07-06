---
title: "配置热重载：mtime 侦测 + 路径感知 + 原子替换"
description: "**核心文件：** `deerflow/config/app_config.py:360-389`"
topics: [hooks, extension, plugin-system]
---

# 配置热重载：mtime 侦测 + 路径感知 + 原子替换

**核心文件：** `deerflow/config/app_config.py:360-389`

DeerFlow 的配置热重载是**拉模式**——没有文件系统 watcher，没有 inotify。每次调用 `get_app_config()` 时，它主动对比文件 mtime 和路径，发现变化就重载。

## 三步检测

```python
def get_app_config() -> AppConfig:
    # 第 1 步：ContextVar 运行时覆盖？
    runtime_override = _current_app_config.get()
    if runtime_override is not None:
        return runtime_override   # ← 直接返回，不读文件

    # 第 2 步：测试/special case 注入的自定义 config？
    if _app_config is not None and _app_config_is_custom:
        return _app_config         # ← 不检测 mtime

    # 第 3 步：mtime 或路径变了？
    resolved_path = AppConfig.resolve_config_path()
    current_mtime = _get_config_mtime(resolved_path)
    should_reload = (
        _app_config is None
        or _app_config_path != resolved_path
        or _app_config_mtime != current_mtime
    )
    if should_reload:
        _load_and_cache_app_config(str(resolved_path))
    return _app_config
```

优先级：**ContextVar > custom override > mtime/路径变化检测**

### mtime 变化日志

当文件被修改时（且路径没变），DeerFlow 会打一条 INFO 日志：

```
Config file has been modified (mtime: 1717012345.67 -> 1717012400.12), reloading AppConfig
```

## 路径解析链

`AppConfig.resolve_config_path()` (`app_config.py:113-141`) 按 4 级优先级：

1. **显式传参** — `get_app_config(config_path="/path/to/config.yaml")`
2. **环境变量** — `DEER_FLOW_CONFIG_PATH`
3. **项目搜索** — `existing_project_file(("config.yaml",))` 从调用方目录向上搜索
4. **legacy 兼容** — `backend/config.yaml` 或 repo root `config.yaml`

路径变化触发重载——如果你通过环境变量把 `DEER_FLOW_CONFIG_PATH` 从 config-a.yaml 改成 config-b.yaml，下次调用时整个 config 会被替换。

## config_version: 版本升级检测

`_check_config_version()` (`app_config.py:225-268`):

1. 读用户的 `config.yaml` 中的 `config_version` 字段（缺失 = 版本 0）
2. 读同目录（或上级）的 `config.example.yaml` 中的 `config_version`
3. 用户版本 < 示例版本 → WARNING 日志

```python
if user_version < example_version:
    logger.warning(
        "Your config.yaml (version %d) is outdated — the latest version is %d. "
        "Run `make config-upgrade` to merge new fields into your config.",
        user_version, example_version,
    )
```

这个检查在**每次 `from_file()` 时**都执行，所以 reload 也会触发。

## 验证失败回退：不污染旧配置

`_load_and_cache_app_config()` (`app_config.py:348-357`) 是**先加载后缓存**的。如果 `AppConfig.from_file()` 抛出异常（比如 Pydantic ValidationError），函数**还没执行到赋值那一步**，`_app_config` 保持旧值不变。

测试 `test_get_app_config_does_not_mutate_singletons_when_reload_validation_fails` 验证了这一点：写一个 malformed config（`"title": False` 但应该是 dict），`get_app_config()` 抛 ValidationError，但 `_app_config`、子配置单例、checkpointer/store 全部保持不变。

```python
def _load_and_cache_app_config(config_path=None):
    resolved_path = AppConfig.resolve_config_path(config_path)
    _app_config = AppConfig.from_file(str(resolved_path))  # ← 如果这里抛异常
    _app_config_path = resolved_path                        #    下面这几行不执行
    _app_config_mtime = _get_config_mtime(resolved_path)    #    _app_config 不变
    _app_config_is_custom = False
    return _app_config
```

## 环境变量解析

`resolve_env_variables()` (`app_config.py:270-293`) 递归遍历整个 config dict，把 `$OPENAI_API_KEY` 这样的值替换为 `os.getenv("OPENAI_API_KEY")`。

- YAML 层：`app_config.py:162` — `config_data = cls.resolve_env_variables(config_data)`
- Extensions JSON 层：`extensions_config.py:144` — 同样的递归替换
- 差异：YAML 中找不到 env var → 抛异常；JSON 中找不到 → 返回空字符串（避免 MCP server 收到字面量 `$VAR`）

## 测试覆盖的关键场景

| 测试 | 场景 |
|------|------|
| `test_get_app_config_reloads_when_file_changes` | 修改同一个文件 → mtime 变化 → 自动重载 |
| `test_get_app_config_reloads_when_config_path_changes` | 切换 env var 指向不同文件 → 路径变化 → 替换 |
| `test_get_app_config_does_not_mutate_singletons_when_reload_validation_fails` | 写入非法 config → ValidationError → 旧配置不变 |
| `test_get_app_config_resets_singleton_configs_when_sections_removed` | 删除 config section → 子配置单例回退到 default |

## 为什么是拉模式而不是推模式

DeerFlow 选择拉模式有几个原因：

1. **Gateway 天然 request-time** — Gateway 的依赖注入在每个请求上调用 `get_app_config()`，天然形成"下一个请求看到新配置"的语义
2. **LangGraph 进程独立** — MCP tools / LangGraph runtime 是独立进程，文件是它们之间的通信媒介
3. **避免复杂性** — 不需要引入 `watchdog` 依赖，不需要管理 watcher 生命周期，不需要处理跨平台文件系统事件差异
4. **确定性** — 拉模式意味着 config 在单个请求内保持一致。推模式可能导致请求进行到一半时 config 被替换
