---
title: "IM 通道系统全景"
description: 'DeerFlow 通过 IM 平台通道（Feishu/Lark、DingTalk、Slack、Telegram、Discord、WeCom、WeChat、QQ、Buzz）让用户通过聊天消息与 Agent 交互，另有 Lark CLI 托管集成。'
topics: [channels, im, messaging]
verified_against: v2.2.0
last_verified: 2026-11-08
---

# IM 通道系统全景

DeerFlow 通过 **9 个 IM 平台通道**（Feishu/Lark、DingTalk、Slack、Telegram、Discord、WeCom、WeChat、**QQ**、Buzz）让用户通过聊天消息与 Agent 交互。另有 **Lark CLI 托管集成**（harness 级，非 app/channels 通道）。`app/channels/` 下还有一个 **GitHub** 通道（webhook 驱动，非聊天平台，见 [../github-integration.md](../github-integration.md)）。通道能力表 `CHANNEL_CAPABILITIES` 因此共 **10 项**，位于独立模块 `app/channels/capabilities.py:20-31`（v2.1.0 曾内联在 `manager.py`，v2.2.0 抽出）。

## 架构全景

```
┌─────────────────────────────────────────────────────────┐
│ External Platforms (Feishu / Slack / Telegram / QQ ...)  │
│   WebSocket / Long-polling / Webhook / NIP-42 Nostr      │
├─────────────────────────────────────────────────────────┤
│ Channel Implementations (app/channels/)                  │
│   ├─ feishu.py   → lark-oapi WebSocket                  │
│   │   └─ feishu_card_interaction.py — 澄清按钮卡片 🆕    │
│   ├─ slack.py    → slack-sdk Socket Mode                │
│   ├─ telegram.py → python-telegram-bot long-polling     │
│   ├─ dingtalk.py → Gateway WebSocket + OAuth2           │
│   ├─ discord.py  → discord.py Gateway WebSocket         │
│   ├─ wecom.py    → aibot WebSocket                      │
│   ├─ wechat.py   → iLink long-polling                   │
│   │   └─ wechat_qr_login.py — 浏览器扫码引导登录 🆕      │
│   ├─ qq.py       → QQ 开放平台 WebSocket（C2C/群）🆕    │
│   └─ buzz.py     → NIP-42 WebSocket (Nostr relay)       │
│       ├─ buzz_nostr.py — NIP-01 签名/验证（BIP-340）    │
│       └─ buzz_run_policy.py — serialize_thread_runs     │
├─────────────────────────────────────────────────────────┤
│ Inbound Dedupe (dedupe_store.py)                         │
│   ├─ MemoryInboundDedupeStore — 进程内 OrderedDict       │
│   └─ PostgresInboundDedupeStore — 多副本共享             │
├─────────────────────────────────────────────────────────┤
│ MessageBus (message_bus.py) — 有界入站准入               │
│   ├─ Inbound: asyncio.Queue(capacity) + reservation     │
│   ├─ InboundClaim / dedupe_claimed — 适配器提前占坑      │
│   └─ Outbound: async callback registry（快照派发）       │
├─────────────────────────────────────────────────────────┤
│ ChannelManager (manager.py — 4162 行)                    │
│   ├─ 固定 worker pool（max_concurrency 个 _worker_loop） │
│   ├─ 幂等 run 准入（Idempotency-Key + uuid5 消息 id）🆕  │
│   ├─ _handle_chat() — 核心路由                          │
│   ├─ _apply_channel_policy() — interaction_mode　🆕      │
│   └─ _resolve_run_params() — 4 层 config merge          │
├─────────────────────────────────────────────────────────┤
│ Capabilities / Leadership 🆕                             │
│   ├─ capabilities.py — CHANNEL_CAPABILITIES 能力表       │
│   └─ leadership.py — per-provider 传输层 leader 租约     │
├─────────────────────────────────────────────────────────┤
│ ChannelStore (store.py) — ChannelStore 协议              │
│   ├─ SqlChannelStore → channel_thread_bindings 表        │
│   └─ JsonChannelStore → {base_dir}/channels/store.json   │
├─────────────────────────────────────────────────────────┤
│ Runtime Config (runtime_config_store.py) 🆕              │
│   ├─ SqlChannelRuntimeConfigStore — 密文行 + version     │
│   └─ ChannelRuntimeConfigStore — 历史 JSON（一次性导入） │
├─────────────────────────────────────────────────────────┤
│ ChannelService (service.py — 1247 行)                    │
│   └─ 生命周期管理 + 租约监督 + 运行时配置下发            │
└─────────────────────────────────────────────────────────┘
```

