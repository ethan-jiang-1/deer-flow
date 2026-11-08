---
title: "Integration — 集成参考"
description: "把 DeerFlow 接进你的应用：4 种集成手段、HTTP API 与 SSE、Docker 部署、IM 频道配置、Lark CLI 托管。"
type: index
topics: [integration, api, docker, channels]
---

# Integration — 集成参考

> **定位**：面向接入方的操作手册——先选手段（API / Docker / IM / 托管集成），再按页配置。涵盖 `app/gateway/routers/`（HTTP 面）、`app/channels/`（IM 通道）、`packages/harness/deerflow/integrations/`（托管集成）与 `docker/`（部署栈），基线 v2.2.0。
> **边界**：通道与网关的内部设计见 [../channels/](../channels/README.md) 与 [../app-layer/](../app-layer/README.md)；生产加固见 [../security/](../security/README.md)。

## 阅读路径

1. **先看**：[01-overview.md](01-overview.md) — 4 种集成手段对比、决策树与最小示例。
2. **再看**：[02-api-reference.md](02-api-reference.md) — HTTP 端点详解与 SSE 流式协议。
3. **深入**：[05-lark-cli-managed-integration.md](05-lark-cli-managed-integration.md) — 安装事务、每用户凭据切换、`sandbox_runtime_mode` 四态与 broker 边界。

## 本篇目

| 文件 | 主题 | 深度 |
|---|---|---|
| [01-overview.md](01-overview.md) | 4 种集成手段与选型 | 概览 |
| [02-api-reference.md](02-api-reference.md) | HTTP API 端点与 SSE 协议 | 深入 |
| [03-docker.md](03-docker.md) | Docker 生产部署：5 个服务与网络 | 深入 |
| [04-im-channels.md](04-im-channels.md) | 9 个 IM 平台 + GitHub webhook 的配置项 | 概览 |
| [05-lark-cli-managed-integration.md](05-lark-cli-managed-integration.md) | Lark CLI 托管：安装事务、凭据、Pattern A/B | 深入 |

## 宪章与约定

- 本目录无独立宪章；写作纪律沿用 [根 README](../../README.md)。
- 版本基线 v2.2.0。

## 相关目录

- [Enterprise Operations 总览](../README.md) — 部署、安全、追踪与通道全景。
- [部署架构](../deployment/README.md) — 4 种部署模式的选型与差异。
- [IM Channels](../channels/README.md) — 总线、stream 策略与 thread 映射的内部设计。
- [App Layer](../app-layer/README.md) — Gateway 端点与上传安全的实现面。
- [根 README](../../README.md) — 全库阅读地图与 README 约定。
