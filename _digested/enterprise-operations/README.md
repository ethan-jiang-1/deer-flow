---
title: "Enterprise Operations — 部署、安全、运维"
description: "把 DeerFlow 跑起来之后的事：安全、部署、追踪、IM 通道、应用层与集成参考。"
type: index
topics: [operations, deployment, security, observability]
---

# Enterprise Operations — 部署、安全、运维

> **定位**：平台 / SRE / 运维的实施卷——怎么装、怎么配、怎么盯。回答「跑起来要过哪些关」，而不是「该不该批准」。
> **边界**：治理判断、控制点与缺口见 [enterprise-it-governance/](../enterprise-it-governance/README.md)；首次上手步骤见 [getting-started/](../getting-started/README.md)。

## 阅读路径

1. **先看**：[security/00-overview.md](security/00-overview.md) — 8 道关口、认证凭据路径与已知缺陷；要评估企业就绪度直接跳 [security/07-enterprise-readiness.md](security/07-enterprise-readiness.md)。
2. **再看**：[deployment/00-overview.md](deployment/00-overview.md) — 4 种部署模式对比与选型决策树。
3. **深入**：[app-layer/01-api-reference.md](app-layer/01-api-reference.md) — 221 条 Gateway 端点穷举与「领域异常 → HTTP」映射。

## 本篇目

| 文件 | 主题 | 深度 |
|---|---|---|
| [scheduler.md](scheduler.md) | 定时任务：cron/一次性、lease 锁、执行生命周期、调试 | 深入 |
| [github-integration.md](github-integration.md) | GitHub App webhook、per-agent binding、安装 token、gh CLI | 深入 |
| [backup-and-monitoring.md](backup-and-monitoring.md) | 备份恢复与监控：数据清单、Console API、LangFuse | 概览 |

### 六个子卷

| 目录 | 主题 |
|---|---|
| [security/](security/README.md) | 纵深防御、认证、沙箱隔离、Guardrail、扩展边界、企业级 Agent 安全基准 |
| [deployment/](deployment/README.md) | 4 种部署模式、Docker Compose、Nginx、K3s Provisioner |
| [tracing/](tracing/README.md) | LangSmith + Langfuse 双 provider、请求级 trace id |
| [channels/](channels/README.md) | 9 个 IM 平台、有界消息总线、两种 stream 策略 |
| [app-layer/](app-layer/README.md) | Gateway 架构、REST 端点、上传安全、agent 包 |
| [integration/](integration/README.md) | 4 种集成手段、API/Docker/IM 配置参考、Lark CLI 托管 |

## 宪章与约定

- 本目录无独立宪章；写作纪律沿用 [根 README](../README.md)。

## 相关目录

- [根 README](../README.md) — 全库阅读地图与「README 约定（每个子目录）」。
- [enterprise-it-governance/](../enterprise-it-governance/README.md) — 同一主题的判断面：能不能被 IT 管起来。
- [observability/](../observability/README.md) — 日志、事件流、Console 与上线清单。
