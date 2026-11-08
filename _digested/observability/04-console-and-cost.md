---



title: "Console API 与成本归属"
description: 'GET /api/console/{stats,runs,usage} 是运营侧只读聚合层，直接查 runs/threads_meta 表。配 models[*].pricing 后按 cache-aware 计价。token 由 RunJournal 按 caller 分桶、subagent 用量回并到父 message。'
topics: [observability, cost, console, token-usage]
verified_against: v2.2.0
last_verified: 2026-11-08
---

# Console API 与成本归属

`app/gateway/routers/console.py` 提供三个**只读**运营端点——这是"运营 dashboard / 外部监控"的数据层，不是运行时路径。它直接查 harness 拥有的 `runs` / `threads_meta` 表（短命只读查询），不扩宽 `RunStore` 运行时面。

**前置条件**：`database.backend: sqlite | postgres`。`memory` 后端返回 **503**（不持久化 run 历史，无可报告）。

## 端点参考

### `GET /api/console/stats`

头条计数器（scoped 到当前用户）：

| 字段 | 含义 |
|------|------|
| `total_runs` / `active_runs` / `failed_runs` | run 计数（active=`pending|running`，failed=`error|timeout`） |
| `total_threads` / `total_agents` | 线程数 / 自定义 agent 数 |
| `total_tokens` | 累计 token |
| `total_cost` / `currency` | 估算成本 / 展示货币（🆕 v2.2.0：**pricing 不可用、或任意一次调用显式缺 usage** 时为 `null`） |

### `GET /api/console/runs?limit=&offset=&status=`

跨线程 run 列表，最新在前，join 线程标题。每项：`run_id / thread_id / thread_title / assistant_id / status / model_name / created_at / updated_at / duration_seconds / total_tokens / message_count / cost / error`（`error` 是失败 run 的摘录，截断 300 字符）。`duration_seconds` 对 active run 是**实时已耗时**，否则 `updated - created`。分页 `limit`（1–100）+ `offset`，`has_more` 用 `limit+1` 探测。

### `GET /api/console/usage?days=&tz_offset_minutes=`

每日 token 序列（**零填充**）+ per-model 明细。`days`（1–90）、`tz_offset_minutes`（-840..840，本地时区分桶）。返回 `days[]`（`date/total_tokens/input_tokens/output_tokens/runs/cost`）、`by_model`（含 `cache_read_tokens`）、`total_tokens/total_runs/total_cost/currency`。

## 成本计价（`models[*].pricing`）

`ModelConfig` 是 `extra="allow"`，所以 operator 直接注解：

```yaml
models:
  - name: gpt-4o
    pricing:
      currency: USD
      input_per_million: 2.50
      output_per_million: 10.00
      input_cache_hit_per_million: 1.25   # 缺省 → 按满价（保守上界）
```

计价是 **cache-aware**：`RunJournal` 从 `usage_metadata.input_token_details.cache_read` 累计 prompt-cache 命中，`_token_cost()` 把命中 token 按 `input_cache_hit_per_million` 计价、未命中按满价。规则：

- **单一货币**：混币 → 禁用成本报告，`cost`/`currency` 全 `null`（不产出无效聚合）
- **per-model 优先**：多模型 run（如 subagent 换模型）按 `token_usage_by_model` 逐模型计价；老行回退 run 级 `model_name`
- **未定价模型**：`cost: null`
- 🆕 **v2.2.0：显式缺 usage → 整条不可计价，`cost: null`**（详见下一节）

## 🆕 v2.2.0：缺 usage 的调用让成本变 `null`（不再静默当 0）

v2.1.0 的成本字段描述只有「无 pricing 时为 `null`」，于是**流式 provider 静默丢 usage** 时，那段 token 被当 0 吃掉，报出来的成本偏低却看起来正常。v2.2.0 把「这次调用到底有没有拿到 usage」变成一等信号：

| 环节 | 机制 |
|------|------|
| 标记来源 | `RunJournal` 的外部 LLM 调用登记 `_record_external_usage` 支持 `usage_missing: 1`，在该模型桶里累加 `missing_usage_calls`（见 `02`） |
| 判定 | `_usage_is_missing(usage)` = `missing_usage_calls > 0`（`console.py:231-232`）；`_has_missing_usage(token_usage_by_model)` = 任一桶为真（`console.py:235-236`） |
| 单 run | `_run_cost()` 一进来就 `if _has_missing_usage(...): return None`（`console.py:255-256`）——**局部已知桶和 legacy 总量都不能把它救回来** |
| 每日窗口 | 命中即 `bucket.cost = None` **且** `total_cost = None`（`console.py:498-500`） |
| per-model | 先收集 `missing_models`（小写）+ `missing_model_prices`（用 `id(price)` 认「已配置的 name/provider-ID 别名共享同一价目」，**不能**拿「恰好同价的无关模型」当别名）；最后统一 `entry.cost = None`（`console.py:538-541`）——**后面的已知桶或 legacy 行也不能把它还原**（注释原话：「Do not restore its quote by treating None as zero」） |

`total_cost` 在三处的模型字段描述同步改成「null when pricing is unavailable **or any call explicitly lacks usage**」（`ConsoleStatsResponse` / `ConsoleRunItem` / `ConsoleUsageResponse`），`ConsoleUsageDay.cost` 从 `float = 0.0` 改成 **`float | None`**（`console.py:92`）——这是**响应 schema 的变化**，写死 `day["cost"]` 数值的前端/脚本要处理 `null`。

**运维读法**：`cost: null` 现在有两个截然不同的意思，必须分清——

1. **没配定价**（`models[*].pricing` 缺）→ 去补配置；
2. **配了定价但某次调用没回 usage** → 这是**数据质量问题**，不是配置问题。常见成因就是自定义 OpenAI-compatible gateway 丢了 usage（见下节 `stream_usage=True`），或流式中途断开。

想把第 2 类降为零，得从 provider 侧修（开 `stream_usage`、换会回 usage 的 endpoint），Console 不会替你估。

## token 归属链

`RunJournal` 按 caller 分三桶（`lead_agent` / `subagent:` / `middleware:`，通过 `_identify_caller` 读 tags）。subagent 的用量由 `SubagentTokenCollector` 收集，`TokenUsageMiddleware` 在下一轮 `after_model` 从缓存（key=`tool_call_id`）取出，合并到**触发 subagent 的父 AIMessage** 上：

```
Lead Agent 第 N 轮 AIMessage（dispatch 3 个 subagent）
  → subagent_1/2/3 的 token 用量 → 合并回该 AIMessage.usage_metadata
```

所以"dispatch → subagent 工作 → 返回"的完整成本归属到触发它的父 message。

`create_chat_model()` 对自定义 base_url 的 OpenAI-compatible provider **自动开 `stream_usage=True`**——LangChain 只在标准 OpenAI endpoint 默认开，自定义 gateway（doubao/deepseek）会静默丢 usage 数据。

## 读法（生产）

- `stats` 定时拉，`active_runs` 持续 > 0 可能卡死（见 `07` 告警配方）
- `usage` 看每日成本趋势 + per-model 热点；**`cost` 大面积为 `null` 时先分清是「没定价」还是「缺 usage」**——`by_model` 里某个模型 `cost` 为 `null` 而 `tokens` 仍在涨，就是那个模型丢了 usage
- `runs?status=failed` 拉失败 run，再拿 `run_id` 去 `/runs/{rid}/events` 看 `run.error` / `llm.error`
