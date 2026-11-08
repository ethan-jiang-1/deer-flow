---
title: "沙箱命令审计"
description: "SandboxAuditMiddleware 的三级分类（block/warn/pass）、正则与 shlex 的判定方式，以及「审计只写日志」这个关键边界——它记录到 gateway.log，不落库。"
topics: [governance, audit, sandbox]
---

# 沙箱命令审计

每一次 `bash` 工具调用都过一层审计：先分类，再记录。
分类会**阻断**，但记录只写**日志文件**——这个区别决定了它能支撑什么、不能支撑什么。

## 1. 两个动作，两种持久性

`packages/harness/deerflow/agents/middlewares/sandbox_audit_middleware.py:449-464`
的类 docstring 说明两层职责：

| 职责 | 实现 | 持久性 |
|---|---|---|
| **命令分类** | 正则 + `shlex` 分析（`:454`） | 不适用（实时判定） |
| **审计日志** | 结构化 JSON 经标准 logger 输出 | **只进 gateway.log**（`:456`） |

原文（`:455-457`）：

> **Audit log**: every bash call is recorded as a structured JSON entry
> via the standard logger (visible in gateway.log).

**这是本篇最重要的边界**：审计记录**不写入关系库**，
所以它不随 thread 删除而"保留"，也不受任何保留期策略管理——
它属于日志系统的生命周期，与数据治理章节里的 TTL 体系完全无关。

## 2. 三级分类

`_classify_single_command`（`sandbox_audit_middleware.py:383-384`）返回三种结论：

```python
"""Classify a single (non-compound) command. Return 'block', 'warn', or 'pass'."""
```

| 结论 | 动作 | 例子 |
|---|---|---|
| **block** | 处理器**不被调用**，返回错误 `ToolMessage` | `rm -rf /`、`curl url \| bash` |
| **warn** | 正常执行，在工具结果里追加警告 | `pip install`、`chmod 777` |
| **pass** | 正常执行 | 普通命令 |

### 2.1 block 的行为

`sandbox_audit_middleware.py:458-460`：

> High-risk commands (e.g. `rm -rf /`, `curl url | bash`) are blocked:
> the handler is **not called** and an error `ToolMessage` is returned so the
> agent loop can continue gracefully.

**两个设计意图**：命令不执行；但 agent 循环不崩——agent 会收到错误并有机会换方法。

### 2.2 warn 的行为

`:462-464`：

> Medium-risk commands (e.g. `pip install`, `chmod 777`) are executed
> normally; a warning is appended to the tool result so the LLM is aware.

**"so the LLM is aware"**——警告是给**模型**看的，不是给人看的。
模型可以不理会它继续。

## 3. 复合命令的短路规则

`_classify_command`（`sandbox_audit_middleware.py:414-440`）处理 `a && b; c | d` 这类复合命令：

```python
if verdict == "block":
    return "block"      # short-circuit: can't get worse
if verdict == "warn":
    worst = "warn"
```

| 规则 | 效果 |
|---|---|
| 任一子命令 block → 整体 block | **短路**（`:437-438`） |
| 任一子命令 warn → 整体至少 warn | 取最差（`:439-440`） |
| 全 pass → 整体 pass | — |

**"can't get worse"** 这个注释是判定逻辑的核心：block 是最高等级，无需继续分析。

## 4. 判定依赖的具体攻击模式

`sandbox_audit_middleware.py:27-60` 定义了若干正则族，它们是理解「能拦什么」的关键：

| 模式 | 目标 | 证据 |
|---|---|---|
| `_RISKY_SUBSTITUTION_EXECUTABLES` | `curl`/`wget`/`bash`/`sh`/`python`/`ruby`/`perl`/`base64` | `:27` |
| `_RISKY_SUBSTITUTION` | `$(cmd`、`<(cmd`、反引号三种写法统一处理 | `:33` |
| `_CODE_STRING_INTERPRETERS` | `sh` 族、`python`、`perl`、`ruby`、`node`、`php` | `:46` |
| `_LEADING_FLAGS` | `-c`/`-e`/`-p`/`-r` 这类"把代码当参数"的标志 | `:47` |
| `_COMMAND_POSITION_PREFIX` | `env`/`sudo`/`nohup` 等包装后仍是命令位 | `:60` |

