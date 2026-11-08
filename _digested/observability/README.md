---
title: "Observability — 诊断与观察"
description: "Agent 上线之后怎么观察它、怎么诊断问题。DeerFlow 自带的日志/事件/追踪/控制台基建 + 生产上线实操。"
type: index
---

# Observability — 诊断与观察

Agent 上线之后，最难的不是"能不能跑"，而是"跑出问题时你怎么知道发生了什么"。这里分两层：**DeerFlow 自己带了哪些观测/诊断基建**（参考），以及**生产上线时怎么把它们用起来**（实操）。

> 与 [testing/](../testing/) 互补：testing 管"上线前怎么测"，本目录管"上线后怎么观察、怎么诊断"。

## DeerFlow 自带的观测基建

| 文件 | 内容 |
|------|------|
| `00-overview.md` | 五层观测栈：日志 → 事件流 → 追踪 → 控制台 → 实时流，一次 run 的完整数据流 |
| `01-logging-and-trace-context.md` | 🔑 日志体系 + `trace_id` 请求关联（`logging.enhance`、JSON 结构化、`X-Trace-Id`） |
| `02-run-events-and-journal.md` | 结构化事件流：`RunEventStore` 事件目录 + `RunJournal`（回调 → 事件的汇聚点） |
| `03-tracing-providers.md` | LangSmith / Langfuse / Monocle 三 provider 综述 |
| `04-console-and-cost.md` | 🔑 Console API 全端点参考 + token/成本归属 |
| `05-live-streaming.md` | 实时观测：SSE 事件流、StreamBridge、心跳/重连 |

## 生产上线实操

| 文件 | 内容 |
|------|------|
| `06-debugging-toolkit.md` | 诊断手段：错误分类/重试/断路器、loop 检测、tool 错误元数据、checkpoint 回滚、support bundle |
| `07-production-checklist.md` | 🔑 要上线清单：开什么、看什么、缺什么、怎么告警 |
| `08-direct-usage.md` | 🔑 直接利用：日志到底落哪（stderr 不是 Workspace）、copy-paste 配置、分场景命令、排障决策树 |
| `09-observability-for-your-app.md` | 🔑 写 DeerFlow 应用的可观测最佳实践：三条铁律 + 把自定义 middleware/tool/LLM 挂到同一条观测轨道上 |

## 补充（深潜指向已有笔记）

- 追踪深潜（LangSmith/Langfuse 双 provider 细节）→ [operations/tracing/](../operations/tracing/)
- RunJournal 深潜（回调 → 缓冲 → 刷盘 → token 分桶）→ [internals/runtime/04-journal.md](../internals/runtime/04-journal.md)
- 错误处理 / loop 检测 / 断路器深潜 → [internals/agent-loop/04-error-handling-and-debugging.md](../internals/agent-loop/04-error-handling-and-debugging.md)
- 审计/可观测的 IT 治理视角 + 缺口清单 → [operations/it-ops/04-audit-observability.md](../operations/it-ops/04-audit-observability.md)
- 备份恢复 + 监控脚本 → [operations/backup-and-monitoring.md](../operations/backup-and-monitoring.md)
