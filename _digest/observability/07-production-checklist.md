---
title: "生产上线清单"
description: "要上线前：开什么（SQL 后端、trace 关联、追踪、定价）、日常看什么、排障走哪条路、已知缺口是什么、怎么自己补告警。诚实版——DeerFlow 给原料，不给聚合仪表盘。"
topics: [production, observability, checklist, alerting]
---

# 生产上线清单

DeerFlow 给的是观测**原料**，不是现成的聚合仪表盘和告警。这份清单是"上线前把原料接上、上线后知道去哪看"的最小集。安全硬化另见 [operations/security/](../operations/security/)。

## 上线前必开

| 事项 | 配置 | 为什么 |
|------|------|--------|
| **SQL 持久化后端** | `database.backend: sqlite`（单机）或 `postgres`（多实例） | Console API、持久化 run 历史、事件流都依赖它；`memory` 后端 Console 返回 503 |
| **多 worker 事件后端** | `run_events.backend: db` | `GATEWAY_WORKERS > 1` 时启动门禁拒绝 memory/jsonl（seq 无法跨进程保证） |
| **trace 关联** | `logging.enhance.enabled: true` + `format: json` | 日志带 `trace_id`、响应带 `X-Trace-Id`、Langfuse 带 `deerflow_trace_id`——排障三处对齐（**restart-required**） |
| **外部追踪** | `LANGFUSE_TRACING=true`（或 `LANGSMITH_TRACING=true`）+ `DEER_FLOW_ENV=production` | 调用链、延迟、成本、session 回放；env 打 tag 便于过滤 |
| **成本计价** | `models[*].pricing`（单一货币 + `input_cache_hit_per_million`） | 否则 `cost` 全 `null`，看不到花了多少钱 |
| **关掉 docs** | `GATEWAY_ENABLE_DOCS=false` | 生产不暴露 `/docs` `/openapi.json` |
| **断路器** | `circuit_breaker.failure_threshold` / `recovery_timeout_sec` | 防 LLM 错误雪崩 |

## 日常看什么

| 看 | 端点 | 信号 |
|----|------|------|
| 卡死检测 | `GET /api/console/stats` | `active_runs` 持续 > 0 = 可能卡住（配合 `GET /health` 浅健康检查） |
| 失败 run | `GET /api/console/runs?status=failed` | 拿 `run_id` 去查事件流 |
| 成本趋势 | `GET /api/console/usage?days=30` | 每日 + per-model 热点 |
| 调用链 | Langfuse/LangSmith UI | 延迟分布、token 成本、session 回放 |

## 排障路径（从哪个点都能定位同一次请求）

```
用户报错 / 失败 run
  ├─ 有 trace_id（X-Trace-Id / 日志）→ grep 日志 + Langfuse 按 deerflow_trace_id 过滤
  ├─ 有 run_id → GET /api/threads/{id}/runs/{rid}/events?event_types=run.error,llm.error
  ├─ subagent 问题 → 同端点 ?task_id= 翻 subagent.step，看 stop_reason（token/turn/loop_capped）
  └─ 要丢给上游/社区 → make support-bundle（脱敏）
```

## 已知缺口（诚实版）

DeerFlow 当前**没有**的，得你自己补或接受：

| 缺口 | 现状 |
|------|------|
| 聚合仪表盘 | 无 agent 级 dashboard；数据（RunJournal/tracing/SSE/Console）能支撑，只是无内建 UI |
| 内置告警 | 无；需 cron 打 Console + Langfuse threshold 告警 + 断路器兜底 |
| guardrail deny 审计 | 只走 `logger.warning()`，**不写 RunJournal**（`middleware:guardrail` 事件预留但未接入） |
| SandboxAudit 结构化 | 纯文本日志，非 JSON；接 SIEM/SOAR 需额外解析 |
| agent 级 SLO / error budget | 无；`LLMErrorHandlingMiddleware` 是 per-call retry + 断路器，无 agent 级熔断 |
| 实时成本预算告警 | 有 per-run token 统计，无预算上限 + 实时告警 |
| Agent 操作完整性验证 | 无；无法确认 agent 只做了它声称的操作 |

## 告警配方（自己补）

```bash
# 1. cron 打 Console：active_runs 持续 > 0 说明可能卡死
curl -s http://localhost:8001/api/console/stats | jq '.active_runs'

# 2. Langfuse 里配 cost / latency threshold 告警（无内置）

# 3. 断路器兜底（config.yaml）
circuit_breaker:
  failure_threshold: 5
  recovery_timeout_sec: 60
```

> 多实例部署的共识：`database.backend: postgres` + `run_events.backend: db` + `stream_bridge` redis（跨实例 SSE）+ sandbox ownership redis。这些都齐了才谈得上"上线级"的观测一致性。
