---
title: "IM 频道集成"
description: "DeerFlow 可以接入 7 个即时通讯平台。所有频道通过 outbound 连接（WebSocket 或 polling），不需要公网 IP。"
topics: [integration, sdk, docker-deploy]
---

# IM 频道集成

DeerFlow 可以接入 7 个即时通讯平台。所有频道通过 outbound 连接（WebSocket 或 polling），不需要公网 IP。

## 架构

```
飞书/Slack/Telegram/...
        │
        ▼ (WebSocket/Polling)
  Channel Impl (app/channels/)
        │
        ▼ (langgraph-sdk HTTP)
  Gateway API (localhost:8001)
        │
        ▼
  Lead Agent
```

频道使用 `langgraph-sdk` HTTP 客户端与 Gateway 通信（和前端一样）。内部认证通过 process-local auth token + CSRF cookie/header 对完成。

## 通用配置段

```yaml
channels:
  langgraph_url: http://localhost:8001/api   # LangGraph-compatible API
  gateway_url: http://localhost:8001         # Gateway REST API

  # Docker 中注意：频道在 gateway 容器内运行，
  # localhost 就是 gateway 容器自身，也可以用容器名：
  # langgraph_url: http://gateway:8001/api
  # gateway_url: http://gateway:8001

  session:                        # 可选：所有频道的默认 session 设置
    assistant_id: lead_agent      # 或自定义 Agent 名称
    config:
      recursion_limit: 100
    context:
      thinking_enabled: true
      is_plan_mode: false
      subagent_enabled: false
```

## 飞书 (Feishu/Lark)

```yaml
feishu:
  enabled: true
  app_id: $FEISHU_APP_ID
  app_secret: $FEISHU_APP_SECRET
  # domain: https://open.feishu.cn        # 国内（默认）
  # domain: https://open.larksuite.com    # 国际
```

**消息流**: `runs.stream()` → 先发一条运行中卡片 → 每个增量都会 patch 同一张卡片（`config.update_multi=true`）→ 最终 `is_final=True`。

## Slack

```yaml
slack:
  enabled: true
  bot_token: $SLACK_BOT_TOKEN    # xoxb-...
  app_token: $SLACK_APP_TOKEN    # xapp-... (Socket Mode)
  allowed_users: []              # 空 = 允许所有人；可填 ["U123456"]
```

**消息流**: `runs.wait()` → 阻塞等完成 → 提取最终回复 → 发送。使用 Socket Mode（WebSocket），无需公网 HTTP endpoint。

## Telegram

```yaml
telegram:
  enabled: true
  bot_token: $TELEGRAM_BOT_TOKEN
  allowed_users: []              # 空 = 允许所有人
```

**消息流**: polling 模式，`runs.wait()` → 阻塞等完成 → 发送回复。通过 `allowed_users` 白名单限制。

## WeChat（微信）

```yaml
wechat:
  enabled: true
  bot_token: $WECHAT_BOT_TOKEN
  ilink_bot_id: $WECHAT_ILINK_BOT_ID
  qrcode_login_enabled: true       # 允许首次 QR 码登录（无 bot_token 时）
  ilink_app_id: ""                 # iLink-App-Id header
  route_tag: ""                    # SKRouteTag header
  allowed_users: []
  polling_timeout: 35
  qrcode_poll_interval: 2
  qrcode_poll_timeout: 180
  state_dir: ./.deer-flow/wechat/state  # getupdates cursor 持久化
  max_inbound_image_bytes: 20971520     # 20 MiB
  max_outbound_image_bytes: 20971520
  max_inbound_file_bytes: 52428800      # 50 MiB
  max_outbound_file_bytes: 52428800
  allowed_file_extensions:
    - .txt, .md, .pdf, .csv, .json, .yaml, .yml
    - .xml, .html, .log, .zip
    - .doc, .docx, .xls, .xlsx, .ppt, .pptx, .rtf
```

这是最大的频道实现 (~53KB)，支持图片/文件收发、QR 码登录。

## 企业微信 (WeCom)

```yaml
wecom:
  enabled: true
  bot_id: $WECOM_BOT_ID
  bot_secret: $WECOM_BOT_SECRET
```

相对简洁的配置。

## 钉钉 (DingTalk)

```yaml
dingtalk:
  enabled: true
  client_id: $DINGTALK_CLIENT_ID
  client_secret: $DINGTALK_CLIENT_SECRET
  allowed_users: []
  card_template_id: ""      # 可选：AI Card 模板，启用流式更新
```

**消息流**（有 `card_template_id`）：`runs.stream()` → 创建 AI Card → `PUT /v1.0/card/streaming` 流式更新 → 结束时最终确定。无 card_template_id 则 fallback 到 `sampleMarkdown`。

## Discord

```yaml
discord:
  enabled: true
  bot_token: $DISCORD_BOT_TOKEN
  allowed_guilds: []          # 空 = 所有 guild
  mention_only: false         # true = 仅在被 @ 时回复
  allowed_channels: []        # 免 mention 的 channel（即使 mention_only 时也回复）
  thread_mode: false          # true = 在 Discord 线程中分组对话
```

## 每频道/每用户 Session 覆盖

```yaml
wechat:
  # ...
  session:
    assistant_id: mobile-agent     # 覆盖全局 assistant
    context:
      thinking_enabled: false
    users:                         # 按用户覆盖
      "123456789":
        assistant_id: vip-agent
        config:
          recursion_limit: 150
        context:
          thinking_enabled: true
          subagent_enabled: true
```

## 命令系统

所有频道支持以下命令（在聊天中发送）：

| 命令 | 功能 |
|------|------|
| `/new` | 开始新对话 |
| `/status` | 查看当前状态 |
| `/models` | 列出可用模型 |
| `/memory` | 查看记忆 |
| `/help` | 帮助信息 |

命令在 `ChannelManager._dispatch_loop()` 中本地处理，不经过 Agent。

## 消息流总结

```
                         ┌─────────────┐
                         │ 外部平台消息  │
                         └──────┬──────┘
                                │
                    MessageBus.publish_inbound()
                                │
                        ┌───────▼───────┐
                        │  _dispatch_loop │
                        └───────┬───────┘
                                │
                    ┌───────────┼───────────┐
                    │           │           │
                命令(本地)   聊天(远程)   未知
                    │           │
              handle locally  ┌───┴───┐
                              │       │
                         Feishu/DingTalk  Slack/Telegram
                         runs.stream()    runs.wait()
                              │              │
                         增量 patch       最终回复
                         is_final=False   is_final=True
                              │              │
                              └──────┬───────┘
                                     │
                              Channel.send()
                                     │
                              ┌──────▼──────┐
                              │  外部平台回复  │
                              └─────────────┘
```

## 线程映射存储

频道到 Thread ID 的映射通过 JSON 文件持久化（`app/channels/store.py`）：

```
key: "channel:chat_id"              → 根对话 thread_id
key: "channel:chat_id:topic_id"     → 话题对话 thread_id
```

存储在 Gateway 的数据目录中。

## Docker 中的频道

IM 频道在 Gateway 容器内运行。环境变量：
- `DEER_FLOW_CHANNELS_LANGGRAPH_URL=http://gateway:8001/api`
- `DEER_FLOW_CHANNELS_GATEWAY_URL=http://gateway:8001`
- `DEER_FLOW_INTERNAL_AUTH_TOKEN` — 多 worker 共享认证

`make up` 自动生成并持久化 `DEER_FLOW_INTERNAL_AUTH_TOKEN`，手动多 worker 部署需自己设置。
