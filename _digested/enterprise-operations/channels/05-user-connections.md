---
title: "用户 IM 频道连接"
description: "浏览器端用户将自己的 IM 账号绑定到 DeerFlow 的连接管理流程：bind code 生命周期、single-active-owner 转移、凭据加密（DEER_FLOW_CREDENTIALS_KEY）、WeChat 扫码登录与 provider 差异。"
topics: [channels, im, user-connections, oauth]
---

# 用户 IM 频道连接

这是 **用户拥有的** IM 频道绑定层，不同于 `enterprise-operations/channels/` 中描述的 server-side channel workers。Workers 是运维配置的机器人长期轮询；Connections 是用户通过浏览器将自己的个人 IM 账号绑定到 DeerFlow。

## 架构

```
浏览器 (User A)                        IM Platform                    Channel Worker
     │                                     │                               │
     │  POST /api/channels/slack/connect   │                               │
     │  → Gateway 生成 bind code           │                               │
     │     (secrets.token_urlsafe)         │                               │
     │     TTL 600s, one-time consume      │                               │
     │← 返回 bind code                     │                               │
     │                                     │                               │
     │  User 在 IM 中发送 /connect <code>  │                               │
     │                                     │  inbound message              │
     │                                     │──────────────────────────────►│
     │                                     │                               │ consume_oauth_state(code)
     │                                     │                               │ → upsert_connection:
     │                                     │                               │   provider=slack
     │                                     │                               │   external_account_id=U123
     │                                     │                               │   owner_user_id=User A
     │                                     │                               │   workspace_id=...
     │                                     │                               │
     │  GET /api/channels/connections      │                               │
     │← status: connected                  │                               │
```

## 关键设计

### Bind Code 生命周期

- **生成**：`secrets.token_urlsafe(...)` → 明文只回给浏览器，库里存 `sha256(state).hexdigest()`（`ChannelConnectionRepository.hash_state()`，`sql.py:336`），TTL 600s（`_STATE_TTL_SECONDS`，`channel_connections.py:34`）
- **消费**：IM worker 收到 `/connect <code>` → `consume_oauth_state(code)` → 一次性使用后删除
- **待处理上限**：每个 `(owner, provider)` 最多 5 个待处理码（`_MAX_PENDING_CONNECT_CODES_PER_PROVIDER`，`channel_connections.py:35`），超限 **429**
- **安全模型**：bind 的安全不靠 `allowed_users`（那只是普通消息的过滤器）。Bind code 的机密性才是真正的防线——只有从浏览器发起连接的用户才看得到 code

### Single-Active-Owner 转移

一个外部 IM 身份 `(provider, external_account_id, workspace_id)` 同一时间只有一个 owner：

- `upsert_connection` 在新 bind 成功时撤销其他 owner 的同一身份 active 行
- 数据库层 `uq_channel_connection_active_identity` partial unique index 强制执行（`WHERE status != 'revoked'`）
- 并发 connect 的 loser 重试时看到新 state

### Provider 差异

| Provider | Bind 方式 | 说明 |
|----------|----------|------|
| **Telegram** | Deep-link `/start <code>` | 通过现有 long-polling worker 接收；`bot_username` 随运行时配置持久化（`apply_runtime_connection_config()`） |
| **Slack** | `/connect <code>` | 通过现有 outbound worker 接收；per-connection `WebClient` 优先用连接自己的凭据（`slack.py:325`） |
| **Discord** | `/connect <code>` | 同上 |
| **Feishu/Lark** | `/connect <code>`（群或私聊） | 私聊绑定同时记录 chat 类型，供主动推送选择收件地址；群绑定可用 `im:chat:read` 取群名 |
| **DingTalk** | `/connect <code>` | 同上 |
| **WeChat** | `/connect <code>` 或 🆕 **浏览器扫码登录** | 扫码路径见下节；per-connection 凭据读取在 `wechat.py:426` |
| **WeCom** | `/connect <code>` | 同上 |
| **QQ** 🆕 | `/connect <code>` | `auth_mode: "binding_code"`（`channel_connections.py:120`）；群绑定 `workspace_id` 形如 `<app_id>:group:<group_openid>` |

