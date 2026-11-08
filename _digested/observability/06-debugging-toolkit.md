---
title: "诊断工具箱"
description: "DeerFlow 内建了一组'自动诊断 + 可回滚'的手段：LLM 错误分类/重试/断路器、loop 检测、tool 错误元数据、输出预算外部化、checkpoint 回滚、support bundle。这里给诊断入口和速查。"
topics: [debugging, error-handling, loop-detection, circuit-breaker, rollback]
---

# 诊断工具箱

这些手段分两类：**自动扛住**（错误分类重试、断路器、loop 检测），和**出事后回滚/取证**（checkpoint 回滚、run 事件、support bundle）。深潜见 [internals/agent-loop/04](../internals/agent-loop/04-error-handling-and-debugging.md) 和 [internals/runtime/](../internals/runtime/)。

## 自动扛住

### LLM 错误分类与重试（`llm_error_handling_middleware.py`）

| 类别 | 可重试 | 匹配 |
|------|--------|------|
| `quota` | 否 | billing/quota/credit |
| `auth` | 否 | key/permission/authentication |
| `transient` | 是 | timeout/connection/internal server error/httpx read/`StreamChunkTimeout`/空 generations 的 IndexError |
| `busy` | 是 | busy/overload/high demand/rate limit |

默认最多 3 次，指数退避（base 1000ms，`delay * 2^(attempt-1)`，上限 8000ms），尊重 `Retry-After`。`StreamChunkTimeoutError` 预算减半（2 次）并提示拆分工作。

**断路器**状态机 `closed → open → half_open → closed`：open 时返回 `error_type="CircuitBreakerOpen"`，half-open 只放行一个探测请求。`failure_threshold`（默认 5）、`recovery_timeout_sec`（默认 60）。

### Loop 检测（`loop_detection_middleware.py`）

两层：hash-based（相同 tool call 集合，`read_file` 行范围按 200 行分桶）+ per-tool 频率（跨文件循环）。`warn_threshold=3` / `hard_limit=5` / `tool_freq_warn=30` / `tool_freq_hard_limit=50`，支持 `tool_freq_overrides.bash.warn: 150`。硬停会剥离 `tool_calls` 强制文本回答，并 stamp `loop_capped`（`consume_stop_reason`）。

### Tool 错误元数据（`tool_result_meta.py`）

每个 `ToolMessage` 打 `deerflow_tool_meta`：`status`（success/error/partial_success）、`error_type`、`recoverable_by_model`、`recommended_next_action`（continue/rewrite_query/try_alternative/summarize/stop）、`source`。这是 model 可读的"这步到底成没成、要不要换招"信号。

### 输出预算外部化（`tool_output_budget_middleware.py`）

超 `externalize_min_chars`（默认 12000）的 tool 输出写盘 `{outputs}/.tool-results/{tool}-{id}.{ext}`，context 只留 head（2000）+ 文件引用 + tail（1000）；磁盘不可用才 fallback 硬截断（30000）。`read_file`/`read_file_tool` 默认豁免。bash 输出额外 `mask_secret_values()` 脱敏。

## 出事后回滚 / 取证

### checkpoint 回滚（`runtime/runs/worker.py`）

`_capture_rollback_point`（`worker.py:2953`，调用点 `worker.py:1433`）在 run 开始前抓完整 pre-run state；capture 失败**禁用回滚**（fail-closed），绝不恢复半状态。cancel-with-rollback 把线程恢复到 run 前。delta checkpoint 模式不能 fork，改走「linearize 重写到当前 head」（用 `Overwrite` 覆盖 reducer channel）。edit-replay run 失败/超时/中断时也恢复 pre-run checkpoint。

> 🆕 **v2.2.0 对观测的影响**：rollback 的 `interrupted` ACK 只是**中间态**（恢复还没完成）——`run.terminal` 的发布要等恢复完成、拿到最终 `error` ACK 才会发生（`backend/docs/RUN_EVENT_STREAM.md` 的 Publication Authority 一节）。所以**滚回过程中去查 `run.terminal` 会短暂看不到终态，这是设计而非丢事件**。

### run 事件取证

失败 run → `GET /api/threads/{id}/runs/{rid}/events?event_types=run.error,llm.error` 看错误证据；`?event_types=context:memory` 比 memory identity；`?task_id=` 翻 subagent 步。

**🆕 v2.2.0 的三个新取证入口**（细节见 `02`）：

