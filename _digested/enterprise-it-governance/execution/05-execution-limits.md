---
title: "执行限制"
description: "循环检测、subagent 并发上限、超时控制——防止 agent 无限跑下去。"
topics: [governance, execution]
---

# 执行限制

循环检测、subagent 并发上限、超时控制——防止 agent 无限跑下去。

## 循环检测

`LoopDetectionMiddleware` — 检测 agent 是否陷入了重复调用同一个 tool 的循环：

- **Soft block：** 检测到重复 pattern → 注入警告消息（延迟到 `wrap_model_call` 中注入以兼容 OpenAI/Moonshot message 配对校验）
- **Hard stop：** pattern 持续 → 清除 tool_calls → `should_continue` 路由到 END → agent 强制结束
- 可通过 `config.yaml` 中的 `loop_detection.enabled` 开关

## Subagent 并发限制

`SubagentLimitMiddleware` — 限制 lead agent 一次派发的 subagent 数量。

> ⚠️ **v2.2.0 变更**：此前文档记为 `MAX_CONCURRENT_SUBAGENTS=3`（限幅 [2,4]）。2.2.0 的
> `config/subagents_config.py:17` 是 `MAX_CONCURRENT_SUBAGENT_CALLS = 64`。总数另由
> `subagents.max_total_per_run` 兜底（见 [成本与容量](../cost/01-cost-attribution.md)）。

```
LLM 产出 N 个 task tool_call → SubagentLimitMiddleware 截断到上限 → 多出的被静默丢弃
```

System prompt 里已经警告了 LLM："任何超出限制的调用会被静默丢弃——你会丢失那些工作。"Middleware 是 defense-in-depth。

## 超时控制

| 超时 | 默认值 | 机制 |
|------|--------|------|
| Subagent 执行 | 900s (15 min) | Thread future timeout + polling safety net |
| Subagent 轮询 | (timeout + 60) / 5 次 | task_tool 中 max_poll_count |

## Bash 参数级审计

详见 [../authorization/01-guardrail-layer.md](../authorization/01-guardrail-layer.md)。策略是**硬编码的 regex**，
不可通过配置文件修改。

**IT 管理含义：** 自定义高危命令列表需要 fork `sandbox_audit_middleware.py` 中的
`_HIGH_RISK_PATTERNS`，或在 Guardrail provider 层做参数级检测（provider 能拿到 `tool_input`）。
