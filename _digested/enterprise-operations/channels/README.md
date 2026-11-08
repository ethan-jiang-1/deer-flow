---
title: "IM Channels — 即时通讯平台集成"
description: "9 个 IM 平台 + GitHub webhook + Lark CLI 托管集成：共享有界 MessageBus 与固定 worker pool，stream 策略分裂为两派。"
type: index
topics: [channels, im, message-bus, streaming]
---

# IM Channels — 即时通讯平台集成

> **定位**：IM 通道的内部设计——消息怎么进出、worker pool 怎么调度、thread 怎么映射、凭据与租约怎么管。覆盖 9 个 IM 平台（Feishu/Lark、DingTalk、Slack、Telegram、Discord、WeCom、WeChat、QQ、Buzz/Nostr），另有 GitHub webhook 与 Lark CLI 托管集成。给通道接入与线上排障的工程师看。
> **边界**：只讲内部机制；config.yaml 里怎么填见 [integration/04-im-channels.md](../integration/04-im-channels.md)，凭据加密与用户归属的治理判断见 [identity/](../../enterprise-it-governance/identity/README.md)。

## 阅读路径

1. **先看**：[00-overview.md](00-overview.md) — 9 平台架构图、有界 MessageBus、两种 stream 策略、多实例 leader 租约。
2. **再看**：[01-message-bus.md](01-message-bus.md) — 有界入站准入、预留/去重占坑、固定 worker pool 与停机顺序。
3. **深入**：[02-stream-strategies.md](02-stream-strategies.md) — 增量流式 vs 阻塞等待，以及 Feishu 卡片、Telegram 原地编辑等实现差异。

## 本篇目

| 文件 | 主题 | 深度 |
|---|---|---|
| [00-overview.md](00-overview.md) | 9 平台架构、总线、策略分裂与多实例租约 | 概览 |
| [01-message-bus.md](01-message-bus.md) | MessageBus 有界准入、worker pool、幂等 run 准入 | 深入 |
| [02-stream-strategies.md](02-stream-strategies.md) | 增量流式 vs 阻塞等待与各平台卡片实现 | 深入 |
| [03-thread-mapping.md](03-thread-mapping.md) | ChannelStore、跨实例绑定收敛、命令系统与 `/agent` | 深入 |
| [05-user-connections.md](05-user-connections.md) | 用户 IM 连接：bind code、owner 转移、凭据加密 | 深入 |
| [06-buzz.md](06-buzz.md) | Buzz（Nostr）：NIP-01/42、BIP-340、去重与 watermark | 深入 |

## 宪章与约定

- 本目录无独立宪章；写作纪律沿用 [根 README](../../README.md)。
- 机制与结论以 `file:line` 为据，版本基线以各页标注为准（当前 v2.2.0）。

## 相关目录

- [Enterprise Operations 总览](../README.md) — 部署、安全、追踪与 API 全景。
- [Integration](../integration/README.md) — IM 通道的配置层面（与本域互补）。
- [App Layer](../app-layer/README.md) — Gateway 如何承载通道的 run 与 SSE。
- [根 README](../../README.md) — 全库阅读地图与 README 约定。
