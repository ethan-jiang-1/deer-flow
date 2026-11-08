---



title: "输出与错误脱敏"
description: 'mask_local_paths_in_output 的映射顺序与四类覆盖：skills、per-user 自定义技能、ACP workspace、user-data。以及它防的是什么、不防什么。'
topics: [governance, data, redaction]
verified_against: v2.2.0
last_verified: 2026-11-08
---

# 输出与错误脱敏

Agent 在沙箱里看到的是 `/mnt/user-data/...` 这类虚拟路径，但工具实现跑在 host 上，
原始输出里可能出现真实 host 路径。这一层负责把路径换回虚拟形式。

## 1. 函数与位置

`packages/harness/deerflow/sandbox/tools.py:862` 的 `mask_local_paths_in_output`：

```python
def mask_local_paths_in_output(output: str, thread_data: ThreadDataState | None) -> str:
    """Mask host absolute paths from local sandbox output using virtual paths.

    Handles user-data paths (per-thread), skills paths (global + per-user
    custom + managed integrations), and ACP workspace paths (per-thread).
    """
```

## 2. 四类覆盖与映射顺序

`packages/harness/deerflow/sandbox/tools.py:870-873` 的注释明确要求**顺序保留**：

> Order is preserved from the original implementation: skills, then per-user
> custom/integration skills, then ACP workspace, then user-data mappings
> (**longest host path first**).

| 顺序 | 类别 | host 前缀 | 替换为 | 证据 |
|---|---|---|---|---|
| 1 | 全局 skills | `_get_skills_host_path()` | `/mnt/skills` | `packages/harness/deerflow/sandbox/tools.py:875-877` |
| 2 | 受管集成技能 | `integration_skills_dir()` | `/mnt/skills/integrations` | `packages/harness/deerflow/sandbox/tools.py:891`、`:895-897` |
| 3 | per-user 自定义技能 | `user_custom_skills_dir(user_id)` | `/mnt/skills/custom` | `packages/harness/deerflow/sandbox/tools.py:890-894` |
| 4 | ACP workspace | `_get_acp_workspace_host_path(...)` | ACP 虚拟路径 | `packages/harness/deerflow/sandbox/tools.py:901-903` |
| 5 | user-data | `_thread_actual_to_virtual_mappings(...)` | `/mnt/user-data/*` | `packages/harness/deerflow/sandbox/tools.py:905-908` |

### 2.1 为什么「最长 host 路径优先」

`packages/harness/deerflow/sandbox/tools.py:907` 用 `sorted(..., key=lambda item: len(item[0]), reverse=True)`。

**原因**：如果短前缀先替换，长前缀的后半段就再也匹配不到了。
例如 `/a/b` 与 `/a/b/c` 两个映射：先处理 `/a/b` 会把 `/a/b/c/x` 变成一个不认识的形式。
从长到短可以保证最具体的先命中。

### 2.2 stable 与 dynamic 两类

| 类别 | 何时构建 | 例子 |
|---|---|---|
| `stable_sources` | 每次调用时静态确定 | 全局 skills、集成技能 |
| `dynamic_sources` | 依赖当前 user / thread | per-user 技能、ACP workspace、user-data |

`packages/harness/deerflow/sandbox/tools.py:874-875` 把两者分开收集，静态的会被编译成正则缓存（`packages/harness/deerflow/sandbox/tools.py:914` `_compiled_mask_patterns`），
动态的逐个处理。

## 3. 自定义挂载路径的处理落在别处

`packages/harness/deerflow/sandbox/tools.py:871-872` 点明了一个分工：

> Custom mount host paths are masked by `LocalSandbox._reverse_resolve_paths_in_output()`.

**含义**：`mask_local_paths_in_output` 只负责**内置**的四类路径。
用户自定义的挂载点由沙箱自己的 `_reverse_resolve_paths_in_output()` 处理。

**这是评审时的易漏点**：两份实现、两处覆盖。排查「某个路径没被脱敏」时
要同时看这两个函数。

## 4. 它防什么、不防什么

| 防 | 不防 |
|---|---|
| Agent 输出里出现 `{project_root}/.deer-flow/users/{user_id}/threads/{thread_id}/...` | PII（手机号、身份证号等）——见 [05-pii-redaction.md](05-pii-redaction.md) |
| 工具的异常消息泄露 host 目录结构 | 凭据（API key、token）；bash 输出另有 `mask_secret_values` 额外擦除密钥（`sandbox/tools.py:2913`、`:2942-2946`） |
| 沙箱与 host 路径不一致导致的困惑 | 业务敏感词 |

**定位**：这是**信息暴露面**收敛，不是合规意义上的数据脱敏。

## 5. 错误信息脱敏

工具异常在 Local 模式下同样经过路径替换（`tools.py` 内 `mask_local_paths_in_output` 的调用点）。
所以「工具报错把 host 路径打到前端」这条泄露路径被覆盖。

**边界**：只覆盖路径。异常消息里的其他内容（如命令行参数、SQL 片段）原样透出。

## 6. 缺口

| 缺口 | 状态 | 边界 |
|---|---|---|
| PII / 凭据脱敏 | **无（在另一处）** | 见 [05-pii-redaction.md](05-pii-redaction.md)；且该处默认关闭 |
| 自定义挂载的统一处理 | **部分** | 内置路径与本函数一致；自定义挂载由沙箱实现处理，两处逻辑 |
| user_id 的替换 | **有（仅本 thread）** | 本 thread 的 `{user_id}` 段随映射替换成虚拟路径（`backend/packages/harness/deerflow/sandbox/tools.py:790-817`）；**他用户的绝对路径不在 map 里，会原样泄露** |
| 输出长度截断 | 与脱敏无关 | 见 execution 卷的资源限制 |
| 脱敏的日志留痕 | **无** | 脱敏动作不产生事件；无法统计「发生了多少次路径泄露尝试」 |

第 3 条值得注意：映射表只由**当前 thread** 的 workspace/uploads/outputs 构造
（`backend/packages/harness/deerflow/sandbox/tools.py:790-817`、`:905-908`）。所以本用户的 `{user_id}` 段会被替换，
但**另一个用户的绝对路径不在 map 里，会原样出现在输出中**——
这既暴露了越权读取的尝试，也是一条真实的路径泄露面。

## 7. 与其他章节的关系

- 目录布局：[01-storage-and-isolation.md](01-storage-and-isolation.md)
- PII 脱敏（默认关闭的那一层）：[05-pii-redaction.md](05-pii-redaction.md)
- 沙箱模式与挂载：[../execution/01-sandbox-modes.md](../execution/01-sandbox-modes.md)