**Buzz 不在连接模型里**：Buzz 的 run 策略声明 `requires_bound_identity=False`（`buzz_run_policy.py:9`）——身份闸门是 adapter 层（pubkey allowlist）而非绑定身份，所以不走 `/connect <code>` 流程。详见 [06-buzz.md](06-buzz.md)。

所有 provider 都复用现有的 channel workers——不需要额外的 public IP、OAuth callback URL 或 webhook route。`_PROVIDER_META` 表（`channel_connections.py:115-125`）共 9 项，`buzz` 虽有元数据但策略上不做绑定校验。

### WeChat 扫码引导登录 🆕

`app/channels/wechat_qr_login.py`（225 行）让管理员在浏览器里扫码把 WeChat iLink 机器人接上，**凭据从不离开服务端**：

- `WechatQRLogin` 持有**进程内单会话**（`_Session`，id 来自 `secrets.token_urlsafe(32)`，`expires_at = monotonic() + 180`），状态机 `pending → scanned → verification_required → confirmed`（终态还有 `expired` / `failed`）。
- 路由（`channel_connections.py:813-850`）：`POST /api/channels/wechat/qr-login`（开始）、`POST /api/channels/wechat/qr-login/{session_id}/poll`（轮询，可带 `verify_code`，pattern `^[0-9]{1,16}$`）、`DELETE /api/channels/wechat/qr-login/{session_id}`（取消）。三者都要求 **admin**（`_require_wechat_qr_login`，`channel_connections.py:788`）。
- 网络轮询在**mutation 锁之外**执行，使取消能挡住迟到的确认；凭据落地与手工配置/断开共享同一把锁（`WechatQRLogin.mutation()`）。不保留后台任务、打开中的 client 或 token。
- 登录响应里的 `base_url` 只接受 `https://*.weixin.qq.com`（`_wechat_api_url()`，`wechat_qr_login.py:29`）——不可信响应不能把轮询标识或 bot token 重定向到任意主机。
- 错误分类（`WechatQRLoginResponse.error`）：`network` / `invalid_response` / `verification_rejected` / `verification_blocked` / `already_bound`。
- 与运行时配置写路径互斥：WeChat 的 `POST/DELETE /{provider}/runtime-config` 先取同一把 mutation 锁（`channel_connections.py:616,705`），避免扫码结果与手工保存互相覆盖。
- 配置侧另有 `channels.wechat.qrcode_login_enabled`（默认 true）允许首次启动时在缺 `bot_token` 的情况下走 QR bootstrap。

### 连接后

- `owner_user_id` 成为 DeerFlow run 的 `user_id`
- 原始 IM 用户 ID 变为 `channel_user_id`（通过 runtime context 传递，暴露为 sandbox 环境变量 `DEERFLOW_CHANNEL_USER_ID`）
- Inbound 消息携带 `connection_id` + `owner_user_id` + `workspace_id`
- 宿主自撰回复（`/connect` 确认、`/goal` 状态）用 owner 的 Web UI 语言（`reply_locale.py`，见 [03-thread-mapping.md](03-thread-mapping.md)）

### Lark/Feishu 凭据切换不丢密钥（#4820）

Lark CLI 托管集成的 per-user 凭据切换（`POST /api/integrations/lark/config/credentials`）是原子操作：

- 先用官方 CLI 的 live tenant-token 探针**校验**新 `app_id`/`app_secret`，校验通过才落盘——切换失败时**恢复先前的凭据树**，已有的 app secret 与 OAuth tokens 原样保留
- 切换成功才撤销（revoke/remove）旧 OAuth tokens；配置与授权流共享 server 签发的 per-user generation（存于凭据锁下），被拒绝的直接切换不动 generation，过期的完成请求返回 409

## API

