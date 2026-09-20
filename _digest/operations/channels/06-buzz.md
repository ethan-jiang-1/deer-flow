---
title: "Buzz 频道 — Nostr relay 上的身份验证与去重"
description: "Buzz 是 DeerFlow 的 Nostr（NIP-01/NIP-42）IM 通道：一条经 BIP-340 签名验证的 WebSocket 接入 relay，pubkey allowlist + 三重闸门入站，kind-40003 原地编辑流式出站。"
topics: [channels, im, buzz, nostr, nip-01, nip-42, bip-340, dedupe]
---

# Buzz 频道 — Nostr relay 上的身份验证与去重

> 同步 #4（e5c62cab）新增。Buzz 让 DeerFlow 成为某个 Nostr relay 上 **workspace 的成员**——用户通过 Buzz 的聊天界面发消息，DeerFlow 作为成员回复。与 Feishu/Slack 等"机器人接入平台"不同，Buzz 的一切都发生在 **relay 协议层**：身份是 pubkey（BIP-340 Schnorr 签名），消息是不可变公开事件，频道订阅按 `#h` 过滤。

## 与其它通道的根本差异

| 维度 | 传统通道（Feishu/Slack…） | Buzz |
|------|---------------------------|------|
| 连接 | 平台 WebSocket / long-polling | 单条 **NIP-42 认证** WebSocket → relay |
| 身份 | 平台账号 + 平台签名 | **pubkey**（BIP-340 Schnorr，relay 无法伪造） |
| 消息模型 | 可编辑/可撤回 | **不可变公开 Nostr 事件**（流出即泄露，无法撤回） |
| 订阅 | 平台按会话分发 | **channel-scoped REQ**（`#h:[uuid]`），relay 只给该频道订阅推 kind-9 |
| 去重 | manager 内存 | 两级 store：进程内 OrderedDict / Postgres 条件 upsert |
| 流式 | 编辑同一条消息 | **kind-40003 原地编辑**（每条更新都是新事件） |

## 核心文件

| 文件 | 行数 | 职责 |
|------|------|------|
| `app/channels/buzz.py` | 1413 | BuzzChannel：连接、订阅恢复、入站闸门、出站流式 |
| `app/channels/buzz_nostr.py` | ~200 | 纯 NIP-01 工具：bech32、事件签名/验证（BIP-340） |
| `app/channels/buzz_run_policy.py` | 12 | run 策略注册（import side-effect） |
| `app/channels/dedupe_store.py` | 277 | 入站去重存储（Memory/Postgres，issue #4120） |
| `app/channels/buzz_seen_events.py` | 385 | 连接层 seen-id 持久去重（`BuzzSeenEventStore`，issue #4888；🆕 同步 #6 落盘移出事件循环 #5103） |

## Nostr 协议层（`buzz_nostr.py`）

纯函数、无 I/O、无 wall-clock（`created_at` 由调用方传入），BIP-340 走可选的 `coincurve`（`buzz` extra，懒加载）。

- **Key 解析**：`parse_private_key()` 接受 64-hex 或 bech32 `nsec1...`，派生压缩 pubkey（32 字节 x-only）；`parse_pubkey()` 接受 64-hex 或 `npub1...`。bech32 校验（polymod + checksum）在纯 Python 实现。
- **事件 id（NIP-01）**：`event_id()` 对 `[0, pubkey, created_at, kind, tags, content]` 做 `json.dumps(separators=(",", ":"), ensure_ascii=False)` 后 SHA-256——**规范序列化**（分隔符紧凑、非 ASCII 不转义）是 id 稳定性的前提。
- **事件类型（kind）**：

| kind | 常量 | 用途 |
|------|------|------|
| 9 | `KIND_CHAT` | 聊天消息（`h` tag 限定频道，`e` tag 引用回复目标，`p` tags 提及） |
| 40003 | `KIND_EDIT` | 流式原地编辑（relay 用它替换已发布的 kind-9 渲染） |
| 22242 | `KIND_AUTH` | NIP-42 认证（`relay` + `challenge` tags） |
| 39000 | `KIND_CHANNEL_META` | 频道元数据（relay 成员都可签名发布） |
| 44100 / 44101 | `KIND_MEMBER_ADDED/REMOVED` | relay 签名的成员增删通知（`p` = 受影响成员，`h` = 频道 uuid） |

- **BIP-340 签名**：`sign_event()` 用 `coincurve.PrivateKey.sign_schnorr(eid)` 签事件 id；`verify_event()` 是**入站信任锚点**——(1) 从事件自身字段重算 NIP-01 id 必须等于声称的 `id`（防止借用合法事件的 id 换 payload），(2) 用 `PublicKeyXOnly(pubkey).verify(sig, id)` 验证 Schnorr 签名真正绑定作者。**Total：任何畸形输入返回 `False`，绝不抛异常**——"malformed" 和 "forged" 在调用侧等价，无需 try/except。布尔是 int 子类，JSON `true` 会被拒绝（防止规范序列化漂移）。

