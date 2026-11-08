---
title: "生产认证配置"
description: "生产环境 JWT 认证设置的分步指南：环境变量、多用户隔离、Nginx 速率限制。"
topics: [auth, production, security, deployment]
---

# 生产认证配置

## 快速清单

```bash
# 1. 认证默认就是开启的（不存在"启用认证"的开关变量）。
#    仅本地/E2E 调试用下面这个关闭认证（生产禁用，见下文风险）：
#    export DEER_FLOW_AUTH_DISABLED=1

# 2. JWT 签名密钥（自动生成不安全——生产必须手动设）
export AUTH_JWT_SECRET="$(openssl rand -base64 64)"

# 3. 内部服务间通信 token（多 worker 必须设为相同值）
export DEER_FLOW_INTERNAL_AUTH_TOKEN="$(openssl rand -base64 32)"

# 4. 前端 session 加密（与 JWT 是不同密钥）
export BETTER_AUTH_SECRET="$(openssl rand -base64 64)"

# 5. CORS（设为前端实际域名，不要用 *）
export GATEWAY_CORS_ORIGINS="https://deerflow.yourcompany.com"

# 6. 如果有反向代理（正确获取客户端 IP）
export AUTH_TRUSTED_PROXIES="10.0.0.0/8,172.16.0.0/12"

# 7. 关闭 API 文档公开访问
export GATEWAY_ENABLE_DOCS=false
```

**重启 Gateway 后生效**（auth 配置非热加载）。

## 用户管理

每个团队成员通过 Web UI 注册（`/login` 页面的注册流程），或通过 API：

```bash
curl -X POST https://deerflow.yourcompany.com/api/v1/auth/register \
  -H "Content-Type: application/json" \
  -d '{"email": "user@company.com", "password": "strong-password"}'
```

首次部署时访问 `/setup` 创建管理员账户。

## 隔离机制

认证启用后自动生效——无需额外配置：

```
.deer-flow/users/{user_id}/
├── memory.json          ← 每个用户独立
├── agents/{name}/       ← 每个用户独立
└── threads/{tid}/       ← 每个用户独立
```

从无认证迁移：运行 `python scripts/migrate_user_isolation.py --user-id USER_ID`。

## Nginx 速率限制

保护 `/api/v1/auth/login` 端点：

```nginx
limit_req_zone $binary_remote_addr zone=login:10m rate=5r/m;
location /api/v1/auth/login {
    limit_req zone=login burst=3 nodelay;
    proxy_pass http://gateway:8001;
}
```

## 权限模型

所有已认证用户自动获得全部 6 项权限（`threads:read/write`、`agents:read/write`、`memory:read/write`）。

## 内部 Token 说明

`DEER_FLOW_INTERNAL_AUTH_TOKEN` 用于 IM channel worker 回调 Gateway。单 worker 自动生成即可。**多 worker 必须手动设相同值**，否则来自其他 worker 的内部请求会被拒。

## 多 worker 注意事项

- 登录速率限制是进程内内存字典——同一 IP 打不同 worker 可以绕过。生产建议在 Nginx 层加 `limit_req_zone`
- JWT 密钥在所有 worker 间必须一致
- 内部 token 在所有 worker 间必须一致

## 另外两块凭据（PAT 与 IM 连接凭据）

- **Personal Access Token（PAT）**：迁移 `0017_personal_access_tokens` 建表；**明文 token 不落库**，只存 SHA-256 digest（与 `token_digest` 唯一索引），认证时摘要比对，过期在**读取时**判定（不靠后台任务）。仓储契约见 [01-auth.md](01-auth.md) 的「仓储层契约」一节。
- ⚠️ **IM channel 凭据加密尚未接线（v2.1.0 源码现状）**：`ChannelCredentialCipher`（Fernet，密钥由 `sha256(key)` 派生）已实现、`channel_credentials` 表也已建好，但生产构造点 `app/channels/service.py:110` 与 `app/gateway/routers/channel_connections.py:204` **都不传 `cipher`**——因此生产路径下 `repository.get_credentials()` 恒为 `None`（Slack 回落到 operator bot token），`store_credentials()` 会抛 `RuntimeError`。这是"已建表、已实现、尚未接线"的事实记录，不是配置项缺失；排障时不要把它当成密钥没配。详见 [../channels/05-user-connections.md](../channels/05-user-connections.md)。

## 环境变量参考

| 变量 | 用途 | 默认 |
|------|------|------|
| `DEER_FLOW_AUTH_DISABLED` | **关闭**认证（仅本地/E2E；`DEER_FLOW_ENV`/`ENVIRONMENT` 为 `prod`/`production` 时被忽略） | 未设（= 认证开启） |
| `AUTH_JWT_SECRET` | JWT HS256 签名密钥 | 自动生成到 `.jwt_secret` |
| `DEER_FLOW_INTERNAL_AUTH_TOKEN` | 内部服务 token | 自动生成 `secrets.token_urlsafe(32)` |
| `BETTER_AUTH_SECRET` | 前端 session 加密 | — |
| `GATEWAY_CORS_ORIGINS` | 允许的 CORS 来源 | — |
| `AUTH_TRUSTED_PROXIES` | 受信任的反向代理 IP | — |
| `GATEWAY_ENABLE_DOCS` | 公开 `/docs`、`/redoc` | true |
