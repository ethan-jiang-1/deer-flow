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
3. 自动搜索：  项目根目录（existing_project_file(("config.yaml",))）→ 遗留的 backend/ 与 repo root 候选
```

源码位置：`backend/packages/harness/deerflow/config/app_config.py` L447-476 `resolve_config_path()`（classmethod）。

**前两级是 fail-loud 的**：传了 `config_path` 但文件不存在 → `FileNotFoundError`；设了 `DEER_FLOW_CONFIG_PATH` 但文件不存在 → 同样 `FileNotFoundError`（两条报错文案不同，注意区分是哪个来源出的错）。第三级找不到才抛「not found in the project root or legacy backend/repository root locations」。

> 🔄 同步 #8（v2.2.0）：行号 `384-411` 已漂移到 **L447-476**（`app_config.py` 现在 958 行）。语义未变。

**实际用法：**

```bash
# 方式 A：环境变量——最常用
DEER_FLOW_CONFIG_PATH=/etc/deerflow/production.yaml make dev

# 方式 B：Docker Compose 里指定
environment:
  - DEER_FLOW_CONFIG_PATH=/app/project/config-production.yaml

# 方式 C：代码里显式传参
from deerflow.config.app_config import AppConfig   # 注意：deerflow.config 的 __init__ 不导出 AppConfig
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

源码位置：`app_config.py` L643-667 `resolve_env_variables()`。

**这是递归的**——字典的每一层、列表的每个元素都会被扫描。找到 `$` 前缀的字符串就替换。找不到对应的环境变量 → 直接报错 `ValueError`。

**三个容易踩空的细节**（读源码才知道）：

1. **只匹配「整串以 `$` 开头」**，不是任意位置替换——`sk-$SUFFIX` 不会被替换，`$PREFIX-sk` 会。
2. **判空用的是 `is None`**，所以 `os.environ["FOO"] = ""` 是**合法值**，会注入空字符串而不是报错。想让某个必填项确实缺失，得 unset 而不是设空。
3. **它在 `_from_yaml_text()` 里、在建模型之前执行**（L505 `_check_config_version` → L507 `resolve_env_variables`），所以版本检查看到的是**未替换**的原始文本，而 Pydantic 校验看到的是替换后的值。

> 🔄 同步 #8（v2.2.0）：行号 `565-587` → **L643-667**。

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

源码位置：`app_config.py` L943-948（`push_current_app_config`）/ L950-958（`pop_current_app_config`）；另有 `peek_current_app_config` L921-923、`peek_loaded_app_config` L926-941。

**语义细节（2.2.0 核对）**：它内部是**两个** ContextVar——`_current_app_config`（当前值）与 `_current_app_config_stack`（保存被压住的前值元组）。所以 `pop` 不是简单清空，而是恢复上一个；栈空时 `pop` 把当前值设成 `None`（不报错）。`get_app_config()` 的第一行就是 `runtime_override = _current_app_config.get(); if runtime_override is not None: return runtime_override`（L812-814）——**覆盖值绕过一切缓存与热加载检测**。这意味着：在 push 的 scope 内，你改磁盘上的 yaml 也不会被看到。

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

源码位置：`app_config.py` L798-843 `get_app_config()`（签名检测 `_get_config_mtime` / `_get_config_signature`）。

> 🔄 同步 #8（v2.2.0）：行号 `681-713` → **L798-843**。判定条件实际是四个「或」：首次加载 / **路径变了** / **内容签名变了** / **extensions_config 对象换了**（后两个各自打不同日志）。另外 `_app_config_is_custom` 为真时直接返回缓存**不做任何检测**（L817-818）。

**注意**：只有 `STARTUP_ONLY_FIELDS` 里的字段（database、checkpointer、sandbox、channels 等基础设施）改后需要重启。其他字段（models、tools、summarization、memory、guardrails 等）改了就生效。