## 连接与订阅模型（`buzz.py`）

一条连接开三类订阅。**关键发现（实测验证）**：relay 只把 kind-9 聊天事件 fan 给 **channel-scoped** 订阅——`REQ {"kinds":[9]}`（全局）会被接受并回 `EOSE`，但永远收不到事件（已对活 relay 证明）；`REQ {"kinds":[9],"#h":[uuid]}` 才工作；多值 `#h` 不匹配。所以**一个频道恰好一条 chat 订阅**（与 Buzz 自己的 agent harness 一致）。

```
连接建立
  ├─ REQ "buzz-discovery"   kinds:[39000]             ← 历史查询：这条身份属于哪些频道（EOSE 即完整性屏障）
  ├─ REQ "buzz-membership"  kinds:[44100,44101] #p:<us> since:<connect − 60s>   ← 实时成员变动
  └─ per discovered channel：REQ "buzz-chat-<uuid>"  kinds:[9] #h:[uuid]         ← 每频道一条
```

- **membership 订阅是 LIVE-scoped，且这是 load-bearing**：relay *存储* 44100/44101 并 newest-first 服务（默认上限 2000）。不加 `since` 会把整段成员历史当 live 重放——每条"你被加入"触发一次 discovery、每条"你被移除"临时退订仍在的频道（实测：一次连接 M+1 次 discovery 重放）。`since` 锚定在 socket 打开时刻减 `MEMBERSHIP_LOOKBACK_SECONDS`（60s）的 slack，覆盖 relay 时钟偏差和握手期间的成员变更。
- **频道发现是完备性屏障**：discovery 的 `EOSE` 到达后，重试任何失败/尚未打开的 chat 订阅；discovery 一个频道都没有时报警告。kind-44100（自己的 pubkey）**实时**订阅新频道，然后仅在元数据缺失时才补 discovery（无条件刷新会在 44100 突发时放大成 N 次 discovery）；kind-44101 发 `buzz_nostr.close_frame` 精确退订该频道并删元数据缓存。

## NIP-42 认证

- 连接先开控制订阅（万一 relay 允许未认证读），关闭的 relay 回 `auth-required:` + `AUTH` challenge，认证分支再重开所有订阅。
- `auth-required:` **在握手完成前是预期引导序列而非拒绝**——`_session` 用 `_auth_completed` 标志（发送签名 AUTH 事件后置位）区分：前置位按 DEBUG 处理且不消耗重试预算；后置位是真 outage，保持响亮。
- 每个入站 `EVENT` 在 `handle_relay_frame` 单一入口重算 NIP-01 id + 验证 BIP-340 签名，`pubkey`（allowlist 和 `/connect` 绑定的主体）**不可被 relay 伪造**。

## 信任模型与入站闸门

- **`allowed_users` deny-by-default**（空 = 任何人都不行，与其它通道的空 = 全部人相反）。为空时 `start()` 报警告。
- 三重闸门在 allowlist 之后：**mention / DM / thread-follow**。`/connect <code>` 绑定在闸门前处理。
- **残余信任面（已文档化）**：kind-39000 频道元数据任何成员都可签名。伪造一份 39000 能 (a) 把频道标成 `type:"dm"`（放宽该频道 `require_mention`）(b) 诱导对任意频道开 chat 订阅。但**不会被 acted on**：`allowed_users` + 逐事件签名是独立闸门，诱导订阅只是 relay 把自己的流量读回给一个丢弃它的订阅者，被 `MAX_CHANNEL_SUBSCRIPTIONS`（256，拒绝而非驱逐）封顶。修复需要配置可信 relay pubkey，而 `relay_url` 不是。

## 断线恢复（CLOSED frame 而非被遗忘）

每条订阅都可能被一条 `CLOSED` 帧杀死，且每条死亡都是**静默 outage**（死订阅 = 聋；死 membership = 永远不知道被加/移除；死 discovery = 完整性 sweep 失效）。所以：

