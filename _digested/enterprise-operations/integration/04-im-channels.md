---



title: "IM 频道集成"
description: 'DeerFlow 可以接入 9 个即时通讯平台（外加 GitHub webhook 通道）。所有频道通过 outbound 连接（WebSocket 或 polling），不需要公网 IP。'
topics: [integration, sdk, docker-deploy]
verified_against: v2.2.0
last_verified: 2026-11-08
---

# IM 频道集成

DeerFlow 可以接入 **9 个即时通讯平台**：Feishu/Lark、DingTalk、Slack、Telegram、Discord、WeCom、WeChat、**QQ**、Buzz。另有第 10 个通道 **GitHub**（webhook 驱动，不是聊天平台，见 `enterprise-operations/github-integration.md`）。`CHANNEL_CAPABILITIES`（`app/channels/capabilities.py:20-31`）共 **10** 项（含 `github`；v2.1.0 时它是 manager 里的 9 项 dict，v2.2.0 抽成独立模块并补上 `qq`）。所有聊天频道通过 outbound 连接（WebSocket 或 polling），不需要公网 IP。

## 架构

```
飞书/Slack/Telegram/QQ/...
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

  # 🆕 v2.2.0 新增的一层：总线与 worker pool
  inbound_queue_maxsize: 1000              # 入站总线容量上限（默认 1000）
  max_concurrency: 5                       # 固定 worker 数（默认 5）
  shutdown_grace_period_seconds: 3         # 停机宽限（默认 3）

  # 🆕 多实例：每个 provider 只允许一个 Gateway 持有平台连接
  leader_lease:
    enabled: auto                          # auto | true | false
    lease_seconds: 30                      # ≥3
    grace_seconds: 10                      # ≥0
```

`leader_lease.enabled: auto` 在多进程部署下自动开启；`github` 是唯一不参与仲裁的 provider（`_UNARBITRATED_PROVIDERS`，`service.py:62`）。机制细节见 [channels/00-overview.md](../channels/00-overview.md)。

## 飞书 (Feishu/Lark)

```yaml
feishu:
  enabled: true
  app_id: $FEISHU_APP_ID
  app_secret: $FEISHU_APP_SECRET
  # domain: https://open.feishu.cn        # 国内（默认）
  # domain: https://open.larksuite.com    # 国际
  card_interaction_enabled: false        # 🆕 澄清问题的按钮卡片（默认关）
```

**消息流**: `runs.stream()` → 先发一条运行中卡片 → 每个增量都会 patch 同一张卡片（`config.update_multi=true`）→ 最终 `is_final=True`。

`card_interaction_enabled: true` 时（`feishu.py:195`）额外注册 `register_p2_card_action_trigger`（`feishu.py:296`）：`ask_clarification` 的 ≤4 个选项渲染成按钮卡片（`feishu_card_interaction.py`，`MAX_CARD_OPTIONS = 4`），点击即作为澄清回复送入同一条 thread；卡片 30 分钟过期。**该路径是 fail-closed 的进程内注册表**——多个 Gateway 副本时，点击可能落在没有该卡片记录的副本上，于是被拒绝而不是猜测。生产配置的一处易错点：飞书应用的事件订阅里如果启用了"卡片回调"，平台会把 `card.action.trigger` 投给**第一个**注册它的副本，所以该开关与多副本组合使用前要先确认单副本或粘性路由。

## Slack

```yaml
slack:
  enabled: true
  bot_token: $SLACK_BOT_TOKEN    # xoxb-...
  app_token: $SLACK_APP_TOKEN    # xapp-... (Socket Mode)
  allowed_users: []              # 空 = 允许所有人；可填 ["U123456"]
```

**消息流**: `runs.wait()` → 阻塞等完成 → 提取最终回复 → 发送。使用 Socket Mode（WebSocket），无需公网 HTTP endpoint。用户连接形态下优先用 per-connection 的 `WebClient` 凭据（`slack.py:325`），取不到才回落 operator bot token。

## Telegram

```yaml
telegram:
  enabled: true
  bot_token: $TELEGRAM_BOT_TOKEN
  allowed_users: []              # 空 = 允许所有人
```

**消息流**: polling 模式，`runs.wait()` → 阻塞等完成 → 发送回复。通过 `allowed_users` 白名单限制。

