---
title: "DeerFlow 配置灵活性全景"
description: "三层机制：文件路径切换、YAML 内 $ENV_VAR 注入、运行时 ContextVar 覆盖。也讲清楚它做不到什么。"
---

# DeerFlow 配置灵活性全景

## 你能做的三件事

### 机制一：切换配置文件路径

**这是最直接的灵活性。** 你可以用任意路径的 `.yaml` 文件启动 DeerFlow，不限于 `config.yaml`。

三个优先级（从高到低）：

```
1. 代码传参：  AppConfig.from_file(config_path="/home/me/prod-config.yaml")
2. 环境变量：  DEER_FLOW_CONFIG_PATH=/home/me/prod-config.yaml
3. 自动搜索：  项目根目录 → backend/ → repo root 的 config.yaml
```

源码位置：`app_config.py:268-295` `resolve_config_path()`

**实际用法：**

```bash
# 方式 A：环境变量——最常用
DEER_FLOW_CONFIG_PATH=/etc/deerflow/production.yaml make dev

# 方式 B：Docker Compose 里指定
environment:
  - DEER_FLOW_CONFIG_PATH=/app/project/config-production.yaml

# 方式 C：代码里显式传参
from deerflow.config import AppConfig
cfg = AppConfig.from_file(config_path="./my-custom-config.yaml")
```

`extensions_config.json` 同理，有 `DEER_FLOW_EXTENSIONS_CONFIG_PATH`。

> **关键约束**：无论路径在哪里，文件名不强制叫 `config.yaml`——`.yaml` 后缀即可。你可以维护 `dev.yaml`、`staging.yaml`、`prod.yaml` 三套配置，通过环境变量切换。

---

### 机制二：YAML 内 `$ENV_VAR` 注入

配置值以 `$` 开头时，DeerFlow 会用 `os.getenv()` 替换：

```yaml
# config.yaml
models:
  - name: gpt-4o
    provider: openai
    api_key: $OPENAI_API_KEY        # ← 从环境变量读取
    base_url: $CUSTOM_OPENAI_BASE   # ← 也可以
```

源码位置：`app_config.py:431-453` `resolve_env_variables()`

**这是递归的**——字典的每一层、列表的每个元素都会被扫描。找到 `$` 前缀的字符串就替换。找不到对应的环境变量 → 直接报错 `ValueError`。

**这个机制覆盖了"不同的环境用不同的 key/endpoint/secret"的需求**，不需要为每个环境维护一套完整的 YAML。

结合机制一，你可以：
- `dev.yaml` + 开发环境的 env vars → `DEER_FLOW_CONFIG_PATH=dev.yaml`
- `prod.yaml` + 生产环境的 env vars → `DEER_FLOW_CONFIG_PATH=prod.yaml`

---

### 机制三：运行时编程式覆盖（ContextVar）

这是最底层也最强大的机制。DeerFlow 有一个进程级 ContextVar 可以**在运行时替换整个 AppConfig 对象**：

```python
from deerflow.config.app_config import (
    push_current_app_config,
    pop_current_app_config,
    AppConfig,
)

# 构建一个定制的 config
custom_cfg = AppConfig.from_file("base.yaml")
# 甚至可以编程式修改字段
custom_cfg.models[0].max_tokens = 8000

# 压栈——当前 ContextVar 范围内的所有 get_app_config() 调用都返回它
push_current_app_config(custom_cfg)

# ... 在这个 scope 内运行 agent ...

# 弹栈——恢复原来的 config
pop_current_app_config()
```

源码位置：`app_config.py:634-648`

**这就是你能"动态改配置"的入口**。不需要重启 Gateway，不需要改 YAML 文件——在代码里构建一个新的 `AppConfig`，push 到 ContextVar 栈上，之后所有的 middleware、tools、agent 调用都会看到这个新配置。

Gateway 启动时就是利用这个机制来隔离不同请求间的 config 快照。

---

## 自动热加载（你不需要手动管的）

`get_app_config()` 返回缓存的单例，但会在底层自动检测变化：

| 检测条件 | 触发 |
|---------|------|
| 配置**文件路径**变了（`DEER_FLOW_CONFIG_PATH` 切换了） | ✅ 自动重载 |
| 文件**内容签名**变了（sha256 + mtime + size） | ✅ 自动重载 |
| 仅 mtime 变了 | ✅ 自动重载（兼容） |