- `_handle_closed` 重发 REQ，预算 **`MAX_RESUBSCRIBE_ATTEMPTS`（3）/ 订阅 / 连接 / auth epoch**。首次重试立即；后续退避 1s→2s，内联在 relay 读循环里等待（后台任务会活过自己的 socket）。
- `_is_transient_close` 决定是否重试：NIP-01/42 前缀 `auth-required:/restricted:/blocked:/mute:/invalid:/pow:` 和 buzz-relay 的撤销散文（`revoke`/`not a member`/`archiv`/`not found`…）是**永久**——不与 relay 对着干；`rate-limited:/error:/无原因` 及任何未识别理由**默认暂态**——**朝着"继续听"收敛**，因为最坏失败是悄悄变聋，重试预算兜底猜错。
- chat 订阅的 `CLOSED` **只对已在 `_chat_subscriptions` 中的频道恢复**——`CLOSED` 是 relay 供应的，对未知频道动作用户会让 relay 仅凭命名就诱导订阅。
- 每个无人监听的订阅都记 **WARNING**，永不是 INFO——"听不到任何东西"不能再与"没人说话"不可区分。

## 去重存储（`dedupe_store.py`，issue #4120）

manager 层的入站去重（`_inbound_dedupe_key` = `(channel, workspace_id, chat_id, message_id)`）防 provider 重投。两级实现：

| Store | 语义 | 并发 |
|------|------|------|
| **`MemoryInboundDedupeStore`** | `OrderedDict[key, monotonic_ts]`，TTL 10min，上限 4096 | 单 pod。插入序 == 时间序，过期/溢出从队首 `popitem(last=False)` O(k) 清理 |
| **`PostgresInboundDedupeStore`** | `webhook_deliveries` 表，`(channel, workspace, chat, message_id)` 唯一 | **多 pod**。单条原子条件 upsert：`INSERT ... ON CONFLICT DO UPDATE SET first_seen=now() WHERE first_seen < now()−TTL RETURNING channel`——无冲突→插入→proceed；冲突+已过期→刷新并 proceed（手动 "Redeliver" 重进）；冲突+存活→无 RETURNING→drop |

- **单条 row-locked upsert 无 TOCTOU 窗口**：两 pod 竞争同一过期 key 不可能同时 proceed（一个赢得 UPDATE，另一个看到新行被 drop）。
- **fail-open**：任何 DB 错误 log + 视为 allow——存储故障绝不丢 webhook / 对 provider 返回 5xx。
- **`make_inbound_dedupe_store()` 解析**：`auto`（默认）→ 应用 DB 是 Postgres 就用共享 store，否则内存 store；多 worker / 多 replica 却只能用内存时发 **WARNING**（跨 pod 去重缺口显式化为 misconfiguration 而非静默）。

## Seen-Event 持久去重（`buzz_seen_events.py`，issue #4888）

manager 层 `dedupe_store` 是**进程内 + 10 分钟 TTL**，补不了「重连/重启后重放」的缺口：resubscribe 的 `since` 是最后处理事件的 `created_at`，而 NIP-01 的 `since` 是**闭区间**，所以每次重连至少重投那一条 watermark 事件——重连距上一条消息超过 10 分钟（或任何一次 Gateway 重启）就会重新回答旧消息。`BuzzSeenEventStore` 在连接层关掉这个缺口：

- **按频道持久化「已完整处理事件」的 id**（JSON 存 `{base_dir}/channels/`，原子写），`_handle_chat_event` 在 `/connect` 分支**之前**丢弃重投 id——否则一条重放的 `/connect` 会被误答成 "code invalid or expired"。
- **只按精确 event id 匹配，绝不按时间戳**：真正的新事件（哪怕 author 选了一秒内的、或有时钟偏差的 `created_at`）总有新 id，永远不会被跳过——保住连接层「fail toward replay」的不变量。
- **只记录完整处理过的事件**（与 watermark 规则镜像）：被闸门 drop 的、或 publish 失败的事件保持可重放。
- **双向 fail-open**：读不了的 store 当空载入（代价是至多一次重放回复，即旧行为）；写失败 log + 下次 flush 重试（代价是重放，永不漏）。
- **有界**：每频道 `MAX_IDS_PER_CHANNEL=512`、频道数 `MAX_CHANNELS=512`（LRU 驱逐）。重启保护因此也是每频道最新 512 条 id——relay 默认 backlog 若更深，超出的尾部仍会重放；真遇到更深的 backlog 需调大该常量。
- **写合并（coalescing）+ 🆕 落盘移出事件循环（#5103）**：`record()` 标脏后每 `FLUSH_DELAY_SECONDS=1.0` 合并一次 flush，重连 backlog 突发只付一次 O(store) 文件写而非每条一次；同步调用方（测试/工具）立即写，`BuzzChannel.stop()` 走 `aflush()` 干净关停。窗口内崩溃只损失重放、不损失跳过。文件 I/O 本身经 **`asyncio.to_thread` 落到 worker 线程**（`aseen`/`arecord` 的加载也一样），不再阻塞事件循环；generation 计数器保住 flush 期间新到的记录——worker 写的是旧快照时，更新的 generation 会被重新排程；Gateway 取消/关停时 in-flight 的 worker 写被 shield 并保留，最终 flush 可重试（超时留下的是一次可重试写而非丢移交）。
- **原子替换 + temp 清理**：`_write_snapshot()` 用同目录 tempfile + `Path.replace()`（与 `ChannelStore` 对齐）；失败时 unlink temp，避免持久写不进去时累积 `*.tmp`。
- **线程模型**：🆕 双锁——`threading.Lock` 保护内存态 + `_load_lock` 保护惰性加载（off-loop 用户与 worker 线程共存后不再"单循环无锁"）；`quiesce()`/`resume()` 让通道 stop 后排空迟到的 seen 事件、重启后恢复记录。`path=None` = memory-only（测试/工具无文件副作用）；真实部署由 `ChannelService` 注入 `seen_event_store_path`（同 `channel_store` 的接线方式）。

