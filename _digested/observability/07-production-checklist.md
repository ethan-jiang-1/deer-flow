---
title: "生产上线清单"
description: "要上线前：开什么（SQL 后端、trace 关联、追踪、定价）、日常看什么、排障走哪条路、已知缺口是什么、怎么自己补告警。诚实版——DeerFlow 给原料，不给聚合仪表盘。"
topics: [production, observability, checklist, alerting]
---

# 生产上线清单

DeerFlow 给的是观测**原料**，不是现成的聚合仪表盘和告警。这份清单是"上线前把原料接上、上线后知道去哪看"的最小集。安全硬化另见 [enterprise-operations/security/](../enterprise-operations/security/)。

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
| 🆕 **多实例 SSE** | `stream_bridge.type: redis` + `legacy_end_scan_enabled: true`（默认） | 跨实例 SSE；升级网关时先保持 `true`，等旧 writer 全停、旧 buffer 全过期再关（见 `05`） |
| 🆕 **孤儿流恢复** | `stream_bridge.producer_lease_recovery_enabled: true`（默认 `false`） | 让终态 run 能从**过期的 producer lease** 恢复缺失的 `end`。**只**在所有 Gateway writer 都升到 v2.2.0、且升级前的 run 已排空后才开 |

## 日常看什么

| 看 | 端点 | 信号 |
|----|------|------|
| 卡死检测 | `GET /api/console/stats` | `active_runs` 持续 > 0 = 可能卡住（配合 `GET /health` 浅健康检查） |
| 失败 run | `GET /api/console/runs?status=failed` | 拿 `run_id` 去查事件流 |
| 成本趋势 | `GET /api/console/usage?days=30` | 每日 + per-model 热点；🆕 `cost: null` 要分清「没定价」vs「某次调用缺 usage」 |
| 🆕 终态证据 | `GET /api/threads/{id}/runs/{rid}/events?event_types=run.terminal` | 该 run 的业务结局。**缺失** = 证据不全（可能是终态提交后、事件确认前崩溃）；`metadata.recovered=true` = takeover 恢复补写的 |
| 调用链 | Langfuse/LangSmith UI | 延迟分布、token 成本、session 回放 |

## 排障路径（从哪个点都能定位同一次请求）

```
用户报错 / 失败 run
  ├─ 有 trace_id（X-Trace-Id / 日志）→ grep 日志 + Langfuse 按 deerflow_trace_id 过滤
  ├─ 有 run_id → GET /api/threads/{id}/runs/{rid}/events?event_types=run.error,llm.error
  ├─ run 到底成没成 → 同端点 ?event_types=run.terminal（🆕 v2.2.0；别拿 run.end 当终态）
  ├─ subagent 问题 → 同端点 ?task_id= 翻 subagent.step，看 stop_reason（token/turn/loop_capped）
  ├─ SSE 订阅者卡住等不到 end → 看 stream_bridge.producer_lease_state（expired + run 已终态 = 没人会写 end）
  └─ 要丢给上游/社区 → make support-bundle（脱敏）
```

## 已知缺口（诚实版）

DeerFlow 当前**没有**的，得你自己补或接受：

| 缺口 | 现状 |
|------|------|
| 聚合仪表盘 | 无 agent 级 dashboard；数据（RunJournal/tracing/SSE/Console）能支撑，只是无内建 UI |
| 内置告警 | 无；需 cron 打 Console + Langfuse threshold 告警 + 断路器兜底 |
| guardrail deny 审计 | ~~只走 `logger.warning()`，不写 RunJournal~~ —— **v2.2.0 实测这条是错的**：`middleware:guardrail` 已接入（`guardrails/middleware.py:170-177` 调 `journal.record_middleware(tag=MIDDLEWARE_GUARDRAIL_TAG, hook="wrap_tool_call", ...)`，`changes` 带 `allow` / `policy_id` / `reason_codes` / `reason_messages` / `fail_closed` / `provider_error`）。注意它**只覆盖 `wrap_tool_call`**，模型输入侧的 guardrail 决策不在事件流里 |
| SandboxAudit 结构化 | 纯文本日志，非 JSON；接 SIEM/SOAR 需额外解析 |
| agent 级 SLO / error budget | 无；`LLMErrorHandlingMiddleware` 是 per-call retry + 断路器，无 agent 级熔断 |
| 实时成本预算告警 | 有 per-run token 统计，无预算上限 + 实时告警 |
| Agent 操作完整性验证 | 部分改善但**未闭合**：🆕 v2.2.0 有 `run.terminal` + Evidence Receipt/Seal（`RunRow.evidence_seal_state`）+ `content_sha256` 逐条摘要素，能校验「事件没被改、范围有界」；但**不**能证明 agent 只做了它声称的操作 |
| 🆕 终态事件的原子性 | `run.terminal` 单例插入与 `RunRow` 终态提交是**两个事务**；两者之间崩溃且无 takeover claim → 有终态行、没有 `run.terminal`。上游明确写"需要 durable outbox / 对账才能闭合，不在本次范围" |
| 🆕 事件删除即证据失效 | 删 thread/run 事件会让该 run 的 `evidence_seal_state` 变 `partial`、`evidence_retention_revision` +1、并删 `CompletedRunSnapshotRow`——所以"删了就能赖掉审计"只在证据层做实，**事件行本身真的没了** |

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

> 多实例部署的共识：`database.backend: postgres` + `run_events.backend: db`（否则 seq 跨进程无保证、也拿不到 `evidence_receipt`）+ `stream_bridge` redis（跨实例 SSE；🆕 v2.2.0 还要决定 `producer_lease_recovery_enabled`）+ sandbox ownership redis。这些都齐了才谈得上「上线级」的观测一致性。短期跨实例过不了的话，**至少**接受：seq 只在单进程内单调、终态证据不完整、成本可能因缺 usage 变 `null`。
