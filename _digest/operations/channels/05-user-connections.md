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

---
> **See also:** [IM 通道系统全景](00-overview.md) · [Channel Manager 调度](01-message-bus.md) · [API Reference](../../operations/app-layer/01-api-reference.md)