源码位置：`app_config.py:547-578`

**注意**：只有 `STARTUP_ONLY_FIELDS` 里的字段（database、checkpointer、sandbox、channels 等基础设施）改后需要重启。其他字段（models、tools、summarization、memory、guardrails 等）改了就生效。

---

## 做不到的事情（诚实地说）

| 你想要的 | 现状 |
|---------|------|
| **多文件 merge**（如 `config.d/*.yaml` 全部加载） | ❌ 不支持。只有一个文件 + 一个 extensions JSON |
| **YAML `!include` 指令**（把配置拆成多个文件互相引用） | ❌ 不支持。YAML 是单文件加载 |
| **命令行 `--config` 开关** | ❌ CLI 没有。只能靠环境变量或代码传参 |
| **Per-model 独立配置文件** | ❌ 所有 model 配置都在 `config.yaml` 的 `models:` 列表里 |
| **Per-agent 独立配置文件** | ⚠️ Custom agent 的 `config.yaml` 放在 agent 目录下，但它的 schema 是 `SubagentConfig` 子集，不是完整 `AppConfig` |
| **运行时通过 API 改 `config.yaml`** | ⚠️ 只有 `extensions_config.json` 有 `PUT /api/mcp/config` 和 `PUT /api/skills/{name}` 运行时 API。主 `config.yaml` 没有 REST 接口 |
| **配置版本回滚** | ❌ 没有。`config_version` 只做升级检测（warning），不做回滚 |

---

## 实践的灵活性上限

把三层机制组合起来，你可以做到：

```
┌─────────────────────────────────────────────┐
│  DEER_FLOW_CONFIG_PATH=scenarios/prod.yaml   │  ← 切换整个配置文件
│                                             │
│  prod.yaml 里：                              │
│    api_key: $PROD_OPENAI_KEY                │  ← 敏感值走 env var
│    database:                                 │
│      backend: postgres                       │
│      url: $PROD_DB_URL                      │
│                                             │
│  代码层：                                    │
│    push_current_app_config(tuned_config)     │  ← 临时覆盖（per-request）│
└─────────────────────────────────────────────┘
```

**所以你完全可以维护多套配置**（`dev.yaml`、`staging.yaml`、`prod.yaml`、`test.yaml`），通过 `DEER_FLOW_CONFIG_PATH` 切换。只是每个文件都是**完整的独立配置**，不能像 Docker Compose 那样用 `extends` 或 `include` 来继承共享部分。

---

## 如果你想要"配置文件 + override patch"模式

目前没有一个内建的机制让你写：

```yaml
# base.yaml — 共享配置
models: [...]
sandbox: {...}

# prod.yaml — 只写差异
extends: base.yaml
database:
  backend: postgres
```

但你可以用 ContextVar 机制**自己实现**：

```python
base = AppConfig.from_file("base.yaml")
override = AppConfig.from_file("prod-override.yaml")

# 合并（用 override 的字段覆盖 base）
merged_dict = deep_merge(base.model_dump(), override.model_dump())
merged = AppConfig.model_validate(merged_dict)

push_current_app_config(merged)
```

这不是内建功能，但 AppConfig 的 `model_dump()` + `model_validate()` 往返提供了足够的可编程性。

---

## 关键源码索引

| 想看什么 | 去这里 |
|---------|--------|
| 配置文件路径解析（3 优先级） | `app_config.py:268-295` `resolve_config_path()` |
| `$ENV_VAR` 递归替换 | `app_config.py:431-453` `resolve_env_variables()` |
| 启动时加载 + 传播到子系统 singleton | `app_config.py:298-335` `from_file()` |
| 热加载检测（content signature） | `app_config.py:547-578` `get_app_config()` |
| ContextVar 运行时覆盖 | `app_config.py:634-648` `push/pop_current_app_config()` |
| 哪些字段改后需要重启 | `reload_boundary.py` `STARTUP_ONLY_FIELDS` |
| Extensions JSON 热加载 | `extensions_config.py:152-200` `resolve_config_path()` |
| Gateway 启动时 config 装载 | `gateway/app.py` `lifespan()` |
| `make config-upgrade`（版本迁移） | `Makefile` `config-upgrade` target |
