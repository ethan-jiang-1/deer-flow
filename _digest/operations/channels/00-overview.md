---
title: "IM 通道系统全景"
description: "DeerFlow 通过 IM 平台通道（Feishu/Lark、DingTalk、Slack、Telegram、Discord、WeCom、WeChat、Buzz）让用户通过聊天消息与 Agent 交互，另有 Lark CLI 托管集成。"
topics: [channels, im, messaging]
---

# IM 通道系统全景

DeerFlow 通过 8 个 IM 平台通道（Feishu/Lark、DingTalk、Slack、Telegram、Discord、WeCom、WeChat、Buzz）让用户通过聊天消息与 Agent 交互。另有 **Lark CLI 托管集成**（harness 级，非 app/channels 通道）。`app/channels/` 下还有一个 **GitHub** 通道（webhook 驱动，非聊天平台，见 [../github-integration.md](../github-integration.md)）——通道能力表 `CHANNEL_CAPABILITIES` 因此共 **9 项**（`manager.py:139-149`）。

## 架构全景

```
┌─────────────────────────────────────────────────────────┐
│ External Platforms (Feishu / Slack / Telegram / Buzz ...)│
│   WebSocket / Long-polling / Webhook / NIP-42 Nostr      │
├─────────────────────────────────────────────────────────┤
│ Channel Implementations (app/channels/)                  │
│   ├─ feishu.py   → lark-oapi WebSocket                  │
│   ├─ slack.py    → slack-sdk Socket Mode                │
│   ├─ telegram.py → python-telegram-bot long-polling     │
│   ├─ dingtalk.py → Gateway WebSocket + OAuth2           │
│   ├─ discord.py  → discord.py Gateway WebSocket         │
│   ├─ wecom.py    → aibot WebSocket                      │
│   ├─ wechat.py   → iLink long-polling                   │
│   └─ buzz.py     → NIP-42 WebSocket (Nostr relay) 🆕    │
│       ├─ buzz_nostr.py — NIP-01 签名/验证（BIP-340）    │
│       └─ buzz_run_policy.py — serialize_thread_runs     │
├─────────────────────────────────────────────────────────┤
│ Inbound Dedupe (dedupe_store.py) 🆕                      │
│   ├─ MemoryInboundDedupeStore — 进程内 OrderedDict       │
│   └─ PostgresInboundDedupeStore — 多副本共享             │
├─────────────────────────────────────────────────────────┤
│ MessageBus (message_bus.py)                              │
│   ├─ Inbound: single asyncio.Queue[InboundMessage]      │
│   └─ Outbound: async callback registry                  │
├─────────────────────────────────────────────────────────┤
│ ChannelManager (manager.py — ~2800 行)                   │
│   ├─ _dispatch_loop() — semaphore(5) + 去重检查         │
│   ├─ _handle_chat() — 核心路由                          │
│   ├─ /agent 命令 — 会话级 Custom Agent 选择 🆕          │
│   ├─ _accumulate_stream_text() — allowlist 累积         │
│   └─ _resolve_run_params() — 4 层 config merge          │
├─────────────────────────────────────────────────────────┤
│ Inbound Attachments (sandbox_files.py) 🆕                │
│   └─ 非挂载沙箱附件同步：非释放沙箱 client lease         │
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
| **增量流式** (supports_streaming=true) | Feishu, WeCom, Telegram, **Buzz** 🆕, DingTalk (Card mode) | `client.runs.stream()` → 逐 chunk 更新消息（Buzz 用 kind-40003 原地编辑、Telegram 用 `edit_message_text` 原地编辑）→ `is_final=True` 时完成 |
| **阻塞等待** (supports_streaming=false) | Slack, Discord, WeChat, DingTalk (non-Card) | `client.runs.wait()` → 等 Agent 完成 → 一次性发送完整响应 |
| **fire-and-forget**（`ChannelRunPolicy.fire_and_forget`） | GitHub（webhook 驱动，非聊天平台） | `client.runs.create()` 返回后即结束，由通道自己在 issue/PR 上回帖；manager 不搬运回复 |

两种策略的根本区别：增量流式在 Agent 执行期间持续更新消息（用户看到 "实时思考"），阻塞等待在所有 tool call 完成后才发送第一条响应（用户只看最终结果）。

## 连接方式

8 个 IM 聊天平台通道都使用 **无需公网 IP** 的连接方式——通过 WebSocket 或 long-polling 出站连接平台服务（GitHub 通道例外：它走平台推来的入站 webhook，需要公网可达端点）：

| 通道 | 连接方式 | 线程模型 |
|------|---------|---------|
| Feishu | WebSocket 长连接 | 独立 `threading.Thread` + 专有 asyncio event loop |
| Slack | Socket Mode WebSocket | 主 asyncio loop |
| Telegram | Long-polling | 独立 `threading.Thread` |
| DingTalk | Gateway WebSocket | 独立 `threading.Thread` |
| Discord | Gateway WebSocket | 独立 `threading.Thread` |
| WeCom | WebSocket | 主 asyncio loop |
| WeChat | iLink long-polling | 独立 `threading.Thread` |
| **Buzz** 🆕 | **NIP-42 认证 WebSocket**（Nostr relay） | 独立 `threading.Thread` + 专有 asyncio event loop |

独立线程 + 专有 event loop 的模式用于需要长时间保持连接的平台——避免阻塞主 asyncio loop。

## Buzz 频道（Nostr）🆕

Buzz 是基于 **Nostr 协议**（NIP-01/NIP-42）的 IM 通道，通过 WebSocket 接入一个 Buzz relay，让 DeerFlow 成为 relay 上某个 workspace 的成员。需要 `buzz` 依赖 extra。→ 深挖见 [06-buzz.md](06-buzz.md)。

- **入站**：一条 NIP-42 认证的 WebSocket，三类订阅：(a) `buzz-discovery`（kind-39000，发现所属频道列表）；(b) `buzz-membership`（kind-44100/44101，实时成员变动）；(c) 每频道一个 `buzz-chat-<uuid>`（kind-9，`#h:[uuid]` 限定——relay 只把事件推给 channel-scoped 订阅）
- **门控**：pubkey allowlist（deny-by-default）+ mention/DM/thread-follow 三重闸门；`/connect <code>` 绑定在闸门前
- **出站**：首条 kind-9 聊天事件，流式更新用 **kind-40003 原地编辑**（每条都是不可变公开 Nostr 事件，泄漏无法撤回——`send()` 拒绝发布带 `<memory>` 等隐藏上下文标记的文本）
- **身份验证**：每个入站 EVENT 在 `handle_relay_frame` 单一入口重算 NIP-01 id + 验证 BIP-340 Schnorr 签名，`pubkey` 不可被 relay 伪造
- **可靠性**：订阅 `CLOSED` 帧恢复（`MAX_RESUBSCRIBE_ATTEMPTS=3`）；重订阅 watermark **按频道**且拒绝未来时间戳（`MAX_FUTURE_SKEW_SECONDS=60`）；relay 单频道历史上限 2000 条（已知边界，超出丢最旧）
- **去重**：`dedupe_store.py` 两级——进程内 `MemoryInboundDedupeStore`（TTL 10min）或 `PostgresInboundDedupeStore`（多副本共享）

