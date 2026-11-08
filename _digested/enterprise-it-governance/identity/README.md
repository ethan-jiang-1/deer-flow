---
title: "身份与接入"
description: "企业采购的第一问：谁能进来？用什么身份？离职了怎么马上关掉？"
type: index
topics: [governance, identity, authentication, sso]
---

# 身份与接入

> **定位**：身份是所有授权的前提。本域回答两件事——「人怎么认证进来」（本地密码 / SSO-OIDC / PAT / 内部 token）与「agent 用什么身份跑」。给做接入方案与账号生命周期评审的人看。
> **边界**：「进来之后能做什么」见 [authorization/](../authorization/README.md)；per-user 数据布局与凭据存储见 [data/](../data/README.md)。部署配置步骤不在这里，见 [enterprise-operations/](../../enterprise-operations/README.md)。

## 阅读路径

1. **先看**：[01-authentication-model.md](01-authentication-model.md) — 四条并行认证路径与共享的 Gateway 中间件链。
2. **再看**：[03-user-isolation.md](03-user-isolation.md) — per-user 目录布局、`user_id` 解析与 no-auth 模式风险。
3. **深入**：[04-agent-identity-gap.md](04-agent-identity-gap.md) — agent 继承用户权限、没有独立身份（NHI），本域最大的结构性缺口。

## 本篇目

| 文件 | 主题 | 深度 |
|---|---|---|
| [01-authentication-model.md](01-authentication-model.md) | 四条并行认证路径 | 概览 |
| [02-internal-token.md](02-internal-token.md) | Gateway 与 IM channel 之间的内部调用凭据 | 深入 |
| [03-user-isolation.md](03-user-isolation.md) | per-user 目录布局、`user_id` 解析、no-auth 风险 | 深入 |
| [04-agent-identity-gap.md](04-agent-identity-gap.md) | Agent 身份：继承用户权限、无 NHI | 深入 |
| [05-gateway-access-control.md](05-gateway-access-control.md) | Gateway API 层访问控制：扩展面身份投影、插件管理路由 resolver | 深入 |
| [06-design-decisions.md](06-design-decisions.md) | 设计决策：CSRF double-submit、`token_version` 校验 | 概览 |
| [07-sso-and-oidc.md](07-sso-and-oidc.md) | 企业 SSO / OIDC：PKCE、nonce、provisioning 四策略 | 深入 |
| [08-pat.md](08-pat.md) | PAT：scope 模型、默认拒绝路由边界、摘要存储、过期 | 深入 |
| [09-login-throttle.md](09-login-throttle.md) | 登录限速：auto/memory/db 三档，多副本共享锁禁 | 深入 |
| [10-registration-policy.md](10-registration-policy.md) | 注册策略：`allow_registration` 与 SSO provisioning 的边界 | 深入 |

## 宪章与约定

- 本目录无独立宪章；父级卷宪章为 [../PLAN.md](../PLAN.md)。
- 写作纪律沿用 [根 README](../../README.md)：判断性段落附 `file:line`，基线 v2.2.0。
- 阅读约定：缺口按「无 / 有但不覆盖 / 部分闭合」三态标注，每处写明边界条件。

## 相关目录

- [企业 IT 治理总览](../README.md) — 八个治理面向与默认关闭项。
- [授权模型](../authorization/README.md) — 认证之后「能操作什么」。
- [审计与追责](../audit/README.md) — 登录、PAT 与身份决策如何留痕。
- [Enterprise Operations](../../enterprise-operations/README.md) — SSO、JWT 与限速的配置落点。
