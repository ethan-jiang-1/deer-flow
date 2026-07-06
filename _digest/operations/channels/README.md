---
title: "IM Channels — 即时通讯平台集成"
description: "DeerFlow 通过 outbound WebSocket/polling 连接接入 7 个 IM 平台。所有频道共享同一套消息总线架构，但在 stream 策略上分裂为两派：增量流式（Feishu/DingTalk）和阻塞等待（Slac"
type: index
---

# IM Channels — 即时通讯平台集成

DeerFlow 通过 outbound WebSocket/polling 连接接入 7 个 IM 平台。所有频道共享同一套消息总线架构，但在 stream 策略上分裂为两派：增量流式（Feishu/DingTalk）和阻塞等待（Slack/Telegram）。

**回答的核心问题**：MessageBus 的 pub/sub 怎么工作？ChannelManager 的 dispatch loop 怎么调度？7 个平台的 stream 策略为什么不同？怎么加一个新平台？

> **约束：不修改项目源代码。** 本 `_digest/` 下所有内容仅作研究记录。详见 [根 README](../README.md)。

## 阅读顺序

| 文件 | 内容 |
|------|------|
| **00-overview.md** | 全景：7 平台架构图、MessageBus 模式、两种 stream 策略分裂 |
| **01-message-bus.md** | MessageBus pub/sub 机制、ChannelManager._dispatch_loop() 核心调度 |
| **02-stream-strategies.md** | 增量流式 vs 阻塞等待：Feishu AI Card patch、DingTalk streaming card、Slack/Telegram wait 模式 |
| **03-thread-mapping.md** | Channel → Thread ID 映射持久化、多平台 session 覆盖、命令系统 |
| **04-platform-deep-dive.md** | 逐平台深入：Feishu (33KB)、WeChat (53KB)、DingTalk (31KB)、Discord (25KB) 的特殊处理 |

## 关键问题

- 消息从 IM 平台到 Agent 再到回复的完整链路？→ `00-overview.md`
- MessageBus 怎么解耦平台接入和消息处理？→ `01-message-bus.md`
- 为什么 Feishu 用 stream 而 Slack 用 wait？→ `02-stream-strategies.md`
- 用户在不同平台上的对话怎么映射到 thread？→ `03-thread-mapping.md`
- WeChat 的 QR 码登录和文件收发怎么处理？→ `04-platform-deep-dive.md`

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
| 频道服务启动 | `app/channels/service.py` |

## 与 integration/ 的关系

`integration/07-im-channels.md` 覆盖了**配置层面**（怎么在 config.yaml 里配飞书/Slack），本 section 覆盖**内部设计**（MessageBus 怎么调度、stream 策略怎么分裂、thread 映射怎么持久化）。两者互补。
