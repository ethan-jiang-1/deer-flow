---
title: "多实例部署"
description: "声明多实例后启动闸门会强制 4 项要求、拒绝 3 类配置。以及 GATEWAY_WORKERS 只覆盖单进程树的盲区——K8s 多 Pod 部署必须显式声明。"
topics: [governance, cost, multi-instance, deployment]
---

# 多实例部署

多实例是治理分歧点最大的部署形态：单个 Gateway 时很多「本地状态」无害，
一旦复制成 N 个 Pod，锁禁、事件序列、SSE、调度器全部开始出错。
DeerFlow 用**启动闸门**处理这件事——声明了多实例就必须配齐。

## 1. 为什么需要显式声明

`packages/harness/deerflow/config/deployment_config.py:34-45` 的字段描述点明盲区：

> Declare that more than one Gateway instance (uvicorn worker, container, or Kubernetes
> Pod) shares this database. **`GATEWAY_WORKERS` counts only one process tree**, so
> replicas > 1 with one worker per Pod are invisible to the startup safety gate without
> this flag.

| 部署形态 | `GATEWAY_WORKERS` 能发现吗 | 需要 `multi_instance` 吗 |
|---|---|---|
| 1 个 uvicorn 进程 | — | 不需要 |
| 1 个进程 + 8 worker | 能（同一进程树） | 不需要 |
| 8 个 Pod × 1 worker | **不能** | **必须** |

**这就是企业 K8s 部署最易踩的坑**：`GATEWAY_WORKERS=1` 看起来安全，
但 8 个副本共享同一个 Postgres 时，闸门完全看不见。

声明方式有两种（`deployment_config.py:24-26`、`:76-110`）：

| 来源 | 写法 | `knob` 文本 |
|---|---|---|
| 环境变量 | `DEER_FLOW_MULTI_INSTANCE=1` | `DEER_FLOW_MULTI_INSTANCE=1` |
| 配置文件 | `deployment.multi_instance: true` | `deployment.multi_instance=true` |

**环境变量优先**（`deployment_config.py:93-99`）：部署工具知道真实拓扑，
所以 env 先于 config.yaml 被采纳。

### 1.1 falsy 值判定

`deployment_config.py:28`、`:76-89`：

```python
_FALSY = frozenset({"", "0", "false", "no", "off"})
```

> Blank, `0`, `false`, `no` and `off` mean "not declared", so a templated
> `DEER_FLOW_MULTI_INSTANCE=false` stays inert. **Every other value is a declaration:
> a typo in this variable must fail closed** (run the gate) rather than silently
> disable it.

所以 `DEER_FLOW_MULTI_INSTANCE=ture`（拼错）会被当作**已声明**，从而跑闸门。
这是刻意的 fail-closed 设计。

## 2. 四条强制要求

声明多实例后，启动时必须满足（`deployment_config.py:37-40`）：

| # | 要求 | 原因 |
|---|---|---|
| 1 | `database.backend: postgres` | 共享状态的地基 |
| 2 | `run_events.backend: db` | seq 需跨进程单调 |
| 3 | `run_ownership.heartbeat_enabled: true` | 孤儿 run 可被接管 |
| 4 | Redis stream bridge | 跨实例 SSE |

任何一条不满足，**Gateway 拒绝启动**。这不是警告，是硬闸门。

## 3. 三类被拒绝的配置

| # | 被拒配置 | 原因 | 证据 |
|---|---|---|---|
| 1 | 显式 `memory` 沙箱归属存储 | 归属需跨实例可见 | `deployment_config.py:39` |
| 2 | 进程内 browser 工具 | 浏览器会话绑进程 | `deployment_config.py:40` |
| 3 | `scheduler.enabled: true` 但 `scheduler.multi_instance: false` | 调度器默认单实例 | `deployment_config.py:40` |

第 3 条最容易被忽略：**调度器默认单实例**（`config.example.yaml:2836`：
"The scheduler is single-instance by default"），需要显式
`scheduler.multi_instance: true`（`config.example.yaml:2854`、`:2865`）
才能在多实例下安全启用。它用的是 lease-aware recovery 机制（`config.example.yaml:2914`）。

## 4. 由多实例倒逼的其他配置

除闸门强制的四条外，实际生产中还有几项需要一起对齐：

| 配置 | 单实例 | 多实例 | 后果 |
|---|---|---|---|
| `auth.local.throttle_storage` | `memory` 可接受 | **必须** `auto`(有库) 或 `db` | `memory` 下 N 副本 = N× 次猜测机会 |
| `stream_bridge.producer_lease_recovery_enabled` | 无所谓 | 需决定 | 只在所有 writer 升级后才开 |
| `channel_leader_lease` | 自动关 | 随 `multi_instance` 自动开 | `deployment_config.py:46` 引用自 `channel_leader_lease_config.py` |
| `agent_storage` | 本地可接受 | 需共享 catalog | `agent_storage_config.py:35` |

`agent_storage_config.py:33-37` 对 agent catalog 的要求：

> multi-instance deployment sees the same catalog on every node; it requires ...

这是「agent 定义存在哪」的问题——本地文件在多副本下会导致各节点看到的 agent 列表不同。

## 5. 回滚单步

`deployment_config.py:58-66` 的 `rollback` 属性给出撤销声明的**唯一步骤**：

| 声明来源 | 回滚动作 |
|---|---|
| env | `unset DEER_FLOW_MULTI_INSTANCE` |
| config | `set deployment.multi_instance=false` |

设计意图（`deployment_config.py:50-52`）："the display text is never the thing to inspect"——
调用方按 `source` 分支，而不是去解析提示字符串。所以拒绝消息里给的处置建议是准确的。

## 6. 缺口

| 缺口 | 状态 | 边界 |
|---|---|---|
| 自动拓扑探测 | **无** | 必须**显式声明**；副本数变化不会自动触发闸门 |
| 优雅的滚动升级指引 | **部分** | `producer_lease_recovery_enabled` 的开关顺序有文档（见 `observability/07`），但无自动化编排 |
| 跨实例的一致性校验 | **无** | 无运行时的「各副本配置是否一致」检查 |
| 脑裂检测 | **无** | 无基于 lease 的主动扩容保护（channel lease 只是让重复 poller 不同时跑） |
| 副本数感知 | **无** | 闸门是二值（单实例/多实例），不因副本数 1 vs 8 而调整 |

## 7. 与其他章节的关系

- 登录锁禁的存储选择：[../identity/09-login-throttle.md](../identity/09-login-throttle.md) §4
- 事件序列与 `run_events.backend`：`_digested/observability/02-run-events-and-journal.md`
- 调度器：[../cost/02-deployment-and-ops.md](02-deployment-and-ops.md)