> 🔄 同步 #8（v2.2.0）：`config_version` **45 → 63**；`config.example.yaml` 顶层 section **38 → 43**。v2.1.0 → v2.2.0 新增 5 个顶层键：**`blob_storage`**（对象存储后端，大工件不进 state/DB）、**`knowledge_base`**（知识库检索）、**`pii_redaction`**（PII 脱敏）、**`tool_artifacts`**（工具工件清单/消费账本）、**`deployment`**（`multi_instance` 拓扑声明——这一节改了**必须重启所有实例**，见下表）。**没有删除任何 section**。
>
> 同一时期还有一批字段级变化（`typesafe` 相关的 `RELOAD` 语义、`scheduler.tool_enabled`、`tenant`/`authorization` 段等），字段级清单以 [_digested/internals/configuration/01-config-yaml.md](../../_digested/internals/configuration/01-config-yaml.md)（config_version 63 / example 43 键 / 新增 section 速查）与 [04-config-reference.md](../../_digested/internals/configuration/04-config-reference.md) 为准，本篇只讲**灵活性的机制**，不重复字段手册。

---

## 重启边界的第四层：`reload_boundary.py`（2.2.0 值得单独看）

热加载不是「非 STARTUP_ONLY 就一定生效」这么简单。`config/reload_boundary.py` L45-125 的 `STARTUP_ONLY_FIELDS` 是一张 **27 条**的 dict，每条都带一段「为什么必须重启」的理由，而且**支持点号路径**（`skills.container_path`、`auth.local.throttle_storage`、`projects.summary_model_name`、`channels.leader_lease`）——同一节里可以有不同边界。

v2.2.0 里以下几个值得记住：

| 字段 | 为什么必须重启（原文要点） |
|---|---|
| `deployment` | 多实例启动门 `_enforce_postgres_for_multi_worker` 只在启动时评估一次；声明或撤回多实例拓扑要**重启每个实例** |
| `scheduler` | `ScheduledTaskService` 构造一次；但**例外**——`scheduler.recursion_limit` 不在此列，每次 dispatch 现读 |
| `run_ownership` | `RunManager` 启动时捕获；租约心跳任务也在那时创建 |
| `auth.local.throttle_storage` | 登录限流存储选的是进程内计数还是共享 `login_throttle` 表——启动时解析一次；但 `max_login_attempts` / `lockout_seconds` 仍是 live-read |
| `projects.summary_*`（6 条） | `SummaryGenerator` 的线程池启动时构造 |

**判读**：`is_startup_only_field(field_path)`（L133-140）是**精确匹配**，不做前缀推断。所以「`sandbox` 要重启」并不能推出「`sandbox` 下的每个键都要重启」——`sandbox.network` 就不在表里。想知道某个具体的键要不要重启，查表，别猜。

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
| **按请求选不同 config 文件** | ⚠️ 半支持：ContextVar 栈是**执行上下文作用域**的，理论上可以在请求入口 push 一份别的 `AppConfig`；但 Gateway 已有自己的 config 快照纪律，别绕过它 |
| **跨进程一致的多实例配置** | ⚠️ v2.2.0 才有一等支持：`deployment.multi_instance` 声明 + 启动门会拒绝 8 类不安全组合。**这是配置项，不是灵活性机制**——它把「所有实例必须同一份配置」从口头约定变成了启动期硬约束 |

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

## 你可能不知道的额外机制

### `.env` 文件支持

**先说 2.2.0 的变化：`serve.sh` 不再 `source` `.env`。** 理由写在脚本注释里——source 会把 `$$` 变成 shell PID、会执行反引号和 `$()`、还会把带空格的值第二个词当命令执行。现在改由 `scripts/dotenv_exports.py` 用「像 python-dotenv 那样」的解析器读文件、打印 shell-quoted 的 exports 再 `eval`（`scripts/serve.sh` L53-68）。

前端进程里则由 `app_config.py` L67-71 处理：

```python
from deerflow.env import load_selected_env_file
...
if not load_selected_env_file():
    load_dotenv()
```

即：**选了 `DEER_FLOW_ENV_FILE` 就只读那一个文件**，没选才回落到 python-dotenv 的自动发现。还有两条约束：

- `DEER_FLOW_ENV_FILE` 与 python-dotenv 自带的 `PYTHON_DOTENV_DISABLED` **同时**设置会直接 `ValueError`（显式选择不能静默失效，`deerflow/env.py` L21-22）；
- 用 `utf-8-sig` 读，吞掉 BOM；`load_dotenv(..., override=False)` 语义——**进程里已存在的变量（包括空值）永远赢**。

所以你可以在项目根目录放一个 `.env`：