## 两种流式策略

DeerFlow 的 IM 通道使用两种完全不同的 Agent 响应策略：

| 策略 | 通道 | 行为 |
|------|------|------|
| **增量流式** (supports_streaming=true) | Feishu, WeCom, Telegram, Buzz, DingTalk (Card mode) | `client.runs.stream()` → 逐 chunk 更新消息（Buzz 用 kind-40003 原地编辑、Telegram 用 `edit_message_text` 原地编辑）→ `is_final=True` 时完成 |
| **阻塞等待** (supports_streaming=false) | Slack, Discord, WeChat, QQ, DingTalk (non-Card) | `client.runs.wait()` → 等 Agent 完成 → 一次性发送完整响应 |
| **fire-and-forget**（`ChannelRunPolicy.fire_and_forget`） | GitHub（webhook 驱动，非聊天平台） | `client.runs.create()` 返回后即结束，由通道自己在 issue/PR 上回帖；manager 不搬运回复 |

两种策略的根本区别：增量流式在 Agent 执行期间持续更新消息（用户看到 "实时思考"），阻塞等待在所有 tool call 完成后才发送第一条响应（用户只看最终结果）。

判定顺序在 `manager.py:1708-1716` 的 `_channel_supports_streaming()`：先问**已启动的通道实例**（`channel.supports_streaming`，例如 DingTalk 在 `dingtalk.py:216-217` 用 `bool(self._card_template_id)` 决定），实例不在时回退到 `CHANNEL_CAPABILITIES` 静态表。基类缺省为 `False`（`base.py:154-155`）。

## 连接方式

9 个 IM 聊天平台通道都使用 **无需公网 IP** 的连接方式——通过 WebSocket 或 long-polling 出站连接平台服务（GitHub 通道例外：它走平台推来的入站 webhook，需要公网可达端点）：

| 通道 | 连接方式 | 线程模型 |
|------|---------|---------|
| Feishu | WebSocket 长连接 | 独立 `threading.Thread` + 专有 asyncio event loop（`shutdown_private_loop()` 有界清理） |
| Slack | Socket Mode WebSocket | 主 asyncio loop |
| Telegram | Long-polling | 独立 `threading.Thread` |
| DingTalk | Gateway WebSocket | 独立 `threading.Thread` |
| Discord | Gateway WebSocket | 独立 `threading.Thread` |
| WeCom | WebSocket | 主 asyncio loop |
| WeChat | iLink long-polling | 独立 `threading.Thread` |
| **QQ** 🆕 | **WebSocket（`wss://api.sgroup.qq.com`，`GROUP_AND_C2C_EVENT = 1 << 25` 意图）** | 主 asyncio loop |
| Buzz | NIP-42 认证 WebSocket（Nostr relay） | 独立 `threading.Thread` + 专有 asyncio event loop |

独立线程 + 专有 event loop 的模式用于需要长时间保持连接的平台——避免阻塞主 asyncio loop。

## 多实例与 leader 租约 🆕

v2.2.0 新增 per-provider **传输层 leader 租约**（`app/channels/leadership.py` + `channel_leases` 表 + `channels.leader_lease` 配置段）。动机：Telegram 第二个 poller 会被 `409 Conflict` 拒绝，Discord 会把每条消息投给每个会话导致用户被答两遍，进程内 `ChannelManager` 状态在多实例间发散。

