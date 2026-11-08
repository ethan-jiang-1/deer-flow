---
title: "生产认证与安全加固"
description: '生产环境 JWT 认证、TLS/安全头、密钥生命周期与备份恢复的分步清单。'
topics: [auth, production, security, deployment]
verified_against: v2.2.0
last_verified: 2026-11-08
---

# 生产认证与安全加固

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

# 4b. 静态加密凭据（MCP OAuth / IM；不设则自动生成 .credentials_key，多副本/重建会丢）
export DEER_FLOW_CREDENTIALS_KEY="$(python -c 'from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())')"

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

所有已认证用户自动获得全部 13 项权限（threads/runs/projects 各 3 + memory 2 + agents 2）；`authorization.enabled: true` 后才按角色收窄。

## 内部 Token 说明

`DEER_FLOW_INTERNAL_AUTH_TOKEN` 用于 IM channel worker 回调 Gateway。单 worker 自动生成即可。**多 worker 必须手动设相同值**，否则来自其他 worker 的内部请求会被拒。

## 多 worker 注意事项

- 登录速率限制是进程内内存字典——同一 IP 打不同 worker 可以绕过。生产建议在 Nginx 层加 `limit_req_zone`
- JWT 密钥在所有 worker 间必须一致
- 内部 token 在所有 worker 间必须一致

## TLS、安全响应头与反向代理

DeerFlow 的 Nginx 只做路由/压缩/SSE 反代，**不终止 TLS，也不注入安全响应头**。生产必须在 Ingress / 负载均衡 / 反向代理层补：

| 项 | 建议 | 说明 |
|----|------|------|
| TLS | 终止在 Ingress/LB，后端走内网 | 不要把明文 2026 直接暴露 |
| HSTS | `Strict-Transport-Security: max-age=31536000; includeSubDomains` | 一旦启用，确认所有子域都支持 HTTPS |
| CSP | 至少 `default-src 'self'`；按前端实际资源放宽 | 前端会加载 SSE、图片、artifact；先 report-only 再 enforce |
| X-Frame-Options / frame-ancestors | `DENY` 或 SAMEORIGIN | 防点击劫持 |
| X-Content-Type-Options | `nosniff` | 与 artifact 强制附件互补 |
| Referrer-Policy | `strict-origin-when-cross-origin` | 减少 URL 泄露 |
| 请求体上限 | 按上传策略设 `client_max_body_size` | 与 `uploads` 配额一致，避免绕过应用层限制 |
| 超时 | SSE/WebSocket 单独放宽；普通 API 收紧 | Nginx 已有 SSE 特殊处理，别把长连接砍断 |

## 密钥与凭据生命周期

| 凭据 | 用途 | 轮换方式 | 注意 |
|------|------|----------|------|
| `AUTH_JWT_SECRET` | JWT HS256 签名 | 换值 + 重启；所有旧 session 失效 | 多 worker 必须一致；不要用自动生成的 `.jwt_secret` 上生产 |
| `DEER_FLOW_INTERNAL_AUTH_TOKEN` | 组件间认证 | 换值 + 重启所有组件 | 多 worker/多服务必须同值；泄露等于全部 IM/default 身份被攻破 |
| `BETTER_AUTH_SECRET` | 前端 session 加密 | 换值 + 重启前端 | 与 JWT 是不同密钥，不要复用 |
| `DEER_FLOW_CREDENTIALS_KEY` | 静态加密 MCP OAuth token / IM 凭据（接线后） | 支持多 key：新 key 在前，旧 key 保留解密，再 `rotate_text` 重写 | 不设则自动生成 `.credentials_key`；多副本/重建会丢，生产必须显式设 |
| `TYPESAFE_API_KEY` / `OPENAI_API_KEY` | Guardrail 风险门 | 按供应商流程轮换 | 风险门会把工具参数发到外部；先做数据保护评估 |
| 模型 provider key | LLM 调用 | 按供应商流程轮换 | 放 `.env`/secret manager，不要进 `config.yaml` 明文 |
| MCP OAuth token | MCP server 认证 | 自动 refresh；`invalid_grant` 要求重新授权 | 静态加密依赖 `DEER_FLOW_CREDENTIALS_KEY` |
| IM channel 凭据 | 飞书/Slack/Telegram 等 | 平台侧轮换 + 更新配置 | ⚠️ `ChannelCredentialCipher` 已实现但生产构造点未接线（见下文），当前不要依赖 DB 加密 |

**轮换纪律**：

1. 先加新 key（`DEER_FLOW_CREDENTIALS_KEY` 支持逗号分隔多 key），保留旧 key 解密；
2. 重启/滚动更新，确认新写入用新 key；
3. 用 `rotate_text` 重写存量密文（或等自然重写）；
4. 观察一个周期后再移除旧 key。

JWT/internal token 没有多 key 兼容，轮换会强制所有 session/组件重连；安排在维护窗口，并先确认没有长跑 run 依赖旧 token。

## 基础设施加固

| 项 | 建议 | 说明 |
|----|------|------|
| **容器权限** | Gateway/前端/Nginx 非 root、`capabilities.drop: ALL`、`no-new-privileges`、seccomp `RuntimeDefault` | Helm chart 已覆盖大部分；Compose 部署要自己补 |
| **Docker socket** | 不挂 `/var/run/docker.sock` 给 Gateway；用 provisioner、rootless Docker 或 socket proxy | socket = host root 等价物，详见 [02-sandbox-isolation.md](02-sandbox-isolation.md) |
| **数据库/Redis** | 不对外暴露；强密码/TLS；只允许 Gateway 网段 | Compose 默认只在内部网络；K8s 用 NetworkPolicy |
| **镜像供应链** | pin digest、镜像扫描、SBOM、非 root、最小化 | 不要用 `latest`；CI 里加 Trivy/Grype |
| **网络分段** | 只有 Nginx/Ingress 对外；Gateway/Frontend/DB 在内网 | egress 也要限制，别让 sandbox 直连内网 |
| **主机与磁盘** | 独立磁盘/配额；日志轮转；监控 inode/磁盘 | Local 模式无 cgroup，资源耗尽会影响 host |
| **审计外送** | gateway.log、RunEvent、SandboxAudit 进 SIEM | 不要只留在本机；日志本身也要防篡改 |

## 备份与恢复

要备份的不是「一个数据库」，而是四类东西：

| 类别 | 内容 | 恢复要点 |
|------|------|----------|
| 配置 | `config.yaml`、`extensions_config.json`、`.env`（密钥单独管） | 配置与密钥不一致会导致启动失败；版本锁步 |
| 用户数据 | `.deer-flow/users/{user_id}/`（memory/agents/threads/uploads/outputs） | 路径按 user_id 隔离；恢复后核对属主 |
| 数据库 | SQLite 文件或 Postgres（runs/events/threads/PAT/MCP token 等） | 与文件系统快照同一时间点；否则 run/artifact 对不上 |
| 密钥 | `AUTH_JWT_SECRET`、`DEER_FLOW_INTERNAL_AUTH_TOKEN`、`BETTER_AUTH_SECRET`、`DEER_FLOW_CREDENTIALS_KEY` | 放 secret manager/KMS；不要和备份放一起 |

**恢复演练**比备份本身更重要：至少每季度在隔离环境恢复一次，验证登录、历史 thread、artifact、PAT、MCP OAuth、定时任务都能工作。

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
