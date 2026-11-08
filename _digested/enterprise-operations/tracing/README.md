---
title: "Tracing — 追踪系统"
description: "LangSmith + Langfuse 双 provider 的配置面，以及 loop detection / tool promotion 的运维侧审计细节；trace id 与注入机制以 observability 为 canonical。"
type: index
topics: [tracing, langsmith, langfuse, trace-id]
---

# Tracing — 追踪系统

> **定位**：运维侧的 tracing 配置与审计补充——双 provider 怎么配、loop detection / tool promotion 的审计事件怎么落库。给接 tracing 后端和查线上问题的工程师看。
> **边界**：trace id 的生成/下发/入口点绑定以 [observability/01](../../observability/01-logging-and-trace-context.md) 为 canonical；图根/模型级注入与 provider 机制以 [observability/03](../../observability/03-tracing-providers.md) 为 canonical；事件目录/信封见 [observability/02](../../observability/02-run-events-and-journal.md)。本目录不重写这些机制。日志、Console 全貌见 [observability/](../../observability/README.md)；成本归因见 [enterprise-it-governance/cost/](../../enterprise-it-governance/cost/README.md)。

## 阅读路径

1. **先看**：[langsmith-langfuse-dual-provider.md](langsmith-langfuse-dual-provider.md) — 双 provider 配置、工厂模式与 Langfuse v4 合约；注入机制链到 observability/03。
2. **深入**：[trace-ids-and-audit-events.md](trace-ids-and-audit-events.md) — loop detection / tool promotion 审计；trace id 机制链到 observability/01。

## 本篇目

| 文件 | 主题 | 深度 |
|---|---|---|
| [langsmith-langfuse-dual-provider.md](langsmith-langfuse-dual-provider.md) | LangSmith / Langfuse 双 provider 与元数据注入 | 概览 |
| [trace-ids-and-audit-events.md](trace-ids-and-audit-events.md) | 请求级 trace id 与中间件审计事件 | 深入 |

### 两篇怎么分工

- 前者管**去哪**：provider 配置、工厂与环境变量；图根/模型两级附着和 `inject_langfuse_metadata()` 的 canonical 在 [observability/03](../../observability/03-tracing-providers.md)。
- 后者管**审计补充**：loop detection / tool promotion 只记元数据，失败不打断 run；trace id 的 canonical 在 [observability/01](../../observability/01-logging-and-trace-context.md)。

## 宪章与约定

- 本目录无独立宪章；写作纪律沿用 [根 README](../../README.md)。
- 机制与结论以 `file:line` 为据，版本基线以各页标注为准（当前 v2.2.0）。

## 相关目录

- [Enterprise Operations 总览](../README.md) — 部署、安全、通道与 API 全景。
- [observability/](../../observability/README.md) — 日志关联、RunEvent 事件流与 Console 调试。
- [security/](../security/README.md) — 审计与防线的实施视角。
- [根 README](../../README.md) — 全库阅读地图与 README 约定。
