---
title: "用户 IM 频道连接"
description: "浏览器端用户将自己的 IM 账号绑定到 DeerFlow 的连接管理流程：bind code 生命周期、single-active-owner 转移、provider 差异。"
topics: [channels, im, user-connections, oauth]
---

# 用户 IM 频道连接

这是 **用户拥有的** IM 频道绑定层，不同于 `operations/channels/` 中描述的 server-side channel workers。Workers 是运维配置的机器人长期轮询；Connections 是用户通过浏览器将自己的个人 IM 账号绑定到 DeerFlow。

## 架构

```
浏览器 (User A)                        IM Platform                    Channel Worker
     │                                     │                               │
     │  POST /api/channels/slack/connect   │                               │
     │  → Gateway 生成 bind code           │                               │
     │     (secrets.token_urlsafe(16))     │                               │
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

- **生成**：`secrets.token_urlsafe(16)` → 存在 `channel_oauth_states` 表中，TTL 600s
- **消费**：IM worker 收到 `/connect <code>` → `consume_oauth_state(code)` → 一次性使用后删除
- **安全模型**：bind 的安全不靠 `allowed_users`（那只是普通消息的过滤器）。Bind code 的机密性才是真正的防线——只有从浏览器发起连接的用户才看得到 code

### Single-Active-Owner 转移

一个外部 IM 身份 `(provider, external_account_id, workspace_id)` 同一时间只有一个 owner：

- `upsert_connection` 在新 bind 成功时撤销其他 owner 的同一身份 active 行
- 数据库层 `uq_channel_connection_active_identity` partial unique index 强制执行（`WHERE status != 'revoked'`）
- 并发 connect 的 loser 重试时看到新 state

### Provider 差异

| Provider | Bind 方式 | 说明 |
|----------|----------|------|
| **Telegram** | Deep-link `/start <code>` | 通过现有 long-polling worker 接收 |
| **Slack** | `/connect <code>` | 通过现有 outbound worker 接收 |
| **Discord** | `/connect <code>` | 同上 |
| **Feishu/Lark** | `/connect <code>` | 同上 |
| **DingTalk** | `/connect <code>` | 同上 |
| **WeChat** | `/connect <code>` | 同上 |
| **WeCom** | `/connect <code>` | 同上 |

**Buzz 不在连接模型里**（sync #4）：Buzz 的 run 策略声明 `requires_bound_identity=False`——身份闸门是 adapter 层（pubkey allowlist）而非绑定身份，所以不走 `/connect <code>` 流程。详见 [06-buzz.md](06-buzz.md)。

所有 provider 都复用现有的 channel workers——不需要额外的 public IP、OAuth callback URL 或 webhook route。

### 连接后

- `owner_user_id` 成为 DeerFlow run 的 `user_id`
- 原始 IM 用户 ID 变为 `channel_user_id`（通过 runtime context 传递，暴露为 sandbox 环境变量 `DEERFLOW_CHANNEL_USER_ID`）
- Inbound 消息携带 `connection_id` + `owner_user_id` + `workspace_id`

### Lark/Feishu 凭据切换不丢密钥（#4820）

Lark CLI 托管集成的 per-user 凭据切换（`POST /api/integrations/lark/config/credentials`）是原子操作：

- 先用官方 CLI 的 live tenant-token 探针**校验**新 `app_id`/`app_secret`，校验通过才落盘——切换失败时**恢复先前的凭据树**，已有的 app secret 与 OAuth tokens 原样保留
- 切换成功才撤销（revoke/remove）旧 OAuth tokens；配置与授权流共享 server 签发的 per-user generation（存于凭据锁下），被拒绝的直接切换不动 generation，过期的完成请求返回 409

## API

| 操作 | Endpoint |
|------|----------|
| 列出 provider | `GET /api/channels/providers` |
| 列出我的连接 | `GET /api/channels/connections` |
| 发起绑定 | `POST /api/channels/{provider}/connect` |
| 撤销绑定 | `DELETE /api/channels/connections/{connection_id}` |

## 数据库

`channel_connections`、`channel_credentials`、`channel_oauth_states`、`channel_conversations` 四张表由 Alembic 管理，通过 `persistence/channel_connections.py` 访问。

## 仓储层契约（`ChannelConnectionRepository` / `ChannelCredentialCipher`）

仓储定义在 `deerflow/persistence/channel_connections/sql.py`（类 `ChannelConnectionRepository` 起于 `sql.py:58`），ORM 在 `model.py`。**每个方法各开一个短 session**，不共享事务；`close()` 只是转调 `persistence.engine.close_engine()`（`sql.py:70`）。

### 表与唯一约束（`model.py`）

| 表 | 约束/要点 | 含义 |
|----|-----------|------|
| `channel_connections` | `uq_channel_connection_owner_provider_identity`(owner_user_id, provider, external_account_id, workspace_id) | 同一 owner 的同一身份只有一行；`external_account_id`/`workspace_id` 是 `NOT NULL default ""`，因为 **NULL 不能进唯一索引**——仓储在写入前统一把空值归一为 `""`（`_normalize_optional_identity`，`sql.py:80`；`upsert_connection` 在 `:125-126`，`find_connection_by_external_identity` 在 `:492-493`） |
| `channel_connections` | `uq_channel_connection_active_identity`(provider, external_account_id, workspace_id) partial unique `WHERE status != 'revoked'`（`model.py:54-62`） | 单一 active owner 的 DB 兜底；SQLite ≥3.8 与 Postgres 都支持 partial index |
| `channel_connections` | `idx_channel_connections_event_lookup`(provider, workspace_id, bot_user_id) | 事件入站按机器人身份反查连接 |
| `channel_credentials` | PK = `connection_id`，FK → `channel_connections` `ON DELETE CASCADE` | **1:1 可选凭据行**；三列 `encrypted_*` + `version`（每次 `store_credentials` +1） |
| `channel_oauth_states` | PK = `state_hash` | 明文 bind code **从不落库**，只存 `sha256(state).hexdigest()`（`hash_state`，`sql.py:282-284`） |
| `channel_conversations` | `uq_channel_conversation_connection_external`(connection_id, external_conversation_id, external_topic_id) | `external_topic_id` 缺省归一为 `""`（`sql.py:512`、`:547`），同样是为了让 NULL 可参与唯一键 |

### `upsert_connection`：owner 转移与重试

`sql.py:110`。写入前若本次 `status == "connected"`，**先** revoke 其他 owner 在同一 `(provider, external_account_id, workspace_id)` 上的非 revoked 行并删除其 credential 行（`_revoke_other_active_owners`，`:137-154`），这样 flush 自己这行时 partial unique index 已经满足（注释 `:168-170`）。并发 loser 命中 `IntegrityError` → rollback → **最多重试 3 次**（`_UPSERT_MAX_ATTEMPTS`，`:32`），每轮重读已可见状态再 revoke+写；3 次后 re-raise 最后一次异常（`:185-192`）。「latest successful bind wins」的所有权转移语义就落在这里。

### `ChannelCredentialCipher`：加解密契约

| 维度 | 契约 | 证据 |
|------|------|------|
| 密钥来源 | `from_key(key: str)`：`sha256(key.encode())` 的 digest 直接 `urlsafe_b64encode` 成 Fernet key。**没有 KDF / salt / 迭代**，强度完全等于调用方 key 的熵 | `sql.py:41-44` |
| 密文格式 | `"fernet:v1:" + Fernet token`（ASCII）。`decrypt_text` 用 `removeprefix` 容忍无前缀的裸 token；`None` 进出都是 `None` | `:46-55` |
| 落库字段 | `encrypted_access_token` / `encrypted_refresh_token`；`extra` 先 `json.dumps(..., ensure_ascii=False)` 再加密进 `encrypted_extra_json`；OAuth 的 `code_verifier` 走同一 cipher 存 `channel_oauth_states.code_verifier_encrypted`（`_encrypt_optional_secret`，`:89-94`） | `:248-253`、`:303` |
| 无密钥时的失败模式 | `store_credentials()` 与 `_encrypt_optional_secret()` 在 `cipher is None` 时抛 `RuntimeError("channel connection encryption key is required")`；`get_credentials()` **不抛、返回 `None`**（凭据按不可用处理） | `:89-94`、`:241-242`、`:258-259` |
| 解密失败的失败模式 | 捕获 `InvalidToken` / `UnicodeError` / `JSONDecodeError`，记 WARNING 后返回 `None`——密钥轮换或密文损坏表现为"凭据不可用"，不会让请求报错 | `:264-280` |
| 消费方 | 唯一读取点是 Slack 的 per-connection `WebClient`（`app/channels/slack.py:243`）；取不到 token 就回落 operator bot token——与"corrupt stored credentials 视为 unavailable"一致 | — |

> ⚠️ **源码现状（事实记录，非设计意图推断）**：`ChannelConnectionRepository` 的生产构造点 `app/channels/service.py:110` 与 `app/gateway/routers/channel_connections.py:204` **都没有传 `cipher`**，所以生产路径下 `get_credentials()` 恒为 `None`、`store_credentials()` 会抛 `RuntimeError`；`ChannelCredentialCipher.from_key()` 目前只在测试中出现。凭据表与加密列因此处于「已建表、已实现、尚未接线」的状态。

### 其余方法契约

| 方法 | file:line | 契约 |
|------|-----------|------|
| `list_connections` | `:194` | owner-scoped，按 `updated_at desc, id desc` |
| `disconnect_connection` | `:199` | owner-scoped；把行置 `revoked` 并删除 credential 行；非 owner/不存在返回 `False` |
| `disconnect_provider_connections` | `:212` | 实例级 provider 移除：批量 revoke 所有非 revoked 行 + 删凭据，返回影响行数 |
| `store_credentials` | `:230` | 按 `connection_id` upsert 单行；`version` 自增；必须已装配 cipher |
| `create_oauth_state` | `:286` | 单次插入 `state_hash` 行（不走 cap 校验的入口） |
| `create_oauth_state_within_cap` | `:314` | per-`(owner, provider)` 待处理上限的**原子**实现：同一事务里"删本 owner 本 provider 的过期码 → count(未消费且未过期) → 插入"；Postgres 先取 `pg_advisory_xact_lock(sha256(owner\x00provider)[:8] & 0x7FFF…FFFF)`（`_oauth_scope_lock_key`，`:400-404`），SQLite 靠前导 DELETE 取得的写锁串行化（`:343-348` 注释）；达到上限 rollback 返回 `False`。调用方 `_create_state`（`routers/channel_connections.py:337-350`）把 `False` 翻成 **429** |
| `consume_oauth_state` | `:438` | 先全局删除过期行，再按 `state_hash` 读；要求 `provider` 相符、未消费、未过期；用条件 UPDATE（`consumed_at IS NULL`）做**一次性消费**，`rowcount != 1` 即返回 `None`——两个并发 worker 不可能都消费同一 code（`:458-471`）。返回 `owner_user_id`/`provider`/`requested_scopes`/`metadata`/`redirect_after`；**不返回 code_verifier** |
| `delete_expired_oauth_states` | `:406` | 全局清理，返回删除行数 |
| `count_oauth_states` | `:413` | `active_only=True` 时只数未消费且未过期 |
| `find_connection_by_external_identity` | `:480` | 按 `(provider, external_account_id, workspace_id)` + `status == "connected"` 查单行；partial unique index 保证唯一，因此解析结果确定（`updated_at desc` 只是兜底） |
| `set_thread_id` / `get_thread_id` | `:502` / `:537` | SQL 版会话→线程映射（文件版 ChannelStore 见 [03-thread-mapping.md](03-thread-mapping.md)）。键为 `(connection_id, external_conversation_id, external_topic_id or "")`；`set_thread_id` 是 upsert，冲突时改写 `thread_id`/`owner_user_id`/`provider` |

---
> **See also:** [IM 通道系统全景](00-overview.md) · [Channel Manager 调度](01-message-bus.md) · [API Reference](../../operations/app-layer/01-api-reference.md)
