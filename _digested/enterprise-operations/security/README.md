---
title: "安全与信任边界"
description: "一段用户 prompt 到 agent 执行 `rm -rf /` — 中间有多少层防护？"
type: index
topics: [security, defense-in-depth, sandbox, guardrail]
---

# 安全与信任边界

> **定位**：实施视角的安全卷——从 Auth 到 OS 隔离的纵深防御、七种沙箱运行模式的 13 维差异、Guardrail 与 SandboxAudit 的分工，以及 v2.2.0 的扩展能力授予面。给做安全加固与上线评审的运维/安全工程师看。
> **边界**：控制点该不该批、缺口如何定级见 [企业 IT 治理卷](../../enterprise-it-governance/README.md)；部署与镜像构建见 [deployment/](../deployment/README.md)。

## 阅读路径

1. **先看**：[00-overview.md](00-overview.md) — 8 道关口、认证凭据路径、隔离对比与已知缺陷。
2. **再看**：[04-trust-boundary.md](04-trust-boundary.md) — 16 层防护在代码中的位置与端到端执行流。
3. **深入**：[07-enterprise-readiness.md](07-enterprise-readiness.md) — OWASP 对照、企业平台基准、P0/P1 差距、责任边界与 20 问应答。
4. **延伸**：[06-extension-boundary.md](06-extension-boundary.md) — 插件逐项授予、`host_access`、model invocation 预算、skill 发布闸门。

## 本篇目

| 文件 | 主题 | 深度 |
|---|---|---|
| [00-overview.md](00-overview.md) | 安全全景：8 道关口、凭据路径、已知缺陷 | 概览 |
| [01-auth.md](01-auth.md) | 认证授权：JWT + PAT + CSRF + Internal Token + 限流 + 权限模型 | 深入 |
| [02-sandbox-isolation.md](02-sandbox-isolation.md) | 沙箱隔离：七种模式、13 维对比、`allow_host_bash`、6 层路径防穿越 | 深入 |
| [03-guardrail.md](03-guardrail.md) | Guardrail + 审计：可插拔授权、高危命令拦截、输出安全 | 深入 |
| [04-trust-boundary.md](04-trust-boundary.md) | 端到端信任链：16 层防护的位置与执行流 | 概览 |
| [05-production-auth-setup.md](05-production-auth-setup.md) | 生产认证配置：JWT 环境变量、多用户隔离、TLS/安全头、密钥轮换、备份 | 概览 |
| [06-extension-boundary.md](06-extension-boundary.md) | 扩展安全边界：授权目标、宿主授予、发布闸门 | 深入 |
| [07-enterprise-readiness.md](07-enterprise-readiness.md) | 企业级 Agent 安全：OWASP 对照、平台基准、DSH/Pi 路线、差距与责任边界 | 深入 |
| [08-control-checklist.md](08-control-checklist.md) | 85 项企业安全评审控制清单：状态、证据、企业需补 | 工具 |

## 宪章与约定

- 本目录无独立宪章；写作纪律沿用 [根 README](../../README.md)。
- 安全判断以 `file:line` 为据，版本基线 v2.2.0；外部厂商资料单独标日期与来源，营销口径与可核事实分开。

## 相关目录

- [Enterprise Operations 总览](../README.md) — 部署、通道、API 与运维全景。
- [Deployment](../deployment/README.md) — Docker Compose、Nginx 与 K3s Provisioner。
- [企业 IT 治理卷](../../enterprise-it-governance/README.md) — 控制点与缺口的判断面。