## 同步 #6 更新（431892e1..769589e8）🆕

- **会话级 custom agent 选择**（#5168）：`/agent list` / `/agent use <name>` 开新对话并固定 custom agent，选择跨 Gateway 重启与 IM/Web 客户端存活；已有对话绝不中途切换。→ 详见 [03-thread-mapping.md](03-thread-mapping.md)
- **WeChat/WeCom `allowed_media_hosts`**：`channels.wechat.allowed_media_hosts` / `channels.wecom.allowed_media_hosts` 增加额外的入站媒体下载 host **后缀**白名单（`"example.com"` 与 `"*.example.com"` 等价），叠加在平台 CDN 默认之上——WeChat 默认 `*.qq.com` + `cdn_base_url` host；WeCom 默认 qq.com 家族 + 官方 COS 媒体 host（`ww-aibot-img-*.myqcloud.com`），COS 账号轮换或媒体走代理时在此追加。config.yaml 的 `wechat:` 与 `wecom:` 两处各有一份。
- **Buzz seen-events 落盘移出事件循环**（#5103）：flush/加载经 `asyncio.to_thread` 进 worker 线程 + generation 计数 + `quiesce()`/`resume()`。→ 详见 [06-buzz.md](06-buzz.md)
- **Discord ack-reaction task 强引用**（#5049）：事件循环只持 `asyncio.create_task` 弱引用，✅ 确认 reaction 任务可能被 GC 掉而静默丢失——**实例级** retention set 持有到完成并记录失败（实例级保证一个通道的 stop 不取消其它实例的在途任务），通道 `stop()` 的所有清理点同时 drain typing task 与 in-flight ack-reaction task，避免 channel 实例与 discord Message 对象图跨重启被钉住。
- **ChannelStore 读同步**（#5083）：`get_thread_id()`/`list_entries()` 读取路径加锁。→ 详见 [03-thread-mapping.md](03-thread-mapping.md)
- **Lark CLI 凭据切换保留 app secrets**（#4820）：`_replace_lark_app_credentials_locked` 调整为**先** `_clear_directory_contents` **再** `_save_lark_app_config_with_cli`——此前先写新凭据再清目录，切换会把刚写入的 app_id/app_secret 一并清掉；事务快照中的旧 auth 撤销保持不变。

