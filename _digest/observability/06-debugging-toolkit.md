---
title: "诊断工具箱"
description: "DeerFlow 内建了一组'自动诊断 + 可回滚'的手段：LLM 错误分类/重试/断路器、loop 检测、tool 错误元数据、输出预算外部化、checkpoint 回滚、support bundle。这里给诊断入口和速查。"
topics: [debugging, error-handling, loop-detection, circuit-breaker, rollback]
---

# 诊断工具箱

这些手段分两类：**自动扛住**（错误分类重试、断路器、loop 检测），和**出事后回滚/取证**（checkpoint 回滚、run 事件、support bundle）。深潜见 [internals/agent-loop/04](../agent-loop/../agent-loop/04-error-handling-and-debugging.md) 和 [internals/runtime/](../runtime/)。

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

`_capture_rollback_point` 在 run 开始前抓完整 pre-run state；capture 失败**禁用回滚**（fail-closed），绝不恢复半状态。cancel-with-rollback 把线程恢复到 run 前。delta checkpoint 模式不能 fork，改走"linearize 重写到当前 head"（用 `Overwrite` 覆盖 reducer channel）。edit-replay run 失败/超时/中断时也恢复 pre-run checkpoint。

### run 事件取证

失败 run → `GET /api/threads/{id}/runs/{rid}/events?event_types=run.error,llm.error` 看错误证据；`?event_types=context:memory` 比 memory identity；`?task_id=` 翻 subagent 步。

### Support Bundle（`scripts/support_bundle.py`）

`make support-bundle` 生成**脱敏**排查包：收集配置（密钥脱敏）、日志、系统信息；secret-key denylist 覆盖 API key/token/password；产出 AI issue draft + 可选 zip。适合丢给社区/上游排查。

### 其它诊断锚点

- **subagent `stop_reason`**：`token_capped` / `turn_capped` / `loop_capped`（加性字段，不破坏 v1 消费方），lead 据此复用 capped 结果而非误当干净结果
- **goal 评估 `stand_down_reason`**：goal 循环停止时记录原因，可观测
- **TUI**：终端界面跑 `DeerFlowClient`，纯 UI 壳不 fork agent 行为，适合本地交互调试
