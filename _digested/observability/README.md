---
title: "Observability — 诊断与观察"
description: "Agent 上线后的观察与诊断：日志/trace、事件流、追踪、控制台、实时流，以及生产上线实操。"
type: index
topics: [observability, logging, tracing, debugging]
---

# Observability — 诊断与观察

> **定位**：Agent 上线后最难的不是「能不能跑」，而是「出问题时你怎么知道发生了什么」。这里分两层：DeerFlow 自带的五层观测栈（日志 → 事件流 → 追踪 → 控制台 → 实时流），以及生产上线时怎么把它们用起来。
> **边界**：不覆盖「上线前怎么测」（见 [testing](../testing/README.md)），不覆盖 IT 治理视角的审计与合规（见 [enterprise-it-governance/audit](../enterprise-it-governance/audit/README.md)），也不重复运行时实现细节（见 [internals/runtime](../internals/runtime/README.md)）。

## 阅读路径

1. **先看**：[00-overview.md](00-overview.md) — 五层观测栈与一次 run 从请求到 trace 的完整数据流。
2. **再看**：[02-run-events-and-journal.md](02-run-events-and-journal.md) — `RunEventStore` + `RunJournal`：审计、回放、调试端点的共同数据源。
3. **深入**：[07-production-checklist.md](07-production-checklist.md) — 开什么、看什么、缺什么、怎么自己补告警。

## 本篇目

| 文件 | 主题 | 深度 |
|---|---|---|
| [00-overview.md](00-overview.md) | 五层观测栈与一次 run 的数据流 | 概览 |
| [01-logging-and-trace-context.md](01-logging-and-trace-context.md) | 日志体系 + `trace_id` 请求关联（`logging.enhance`、JSON、`X-Trace-Id`、URL 脱敏） | 深入 |
| [02-run-events-and-journal.md](02-run-events-and-journal.md) | 结构化事件流：事件目录、证据封印链、`run.terminal`、seq 水位、逐调用遥测 | 深入 |
| [03-tracing-providers.md](03-tracing-providers.md) | LangSmith / Langfuse / Monocle 三 provider 的挂载方式与开关 | 概览 |
| [04-console-and-cost.md](04-console-and-cost.md) | Console API 端点 + token 归属与 cache-aware 计价 | 深入 |
| [05-live-streaming.md](05-live-streaming.md) | StreamBridge / SSE：心跳、续传、memory vs redis、producer lease | 深入 |
| [06-debugging-toolkit.md](06-debugging-toolkit.md) | 错误分类/重试/断路器、loop 检测、tool 错误元数据、checkpoint 回滚、support bundle | 概览 |
| [07-production-checklist.md](07-production-checklist.md) | 要上线清单：开什么、看什么、缺什么、怎么告警 | 概览 |
| [08-direct-usage.md](08-direct-usage.md) | 直接上手：日志落点（stderr）、copy-paste 配置、分场景命令、排障决策树 | 概览 |
| [09-observability-for-your-app.md](09-observability-for-your-app.md) | 把自定义 middleware / tool / LLM 挂到同一条观测轨道上的最佳实践 | 概览 |

## 速览

- **已对齐 v2.2.0**（`git diff v2.1.0 v2.2.0` 逐文件核对）：`run.terminal` 权威终态 + Evidence Receipt/Seal、redis producer lease + 统一 SSE 响应头、URL 日志脱敏与 Langfuse `model:` tag 改用有效模型名、Console `cost: null` 新增「显式缺 usage」成因；**算法、provider 装配、SSE 帧格式零变化**。
- **全部是组件级**：没有聚合仪表盘。观测原料齐备，聚合与告警要自己补（07 给了诚实缺口清单）。
- **必读四篇**：01（trace 关联）、02（事件流）、04（成本）、07（上线清单）；只想要命令的直接看 08。

## 宪章与约定

- 本目录无独立宪章；研究纪律沿用 [根 README](../README.md)（不修改源码、`main` 只镜像上游、笔记只落在 `ethan`）。
- 同步口径：观测域每次按 tag 逐文件 diff 核对，只在确有变化处升版，不重写稳定章节。

## 相关目录

- [testing/](../testing/README.md) — 上线前的测试体系，与本目录互补。
- [enterprise-operations/tracing/](../enterprise-operations/tracing/README.md) — LangSmith / Langfuse 双 provider 的深潜。
- [internals/runtime/](../internals/runtime/README.md) — RunManager、StreamBridge、RunJournal 的实现。
- [enterprise-it-governance/audit/](../enterprise-it-governance/audit/README.md) — 审计与追责的治理视角。
- [enterprise-operations/backup-and-monitoring.md](../enterprise-operations/backup-and-monitoring.md) — 备份恢复与监控脚本（正文页）。
