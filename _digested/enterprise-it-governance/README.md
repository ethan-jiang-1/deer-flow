---
title: "IT 治理视角"
description: "IT 部门负责人关心的不是「middleware 怎么写的」，而是「这东西上线之后会不会出事」。本卷按八个治理面向回答：DeerFlow 在每一面上给了什么机制、还缺什么。"
type: index
---

# IT 治理视角

IT 部门负责人关心的不是「middleware 怎么写的」，而是「这东西上线之后会不会出事」。
安全、合规、审计、成本、运维——这些非功能需求在 Agent 时代更紧迫，因为 agent 不是被动回答问题，而是**主动执行操作**。

**本卷回答的问题**：把 DeerFlow 部署进企业后，IT 能在哪些点上真正管住它，哪些点上管不住。

> **约束：不修改项目源代码。** 本 `_digested/` 下所有内容仅作研究记录。详见[根 README](../README.md)。

## 八个面向

| 目录 | 篇数 | 回答什么 |
|---|---|---|
| **[00-overview.md](00-overview.md)** | — | 全景：治理维度映射与成熟度评估 |
| **[identity/](identity/README.md)** | 11 | **谁在操作** —— 四条认证路径、PAT、SSO/OIDC、用户隔离、agent 身份缺口 |
| **[authorization/](authorization/README.md)** | 6 | **能操作什么** —— 13 个权限、Guardrail 门、MCP scope、bounded autonomy |
| **[execution/](execution/README.md)** | 6 | **操作怎么被执行** —— 七种沙箱模式、六层路径防护、资源限额 |
| **[data/](data/README.md)** | 7 | **数据流向哪里** —— 存储分层、脱敏、上传扫描、凭证、PII、保留期 |
| **[audit/](audit/README.md)** | 5 | **事后能否还原** —— 审计链路、SandboxAudit、可观测、事件覆盖矩阵 |
| **[compliance/](compliance/README.md)** | 5 | **能否对上条款** —— GDPR / SOC2 / ISO27001 / EU AI Act 的机制映射 |
| **[cost/](cost/README.md)** | 6 | **花多少、怎么控** —— 成本归属、限额维度、多实例、并发调度 |
| **[lifecycle/](lifecycle/README.md)** | 4 | **从生到死** —— agent 生命周期、变更控制、蔓延风险 |

`lifecycle/` 与 `cost/` 是新增的两面：前者管「上线之后改了什么」，
后者管「跑起来花了多少」。这两件事在企业里都有明确的责任人。

## 十个高频问题，直接跳转

| 问题 | 去哪里 |
|---|---|
| 一个 prompt 能搞出 `rm -rf /` 吗？ | [execution/](execution/README.md) 六层防线 + 沙箱模式 |
| 怎么限制 agent 只能调某些 tool？ | [authorization/03-configurability.md](authorization/03-configurability.md) |
| 名单门不够用，想要模型判定的风险门？ | [authorization/01-guardrail-layer.md](authorization/01-guardrail-layer.md) §2.2 |
| 用户之间数据隔离吗？ | [identity/03-user-isolation.md](identity/03-user-isolation.md) |
| agent 干了什么，事后能查吗？ | [audit/04-event-coverage.md](audit/04-event-coverage.md) 查询表 |
| 有没有防死循环 / 无限制消费？ | [cost/03-budgets-and-limits.md](cost/03-budgets-and-limits.md) |
| **默认配置下，哪些防线其实是关着的？** | 见下节 |
| 能对上 GDPR / SOC2 的哪些条款？ | [compliance/01-mapping.md](compliance/01-mapping.md) |
| 改了配置怎么生效、能不能回滚？ | [lifecycle/02-change-control.md](lifecycle/02-change-control.md) |
| 能不能对接企业 SSO？ | [identity/07-sso-and-oidc.md](identity/07-sso-and-oidc.md) |

## ⚠ 先看这一节：默认关闭的安全能力

评估时最容易犯的错，是把「代码里有」当成「部署里有」。
以下四项能力**在代码中存在，但示例配置里是关闭的**：

| 能力 | 默认状态 | 依据 |
|---|---|---|
| **Guardrails（工具级授权）** | **关闭** —— 示例配置整块被注释 | `config.example.yaml:3272-3301` |
| **`token_budget`（token 预算）** | **关闭** —— `enabled: false` | `config.example.yaml:105-111` |
| **`pii_redaction`（PII 脱敏）** | **关闭** —— `enabled: false` | `config.example.yaml:1537` |
| **`authorization.enabled`（细粒度权限）** | **未开时返回全部 13 个权限** | `backend/app/gateway/authz.py:278-281` |

与之相反，**默认开启**的是：

| 能力 | 默认状态 | 依据 |
|---|---|---|
| 循环检测 | **开启** | `config.example.yaml:1504` |
| 沙箱审计（bash 命令分类） | 开启，规则硬编码 | `backend/packages/harness/deerflow/agents/middlewares/sandbox_audit_middleware.py:414` |
| 宿主 bash 执行 | **禁止**（`allow_host_bash: false`） | `config.example.yaml:1720` |
| 登录限速 | 开启 | `backend/packages/harness/deerflow/config/auth_config.py:139-140` |

这张表是 [00-overview.md](00-overview.md) 成熟度评估的输入，也是任何安全评审的第一页。

## 与 `enterprise-operations/` 的分工

| 卷 | 回答 |
|---|---|
| **本卷** | 能不能被企业 IT 管起来（判断） |
| [`../enterprise-operations/`](../enterprise-operations/README.md) | 怎么装、怎么配、怎么运维（操作） |

同一主题在两卷都有时：本卷讲**控制点与缺口**，那一卷讲**操作步骤**。

## 阅读约定

| 记号 | 含义 |
|---|---|
| **无** / **有但不覆盖** / **部分闭合** | 缺口三态，每处缺口都必须标出边界条件 |
| `file:line` | 运行时事实的出处，全部经本卷自带的锚点校验脚本核对 |
| 「本卷不构成合规结论」 | 合规页的固定免责声明 |