```bash
# .env
OPENAI_API_KEY=sk-xxx
DEER_FLOW_CONFIG_PATH=prod.yaml
```

**不需要手动 `export`**——DeerFlow 启动时自动加载。

### 专用环境变量（不看 YAML 就能覆盖）

除了 `$VAR` 通用注入，DeerFlow 还有一批**直接读 `os.environ` 的固定 env var**，不经过 YAML：

| Env Var | 覆盖什么 |
|---------|---------|
| `DEER_FLOW_HOME` | 运行时数据目录（默认 `.deer-flow`） |
| `DEER_FLOW_PROJECT_ROOT` | 项目根目录（影响所有相对路径搜索） |
| `DEER_FLOW_SKILLS_PATH` | Skills 目录 |
| `DEER_FLOW_CHANNELS_LANGGRAPH_URL` | IM 通道的 LangGraph API URL |
| `DEER_FLOW_CHANNELS_GATEWAY_URL` | IM 通道的 Gateway URL |
| `DEER_FLOW_STREAM_BRIDGE_REDIS_URL` | Redis Stream Bridge 地址 |
| `DEER_FLOW_SANDBOX_HOST` | AIO Sandbox host |
| `DEER_FLOW_HOST_BASE_DIR` | Docker 卷挂载时 host 侧等价路径 |
| `GATEWAY_HOST` / `GATEWAY_PORT` | Gateway 监听地址 |
| `GATEWAY_ENABLE_DOCS` | 是否启用 `/docs`（生产关闭） |
| `DEER_FLOW_FILE_IO_WORKERS` | 文件 I/O 线程池大小 |
| `DEER_FLOW_ENV_FILE` | 🆕 2.2.0：显式指定后端进程读哪个 dotenv 文件（不设才自动发现） |
| `PYTHON_DOTENV_DISABLED` | 🆕 与上者互斥；同时设 → `ValueError` |

**这些绕过了 YAML**，即使 `config.yaml` 里写了对应值，env var 在代码层直接读取（通过 `os.getenv()`）。

### `ConfigDict(extra="allow")`——未知 key 静默接受

`AppConfig` 用的是 `extra="allow"`（`app_config.py` L327；class 定义在 L224）。这意味着你在 `config.yaml` 里写**不在 schema 里的自定义 key** 不会报错：

```yaml
# 这些 DeerFlow 不认识，但不会报错
my_custom_tool:
  enabled: true
  endpoint: https://...
```

这对第三方扩展很友好——你可以在 config 里塞自己的配置，通过 `AppConfig.model_dump()` 读取。

### Extensions JSON 的 `$VAR` 解析是 fail-soft

`config.yaml` 里 `$MISSING_VAR` → 直接报错 `ValueError`。但 `extensions_config.json` 里同样的写法 **静默退化为空字符串 `""`**——不会让 startup 崩溃。这属于故意的不对称设计：主配置 fail-loud，扩展配置 fail-soft。

### Uvicorn `--reload` 监听 `.yaml` 变动

Dev 模式下，`serve.sh` 启动 uvicorn 时带了 `--reload-include='*.yaml'` 与 `--reload-include='.env'`。所以改 `config.yaml` 不仅触发**应用层**热加载——`uvicorn` 自己的 reloader 还会把 worker 整个重启（进程级）。两层叠加的结果是：dev 下你根本观察不到「哪些字段需要重启」这件事，因为每个文件改动都重启了。**要验证热加载边界，必须在非 `--reload` 模式下测。**