## Outbound：不可变事件 + 原地编辑

- 首条 kind-9 聊天事件；流式更新用 **kind-40003 原地编辑**（`e` tag 指向目标事件）。每条流式更新都是不可变公开事件。
- **`_chunk_text`**：按 UTF-8 **编码字节**长度分块（上限 `EDIT_MAX_BYTES=60000`，留出 relay 64KB 编辑内容帽的余量），字符边界整切——split-mid-character 结构上不可能。
- **`send()` 拒绝发布带隐藏 model-context 包装的文本**（`<memory>`、`<durable_context_data>`、`<system-reminder>`——`_HIDDEN_CONTEXT_MARKERS`），ERROR log + 在 `is_final` 时清理流式簿记。这是 manager allowlist 之后的纵深防御：Buzz 上泄露是永久的（纠正只改渲染，原始事件留在 relay 上）。按字面 opening tag 匹配——单纯"谈论 memory"的回复仍可发布。

## Run 策略（`buzz_run_policy.py`）

```python
CHANNEL_RUN_POLICY["buzz"] = ChannelRunPolicy(serialize_thread_runs=True, requires_bound_identity=False)
```

`serialize_thread_runs=True`（Feishu 先例）：同线程快速跟帖进队列排队，而不是触发 busy 回复；`requires_bound_identity=False`：adapter 层的 pubkey allowlist 就是身份闸门，无需绑定身份。

## Watermark（断线续传游标）

- **按频道**，只对实际处理的 `created_at` 前进，**永不越过 `now + MAX_FUTURE_SKEW_SECONDS`（60）**——游标是 peer 供应的，单条未来-dated 事件否则会永久致聋。
- 按频道而非全局是安全关键半：订阅按频道，全局游标 = 任一频道最新事件，繁忙频道会把安静频道的未读拖过去（活 relay 上实测：一个身份的 3 个频道相隔 ~28h）。按频道游标只会造成重复投递（manager 的 `event_id` 去重吸收），被驱逐退化为"无 since"（relay 默认 backlog）——两者都朝重放失败，不朝漏。
- **已知边界（文档化，未修复）**：relay 把历史投递上限 2000 条/订阅，**newest-first**，即使带 `since`。单频道跨一次断连累积 >2000 条未读会丢最旧的——relay 从不发送，watermark 处理较新事件时越过它们。需要断连 + 单频道超 2000 条才触发，关闭它需要 descending `until` 分页 backlog。

## 源码索引

| 机制 | 位置 |
|------|------|
| 常量与恢复逻辑 | `buzz.py:59-248`（EDIT_MAX_BYTES / MAX_FUTURE_SKEW / MAX_RESUBSCRIBE_ATTEMPTS / 隐藏标记 / transient-close 判定） |
| 订阅生命周期 | `buzz.py:_open_control_subscriptions` / `_ensure_chat_subscription` / `_handle_closed` |
| 签名验证 choke point | `buzz.py:handle_relay_frame` → `buzz_nostr.py:verify_event` |
| 出站编辑 | `buzz.py:send` / `_edit_or_repost` / `_chunk_text` |
| 去重存储 | `dedupe_store.py` 全部 |
| seen-id 持久去重 | `buzz_seen_events.py` 全部（`BuzzSeenEventStore`）+ `buzz.py:_handle_chat_event` 接入点 + `service.py` 注入 `seen_event_store_path` |
| run 策略 | `buzz_run_policy.py`（注册为 import side-effect，`manager.py` 导入） |

## 相关

- 频道全景与架构图 → [`00-overview.md`](00-overview.md)
- 入站去重与 dispatch → [`01-message-bus.md`](01-message-bus.md)
- 用户连接 / `/connect` 绑定 → [`05-user-connections.md`](05-user-connections.md)
- 官方配置说明 → `backend/docs/IM_CHANNEL_CONNECTIONS.md`