## QQ 🆕

```yaml
qq:
  enabled: true
  app_id: $QQ_APP_ID
  client_secret: $QQ_CLIENT_SECRET
  allowed_users: []              # QQ OpenID（不是 QQ 号）；空 = 允许所有人；非空但不可解析则 fail closed
  sandbox: false                 # true 时 REST 走沙箱 host（与开发者后台的沙箱成员资格是两件事）
```

`app/channels/qq.py`（611 行，v2.2.0 新增）。走 QQ 官方机器人 **WebSocket 网关 + HTTP OpenAPI**：`TOKEN_URL` 换 access token（提前续期，`TIMESTAMP_WARNING_INTERVAL = 60.0` 防时钟偏移告警刷屏），`API_URL = "https://api.sgroup.qq.com"`，订阅掩码 `GROUP_AND_C2C_EVENT = 1 << 25`（只收群 @ 与 C2C 消息）。启动握手 `START_TIMEOUT = 30.0`，断线 `RECONNECT_DELAY = 1.0` 重连。

- **消息流**: 阻塞等待（`supports_streaming: False`），**不**做增量流式——QQ 的回复有配额限制：C2C 每条消息最多 `C2C_MAX_REPLIES = 4` 次回复，群聊 `GROUP_MAX_REPLIES = 5`；文本按 `MAX_TEXT_BYTES = 4000` 字节切块并加 `TRUNCATION_MARKER`。
- **入站去重**：进程内 `MAX_CACHED_MESSAGES = 2048` LRU（QQ 网关会重投），入站队列容量 `INBOUND_BUFFER_SIZE = 64`。
- **凭据**：`_CHANNEL_CREDENTIAL_KEYS["qq"] = ["app_id", "client_secret"]`（`service.py:52`），注册表项 `"qq": "app.channels.qq:QQChannel"`（`service.py:39`）。
- **能力**：`proactive_notifications: True` + `proactive_group_notifications: True`——定时任务可推送给绑定用户，也可推送用户显式选的群（群身份形如 `<app_id>:group:<group_openid>`，`notification_groups.py:32`）；绑定群里需先填群名再取绑定码。

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

`wechat.py` 1929 行 / 82KB（`app/channels/` 最大的单个通道实现），支持图片/文件收发。

🆕 **扫码登录有两条路径**，别混淆：`qrcode_login_enabled`（上面的配置项）是 **Gateway 启动时**在缺 `bot_token` 的情况下自行走 QR bootstrap；而 **浏览器里管理员扫码**（Settings 页 → WeChat 卡片）走 `app/channels/wechat_qr_login.py` + `POST /api/channels/wechat/qr-login`（admin-only，180s 单会话，凭据只落服务端）。见 [channels/05-user-connections.md](../channels/05-user-connections.md)。

## 企业微信 (WeCom)

```yaml
wecom:
  enabled: true
  bot_id: $WECOM_BOT_ID
  bot_secret: $WECOM_BOT_SECRET
```

相对简洁的配置。`proactive_notifications: True` + `proactive_group_notifications: True`（群通知需用户先填群名）。

## 钉钉 (DingTalk)

```yaml
dingtalk:
  enabled: true
  client_id: $DINGTALK_CLIENT_ID
  client_secret: $DINGTALK_CLIENT_SECRET
  allowed_users: []
  card_template_id: ""      # 可选：AI Card 模板，启用流式更新
```

**消息流**（有 `card_template_id`）：`runs.stream()` → 创建 AI Card → `PUT /v1.0/card/streaming` 流式更新 → 结束时最终确定。无 `card_template_id` 则 fallback 到 `sampleMarkdown`。注意 `CHANNEL_CAPABILITIES["dingtalk"].supports_streaming` 是 **False**：那张表是没有活动实例时的兜底答案，运行中的实例自己回答（`dingtalk.py:216-217` 的 `supports_streaming` 属性返回 `bool(self._card_template_id)`）。

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

## Buzz

```yaml
buzz:
  enabled: true
  relay_url: wss://buzz.example.com
  private_key: $BUZZ_PRIVATE_KEY      # 64-hex 或 bech32 nsec1…
  allowed_users: []                   # pubkey（hex 或 npub）；空 = 谁都不允许（DENY-BY-DEFAULT）
  require_mention: true               # 频道内需 @ 提及
  mention_free_channels: []           # 无需 @ 的频道 UUID
```