### 4.1 一条注释揭示的设计取舍

`:33-36` 说明为什么三种替换写法共用同一个开头：

> Sharing one opener is what keeps ``eval `curl u` `` from slipping past a rule
> written only for ``eval $(curl u)``.

**这是「按语义归一而非按字形枚举」的做法**——同一种危险行为有多种语法，
规则写在它们共有的结构上。

### 4.2 明示的已知盲区

`:49-51` 承认一处局限：

> A flag taking its value as the next word (`-o pipefail`, `--rcfile f`) can hide
> either form; its value is indistinguishable from a script argument in this
> heuristic (**a documented gap**).

**这是正则式审计的固有边界**：不做真正的 shell 解析，就有歧义无法消除。
框架选择披露而不是假装覆盖。

## 5. 审计记录的结构

`_write_audit`（`sandbox_audit_middleware.py:485-496`）产生四个字段：

```python
record = {
    "timestamp": datetime.now(UTC).isoformat(),
    "thread_id": thread_id or "unknown",
    "command": audited_command,
    "verdict": verdict,
}
logger.info("[SandboxAudit] %s", json.dumps(record, ensure_ascii=False))
```

| 字段 | 说明 |
|---|---|
| `timestamp` | **UTC** ISO 格式 |
| `thread_id` | 缺失时记为 `"unknown"`（有回退，无边界条件） |
| `command` | 命令原文 |
| `verdict` | `block` / `warn` / `pass` |

### 5.1 命令会被截断

`_AUDIT_COMMAND_LIMIT = 200`（`sandbox_audit_middleware.py:483`）：
超过 200 字符的命令被截断，并附上原长度（`... (N chars)`）。

**含义**：长命令的审计记录**不包含完整内容**。要复现一次危险操作，
日志里的命令可能不够。

### 5.2 缺 `user_id`

记录里**没有用户字段**，只有 `thread_id`。要追到人，
需要再用 `thread_id` 反查 thread 归属。

## 6. 能支撑什么、不能支撑什么

| 用途 | 能否支撑 | 原因 |
|---|---|---|
| 事后排查「某次运行执行了什么」 | **能** | gateway.log 里有完整记录 |
| SIEM 采集 | **能**（需自建） | 是结构化 JSON 行 |
| **不依赖日志系统的审计留证** | **不能** | 只写日志，不落库 |
| 按用户查操作 | **间接** | 需 thread_id → user 反查 |
| 统计拦截率 | **能** | `verdict` 字段可聚合 |
| 命令行完整性 | **部分** | 200 字符截断 |
| 防篡改 | **不能** | 日志文件可被有权限者改写 |

## 7. 缺口

| 缺口 | 状态 | 边界 |
|---|---|---|
| 审计入库 | **无** | 只 `logger.info`，不写关系库 |
| 用户维度的记录 | **无** | 只有 `thread_id` |
| 命令完整记录 | **部分** | 200 字符截断（`:483`） |
| 正则无法判定的命令 | **有但不覆盖** | 注释明示盲区（`:49-51`） |
| warn 的强制约束 | **无** | 警告只给模型看，不阻断 |
| 审计日志的保留期 | **无** | 依赖外部日志轮转 |
| 非 bash 工具的审计 | **无** | 本中间件只管 `bash` |

最后一条容易漏：**这个中间件只覆盖 `bash`**。
文件读写、MCP 调用等其他工具不走这条审计路径
（覆盖矩阵见 [03-event-coverage.md](03-event-coverage.md)）。

## 8. 与其他章节的关系

- 全链路审计视图：[01-audit-chain.md](01-audit-chain.md)
- 事件覆盖矩阵：[03-event-coverage.md](03-event-coverage.md)
- 可观测性：[02-observability.md](02-observability.md)
- 沙箱模式：[../execution/01-sandbox-modes.md](../execution/01-sandbox-modes.md)
