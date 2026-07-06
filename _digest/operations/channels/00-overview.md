---
title: "IM 通道系统全景"
description: "DeerFlow 通过 7 个 IM 平台通道（Feishu/Lark、DingTalk、Slack、Telegram、Discord、WeCom、WeChat）让用户通过聊天消息与 Agent 交互。"
topics: [channels, im, messaging]
---

# IM 通道系统全景

DeerFlow 通过 7 个 IM 平台通道（Feishu/Lark、DingTalk、Slack、Telegram、Discord、WeCom、WeChat）让用户通过聊天消息与 Agent 交互。

## 架构全景

```
┌─────────────────────────────────────────────────────────┐
│ External Platforms (Feishu / Slack / Telegram / ...)     │
│   WebSocket / Long-polling / Webhook                     │
├─────────────────────────────────────────────────────────┤
│ Channel Implementations (app/channels/)                  │
│   ├─ feishu.py   → lark-oapi WebSocket                  │
│   ├─ slack.py    → slack-sdk Socket Mode                │
│   ├─ telegram.py → python-telegram-bot long-polling     │
│   ├─ dingtalk.py → Gateway WebSocket + OAuth2           │
│   ├─ discord.py  → discord.py Gateway WebSocket         │
│   ├─ wecom.py    → aibot WebSocket                      │
│   └─ wechat.py   → iLink long-polling                   │
├─────────────────────────────────────────────────────────┤
│ MessageBus (message_bus.py)                              │
│   ├─ Inbound: single asyncio.Queue[InboundMessage]      │
│   └─ Outbound: async callback registry                  │
├─────────────────────────────────────────────────────────┤
│ ChannelManager (manager.py — 1024 行)                   │
│   ├─ _dispatch_loop() — semaphore(5) 并发控制           │
│   ├─ _handle_chat() — 核心路由                          │
│   └─ _resolve_run_params() — 4 层 config merge         │
├─────────────────────────────────────────────────────────┤
│ ChannelStore (store.py)                                  │
│   └─ JSON file: channel+chat_id → thread_id 映射        │
├─────────────────────────────────────────────────────────┤
│ ChannelService (service.py)                              │
│   └─ 生命周期管理，启动/停止所有 channel                 │
└─────────────────────────────────────────────────────────┘
```

## 两种流式策略

DeerFlow 的 IM 通道使用两种完全不同的 Agent 响应策略：

| 策略 | 通道 | 行为 |
|------|------|------|
| **增量流式** (supports_streaming=true) | Feishu, WeCom, DingTalk (Card mode) | `client.runs.stream()` → 逐 chunk 更新消息卡片 → `is_final=True` 时完成 |
| **阻塞等待** (supports_streaming=false) | Slack, Telegram, Discord, WeChat, DingTalk (non-Card) | `client.runs.wait()` → 等 Agent 完成 → 一次性发送完整响应 |

两种策略的根本区别：增量流式在 Agent 执行期间持续更新消息（用户看到 "实时思考"），阻塞等待在所有 tool call 完成后才发送第一条响应（用户只看最终结果）。

## 连接方式

所有通道使用 **无需公网 IP** 的连接方式——通过 WebSocket 或 long-polling 出站连接平台服务：

| 通道 | 连接方式 | 线程模型 |
|------|---------|---------|
| Feishu | WebSocket 长连接 | 独立 `threading.Thread` + 专有 asyncio event loop |
| Slack | Socket Mode WebSocket | 主 asyncio loop |
| Telegram | Long-polling | 独立 `threading.Thread` |
| DingTalk | Gateway WebSocket | 独立 `threading.Thread` |
| Discord | Gateway WebSocket | 独立 `threading.Thread` |
| WeCom | WebSocket | 主 asyncio loop |
| WeChat | iLink long-polling | 独立 `threading.Thread` |

独立线程 + 专有 event loop 的模式用于需要长时间保持连接的平台——避免阻塞主 asyncio loop。

## 启动流程

```
Gateway lifespan()
  → ChannelService.from_app_config(config)
    → 读取 config.yaml channels: section
    → resolve_class() 懒加载每个 channel
    → 为每个启用的 channel 创建实例
    → ChannelManager.start() — 启动 _dispatch_loop()
  → 各 channel.start() — 建立平台连接

Shutdown:
  → ChannelService.stop() — 5s timeout
  → 各 channel.stop() — 断开平台连接
```

## 源码索引

| 文件 | 行数 | 职责 |
|------|------|------|
| `app/channels/base.py` | 131 | `Channel` 抽象基类 |
| `app/channels/message_bus.py` | 173 | `MessageBus` pub/sub |
| `app/channels/manager.py` | 1024 | `ChannelManager` 核心调度 |
| `app/channels/store.py` | 154 | 文件持久化 Channel↔Thread 映射 |
| `app/channels/service.py` | 232 | `ChannelService` 生命周期 |
| `app/channels/commands.py` | 21 | 已知命令集 |
| `app/channels/feishu.py` | 698 | 飞书/Lark |
| `app/channels/slack.py` | 264 | Slack |
| `app/channels/telegram.py` | 317 | Telegram |
| `app/channels/dingtalk.py` | 740 | 钉钉 |
| `app/channels/discord.py` | 553 | Discord |
| `app/channels/wecom.py` | 398 | 企业微信 |
| `app/channels/wechat.py` | 1370 | 微信 |
| `app/gateway/routers/channels.py` | — | Channel 状态/重启 API |
| `app/gateway/app.py` | — | lifespan 启动入口 |