`allowed_users` 在 Buzz 上是**默认拒绝**的（与其它频道"空 = 允许所有人"相反），空列表会在启动时打 warning。`requires_bound_identity=False`——Buzz 不做 `/connect` 绑定，身份靠 pubkey allowlist。详见 [channels/06-buzz.md](../channels/06-buzz.md)。

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
| `/model` 🆕 | 查看/切换当前模型 |
| `/memory` | 查看记忆 |
| `/agent` | 切换/查看当前 Agent |
| `/bootstrap` | 引导/初始化频道绑定 |
| `/connect` | 连接账号（绑定码流程） |
| `/goal` | 设置/查看当前 goal |
| `/help` | 帮助信息 |

命令在 `ChannelManager._worker_loop()`（`app/channels/manager.py:2466`）中本地处理，不经过 Agent。`/new`、`/status`、`/models`、`/model`、`/memory`、`/help`、`/agent`、`/bootstrap`、`/goal` 来自 `KNOWN_CHANNEL_COMMANDS`（`app/channels/commands.py:11-23`）；`/connect <code>` 是单独的一次性绑定码路径（`extract_connect_code()`，`commands.py:68`），不在该集合内。分发入口是 `_handle_command()`（`manager.py:3704`），它先过绑定身份闸门，再生成回复文案（宿主自撰文案走 `reply_locale.py`）。

## 消息流总结

```
                         ┌─────────────┐
                         │ 外部平台消息  │
                         └──────┬──────┘
                                │
                    MessageBus.publish_inbound() / reserve_inbound()
                                │  (有界：满载即丢 + 告警，绝不无界排队)
                        ┌───────▼───────┐
                        │  _worker_loop │   ← 固定 max_concurrency 个 worker
                        └───────┬───────┘
                                │
                    ┌───────────┼───────────┐
                    │           │           │
                命令(本地)   聊天(远程)   未知
                    │           │
              handle locally  ┌───┴───┐
                              │       │
                         Feishu/DingTalk/WeCom/Buzz   Slack/Telegram/Discord/WeChat/QQ
                         runs.stream()                runs.wait()
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

频道到 Thread ID 的映射有两套（`app/channels/store.py`，`ChannelStore` 协议）：

| 后端 | 存储 | 适用 |
|------|------|------|
| `SqlChannelStore`（默认） | 应用数据库表 `channel_thread_bindings`，键 `"channel:chat_id[:topic_id]"` | sqlite / postgres；多副本共享同一份绑定 |
| `JsonChannelStore` | `{base_dir}/channels/store.json`（原子重写） | `database.backend: memory`，以及 SQL 首次启动时的导入源（导入后改名 `.migrated`） |

用户连接形态（消息带 `connection_id`）则落 `channel_conversations` 表。详见 [channels/03-thread-mapping.md](../channels/03-thread-mapping.md)。

## Docker 中的频道

IM 频道在 Gateway 容器内运行。环境变量：
- `DEER_FLOW_CHANNELS_LANGGRAPH_URL=http://gateway:8001/api`
- `DEER_FLOW_CHANNELS_GATEWAY_URL=http://gateway:8001`
- `DEER_FLOW_INTERNAL_AUTH_TOKEN` — 多 worker 共享认证
- `DEER_FLOW_CREDENTIALS_KEY` 🆕 — 静态凭据加密密钥（逗号分隔可轮换）。启用 `channel_connections.enabled` 或从 Web UI 录入通道凭据时**必须**显式设置：多副本无法共享自动生成的 `{base_dir}/.credentials_key`，启动闸门会拒绝。缺该 key 时 `POST /api/channels/{provider}/runtime-config` 返回 503，连接凭据读写降级为"不可用"。

`make up` 自动生成并持久化 `DEER_FLOW_INTERNAL_AUTH_TOKEN`，手动多 worker 部署需自己设置。

## 与 `enterprise-operations/channels/` 的分工

本页是**配置视角**；内部设计（有界总线与准入、worker pool 与停机顺序、幂等 run 准入、stream 策略与能力门、leader 租约、凭据存储、thread 映射收敛）见 [channels/README.md](../channels/README.md)。
