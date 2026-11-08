---
title: "身份与接入"
description: "企业采购的第一问：谁能进来？用什么身份？离职了怎么马上关掉？"
type: index
topics: [governance]
---

# 身份与接入

企业采购的第一问：谁能进来？用什么身份？离职了怎么马上关掉？

身份是所有授权的前提。这一域回答「人怎么认证进来」和「agent 用什么身份跑」两件事——后者是 DeerFlow 最大的结构性缺口（agent 没有独立身份）。

> **约束：不修改项目源代码。** 本 `_digested/` 下所有内容仅作研究记录。详见 [根 README](../../README.md)。

## 本篇目

| 文件 | 主题 | 内容 |
|------|------|------|
| [01-authentication-model.md](01-authentication-model.md) | **认证模型** | 四条并行认证路径：本地密码、SSO/OIDC、API PAT、内部 token |
| [02-internal-token.md](02-internal-token.md) | **内部服务认证** | Gateway 与 IM channel 之间的内部调用凭据 |
| [03-user-isolation.md](03-user-isolation.md) | **用户隔离** | per-user 目录布局、user_id 解析、no-auth 模式风险 |
| [04-agent-identity-gap.md](04-agent-identity-gap.md) | **Agent 身份：缺失的一环** | Agent 继承用户权限，无 NHI |
| [05-gateway-access-control.md](05-gateway-access-control.md) | **Gateway API 层访问控制** | 扩展面身份投影、插件管理路由 resolver |
| [06-design-decisions.md](06-design-decisions.md) | **设计决策** | CSRF double-submit、token_version 校验 |
| [07-sso-and-oidc.md](07-sso-and-oidc.md) | **SSO / OIDC** | 企业 SSO 接入：PKCE、nonce、provisioning 四策略 |
| [08-pat.md](08-pat.md) | **个人访问令牌** | scope 模型、默认拒绝路由边界、摘要存储、过期 |
| [09-login-throttle.md](09-login-throttle.md) | **登录限速** | auto/memory/db 三档，多副本共享锁禁 |
| [10-registration-policy.md](10-registration-policy.md) | **注册策略** | allow_registration 与 SSO provisioning 的边界 |

---

← 返回 [企业 IT 治理总览](../README.md) · 机制细节见 [enterprise-operations/](../../enterprise-operations/README.md)
