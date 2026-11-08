---
title: "IT 治理视角"
description: "IT 部门负责人关心的不是「middleware 怎么写的」，而是「这东西上线之后会不会出事」。本卷按八个治理面向回答：DeerFlow 在每一面上给了什么机制、还缺什么。"
type: index
topics: [governance, compliance, audit, cost]
---

# IT 治理视角

> **定位**：IT 负责人、安全与合规评审者的判断卷——把 DeerFlow 放进企业后，**哪些点管得住、哪些点管不住**。不问「middleware 怎么写」，只问「上线之后会不会出事」；agent 不是被动答问，而是主动执行操作，所以身份、授权、审计、成本都要先看清。
> **边界**：不覆盖安装配置与运维步骤（见 [enterprise-operations/](../enterprise-operations/README.md)）；不覆盖 Agent 内部机制与源码导读（见 [internals/](../internals/README.md)）。同一主题两卷都有时，本卷讲控制点与缺口，那一卷讲操作步骤。

## 阅读路径

1. **先看**：[00-overview.md](00-overview.md) — 12 个管理维度的能力/缺口矩阵、成熟度自评与三条最需提前知道的边界。
2. **再看**：[authorization/04-rbac-permissions.md](authorization/04-rbac-permissions.md) — 13 个 `resource:action` 权限全表，授权评审的基准线。
3. **深入**：[audit/04-event-coverage.md](audit/04-event-coverage.md) — 哪些决策有结构化证据、哪些只剩文本日志。

## 本篇目

| 文件 | 主题 | 深度 |
|---|---|---|
| [00-overview.md](00-overview.md) | 12 个管理维度的能力与缺口矩阵 | 概览 |
| [PLAN.md](PLAN.md) | 本卷重构计划：八个治理域的拆分意图与验收方式 | 概览 |
| [AUDIT-FIX-PLAN.md](AUDIT-FIX-PLAN.md) | 全面审计的 BLOCKER/MAJOR/MINOR 逐项修复底稿 | 深入 |

### 八个面向

| 目录 | 篇数（含 README） | 回答什么 |
|---|---|---|
| [identity/](identity/README.md) | 11 | **谁在操作** —— 四条认证路径、PAT、SSO/OIDC、用户隔离、agent 身份缺口 |
| [authorization/](authorization/README.md) | 6 | **能操作什么** —— 13 个权限、Guardrail 门、MCP scope、bounded autonomy |
| [execution/](execution/README.md) | 6 | **操作怎么被执行** —— 七种沙箱模式、六层路径防护、资源限额 |
| [data/](data/README.md) | 7 | **数据流向哪里** —— 存储分层、脱敏、上传扫描、凭证、PII、保留期 |
| [audit/](audit/README.md) | 5 | **事后能否还原** —— 审计链路、SandboxAudit、可观测、事件覆盖矩阵 |
| [compliance/](compliance/README.md) | 5 | **能否对上条款** —— GDPR / SOC2 / ISO27001 / EU AI Act 的机制映射 |
| [cost/](cost/README.md) | 6 | **花多少、怎么控** —— 成本归属、限额维度、多实例、并发调度 |
| [lifecycle/](lifecycle/README.md) | 4 | **从生到死** —— agent 生命周期、变更控制、蔓延风险 |

### 六个渐进入口

1. **先分清「代码里有」和「部署里有」** → [00-overview.md](00-overview.md)：12 维矩阵，默认关闭项在矩阵里有标注。
2. **一个 prompt 能搞出 `rm -rf /` 吗** → [execution/README.md](execution/README.md)：沙箱模式与路径防穿透。
3. **人和 agent 各是什么身份、用户之间隔不隔离** → [identity/03-user-isolation.md](identity/03-user-isolation.md)。
4. **agent 干了什么，事后查得到吗** → [audit/04-event-coverage.md](audit/04-event-coverage.md)。
5. **会不会跑飞、账单失控** → [cost/03-budgets-and-limits.md](cost/03-budgets-and-limits.md)。
6. **能不能对上 GDPR / SOC2** → [compliance/01-mapping.md](compliance/01-mapping.md)。

> ⚠ **安全评审第一页**：以下四项在代码里存在，但示例配置默认不启用。

| 能力 | 默认状态 | 依据 |
|---|---|---|
| **Guardrails**（工具级授权） | **关闭**——示例配置整块被注释 | `config.example.yaml:3272-3301` |
| **`token_budget`**（顶层） | **关闭**——`enabled: false` | `config.example.yaml:105-111` |
| **`pii_redaction`** | **关闭**——`enabled: false` | `config.example.yaml:1537` |
| **`authorization.enabled`** | 未开时返回全部 **13** 个权限 | `backend/app/gateway/authz.py:288-290` |

`lifecycle/` 与 `cost/` 是最容易漏看的两面：前者管「上线之后改了什么」，后者管「跑起来花了多少」。

## 宪章与约定

- 本卷宪章（执行计划与验收矩阵）：[PLAN.md](PLAN.md)；审计修复底稿与逐项数据：[AUDIT-FIX-PLAN.md](AUDIT-FIX-PLAN.md)。
- 写作纪律沿用 [根 README](../README.md)：判断性段落附 `file:line`，缺口按「无 / 有但不覆盖 / 部分闭合」三态标注。
- 合规页固定免责：「本卷不构成合规结论」，结论必须由审计方给出。

## 相关目录

- [根 README](../README.md) — 全库阅读地图与「README 约定（每个子目录）」。
- [enterprise-operations/](../enterprise-operations/README.md) — 同一主题的操作面：怎么装、怎么配、怎么运维。
- [observability/](../observability/README.md) — 日志、事件流与追踪的实现细节。
