---



title: "资源管控与隔离"
description: '输出截断（可配）、命令长度与 null byte 拒绝（不可配）、sandbox 实例缓存 256、per-thread 隔离的真实边界。'
topics: [governance, execution]
verified_against: v2.2.0
last_verified: 2026-11-08
---

# 资源管控与隔离

资源管控在这个框架里有两类：**可配的**（输出截断）和**不可配的**（安全校验）。
两者的运维含义完全不同。

## 1. 可配的限额：输出截断

`config.example.yaml:1748-1750`：

```yaml
bash_output_max_chars: 20000
read_file_output_max_chars: 50000
ls_output_max_chars: 20000
```

| 资源 | 默认 | 截断方式 | 配置键 |
|---|---|---|---|
| bash 输出 | 20,000 字符 | middle（中间截断） | `bash_output_max_chars`（`backend/packages/harness/deerflow/sandbox/tools.py:2900`） |
| `read_file` 输出 | 50,000 字符 | head | `read_file_output_max_chars`（`backend/packages/harness/deerflow/sandbox/tools.py:3300`） |
| `ls` 输出 | 20,000 字符 | head | `ls_output_max_chars`（`backend/packages/harness/deerflow/sandbox/tools.py:3006`） |

### 1.1 为什么 bash 是中间截断

`backend/packages/harness/deerflow/sandbox/tools.py` 的截断回退值不是同一个：
bash / `ls` 是 **20000**，`read_file` 是 **50000**（`:3300`、`:3302`），都支持配置覆盖。
bash 输出用**中间截断**而不是头部截断，原因是 stdout/stderr 顺序不确定、
错误可能出现在两端（`:2450-2451`）；截中间能同时保住两端。

这对「用 bash 输出判断失败原因」这件事是必要的。

## 2. 不可配的校验：命令本身

`sandbox_audit_middleware.py:535`：

```python
_MAX_COMMAND_LENGTH = 10_000
```

| 校验 | 行 | 行为 | 可配 |
|---|---|---|---|
| 命令长度 > 10,000 字符 | `:541` | **拒绝** | **否** |
| 含 null byte | `:543-544` | **拒绝**，返回 `"null byte detected"` | **否** |

**这两项为什么不该可配**：它们不是策略，是**输入合法性校验**。
超长命令和 null byte 都可能是绕过正则匹配的手段——
让运营方调这两个值，等于给绕过留了配置口子。

和 [03-configurability.md](../authorization/03-configurability.md) §3 同一条思路：
不可配换的是「可证明」。

## 3. Sandbox 实例缓存

`local/local_sandbox_provider.py:33`：

```python
DEFAULT_MAX_CACHED_THREAD_SANDBOXES = 256
```

| 事实 | 含义 |
|---|---|
| 默认缓存 256 个 per-thread sandbox | 内存占用随活跃 thread 数增长 |
| LRU 淘汰 | 超出后最久未用的被回收 |
| 回收后 thread 数据仍在磁盘 | 只回收实例，不删数据 |

**第三行要注意**：淘汰的是内存里的 sandbox 实例，workspace 文件不受影响。
但下一次访问该 thread 会重建实例，有一次性延迟。

## 4. Per-thread 隔离的真实边界

```
thread_1 → sandbox_id="local:alice:thread_1" → users/alice/threads/t1/user-data/workspace
thread_2 → sandbox_id="local:alice:thread_2" → users/alice/threads/t2/user-data/workspace
```

| 保证 | 强度 |
|---|---|
| 通过 sandbox 工具无法读写对方文件 | **有**（路径映射 + 校验） |
| 文件操作锁 `(sandbox_id, path)` 粒度的互斥 | **有** |
| 进程级隔离 | **无**（Local 模式同进程） |
| 任意代码无法互相访问 | **无**——`python -c` 可绕过工具层 |

**最后一行是关键**：per-thread 隔离是**路径层**的隔离，不是**进程层**的隔离。
需要进程级隔离必须换沙箱后端（见 [01-sandbox-modes.md](01-sandbox-modes.md)）。

## 5. 缺口

| 缺口 | 状态 | 边界 |
|---|---|---|
| CPU / 内存 / 磁盘配额 | **部分** | AIO 本地 Docker 默认 2 CPU / 2G 内存 / pids 512（`community/aio_sandbox/local_backend.py:240-242`）；Local 模式无 cgroup；磁盘无配额 |
| 单 thread 的磁盘用量上限 | **无** | 可无限写入直到磁盘满 |
| 全局并发 run 上限 | **部分** | scheduler 有 `max_concurrent_runs=3`；交互式 run 无全局上限（见 [../cost/05](../cost/05-concurrency-and-scheduling.md)） |
| per-user 资源配额 | **无** | 无按用户的汇总限制 |
| 输出截断是否可配 | **有** | 三个键均可配（`config.example.yaml:1748-1750`） |
| 命令校验是否可配 | **无**（有意） | 输入合法性校验，不可调 |

**第一行与第二行是 Local 模式的实质短板**：
AIO Docker 至少有 CPU/内存/pids 默认限，但**磁盘没有配额**；Local 模式连 cgroup 都没有——
一个 agent 跑一段 `yes > /tmp/big` 就能把磁盘写满，框架层没有机制阻止。
这类资源必须由容器/主机层限制。

## 6. 与其他章节的关系

- 沙箱模式：[01-sandbox-modes.md](01-sandbox-modes.md)
- 路径防护：[02-path-containment.md](02-path-containment.md)
- 预算与递归限额：[../cost/03-budgets-and-limits.md](../cost/03-budgets-and-limits.md)
- 策略可配置性：[../authorization/03-configurability.md](../authorization/03-configurability.md)