> 🔄 同步 #8（v2.2.0）：具体行号 `serve.sh:364` 已不适用（脚本重排过），请按 `--reload-include` 关键字定位。

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
| 配置文件路径解析（3 优先级） | `app_config.py` L447-476 `resolve_config_path()` |
| `$ENV_VAR` 递归替换 | `app_config.py` L643-667 `resolve_env_variables()` |
| 启动时加载 + 传播到子系统 singleton | `app_config.py` L478-502 `from_file()` → L484-496 `_from_yaml_text()`（`_check_config_version` 在 L599） |
| 热加载检测（content signature） | `app_config.py` L798-843 `get_app_config()`；强制重载 `reload_app_config()` L846-880 |
| ContextVar 运行时覆盖 | `app_config.py` L921-923 `peek_current_app_config()`、L926-941 `peek_loaded_app_config()`、L943-948 `push`、L950-958 `pop` |
| 哪些字段改后需要重启 | `config/reload_boundary.py` L45-125 `STARTUP_ONLY_FIELDS`（27 条，支持点号路径）；判定入口 L133-140 `is_startup_only_field()` |
| `.env` 选择器（2.2.0 新增） | `deerflow/env.py` L10-40 `load_selected_env_file()`；调用点 `app_config.py` L67-71 |
| `serve.sh` 的 `.env` 解析（不再 source） | `scripts/serve.sh` L53-68；解析器 `scripts/dotenv_exports.py` |
| Extensions JSON 热加载 | `config/extensions_config.py` |
| Gateway 启动时 config 装载 | `app/gateway/app.py` `lifespan()` |
| `make config-upgrade`（版本迁移） | `scripts/config-upgrade.sh`、`Check config version` `scripts/check_config_version.sh` |

> 🔄 同步 #8（v2.2.0）：整表行号按 v2.2.0 源码重扫；旧表里的 `app_config.py:414-459`、`:681-713`、`:768-783` 全部失效。

---

## 版本时间线：这些机制什么时候出现的？

通过 `git blame` 追溯每个关键函数的引入时间：

| 机制 | 引入时间 | 版本 | 引入者 |
|------|---------|------|--------|
| `DEER_FLOW_CONFIG_PATH` 环境变量 | 2026-01-14 | **2.0 初始** | Henry Li |
| `$ENV_VAR` YAML 内递归替换 | 2026-01-14 | **2.0 初始** | Henry Li |
| `load_dotenv()` 自动加载 `.env` | 2026-01-14 | **2.0 初始** | DanielWalnut |
| `resolve_config_path()` 三优先级 | 2026-01-14 | **2.0 初始** | Henry Li |
| `$VAR` missing → `ValueError`（fail-loud） | 2026-02-25 | 2.0.x | JeffJiang |
| `config_version` 版本检测 + 升级 warning | 2026-03-14 | 2.0.x | DanielWalnut |
| `get_app_config()` mtime 热加载 | 2026-03-22 | 2.0.x | Gao Mingfei |
| `push/pop_current_app_config()` ContextVar 栈 | 2026-04-04 | 2.0.x | DanielWalnut |
| `existing_project_file()` 项目根搜索 | 2026-05-01 | 2.0.x | Nan Gao |
| **Content-signature 热加载（sha256 替代纯 mtime）** | **2026-06-17** | **🆕 2.1** | Huixin615 |

**结论：绝大多数灵活性机制是 2.0 就有的，不是 2.1 的新东西。** 2.1 只做了一件事——把热加载检测从纯 mtime 升级为 `(mtime, size, sha256)` content signature，解决了 `git checkout`、`cp -p`、网络挂载等场景下 mtime 不可靠的问题。

**2.2.0 加了什么（就灵活性而言，只有两件）**：

| 变化 | 影响 |
|---|---|
| `DEER_FLOW_ENV_FILE` + `PYTHON_DOTENV_DISABLED` 互斥校验 | 从「自动发现 `.env`」升级为「**可以显式选，且选错了会炸**」。这是 fail-loud 方向的改进，和 `$VAR` missing 报错同源 |
| `serve.sh` 不再 `source` `.env`，改用 `dotenv_exports.py` 解析 | 修的是一个真实的安全面（命令注入 / `$$` 污染），不是新能力 |

**没有加的**：多文件 merge、`!include`、`--config` 命令行开关、`config.d/*.yaml`、配置 diff/patch 语言、版本回滚。三层机制（路径切换 / `$VAR` 注入 / ContextVar 覆盖）从 2.0 到 2.2 一个都没多——**DeerFlow 在配置灵活性上的答案始终是「换文件 + 换环境变量 + 换进程内对象」，而不是「拼装多个文件」**，这是设计选择，不是欠账。

换句话说：**DeerFlow 从一开始就考虑了配置路径切换和环境变量注入**，灵活性设计是 2.0 的架构决策，不是后来打的补丁。这跟你印象中"死在一个文件上"的感觉不一样——可能是因为文档没把这些机制讲清楚。实际上 `DEER_FLOW_CONFIG_PATH` 从第一天就在代码里。
