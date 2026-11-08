---
title: "成本归属"
description: "token 用量在哪里产生、subagent 用量如何回溯到父消息、stream_usage 为什么默认打开，以及「能统计」与「能归因」之间的距离。"
topics: [governance, cost]
---

# 成本归属

成本归属要回答两个不同的问题：**花了多少** 和 **花在谁身上**。
DeerFlow 对前者覆盖较全，对后者有限。

## 1. 用量在哪里产生

`TokenUsageMiddleware`（`agents/middlewares/token_usage_middleware.py:327`）
在每个 `AIMessage` 上标注 `usage_metadata`（`input_tokens` / `output_tokens` / `total_tokens`）。

| 特征 | 事实 |
|---|---|
| 收集粒度 | **每次 LLM 调用** |
| 载体 | `AIMessage.usage_metadata` |
| 是否聚合 | 否——聚合需自行做 |

## 2. subagent 用量如何回溯

### 2.1 机制（与常见描述不同）

subagent 的 token 消耗由 `SubagentTokenCollector`
（`subagents/token_collector.py:16`）收集，写进 ToolMessage 的 `additional_kwargs`：

| 键 | 位置 | 作用 |
|---|---|---|
| `subagent_token_usage` | `status_contract.py:58` | 收集到的用量 |
| `subagent_token_usage_attributed` | `token_usage_middleware.py:20` | **防重复归属**标记 |

读取入口是 `_subagent_usage_from_tool_message`
（`token_usage_middleware.py:234`）：

```python
def _subagent_usage_from_tool_message(message: ToolMessage) -> dict[str, int] | None:
    """Read validated subagent usage from the current run's message state."""
    ...
    if additional_kwargs.get(SUBAGENT_TOKEN_USAGE_ATTRIBUTED_KEY) is True:
        return None
    return normalize_token_usage(additional_kwargs.get(SUBAGENT_TOKEN_USAGE_KEY))
```

### 2.2 三个值得注意的设计

| 设计 | 为什么 |
|---|---|
| 走 ToolMessage 的 `additional_kwargs`，不走独立缓存 | 用量跟着消息走，重放/恢复时不会丢 |
| `..._attributed` 标记 | **防重复累加**——同一条消息被扫到两次也只算一次 |
| `normalize_token_usage` 校验 | 只接受通过校验的用量，脏数据被丢弃 |

第三条是把「外部 provider 返回的怪数据」挡在账本之外。

## 3. `stream_usage` 为什么默认打开

`models/factory.py:677-684` 的注释说得很直接：

> LangChain's `BaseChatOpenAI` only defaults `stream_usage=True` when **no custom
> base_url/api_base** is set, so models hitting third-party endpoints (e.g. doubao,
> deepseek) **silently lose usage data**. We default it to `True` unless explicitly configured.

| 场景 | LangChain 默认 | DeerFlow 处理 |
|---|---|---|
| 官方 OpenAI endpoint | `stream_usage=True` | 不变 |
| 自定义 base_url（豆包、DeepSeek 等） | **`False` → 静默丢 usage** | **默认改为 `True`** |
| 显式配置了 `stream_usage` | 尊重配置 | 不覆盖 |

实现上还有一个守卫：只有模型类真的有 `stream_usage` 字段时才设
（`if "stream_usage" in getattr(model_class, "model_fields", {})`），
避免给不支持该参数的类塞入无效关键字。

**这一条对成本归属是决定性的**：如果用了自建网关而没开这个，
账单是真实发生的，但 DeerFlow 里统计到的是零。

## 4. 能统计 vs 能归因

| 维度 | 是否可统计 | 说明 |
|---|---|---|
| 每次调用 | **是** | `usage_metadata` |
| 每个 run | **是** | 同一 run 的消息可汇总 |
| 每个 subagent | **是** | 经上述归属链回到父消息 |
| 每个用户 | **部分** | 需经 thread → user 关联，无现成视图 |
| 每个 agent 定义 | **部分** | 同上，需自行聚合 |
| 换算成金额 | **否** | 无单价表（见 [03-budgets-and-limits.md](03-budgets-and-limits.md)） |

第 4、5 行是「有数据、没有视图」：数据都在 `usage_metadata` 里，
但要做「按用户排行」需要自己写查询。

## 5. 缺口

| 缺口 | 状态 | 边界 |
|---|---|---|
| 实时成本仪表盘 | **无** | 只有数据，无现成视图 |
| per-user / per-agent 聚合 | **无** | 需自行关联 thread → user |
| 单价配置与金额换算 | **无** | 模型配置里无价格字段 |
| 预算执行与告警 | **部分** | `token_budget` 有 warn/hard-stop，但默认关闭且告警只给模型不给运维 |
| 跨 run 累计 | **无** | 每个 run 独立计数 |
| 缓存命中与成本的关联 | **部分** | `cache_read_tokens` 被单独记录（`token_collector.py:76-77`），但不参与金额计算 |

最后一行值得展开：prompt 缓存命中会显著降低成本，
`token_collector.py:50-57` 特意把 `cache_read_tokens` 单独记下来，注释写着
"needed for cache-aware cost accounting"——**数据留了，计算没做**。

## 6. 与其他章节的关系

- 限额与预算：[03-budgets-and-limits.md](03-budgets-and-limits.md)
- 多实例的成本影响：[04-multi-instance.md](04-multi-instance.md)
- 用量事件是否入 journal：[../audit/03-event-coverage.md](../audit/03-event-coverage.md) §1
