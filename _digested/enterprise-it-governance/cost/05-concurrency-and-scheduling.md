---
title: "并发与调度"
description: '两个并发维度的区别（执行并发默认 3 vs 响应级截断 64）、调度层事实、六条默认「无限制」的容量维度。'
topics: [governance, cost, capacity]
verified_against: v2.2.0
last_verified: 2026-11-08
---

# 并发与调度

本页专讲**容量维度**：同时能跑多少、排队怎么走、默认有哪些不设限。
token 预算与递归上限见 [03-budgets-and-limits.md](03-budgets-and-limits.md)。

## 0. 最容易被误读的一点

「并发上限 64」这个说法在多个文档里出现过，但它指的是**响应级截断上限**，
不是实际并发。真正的执行并发默认是 **3**。两页都讲清楚这件事，是因为
按 64 估容量会高估 20 倍以上。


## 1. 并发与总量

并发有**两个不同的维度**，混在一起是最常见的误读：

| 维度 | 默认 | 位置 | 含义 |
|---|---|---|---|
| **执行并发**（真正同时跑的） | **3** | `config/subagent_runtime_config.py:12`（`max_running`，上限 `le=64`） | 一个 Gateway 进程内同时执行的 native subagent 数 |
| **响应级截断**（一次派发的 ceil） | **64** | `config/subagents_config.py:17`（`MAX_CONCURRENT_SUBAGENT_CALLS`） | 模型单次响应里最多保留多少个 task tool_call |
| **排队上限** | 64 | `subagent_runtime_config.py:18`（`max_queued`） | 等待执行槽位的数量 |
| **排队超时** | 300 秒 | `subagent_runtime_config.py:28`（`queue_timeout_seconds`） | 等不到槽位就失败 |
| **单 run 总数** | 6（区间 1–50） | `subagents_config.py:13`（`DEFAULT_MAX_TOTAL_SUBAGENTS_PER_RUN`） | 一个 run 累计可派发的普通 `task` 总数；durable `batch_task` 另有独立预算（`subagent_batches_config.py:9-23`） |

### 1.1 两个数字怎么配合

`clamp_subagent_concurrency`（`subagents_config.py:20-25`）把响应级并发
夹到「64 安全上限」与「实际执行槽位」中的**较小值**：

```python
upper = MAX_CONCURRENT_SUBAGENT_CALLS          # 64
if execution_capacity is not None:
    upper = min(upper, max(MIN_CONCURRENT_SUBAGENT_CALLS, execution_capacity))
return max(MIN_CONCURRENT_SUBAGENT_CALLS, min(upper, value))
```

所以默认部署的真实并发是 **3**，不是 64。
「64」只在显式把 `subagent_runtime.max_running` 调高后才起作用。

**这对成本估算的影响是决定性的**：按 64 估峰值会高估 20 倍以上。

### 1.2 调度层的其他事实

| 事实 | 影响 |
|---|---|
| `admission_policy` 默认 `queue` | 满了排队而不是直接拒绝；失败形态是**延迟**而非报错 |
| 跨层没有全局公平调度器 | 子代理按「谁先 `_acquire`」服务，多 run 混序 |
| 每层内部都是 FIFO + 有界等待 | 不存在无界排队或优先级倒置 |
| `max_running` 只在启动快照生效 | 热改对已创建的 controller 无效（见 §1.3） |

### 1.2.1 scheduler 的容量旋钮

| 旋钮 | 默认 | 含义 |
|---|---|---|
| `scheduler.max_concurrent_runs` | 3 | 跨实例的已调度 run 全局上限（`config.example.yaml:2870`） |
| `max_concurrent_runs_per_user` | 2 | 单 owner 上限 |
| `queue_timeout_seconds` | 3600 | 调度 occurrence 排队超时 |
| `recursion_limit` | 1000 | 调度 run 的超级步上限（是交互 run 的 10 倍） |

### 1.3 热改不生效的那一项

`subagent_runtime.max_running` 被改后，**已创建的 controller 不受影响**——
它属于启动期快照，不是热加载项。这与 [../lifecycle/01-agent-lifecycle.md](../lifecycle/01-agent-lifecycle.md) §2.2 的「必须重启」清单同类。

运维含义：调整并发必须安排重启窗口，不能指望改完立刻扩容。


## 2. 六条「无限制」事实（搬家承接）

以下六条原在 `orchestration-ladder/03` 的「不理想化清单」，
其治理含义归本卷，故移到这里；原页保留规则细节。

| # | 事实 | 边界 |
|---|---|---|
| 1 | **run 全局并发无限制** | Gateway 不限制跨 thread 的同时 run 数 |
| 2 | **LLM 并发默认无限制** | `llm_call.max_concurrent_calls` 默认 `0` = 关闭上限（`config/app_config.py:112-114`）；且为**进程级**，`GATEWAY_WORKERS > 1` 时实际上限要乘 worker 数 |
| 3 | **RPM 配速默认关闭** | `request_admission` 整块被注释（`config.example.yaml:33`） |
| 4 | **嵌套深度无计数器** | 深度 = 1 靠工具剔除实现，custom agent 配置疏漏时无第二道深度闸 |
| 5 | **每 run 总量上限区间宽松** | 默认 6，schema 允许到 50；响应级截断不追加提示，只有 per-run 总量耗尽才追加一条可见提示 |
| 6 | **子代理容量热改只在启动快照生效** | `max_running` 对已创建的 controller 无效（见 §1.3） |

### 2.1 第 2 条值得展开

`config/app_config.py:116-122` 原文：

> Per-process, **not per-cluster**: with `GATEWAY_WORKERS > 1` the aggregate cap is
> effectively `max_concurrent_calls * GATEWAY_WORKERS` …

即这个旋钮**本身不是集群级限流**，要集群级斜率控制得在入口层另加 `limit_req`。

### 2.2 六条的共同点

都不是 bug，而是「默认不限制、需要时自行收紧」的设计取向。
直接影响：**默认部署在容量维度上是敞口的**，上线前需要逐项显式决定取值。

## 3. 缺口

| 缺口 | 状态 | 边界 |
|---|---|---|
| 跨 thread 的交互式 run 数上限 | **无** | Gateway 不限制同时 run 数；scheduler 的 `max_concurrent_runs` 只管已调度 occurrence |
| 集群级 LLM 并发限制 | **无** | `max_concurrent_calls` 是进程级，多副本需乘 worker 数 |
| 集群级 RPM 配速 | **无** | `request_admission` 默认不配 |
| 嵌套深度计数器 | **无** | 深度=1 靠工具剔除，配置疏漏时无第二道闸 |
| 全局公平调度器 | **无** | 子代理按「谁先 acquire」，多 run 混序 |
| 每层内部的 FIFO + 有界等待 | **有** | 不存在无界排队或优先级倒置 |

**最后一行是正面的**：虽然跨层没有公平调度器，但每一层内部都是有界 FIFO，
不会出现「某个 run 永远排不上」。

## 4. 与其他章节的关系

- token 预算与递归上限：[03-budgets-and-limits.md](03-budgets-and-limits.md)
- 成本归属：[01-cost-attribution.md](01-cost-attribution.md)
- 多实例的影响：[04-multi-instance.md](04-multi-instance.md)
- 执行层循环检测：[../execution/05-execution-limits.md](../execution/05-execution-limits.md)
