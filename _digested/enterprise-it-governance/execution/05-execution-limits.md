---
title: "执行限制"
description: '循环检测、subagent 并发上限、超时控制——防止 agent 无限跑下去。'
topics: [governance, execution]
verified_against: v2.2.0
last_verified: 2026-11-08
---

# 执行限制

循环检测、subagent 并发上限、超时控制——防止 agent 无限跑下去。

## 循环检测

`LoopDetectionMiddleware`（`agents/middlewares/loop_detection_middleware.py:278`）— 检测 agent 是否陷入了重复调用同一个 tool 的循环：

- **Soft block：** 检测到重复 pattern → 注入警告消息（延迟到 `wrap_model_call` 中注入以兼容 OpenAI/Moonshot message 配对校验）
- **Hard stop：** pattern 持续 → 清除 tool_calls → `should_continue` 路由到 END → agent 强制结束
- 可通过 `loop_detection.enabled` 开关（`config.example.yaml:1504`）

`config.example.yaml:1504-1519` 的实际默认值：

| 键 | 默认 | 作用 |
|---|---|---|
| `enabled` | `true` | **默认开启**（与 guardrails 相反） |
| `warn_threshold` | 3 | 重复 3 次开始注入警告 |
| `hard_limit` | 5 | 重复 5 次强制结束 |
| `window_size` | 20 | 检测窗口 |
| `max_tracked_threads` | 100 | 保留 `(thread_id, run_id)` 的历史条数 |
| `tool_freq_warn` / `tool_freq_hard_limit` | 30 / 50 | 同一工具在滑动窗口内的调用数阈值 |

最后一行还有一个实用设计：`tool_freq_overrides` 可对**单个工具**单独调整阈值
（可高可低，例子给的是 `bash` 调到 150/300），不影响其它工具的防护强度。

## Subagent 并发限制

`SubagentLimitMiddleware` — 限制 lead agent 一次派发的 subagent 数量。

> ⚠️ **两个数字别混**：旧值 `MAX_CONCURRENT_SUBAGENTS=3` 仍然存在，是 middleware 的默认值
> （`subagents/executor.py:2337`），2.2.0 又加了 `config/subagents_config.py:17` 的
> `MAX_CONCURRENT_SUBAGENT_CALLS = 64`——但 **64 是响应级截断的安全上限**。
> 真正同时执行的并发由 `subagent_runtime.max_running` 决定，**默认是 3**
> （`config/subagent_runtime_config.py:12`），两者经 `clamp_subagent_concurrency` 取较小值（`subagents_config.py:20-25`）。
> 总数另由 `subagents.max_total_per_run` 兜底。展开见 [并发与调度](../cost/05-concurrency-and-scheduling.md) §1。

```
LLM 产出 N 个 task tool_call → SubagentLimitMiddleware 截断到上限 → 多出的被丢弃
```

System prompt 里的原话是 "Excess calls are discarded and their work is lost."
（`agents/lead_agent/prompt.py:621`）——没有 "silently" 这个词；响应级截断不追加提示，
只有 per-run 总量耗尽时才追加一条可见提示。Middleware 是 defense-in-depth。

## 超时控制

| 超时 | 默认值 | 机制 |
|------|--------|------|
| Subagent 执行 | **1800s (30 min)** | `subagents.timeout_seconds`；`(timeout + 60) // 5` 轮询 |
| Subagent 轮询 | 372 次 | task_tool 中 max_poll_count |

## Bash 参数级审计

详见 [../audit/03-sandbox-audit.md](../audit/03-sandbox-audit.md)。策略是**硬编码的 regex**，
不可通过配置文件修改。

**IT 管理含义：** 自定义高危命令列表需要 fork `sandbox_audit_middleware.py` 中的
`_HIGH_RISK_PATTERNS`，或在 Guardrail provider 层做参数级检测（provider 能拿到 `tool_input`）。