- 每个 provider 一行 `channel_leases`（`deerflow/persistence/channel_leases/model.py`）：`owner_id` / `epoch` / `lease_expires_at` / `transport_running`。所有判定比较都在**同一条 SQL 内用数据库时钟**完成，宿主时钟漂移无法把同一 provider 交给两个实例。
- `enabled: auto`（默认）跟随多进程信号（`GATEWAY_WORKERS`/`WEB_CONCURRENCY > 1`、`deployment.multi_instance: true`、`DEER_FLOW_MULTI_INSTANCE=1`）；`true` 强制开启（需 sqlite/postgres）；`false` 关闭。`lease_seconds` 默认 30（`ge=3`，每 `lease_seconds // 3` 续约一次），`grace_seconds` 默认 10。见 `deerflow/config/channel_leader_lease_config.py`（`ChannelLeaderLeaseConfig`，111 行）。
- 切分点：只有持租约者启动 provider 传输；manager、bus、GitHub webhook 在每个实例上都跑（`_UNARBITRATED_PROVIDERS = frozenset({"github"})`，`service.py:62`）。`ChannelService._start_channel()` 在 `service.py:766` 做租约兜底检查——所有启动路径（启动、readiness、重启、运行时配置、supervisor）都汇到这里。
- 监督循环 `ChannelService._supervise()` 负责续约、接管空闲租约、以及把**任意实例**保存的 web-UI 运行时配置（按 provider `version` 比对）下发到持租约实例。
- 配置段是 restart-required；多进程部署若把 `leader_lease` 明确设为 `false` 且启用了 IM 通道，启动被拒绝。

→ 深挖见 [01-message-bus.md](01-message-bus.md)（bus 准入）、[03-thread-mapping.md](03-thread-mapping.md)（跨副本绑定）、[05-user-connections.md](05-user-connections.md)（凭据加密）。

## QQ 通道 🆕

`app/channels/qq.py`（611 行）接入 QQ 开放平台机器人，**只需 WebSocket、无需公网回调 URL**（开发者后台选择 WebSocket 模式）。文本型 C2C 私聊 + 群内 @ 提及：

- 常量（文件头部）：`TOKEN_URL`、`API_URL = "https://api.sgroup.qq.com"`、`GROUP_AND_C2C_EVENT = 1 << 25`、`MAX_TEXT_BYTES = 4000`、`C2C_MAX_REPLIES = 4`、`GROUP_MAX_REPLIES = 5`、`TIMESTAMP_WARNING_INTERVAL = 60.0`、`MAX_CACHED_MESSAGES = 2048`、`INBOUND_BUFFER_SIZE = 64`、`START_TIMEOUT = 30.0`、`RECONNECT_DELAY = 1.0`、`TRUNCATION_MARKER`。
- 配置（`config.example.yaml` 的 `channels.qq`）：`app_id` / `client_secret` / `allowed_users`（**OpenID，不是 QQ 号**；空=全允许，非空但无可解析 ID 时 fail closed）/ `sandbox`（只切 REST 沙箱域名，后台成员资格另算）。
- 群通知：`workspace_id` 形如 `<app_id>:group:<group_openid>`，由 `notification_groups.qq_notification_group_openid()` 校验（`notification_groups.py:32`）。
- 注册：`service.py:39` `"qq": "app.channels.qq:QQChannel"`，凭据键 `["app_id", "client_secret"]`（`service.py:52`）。

## Buzz 频道（Nostr）

Buzz 是基于 **Nostr 协议**（NIP-01/NIP-42）的 IM 通道，通过 WebSocket 接入一个 Buzz relay，让 DeerFlow 成为 relay 上某个 workspace 的成员。需要 `buzz` 依赖 extra。→ 深挖见 [06-buzz.md](06-buzz.md)。