| 操作 | Endpoint | 备注 |
|------|----------|------|
| 列出 provider | `GET /api/channels/providers` | 每个 provider 带 `proactive_notifications` / `proactive_group_notifications` 布尔位 🆕 |
| 列出我的连接 | `GET /api/channels/connections` | WeChat 旧绑定的 `metadata.context_token` 被剥离后才返回 🆕 |
| 发起绑定 | `POST /api/channels/{provider}/connect` | 可选 body `group_name`（≤256），不支持群通知的 provider 返回 422 |
| 撤销绑定 | `DELETE /api/channels/connections/{connection_id}` | owner-scoped，204 |
| 保存运行时凭据 | `POST /api/channels/{provider}/runtime-config` | **admin**；凭据密钥不可用返回 503 🆕 |
| 断开运行时凭据 | `DELETE /api/channels/{provider}/runtime-config` | **admin**；返回更新后的 provider 状态 🆕 |
| WeChat 扫码 | `POST/DELETE /api/channels/wechat/qr-login…` | **admin**，见上节 🆕 |

## 数据库

`channel_connections`、`channel_credentials`、`channel_oauth_states`、`channel_conversations` 四张表由 Alembic 管理，通过 `deerflow.persistence.channel_connections` 包访问（`model.py` + `sql.py`）。另有本域新增的 `channel_runtime_configs`（UI 录入的通道配置密文，见下文）与 `channel_leases`（leader 租约，见 [00-overview.md](00-overview.md)）。

## 仓储层契约（`ChannelConnectionRepository` / `ChannelCredentialCipher`）

仓储定义在 `deerflow/persistence/channel_connections/sql.py`（类 `ChannelConnectionRepository` 起于 `sql.py:63`），ORM 在 `model.py`。**每个方法各开一个短 session**，不共享事务；`close()` 只是转调 `persistence.engine.close_engine()`（`sql.py:75`）。

### 表与唯一约束（`model.py`）

| 表 | 约束/要点 | 含义 |
|----|-----------|------|
| `channel_connections` | `uq_channel_connection_owner_provider_identity`(owner_user_id, provider, external_account_id, workspace_id) | 同一 owner 的同一身份只有一行；`external_account_id`/`workspace_id` 是 `NOT NULL default ""`，因为 **NULL 不能进唯一索引**——仓储在写入前统一把空值归一为 `""`（`_normalize_optional_identity`，`sql.py:85`） |
| `channel_connections` | `uq_channel_connection_active_identity`(provider, external_account_id, workspace_id) partial unique `WHERE status != 'revoked'`（`model.py:54-62`） | 单一 active owner 的 DB 兜底；SQLite ≥3.8 与 Postgres 都支持 partial index |
| `channel_connections` | `idx_channel_connections_event_lookup`(provider, workspace_id, bot_user_id) | 事件入站按机器人身份反查连接 |
| `channel_credentials` | PK = `connection_id`，FK → `channel_connections` `ON DELETE CASCADE` | **1:1 可选凭据行**；三列 `encrypted_*` + `version`（每次 `store_credentials` +1） |
| `channel_oauth_states` | PK = `state_hash` | 明文 bind code **从不落库**，只存 `sha256(state).hexdigest()`（`hash_state`，`sql.py:336-337`） |
| `channel_conversations` | `uq_channel_conversation_connection_external`(connection_id, external_conversation_id, external_topic_id)（`model.py:118-123`） | `external_topic_id` 缺省归一为 `""`，同样是为了让 NULL 可参与唯一键 |
| `channel_runtime_configs` 🆕 | PK = `provider` | 一行一个 IM provider 的 web-UI 运行时配置：`config_ciphertext`（整块 JSON 的 `DEER_FLOW_CREDENTIALS_KEY` 密文，断开时为 NULL）、`disconnected`（明文 tombstone）、`version`（每次保存 +1，**行永不删除**所以版本单调） |

### `upsert_connection`：owner 转移与重试

