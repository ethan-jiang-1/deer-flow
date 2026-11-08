---
title: "IM Channels — 即时通讯平台集成"
description: "DeerFlow 通过 outbound WebSocket/polling 连接接入 9 个 IM 平台（含 QQ 与 Buzz/Nostr），另有 GitHub webhook 通道与 Lark CLI 托管集成。所有频道共享同一套有界消息总线与固定 worker pool，但在 stream 策略上分裂为两派：增量流式（Feishu/WeCom/Telegram/DingTalk Card/Buzz）和阻塞等待（Slack/Discord/WeChat/QQ）。"
type: index
---

# IM Channels — 即时通讯平台集成

DeerFlow 通过 outbound WebSocket/polling 连接接入 **9 个 IM 平台**（Feishu/Lark、DingTalk、Slack、Telegram、Discord、WeCom、WeChat、**QQ**、Buzz）。另有 **Lark CLI 托管集成**（harness 级 `integrations/lark_cli.py`，管理 27 个官方 `lark-*` 技能包，不是 app/channels 通道）；`app/channels/` 还含一个 webhook 驱动的 **GitHub** 通道（非聊天平台，见 [../github-integration.md](../github-integration.md)）。所有频道共享同一套消息总线架构，但在 stream 策略上分裂为两派：增量流式（Feishu/WeCom/Telegram/DingTalk Card/Buzz）和阻塞等待（Slack/Discord/WeChat/QQ）。

**回答的核心问题**：MessageBus 的**有界**入站准入与 reservation 怎么工作？ChannelManager 的固定 worker pool 怎么调度、怎么做到 run 幂等准入？9 个平台的 stream 策略为什么不同？Buzz（Nostr）怎么把身份验证和去重做到 relay 协议层？多实例部署怎么保证每个 provider 只有一条平台连接？怎么在 IM 会话里切换 custom agent？怎么加一个新平台？

> **约束：不修改项目源代码。** 本 `_digested/` 下所有内容仅作研究记录。详见 [根 README](../README.md)。

## 阅读顺序

| 文件 | 内容 |
|------|------|
| **00-overview.md** | 全景：9 平台架构图、有界 MessageBus、两种 stream 策略分裂、多实例 leader 租约、QQ、Buzz/Lark CLI 概览、v2.2.0 同步要点 |
| **01-message-bus.md** | MessageBus 有界入站准入/预留/去重占坑/暂存清理、worker pool 与停机顺序、幂等 run 准入、Config 层叠 |
| **02-stream-strategies.md** | 增量流式 vs 阻塞等待：能力表与主动推送门、Feishu AI Card patch + 澄清按钮卡片、Telegram 原地编辑、DingTalk streaming card、interaction_mode |
| **03-thread-mapping.md** | ChannelStore 协议（SQL/JSON）、跨实例绑定收敛、未解析≠未命中、命令系统、🆕 会话级 custom agent 选择（/agent）、回复语言 |
| **05-user-connections.md** 🆕 | 用户拥有的 IM 频道连接：bind code 生命周期、single-active-owner 转移、`DEER_FLOW_CREDENTIALS_KEY` 凭据加密、WeChat 扫码登录、9 平台差异、通知群 |
| **06-buzz.md** 🆕 | Buzz（Nostr）通道深挖：NIP-01/42、BIP-340 签名验证、订阅/去重/watermark、run policy |

## 关键问题

- 消息从 IM 平台到 Agent 再到回复的完整链路？→ `00-overview.md`
- MessageBus 怎么解耦平台接入和消息处理？满载时怎么办？→ `01-message-bus.md`
- 为什么 Feishu 用 stream 而 Slack 用 wait？→ `02-stream-strategies.md`
- 用户在不同平台上的对话怎么映射到 thread？多实例会不会各建一条？→ `03-thread-mapping.md`
- 用户怎么把自己的 IM 账号绑定到 DeerFlow？凭据存在哪、怎么加密？→ `05-user-connections.md`
- Buzz 在 Nostr relay 上怎么验证身份、去重、断线恢复？→ `06-buzz.md`

## 源文件索引

| 组件 | 路径 | 行数/大小 |
|------|------|-----------|
| Channel 基类 | `app/channels/base.py` | 605 行 |
| Channel 管理器 | `app/channels/manager.py` | 4162 行 |
| 消息总线 | `app/channels/message_bus.py` | 432 行 |
| 能力表 🆕 | `app/channels/capabilities.py` | 43 行 |
| leader 租约 🆕 | `app/channels/leadership.py` | 225 行 |
| 线程映射存储 | `app/channels/store.py` | 436 行（SQL + JSON 两实现） |
| 运行时配置存储 | `app/channels/runtime_config_store.py` | 531 行（SQL 密文 + 历史 JSON） |
| 命令系统 | `app/channels/commands.py` | 91 行 |
| run 策略 | `app/channels/run_policy.py` + `feishu_run_policy.py` + `buzz_run_policy.py` | 130 / 15 / 12 行 |
| 飞书 | `app/channels/feishu.py` | 2051 行 / 100KB |
| 飞书卡片交互 🆕 | `app/channels/feishu_card_interaction.py` | 283 行 |
| Slack | `app/channels/slack.py` | 786 行 / 34KB |
| Telegram | `app/channels/telegram.py` | 1310 行 / 58KB |
| 微信 | `app/channels/wechat.py` | 1929 行 / 82KB |
| 扫码登录 🆕 | `app/channels/wechat_qr_login.py` | 225 行 |
| 企业微信 | `app/channels/wecom.py` | 817 行 / 36KB |
| 钉钉 | `app/channels/dingtalk.py` | 1372 行 / 61KB |
| Discord | `app/channels/discord.py` | 1338 行 / 62KB |
| **QQ** 🆕 | `app/channels/qq.py` | 611 行 / 27KB |
| **Buzz（Nostr）** | `app/channels/buzz.py` + `buzz_nostr.py` + `buzz_run_policy.py` | 1749 / 201 / 12 行 |
| **入站去重存储** | `app/channels/dedupe_store.py` | 309 行（Memory/Postgres 两级） |
| 宿主自撰文案 🆕 | `app/channels/reply_locale.py` + `goal_status.py` + `notification_groups.py` | 107 / 125 / 87 行 |
| 入站附件工具 🆕 | `app/channels/inbound_files.py` + `sandbox_files.py` + `credential_staging.py` | 41 / 52 / 56 行 |
| allowlist 解析 🆕 | `app/channels/allowed_users.py` | 111 行 |
| **Lark CLI 托管集成** | `deerflow/integrations/lark_cli.py` + `lark_broker.py`（Pattern B sidecar） | 3709 / 554 行 |
| 频道服务启动 | `app/channels/service.py` | 1247 行 |

## 与 integration/ 的关系

`integration/04-im-channels.md` 覆盖了**配置层面**（怎么在 config.yaml 里配飞书/Slack/QQ），本 section 覆盖**内部设计**（MessageBus 怎么调度、stream 策略怎么分裂、thread 映射怎么持久化、租约与凭据怎么管）。两者互补。
