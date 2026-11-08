---
title: "Tracing — 追踪系统"
description: "LangSmith + Langfuse 双 provider、两层附着策略，以及请求级 `X-Trace-Id` 与中间件审计事件。"
type: index
topics: [tracing, langsmith, langfuse, trace-id]
---

# Tracing — 追踪系统

> **定位**：排障与可观测视角的追踪说明——trace 挂在哪一层、双 provider 怎么选、请求 id 从哪来，以及审计事件如何随 run 落库。给接 tracing 后端和查线上问题的工程师看。
> **边界**：日志、事件流与 Console 的全貌见 [observability/](../../observability/README.md)；成本归因见 [enterprise-it-governance/cost/](../../enterprise-it-governance/cost/README.md)。

## 阅读路径

1. **先看**：[langsmith-langfuse-dual-provider.md](langsmith-langfuse-dual-provider.md) — 两层附着策略、双 provider、工厂模式与 Langfuse v4 合约。
2. **深入**：[trace-ids-and-audit-events.md](trace-ids-and-audit-events.md) — `X-Trace-Id` 无条件签发、非 HTTP 入口绑定、审计事件持久化。

## 本篇目

| 文件 | 主题 | 深度 |
|---|---|---|
| [langsmith-langfuse-dual-provider.md](langsmith-langfuse-dual-provider.md) | LangSmith / Langfuse 双 provider 与元数据注入 | 概览 |
| [trace-ids-and-audit-events.md](trace-ids-and-audit-events.md) | 请求级 trace id 与中间件审计事件 | 深入 |

### 两篇怎么分工

- 前者管**去哪**：provider 工厂、图根/模型两级附着、`inject_langfuse_metadata()` 双路径共享。
- 后者管**凭什么串起来**：trace id 无条件签发且 ContextVar 是唯一源；loop detection / tool promotion 只记元数据，失败不打断 run。

## 宪章与约定

- 本目录无独立宪章；写作纪律沿用 [根 README](../../README.md)。
- 机制与结论以 `file:line` 为据，版本基线以各页标注为准（当前 v2.2.0）。

## 相关目录

- [Enterprise Operations 总览](../README.md) — 部署、安全、通道与 API 全景。
- [observability/](../../observability/README.md) — 日志关联、RunEvent 事件流与 Console 调试。
- [security/](../security/README.md) — 审计与防线的实施视角。
- [根 README](../../README.md) — 全库阅读地图与 README 约定。