`sql.py:120`。写入前若本次 `status == "connected"`，**先** revoke 其他 owner 在同一 `(provider, external_account_id, workspace_id)` 上的非 revoked 行并删除其 credential 行（`_revoke_other_active_owners`，`sql.py:147`），这样 flush 自己这行时 partial unique index 已经满足。并发 loser 命中 `IntegrityError` → rollback → **最多重试 3 次**（`_UPSERT_MAX_ATTEMPTS`，`sql.py:35`），每轮重读已可见状态再 revoke+写。「latest successful bind wins」的所有权转移语义就落在这里。

### 凭据加密：从 `ChannelCredentialCipher` 到部署级 `DEER_FLOW_CREDENTIALS_KEY` 🆕

v2.1.0 时本节记过一个重要事实：生产构造点没传 `cipher`，凭据表「已建表、已实现、尚未接线」。**v2.2.0 已接线**，并把密钥统一到部署级的 `DEER_FLOW_CREDENTIALS_KEY`（`deerflow/config/credentials_key.py`，165 行）：

| 维度 | 契约 | 证据 |
|------|------|------|
| 密钥来源 | 环境变量 `DEER_FLOW_CREDENTIALS_KEY`（`CREDENTIALS_KEY_ENV_VAR`，`credentials_key.py:39`），**逗号分隔的多个 Fernet key** → `MultiFernet`：第一个负责加密，全部参与解密（即支持轮换）。未设置时自动生成 `{base_dir}/.credentials_key`（0600，文件名 `CREDENTIALS_KEY_FILENAME`，`:40`） | `parse_credentials_keys()`（`:58`）、`load_credentials_cipher()`（`:119`）、`get_credentials_cipher()`（`:152`）、`reset_credentials_cipher()`（`:161`） |
| 密文格式 | `fernet:v2:` 前缀（`CIPHERTEXT_PREFIX`，`:41`）；历史 `fernet:v1:` 仍可读（`LEGACY_CIPHERTEXT_PREFIX`，`:42`） | `CredentialsCipher.encrypt_text()` / `decrypt_text()` / `rotate_text()`（`credentials_key.py:83` 的类，方法在 `:99` / `:102` / `:114`） |
| 历史子类 | `ChannelCredentialCipher(CredentialsCipher)`（`sql.py:38`）只保留旧 API：单 `Fernet` + `from_key()` 的 SHA-256 passphrase 派生（无 KDF/salt/迭代，强度等于调用方 key 的熵）。新值都写 `fernet:v2:`，旧的 `fernet:v1:` 在同 key 下仍可解 | `sql.py:38-59` |
| 启动装载 | `app/gateway/app.py:444` 的 `_load_credentials_cipher()`：只有当 `credentials_key_consumers(config)` 非空时才装载（`channel_connections.enabled=true` 或启用了 refresh-token 型 MCP OAuth，`deps.py:295`），并在 worker 线程里跑（可能要创建 key 文件）；结果写入 `app.state.credentials_cipher`（`app.py:782`）。装载失败只记异常、**不阻止 Gateway 启动**（存储的凭据视为不可用） | — |
| 生产构造点 | `ChannelService._make_connection_repo()`（`service.py:150-168`）传 `cipher=credentials_cipher`；路由侧 `_get_repository()`（`channel_connections.py:225-237`）用 `app.state.credentials_cipher` | — |
| 落库字段 | `encrypted_access_token` / `encrypted_refresh_token`；`extra` 先 `json.dumps(..., ensure_ascii=False)` 再加密进 `encrypted_extra_json`；OAuth 的 `code_verifier` 走同一 cipher 存 `channel_oauth_states.code_verifier_encrypted`（`_encrypt_optional_secret`，`sql.py:94`） | — |
| 无密钥时的失败模式 | `store_credentials()` 与 `_encrypt_optional_secret()` 在 `cipher is None` 时抛 `RuntimeError("channel connection encryption key is required")`；`get_credentials()` **不抛、返回 `None`**（`sql.py:310-312`）。运行时配置写入路径更严格：直接 **503** 并点名 `DEER_FLOW_CREDENTIALS_KEY`（`channel_connections.py:767-772`），避免"跑在没人能看见的凭据上" | — |
| 解密失败的失败模式 | 捕获 `InvalidToken` / `UnicodeError` / `JSONDecodeError`，记 WARNING 后返回 `None`——密钥轮换失配或密文损坏表现为"凭据不可用"，不会让请求报错 | `sql.py:328-334` |
| 消费方 | `app/channels/slack.py:325`（per-connection `WebClient`，取不到 token 就回落 operator bot token）与 `app/channels/wechat.py:426`（per-connection iLink 凭据） | — |
| 多实例约束 | `_enforce_credentials_key()`（`deps.py:321`）：环境变量给了 key 就必须能解析（任何拓扑）；只有在**实例无法共享自动生成的 key 文件**时才对缺失的 key 拒绝启动。`credentials_key_consumers()` 返回的每一项就是拒绝文案里出现的设置名 | — |