- **入站**：一条 NIP-42 认证的 WebSocket，三类订阅：(a) `buzz-discovery`（kind-39000，发现所属频道列表）；(b) `buzz-membership`（kind-44100/44101，实时成员变动）；(c) 每频道一个 `buzz-chat-<uuid>`（kind-9，`#h:[uuid]` 限定——relay 只把事件推给 channel-scoped 订阅）
- **门控**：pubkey allowlist（deny-by-default）+ mention/DM/thread-follow 三重闸门；`/connect <code>` 绑定在闸门前
- **出站**：首条 kind-9 聊天事件，流式更新用 **kind-40003 原地编辑**（每条都是不可变公开 Nostr 事件，泄漏无法撤回——`send()` 拒绝发布带 `<memory>` 等隐藏上下文标记的文本）
- **身份验证**：每个入站 EVENT 在 `handle_relay_frame` 单一入口重算 NIP-01 id + 验证 BIP-340 Schnorr 签名，`pubkey` 不可被 relay 伪造
- **可靠性**：订阅 `CLOSED` 帧恢复（`MAX_RESUBSCRIBE_ATTEMPTS=3`）；重订阅 watermark **按频道**且拒绝未来时间戳（`MAX_FUTURE_SKEW_SECONDS=60`）；relay 单频道历史上限 2000 条（已知边界，超出丢最旧）
- **去重**：`dedupe_store.py` 两级——进程内 `MemoryInboundDedupeStore`（TTL 10min）或 `PostgresInboundDedupeStore`（多副本共享）；连接层另有 `buzz_seen_events.py` 的 durable seen-id 存储

## v2.2.0 同步要点 🆕

以下为 v2.1.0 → v2.2.0 在本域新增/重写的机制，逐条落到对应专题页：

- **有界入站准入**：`MessageBus` 从无界 `Queue()` 变为 `asyncio.Queue(maxsize=inbound_queue_maxsize)`（默认 `DEFAULT_INBOUND_QUEUE_MAXSIZE = 1000`），`publish_inbound()` 改为 **reservation + `put_nowait`**，超载时抛 `InboundQueueFullError` 而不是让 producer 无限堆积等待（`message_bus.py:215-300` 一带）。配置项 `channels.inbound_queue_maxsize`。
- **固定 worker pool 取代 `Semaphore(5)`**：`ChannelManager.start()` 启动 `max_concurrency`（默认 `DEFAULT_CHANNEL_MAX_CONCURRENCY = 5`，`manager.py:79`）个 `_worker_loop()` 长驻任务；消息**内联处理**（不 per-message 建 task）。→ [01-message-bus.md](01-message-bus.md)
- **幂等 run 准入**：`Idempotency-Key` 头 + `_RUN_IDEMPOTENCY_KEY_PREFIX = "channel-inbound:v1:"` + uuid5 人类消息 id；重投返回 `ALREADY_ADMITTED_MESSAGE`。→ [01-message-bus.md](01-message-bus.md)
- **`interaction_mode`**：`ChannelRunPolicy` 新增 `interaction_mode: Literal["interactive","webhook","scheduled","autonomous"] | None`（`run_policy.py:22,112`），非 interactive 时 `disable_clarification`。→ [02-stream-strategies.md](02-stream-strategies.md)
- **入站去重提前占坑**：`InboundMessage.dedupe_claimed` + `MessageBus.claim_inbound()` / `release_inbound_claim()`，供有平台副作用的适配器（Discord 建 thread）在副作用前占键。→ [01-message-bus.md](01-message-bus.md)
- **入站暂存文件清理**：`INBOUND_FILE_CLEANUP_KEY = "_cleanup"` + `cleanup_inbound_files()`，把清理责任交还适配器并等待其落地。→ [01-message-bus.md](01-message-bus.md)
- **QQ 通道**：见上节。
- **WeChat 扫码引导登录**：`wechat_qr_login.py` 进程内单会话，浏览器发起、服务端轮询，**bot 凭据从不离开服务端**；`POST /api/channels/wechat/qr-login` 系列 3 个路由。→ [05-user-connections.md](05-user-connections.md)
- **Feishu 澄清按钮卡片**：`feishu_card_interaction.py`，默认关闭，需控制台订阅 `card.action.trigger` 并发布新版本。→ [02-stream-strategies.md](02-stream-strategies.md)
- **凭据加密**：`DEER_FLOW_CREDENTIALS_KEY`（`deerflow/config/credentials_key.py`）+ `channel_runtime_configs` 密文行。→ [05-user-connections.md](05-user-connections.md)
- **线程绑定存储改为协议 + SQL 实现**：`ChannelStore` 协议 / `SqlChannelStore` / `JsonChannelStore`，`claim_thread_id()` 插入-若缺。→ [03-thread-mapping.md](03-thread-mapping.md)
- **宿主自撰文案本地化**：`reply_locale.py`（`/connect`、`/goal` 回复跟绑定者 Web UI 语言）+ `goal_status.py`（`/goal` 文案）。`/goal` 命令本身也是本窗口新增。
- **新命令 `/model`**：`KNOWN_CHANNEL_COMMANDS` 增加 `/model`（`commands.py`）。

