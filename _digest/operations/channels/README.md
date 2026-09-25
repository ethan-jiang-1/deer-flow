---
title: "IM Channels — 即时通讯平台集成"
description: "DeerFlow 通过 outbound WebSocket/polling 连接接入 8 个 IM 平台（含 Buzz/Nostr），另有 GitHub webhook 通道与 Lark CLI 托管集成。所有频道共享同一套消息总线架构，但在 stream 策略上分裂为两派：增量流式（Feishu/WeCom/Telegram/DingTalk Card/Buzz）和阻塞等待（Slack/Discord/WeChat）。"
type: index
---

# IM Channels — 即时通讯平台集成

DeerFlow 通过 outbound WebSocket/polling 连接接入 8 个 IM 平台（Feishu/Lark、DingTalk、Slack、Telegram、Discord、WeCom、WeChat、**Buzz**）。另有 **Lark CLI 托管集成**（harness 级 `integrations/lark_cli.py`，管理 27 个官方 `lark-*` 技能包，不是 app/channels 通道）；`app/channels/` 还含一个 webhook 驱动的 **GitHub** 通道（非聊天平台，见 [../github-integration.md](../github-integration.md)）。所有频道共享同一套消息总线架构，但在 stream 策略上分裂为两派：增量流式（Feishu/WeCom/Telegram/DingTalk Card/Buzz）和阻塞等待（Slack/Discord/WeChat）。

**回答的核心问题**：MessageBus 的 pub/sub 怎么工作？ChannelManager 的 dispatch loop 怎么调度？8 个平台的 stream 策略为什么不同？Buzz（Nostr）怎么把身份验证和去重做到 relay 协议层？怎么在 IM 会话里切换 custom agent？怎么加一个新平台？

> **约束：不修改项目源代码。** 本 `_digest/` 下所有内容仅作研究记录。详见 [根 README](../README.md)。

## 阅读顺序

| 文件 | 内容 |
|------|------|
| **00-overview.md** | 全景：8 平台架构图、MessageBus 模式、两种 stream 策略分裂、Buzz/Lark CLI 概览 |
| **01-message-bus.md** | MessageBus pub/sub 机制、ChannelManager._dispatch_loop() 核心调度 |
| **02-stream-strategies.md** | 增量流式 vs 阻塞等待：Feishu AI Card patch、Telegram 原地编辑、DingTalk streaming card、Slack/WeChat wait 模式 |
| **03-thread-mapping.md** | Channel → Thread ID 映射持久化、多平台 session 覆盖、命令系统、🆕 会话级 custom agent 选择（/agent） |
| **05-user-connections.md** 🆕 | 用户拥有的 IM 频道连接：bind code 生命周期、single-active-owner 转移、8 平台差异 |
| **06-buzz.md** 🆕 | Buzz（Nostr）通道深挖：NIP-01/42、BIP-340 签名验证、订阅/去重/watermark、run policy |

## 关键问题

- 消息从 IM 平台到 Agent 再到回复的完整链路？→ `00-overview.md`
- MessageBus 怎么解耦平台接入和消息处理？→ `01-message-bus.md`
- 为什么 Feishu 用 stream 而 Slack 用 wait？→ `02-stream-strategies.md`
- 用户在不同平台上的对话怎么映射到 thread？→ `03-thread-mapping.md`
- 用户怎么把自己的 IM 账号绑定到 DeerFlow？→ `05-user-connections.md`
- Buzz 在 Nostr relay 上怎么验证身份、去重、断线恢复？→ `06-buzz.md`

## 源文件索引

| 组件 | 路径 |
|------|------|
| Channel 基类 | `app/channels/base.py` |
| Channel 管理器 | `app/channels/manager.py` (~40KB) |
| 消息总线 | `app/channels/message_bus.py` |
| 线程映射存储 | `app/channels/store.py` |
| 命令系统 | `app/channels/commands.py` |
| 飞书 | `app/channels/feishu.py` (~33KB) |
| Slack | `app/channels/slack.py` |
| Telegram | `app/channels/telegram.py` |
| 微信 | `app/channels/wechat.py` (~53KB) |
| 企业微信 | `app/channels/wecom.py` |
| 钉钉 | `app/channels/dingtalk.py` (~31KB) |
| Discord | `app/channels/discord.py` (~25KB) |
| **Buzz（Nostr）** 🆕 | `app/channels/buzz.py` (~55KB) + `buzz_nostr.py` + `buzz_run_policy.py` |
| **入站去重存储** 🆕 | `app/channels/dedupe_store.py`（Memory/Postgres 两级） |
| **Lark CLI 托管集成** 🆕 | `deerflow/integrations/lark_cli.py` + `lark_broker.py`（Pattern B sidecar） |
| 频道服务启动 | `app/channels/service.py` |

## 与 integration/ 的关系

`integration/04-im-channels.md` 覆盖了**配置层面**（怎么在 config.yaml 里配飞书/Slack），本 section 覆盖**内部设计**（MessageBus 怎么调度、stream 策略怎么分裂、thread 映射怎么持久化）。两者互补。