### 运行时配置存储（`runtime_config_store.py`，531 行）🆕

Web UI 录入的通道凭据不走 `channel.yaml`，而是落到这里，再覆盖到 `channels.*` 块上：

| 实现 | 存储 | 说明 |
|------|------|------|
| `SqlChannelRuntimeConfigStore`（`runtime_config_store.py:261`） | `channel_runtime_configs` 表 | 每 provider 的整块配置以 `DEER_FLOW_CREDENTIALS_KEY` 密文存储；断开是**无密钥的明文 tombstone**（`disconnected` + `enabled: false`），所以密钥不可用也仍能表达"已断开"。每次保存 `version` +1，leader supervisor 只比数字就能发现别处的保存，无需解密。`can_store_credentials` 属性（`:284`）就是 503 判据 |
| `ChannelRuntimeConfigStore`（`:132`） | 历史 JSON `{base_dir}/channels/runtime-config.json`（明文，0600） | 只给 `database.backend: memory`（单进程，没有东西要共享）用；同时是 SQL 存储**一次性导入**的来源，导入后删除文件（`import_legacy_json()`，`:308`） |

`resolve_runtime_config_store(app_config, *, cipher, ...)`（`:429`）负责选择；`_prepare_runtime_config()`（`service.py:141`）在启动时解析、必要时导入、再 `merge_runtime_channel_configs()` 合并。合并/覆盖的纯函数：`overlay_runtime_channel_configs()`（`:464`，逐键覆盖，`keep_disconnected` 保留 tombstone 以便区分"断开"与"未配置"）、`merge_runtime_channel_configs()`（`:496`）、`apply_runtime_connection_config()`（`:508`，把 Telegram `bot_username` 这类 `channels` 之外的元数据贴回去）。密钥不可用且解密失败时抛 `ChannelRuntimeConfigEncryptionUnavailable`（`:59`），日志在 `:365` / `:373`。

暂存文件（`credential_staging.py`，56 行）：凭据在写入数据库前先落一个暂存文件，启动时 `cleanup_stale_credential_staging()` 扫描并清理崩溃遗留物（`credential_staging_prefix()` 给出前缀）。

### 其余方法契约