## 启动流程

```
Gateway lifespan()
  → ChannelService.from_app_config(config)
    → 读取 config.yaml channels: section
    → channels.leader_lease 段单独校验（restart-required）
    → resolve_runtime_config_store()（有数据库则 SQL 密文存储）
    → 多进程且租约生效时构造 ChannelLeadership
    → resolve_class() 懒加载每个 channel
    → 为每个启用的 channel 创建实例（无租约者跳过传输）
    → ChannelManager.start() — 启动固定 worker pool
  → 各 channel.start() — 建立平台连接

Shutdown:
  → ChannelService.stop() — 有界超时
  → ChannelManager.stop()：关准入 → 排空已接受队列（shutdown_grace_period_seconds）
    → 取消 worker → 丢弃剩余入站（清理暂存文件、归还去重键）
  → 各 channel.stop() — 断开平台连接（SDK 私有 loop 有界关闭）
```

## 源码索引

> 数字口径：本表行数为 **v2.2.0 基线实测**（`wc -l`，`backend/` 下路径省略前缀）。

| 文件 | 行数 | 职责 |
|------|------|------|
| `app/channels/base.py` | 605 | `Channel` 抽象基类；`ChannelUnavailable` / `ChannelStopTimeout` / `shutdown_private_loop()` / `abort_connection_transport()` / 附件投递反馈 🆕 |
| `app/channels/message_bus.py` | 432 | `MessageBus` pub/sub；有界入站准入 + reservation + `InboundClaim` 🆕 |
| `app/channels/manager.py` | 4162 | `ChannelManager` 核心调度；worker pool + 幂等准入 + 跟进缓冲 |
| `app/channels/capabilities.py` | 43 | 🆕 `CHANNEL_CAPABILITIES` 能力表（10 项）+ `supports_proactive_notifications()` / `supports_proactive_group_notifications()` |
| `app/channels/leadership.py` | 225 | 🆕 per-provider 传输 leader 租约（`ChannelLeadership`、`RenewOutcome`、fail-closed 续约） |
| `app/channels/store.py` | 436 | Channel↔Thread 映射：`ChannelStore` 协议 / `SqlChannelStore` / `JsonChannelStore` + `import_legacy_json()` |
| `app/channels/service.py` | 1247 | `ChannelService` 生命周期 + 租约监督 `_supervise()` + 运行时配置下发 |
| `app/channels/commands.py` | 91 | 已知命令集（含 `/agent`、`/goal`、`/model` 🆕） |
| `app/channels/run_policy.py` | 130 | `ChannelRunPolicy` 注册表（per-channel 流式/串行/fire-and-forget/`interaction_mode` 🆕） |
| `app/channels/allowed_users.py` | 111 | 🆕 `parse_allowed_users()` — 各通道 allowlist 的统一解析（fail closed 语义） |
| `app/channels/reply_locale.py` | 107 | 🆕 宿主自撰回复的语言（`ReplyLocaleResolver` / `connect_reply_text()`） |
| `app/channels/goal_status.py` | 125 | 🆕 `/goal` 的 IM 文案（对齐 Web 端 goal bar） |
| `app/channels/notification_groups.py` | 87 | 🆕 通知群目的地校验（Feishu 群 / QQ 群 / 显示名截断） |
| `app/channels/inbound_files.py` | 41 | 🆕 入站 URL 附件的字节上限与暂存命名（`MAX_INBOUND_URL_FILE_BYTES` 50 MB） |
| `app/channels/credential_staging.py` | 56 | 🆕 运行时凭据暂存文件的清理扫描（`cleanup_stale_credential_staging()`） |
| `app/channels/sandbox_files.py` | 52 | 入站附件→沙箱同步（非释放沙箱 client lease，防并行 run 关闭共享 client；`release_on_last` 🆕） |
| `app/channels/connection_identity.py` | 61 | 把持久化的连接所有权归到入站消息；`lookup_thread_id()` 🆕 |
| `app/channels/feishu.py` | 2051 | 飞书/Lark（SDK 私有 loop 有界关闭、未解析绑定延后路由、卡片交互） |
| `app/channels/feishu_card_interaction.py` | 283 | 🆕 澄清按钮卡片（`MAX_CARD_OPTIONS = 4`、`PENDING_CARD_TTL_SECONDS = 30*60`） |
| `app/channels/feishu_run_policy.py` | 15 | 飞书 run 策略（`serialize_thread_runs=True`） |
| `app/channels/slack.py` | 786 | Slack |
| `app/channels/telegram.py` | 1310 | Telegram |
| `app/channels/dingtalk.py` | 1372 | 钉钉 |
| `app/channels/discord.py` | 1338 | Discord |
| `app/channels/wecom.py` | 817 | 企业微信（出站 20480 UTF-8 字节协议上限） |
| `app/channels/wechat.py` | 1929 | 微信 |
| `app/channels/wechat_qr_login.py` | 225 | 🆕 浏览器扫码引导登录（`WechatQRLogin`，进程内单会话） |
| `app/channels/qq.py` | 611 | 🆕 QQ 开放平台机器人（C2C + 群 @，WebSocket，无公网回调） |
| `app/channels/buzz.py` | 1749 | Buzz（Nostr relay，NIP-42 认证） |
| `app/channels/buzz_nostr.py` | 201 | NIP-01 事件签名/验证（BIP-340 Schnorr） |
| `app/channels/buzz_run_policy.py` | 12 | Buzz run 策略（`serialize_thread_runs`） |
| `app/channels/buzz_seen_events.py` | 398 | 连接层 seen-id 持久去重（`BuzzSeenEventStore`，事件循环外读写） |
| `app/channels/dedupe_store.py` | 309 | 入站消息去重存储（Memory/Postgres 两级） |
| `app/channels/runtime_config_store.py` | 531 | UI 录入的 channel 配置持久化：`SqlChannelRuntimeConfigStore`（密文 + version）/ 历史 `ChannelRuntimeConfigStore`（JSON，一次性导入后改名） |
| `app/channels/github.py` | 115 | webhook 驱动的 GitHub 通道（PR/issue 评论；唯一 push 型通道，详见 [../github-integration.md](../github-integration.md)） |
| `deerflow/integrations/lark_cli.py` | 3709 | Lark CLI 托管集成安装器（27 个 lark-* 技能包） |
| `deerflow/integrations/lark_broker.py` | 554 | Pattern B 凭据 broker（沙箱侧 sidecar） |
| `app/gateway/routers/channels.py` | — | Channel 状态/重启 API（63 行） |
| `app/gateway/routers/channel_connections.py` | — | 绑定/运行时配置/扫码登录 API（850 行） |
| `app/gateway/app.py` | — | lifespan 启动入口（`_load_credentials_cipher`） |
