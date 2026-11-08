---
title: "安全与信任边界"
description: "一段用户 prompt 到 agent 执行 `rm -rf /` — 中间有多少层防护？"
type: index
---

# 安全与信任边界

一段用户 prompt 到 agent 执行 `rm -rf /` — 中间有多少层防护？

**回答的核心问题**：纵深防御层次（从 Auth 到 OS 隔离）、七种沙箱的 13 维差异对比、Guardrail 与 SandboxAudit 的分工、端到端信任边界上的每道防线在代码中的位置、以及 🆕 2.2.0 的扩展能力授予面。

> **约束：不修改项目源代码。** 本 `_digested/` 下所有内容仅作研究记录。详见 [根 README](../README.md)。

## 阅读顺序

| 文件 | 内容 |
|------|------|
| **00-overview.md** | 全景：纵深防御同心圆图、认证凭据路径图、隔离对比表、已知缺陷 |
| **01-auth.md** | 认证授权：JWT + PAT + CSRF + Internal Token + 登录限流 + 权限模型（Phase 4 effective permissions 贯通） |
| **02-sandbox-isolation.md** | 沙箱隔离：三档对比(13维)、allow_host_bash、6层路径防穿越 |
| **03-guardrail.md** | Guardrail + 审计：可插拔授权、高危命令拦截、MCP 结果清洗、blocked payload elision、输出安全 |
| **04-trust-boundary.md** | 端到端信任链：16 层防护（2.1 的 14 层 + 🆕 插件 action/管理授权）在代码中的位置和执行流 |
| **05-production-auth-setup.md** | 生产认证配置：JWT 环境变量、多用户隔离、Nginx 速率限制分步指南 |
| 🆕 **06-extension-boundary.md** | 扩展安全边界：plugin action/management 授权目标、host_access 授予、model invocation 预算、skill mutation 发布闸门、completed-run evidence |

## 关键问题

- 七种沙箱差多少？→ `02-sandbox-isolation.md` 13 维对比表
- `allow_host_bash: false` 到底防了什么？→ `02-sandbox-isolation.md` LocalSandbox 节
- Guardrail 和 SandboxAudit 有什么区别？→ `03-guardrail.md`
- 🆕 TypeSafe / OpenAI Decisions 这两个风险门有什么不同？→ `03-guardrail.md` 三道工具级风险门表
- 🆕 插件能拿到什么、拿不到什么？→ `06-extension-boundary.md`
- 从请求到执行经过多少层检查？→ `04-trust-boundary.md` 链路图
- 最大的安全短板是什么？→ `00-overview.md` 已知缺陷表