| 方法 | file:line | 契约 |
|------|-----------|------|
| `list_connections` | `sql.py:204` | owner-scoped，按 `updated_at desc, id desc` |
| `disconnect_connection` | `sql.py:209` | owner-scoped；把行置 `revoked` 并删除 credential 行；非 owner/不存在返回 `False` |
| `disconnect_provider_connections` | `sql.py:222` | 实例级 provider 移除：批量 revoke 所有非 revoked 行 + 删凭据，返回影响行数 |
| `store_connection_context` | `sql.py:240` | 写入 WeChat 等私有路由 token 的加密副本（浏览器侧读取时被剥离） |
| `store_credentials` | `sql.py:283` | 按 `connection_id` upsert 单行；`version` 自增；必须已装配 cipher |
| `create_oauth_state` | `sql.py:339` | 单次插入 `state_hash` 行（不走 cap 校验的入口） |
| `create_oauth_state_within_cap` | `sql.py:367` | per-`(owner, provider)` 待处理上限的**原子**实现：同一事务里"删本 owner 本 provider 的过期码 → count(未消费且未过期) → 插入"；Postgres 先取 `pg_advisory_xact_lock(sha256(owner\x00provider) 的前 8 字节)`（`_oauth_scope_lock_key`，`sql.py:454`），SQLite 靠前导 DELETE 取得的写锁串行化（`_serialize_oauth_owner_scope`，`sql.py:438`）；达到上限 rollback 返回 `False`。调用方 `_create_state`（`channel_connections.py:358`）把 `False` 翻成 **429**（`:380`） |
| `consume_oauth_state` | `sql.py:491` | 先全局删除过期行，再按 `state_hash` 读；要求 `provider` 相符、未消费、未过期；用条件 UPDATE（`consumed_at IS NULL`）做**一次性消费**，`rowcount != 1` 即返回 `None`——两个并发 worker 不可能都消费同一 code。返回 `owner_user_id`/`provider`/`requested_scopes`/`metadata`/`redirect_after`；**不返回 code_verifier** |
| `delete_expired_oauth_states` | `sql.py:459` | 全局清理，返回删除行数 |
| `count_oauth_states` | `sql.py:466` | `active_only=True` 时只数未消费且未过期 |
| `find_connection_by_external_identity` | `sql.py:533` | 按 `(provider, external_account_id, workspace_id)` + `status == "connected"` 查单行；partial unique index 保证唯一，因此解析结果确定（`updated_at desc` 只是兜底）。`connection_identity.attach_connection_identity()` 用它给入站消息挂 `connection_id` |
| `set_thread_id` | `sql.py:555` | 会话→线程的**重绑定**（`/new`）：upsert，冲突回滚改 update，可转移 `owner_user_id` |
| `claim_thread_id` 🆕 | `sql.py:606` | 会话→线程的**首次绑定**（插入-若缺）：`INSERT ... ON CONFLICT DO NOTHING`，同事务 SELECT 返回胜者 |
| `get_thread_id` | `sql.py:654` | 读回映射（文件版 `ChannelStore` 见 [03-thread-mapping.md](03-thread-mapping.md)） |

---

## 主动推送与通知群 🆕

连接不只用于收消息，也是定时任务推送的目的地：

- **能力门**：`supports_proactive_notifications()` / `supports_proactive_group_notifications()`（`capabilities.py:34,40`）决定 `/providers` 返回的两个布尔位，Settings 页据此标注每张卡。
- **个人通知**：Feishu 等 provider 通过通知 outbox 发静态 Markdown 卡片给任务 owner **当前绑定的用户**；outbox 自带重试、本地化、脱敏与发送时绑定校验。群聊**永不**用于个人通知。仍需 WebSocket 通道在跑（发送走 REST client，无需公网回调或交互卡片订阅）。
- **群通知**：任务可额外选一个已连接的 Feishu / QQ / WeCom 群。任务保存 `notification_group_connection_id`，群通知以该连接 ID 作为 outbox 目标并带 `payload.target_type="group"`；**绝不**从 owner 的全部绑定里推断群目的地。QQ / WeCom 需用户先填群名再生成绑定码（`group_name` 随 `POST /api/channels/{provider}/connect` 存进单次 OAuth state），Feishu 取群名需 `im:chat:read`。每次投递都校验 owner、连接 ID、connected 状态与记录的群/聊天身份（`notification_groups.py`）；绑定丢失不会回落到别的群或私聊。
- **PATCH 语义**：省略该字段保留原值，`null` 清空。

---
> **See also:** [IM 通道系统全景](00-overview.md) · [Channel Manager 调度](01-message-bus.md) · [API Reference](../../enterprise-operations/app-layer/01-api-reference.md)