| 想看 | 过滤 | 说明 |
|------|------|------|
| run 到成没成 | `?event_types=run.terminal` | 🆕 权威终态单例：`content.status` ∈ `success/error/interrupted/timeout`，`metadata.protocol_version=1` + `metadata.recovered`。**缺失就是证据不全**，不要退回用 `run.end`（它恒 `success`） |
| 每次 LLM 调用花了多少/为什么慢 | `?event_types=llm.ai.response,llm.error` | 🆕 metadata 有 `langchain_run_id` / `caller_category` / `provider` / `model` / `stop_reason` / `status` / `*_tokens` / `request_chars` / `request_message_count` / `request_started_at`。按 `langchain_run_id` 能和 LangSmith/Langfuse 的 span 对齐 |
| 上下文为什么被压 | `?event_types=middleware:summarize` | 🆕 `changes` 带 `noop` / `llm_call_skipped` / `summary_chars` / `previous_summary_chars` / `summarized_message_count` / `call_count` / `skip_count`。`noop=true` 的 cache 复用也会发 |

**分页用 `after_seq`**：v2.2.0 起 seq 在删除后不复用（DB/JSONL），所以「我上次读到 seq=N」这个游标是可靠的——不会因为中间某个 run 被删而漏读后面的。反过来说 memory 后端没有这个保证（删除后从 1 重排）。
**空 `event_types=[]` 等价于不过滤**（v2.2.0 起显式定义为 `is not None` 判断），别用空列表表达"什么都不要"。

### 🆕 证据链：Receipt / Seal / 失效

v2.2.0 把"这批事件有没有被完整封存"变成可查的字段（`persistence/run/model.py:67` `evidence_seal_state`、`:72` `evidence_retention_revision`）：

| 概念 | 落在哪 | 含义 |
|------|--------|------|
| **Evidence Receipt** | `DbRunEventStore.evidence_receipt()`（`db.py:379`） | Journal 停掉生产者并 drain 之后，取一组**已确认的**持久边界：`upper_event_seq` / `event_count` / `retention_revision`。**memory / JSONL 返回 `None`**——没有 durable receipt 就没有封存 |
| **Evidence Seal** | worker 调 `run_manager.seal_completed_evidence()`（`manager.py:932`） | 把 receipt 落成 `RunRow` 上的封存状态。失败走 `mark_evidence_partial()`（`manager.py:944`）记为 `partial` 而不是静默成功 |
| **封条失败原因** | worker 写进 `partial` 的 error | lead graph 从未开始执行（`"Lead graph execution did not begin; producer coverage is partial."`）、终态确认未通过、或 seal 落库失败——`worker.py` 终局化段 |
| **失效** | 任何事件删除 | `delete_by_thread()` / `delete_by_run()` 都把 `evidence_retention_revision` +1、`evidence_seal_state='partial'`、删 `CompletedRunSnapshotRow`（`db.py:401` 的 `_invalidate_evidence`） |

**怎么用**：拿到一行封存完好的 run，按其 `upper_event_seq` 拉 `list_events` 到该 seq 且 `event_count` 对得上，才算"证据完整"。对不上或 `seal_state != complete` → 这个 run 的审计结论只能当参考。**注意**：能封住「事件没被改（`content_sha256`）＋范围有界」，但**封不住**"agent 的行为本身完整"——那不是证据链能解决的问题。

### Support Bundle（`scripts/support_bundle.py`）

`make support-bundle` 生成**脱敏**排查包：收集配置（密钥脱敏）、日志、系统信息；secret-key denylist 覆盖 API key/token/password；产出 AI issue draft + 可选 zip。适合丢给社区/上游排查。

### 其它诊断锚点

- **subagent `stop_reason`**：`token_capped` / `turn_capped` / `loop_capped`（加性字段，不破坏 v1 消费方），lead 据此复用 capped 结果而非误当干净结果
- **goal 评估 `stand_down_reason`**：goal 循环停止时记录原因，可观测
- 🆕 **`missing_usage_calls`**：Console 里 `cost: null` 的另一个成因是"某次调用没回 usage"（不是没定价）。逐模型看 `by_model` 里 `cost=null` 而 `tokens` 在涨的那个，就是丢 usage 的 provider（见 `04`）
- 🆕 **producer lease `expired`**：SSE 订阅者等不到 `end` 时，`stream_bridge.producer_lease_state(run_id) == expired` 且 run 已终态 → 生产者已死，没有别人会写 end（见 `05`）
- **TUI**：终端界面跑 `DeerFlowClient`，纯 UI 壳不 fork agent 行为，适合本地交互调试