## Lark CLI 托管集成 🆕

`deerflow/integrations/lark_cli.py` 是 harness 级托管集成安装器（不是 app/channels 通道），管理 27 个官方 `lark-*` 技能包（Feishu/Lark 办公套件）。部署时通过 `GET /api/integrations/lark/status` 暴露 `sandbox_runtime_mode` / `sandbox_runtime_ready`。

两种沙箱供给模式：
- **Pattern A（init-container 二进制）**：`docker/lark-cli-init/` 镜像把 `lark-cli` 二进制写入共享 emptyDir，沙箱直接调用。凭据目录仍挂载进沙箱——**plaintext 密钥对沙箱进程可见**（仅防篡改，不防读取）
- **Pattern B（broker sidecar）**：`docker/lark-cli-broker/` 镜像在 loopback `:8788` 运行 broker，持有真实凭据（只挂载到 sidecar），沙箱通过 shim 把 `lark-cli` 调用代理成 `POST /v1/exec`。**凭据文件从不出现在沙箱文件系统**（issue #4338，`LARK_CLI_BROKER_IMAGE` 启用）

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
| `app/channels/base.py` | 393 | `Channel` 抽象基类 |
| `app/channels/message_bus.py` | 359 | `MessageBus` pub/sub |
| `app/channels/manager.py` | 2786 | `ChannelManager` 核心调度 |
| `app/channels/store.py` | 157 | 文件持久化 Channel↔Thread 映射（读写全部在 `_lock` 内） |
| `app/channels/service.py` | 588 | `ChannelService` 生命周期 |
| `app/channels/commands.py` | 90 | 已知命令集（含 `/agent`、`/goal`） |
| `app/channels/run_policy.py` | 118 | `ChannelRunPolicy` 注册表（per-channel 流式/串行/fire-and-forget 策略） |
| `app/channels/sandbox_files.py` | 43 | 🆕 入站附件→沙箱同步（非释放沙箱 client lease，防并行 run 关闭共享 client） |
| `app/channels/feishu.py` | 1244 | 飞书/Lark |
| `app/channels/slack.py` | 475 | Slack |
| `app/channels/telegram.py` | 992 | Telegram |
| `app/channels/dingtalk.py` | 1129 | 钉钉 |
| `app/channels/discord.py` | 858 | Discord |
| `app/channels/wecom.py` | 619 | 企业微信（出站 20480 UTF-8 字节协议上限 🆕） |
| `app/channels/wechat.py` | 1479 | 微信 |
| `app/channels/buzz.py` | 1472 | 🆕 Buzz（Nostr relay，NIP-42 认证） |
| `app/channels/buzz_nostr.py` | 201 | 🆕 NIP-01 事件签名/验证（BIP-340 Schnorr） |
| `app/channels/buzz_run_policy.py` | 12 | 🆕 Buzz run 策略（serialize_thread_runs） |
| `app/channels/buzz_seen_events.py` | 385 | 🆕 连接层 seen-id 持久去重（`BuzzSeenEventStore`，事件循环外读写） |
| `app/channels/dedupe_store.py` | 276 | 🆕 入站消息去重存储（Memory/Postgres 两级） |
| `deerflow/integrations/lark_cli.py` | 1724 | 🆕 Lark CLI 托管集成安装器（27 个 lark-* 技能包） |
| `deerflow/integrations/lark_broker.py` | 457 | 🆕 Pattern B 凭据 broker（沙箱侧 sidecar） |
| `app/gateway/routers/channels.py` | — | Channel 状态/重启 API |
| `app/gateway/app.py` | — | lifespan 启动入口 |
