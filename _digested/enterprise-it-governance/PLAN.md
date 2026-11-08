---
title: "企业 IT 治理卷 — 重构计划"
description: "把 _digested 里的企业视角从『运维的一个子话题』提升为独立一卷：8 个治理域、27 篇、目标约 3200 行。本文件是待审阅的执行计划。"
topics: [governance, plan]
---

# 企业 IT 治理卷 — 重构计划

> **状态**：待审阅。本文只是计划，除已完成的目录骨架外尚未改写内容。
> **日期**：2026-11-08
> **基线**：DeerFlow `v2.2.0`（`58fc5bd5b`）

## 0. 背景与意图

DeerFlow 与个人玩具的区别在于：**它能被企业 IT 管起来**。治理、安全、授权、审计、合规——这些
传统企业关心的部分，比「内部 agent 到底多能干」更重要。

原有的 `operations/it-ops/` 视角是对的（它开篇就写「IT 负责人关心的不是 middleware 怎么写，
而是这东西上线之后会不会出事」），但存在三个实际问题：

### 0.1 没跟上 2.2 同步

`_upstream-sync` 的 P2 分域表里没有它，导致多处断言停留在 2.1：

| 原文档写的 | v2.2.0 实际 | 证据 |
|---|---|---|
| Subagent 并发「≤3」 | 64 | `packages/harness/deerflow/config/subagents_config.py:17` `MAX_CONCURRENT_SUBAGENT_CALLS = 64` |
| 「无 per-run 预算上限」 | 有 | `packages/harness/deerflow/config/subagents_config.py:50` `max_total_per_run` + `TokenBudgetConfig` |
| 「Guardrail deny 不写 RunJournal」 | 已写 | `packages/harness/deerflow/guardrails/middleware.py:171` `record_middleware`（定义在 `:131`），带 `allow`/`policy_id`/`reason_codes`/`fail_closed`/`user_role`/`provider_error` |
| `backend/.deer-flow/users/` | `{project_root}/.deer-flow/users/` | 2.2 新增 `USER.md` 与 per-user `skills/` |

这不是笔误——它会让 IT 依据错误信息判断「能力不足」或「已覆盖」。

### 0.2 企业采购的第一问完全没写

v2.2.0 有完整的 OIDC/SSO：

| 文件 | 行数 | 作用 |
|---|---|---|
| `app/gateway/auth/oidc.py` | 481 | discovery、授权码交换、ID token 校验、userinfo |
| `app/gateway/auth/oidc_state.py` | 124 | state cookie、CSRF 防护 |
| `app/gateway/auth/user_provisioning.py` | 120 | 账号自动创建、域名限制、管理员提升 |
| `backend/docs/SSO.md` | 302 | 运维手册 |
| `config.example.yaml:3509-3602` | 94 | 配置契约（PKCE、nonce 默认开） |

而原 `it-ops/` 全文 **`SSO`/`OIDC` 命中 0 次**。同样缺失的还有：登录限速的三档存储
（`auto`/`memory`/`db`，`db` 让多 Gateway 副本共享锁禁）、PAT 的默认拒绝路由边界、
13 个 RBAC 权限全表、`agents_api`、`multi_instance`、`DEER_FLOW_CREDENTIALS_KEY`、
`blob_storage`、`knowledge_base`、保留期。

### 0.3 结构上被淹没

原 `operations/README.md` 只有 24 行，`it-ops/` 排在 deployment、channels、integration
之后第 5 位——而那三个都是实现参考。IT 负责人点进 `operations/` 先看到的是 Docker 怎么装，
而不是「能不能过我们风控」。

### 0.4 结论

**不是内容多了，是覆盖偏心**：安全实现讲得细，企业采购与合规视角几乎空白。
所以要做的是「重定位 + 补写」，不是「精简」。

## 1. 已完成的目录骨架

```
_digested/
├── enterprise-it-governance/        ← 治理视角：能不能被企业 IT 管起来
│   ├── README.md
│   ├── 00-overview.md
│   ├── identity/          6 篇
│   ├── authorization/     3 篇
│   ├── execution/         5 篇
│   ├── data/              4 篇
│   ├── audit/             2 篇
│   ├── cost/              2 篇
│   ├── lifecycle/         3 篇
│   ├── compliance/        1 篇
│   └── figures/{defense-in-depth,governance-overview}.svg
└── enterprise-operations/           ← 实现视角：怎么装、怎么配、怎么运维
    ├── security/ deployment/ channels/ integration/ app-layer/ tracing/
    ├── scheduler.md  github-integration.md  backup-and-monitoring.md
    └── README.md
```

**命名约定**：两个顶层目录带 `enterprise-` 前缀；子目录（孙）不带，因为上级已声明语境。

**分工**：

| | `enterprise-it-governance/` | `enterprise-operations/` |
|---|---|---|
| 读者 | IT 负责人、安全评审、合规 | 平台工程师、SRE |
| 问题 | 能不能接 Okta？离职账号怎么回收？被拒绝的操作能不能导报告？ | 认证中间件怎么走？Docker 怎么起？ |
| 产出 | 能力矩阵 + 证据位置 + 缺口 | 机制说明 + 配置项 + 操作步骤 |

**已完成**：原 5 篇（873 行）按域拆成 25 篇，逐个标题核对**内容零丢失**；
44 个文件、161 处 `operations/` → `enterprise-operations/` 的引用已修；
历史 `UPDATE_PLAN_1–7` 已回退以保留当年路径记录。

## 2. 目标形态与工作量

现状 27 篇、1060 行（多为拆分后的骨架）。目标约 **3290 行**，净增约 2230 行（含从别处搬入的内容）。

| 域 | 现有 | 目标 | 净增 | 主要工作 |
|---|---:|---:|---:|---|
| `identity/` | 199 | 700 | +501 | **SSO/OIDC 全节（最大缺口）**、PAT、登录限速、`agents_api` |
| `authorization/` | 149 | 500 | +351 | **13 个 RBAC 权限全表**、MCP 作用域、`personal_mcp` |
| `execution/` | 219 | 400 | +181 | 订正过期断言、扩展执行租约、MCP durable task |
| `data/` | 107 | 450 | +343 | **凭据加密**、PII 脱敏、保留期、blob/knowledge 驻留 |
| `audit/` | 152 | 490 | +338 | 订正「guardrail 不写 journal」+ **承接 `observability/07` 搬来的 6 条证据/可观测缺口** + 事件覆盖矩阵（见 §4.3） |
| `cost/` | 75 | 330 | +255 | **承接** `orchestration-ladder/03` 搬来的不理想化清单 + 九层链条治理视角表 + 多实例完整要求（见 §4） |
| `lifecycle/` | 116 | 300 | +184 | 配置版本 63、插件授予、skill mutation、**无 kill switch** |
| `compliance/` | 43 | 400 | +357 | **GDPR/SOC2/ISO27001/EU AI Act 逐条映射表** |
| `00-overview.md` | 64 | 150 | +86 | 12 维度矩阵订正 + 「对应章节」列 |
| `README.md` | 62 | 120 | +58 | 按 IT 关键问题重排导航 |
| **合计** | **1060** | **~3290** | **~+2230** | |

## 3. 逐篇清单

### 3.1 `identity/` — 身份与接入（企业采购第一问）

| 文件 | 现有 | 目标 | 内容 |
|---|---:|---:|---|
| `01-authentication-model.md` | 38 | 120 | 三条认证路径总览（Web JWT / API PAT / 内部 token），谁用哪条 |
| `02-internal-token.md` | 13 | 60 | `X-DeerFlow-Internal-Token`、`DEER_FLOW_INTERNAL_AUTH_TOKEN`、多 worker 必须显式设置 |
| `03-user-isolation.md` | 41 | 120 | per-user 目录、`user_id` 解析、no-auth 模式风险 |
| `04-agent-identity-gap.md` | 28 | 100 | **Agent 无独立身份（NHI）**——企业治理的首要缺口 |
| `05-gateway-access-control.md` | 42 | 100 | 扩展面身份投影、插件管理路由 resolver |
| `06-design-decisions.md` | 37 | 60 | CSRF double-submit、token_version |
| `07-sso-and-oidc.md` | — | **200** | 🆕 **企业首要问题**：discovery、授权码流、PKCE S256、nonce、`sso_failed` 契约、provisioning 四策略（`auto_create_users`/`require_verified_email`/`allowed_email_domains`/`admin_emails`）、Keycloak/Azure AD/Okta 配置形态 |
| `08-pat.md` | — | **100** | 🆕 个人访问令牌：scope 模型、**默认拒绝路由边界（#5041）**、base62 与摘要存储 |
| `09-login-throttle.md` | — | **100** | 🆕 三档存储：`auto`/`memory`/`db`；`db` 让多副本共享锁禁；企业代理 NAT 下的调参 |
| `10-registration-policy.md` | — | **60** | 🆕 `allow_registration` 与 SSO provisioning 的策略边界（配置注释明确警告的陷阱） |

### 3.2 `authorization/` — 授权模型

| 文件 | 现有 | 目标 | 内容 |
|---|---:|---:|---|
| `01-guardrail-layer.md` | 66 | 150 | Tool 级授权、可插拔 provider、2.2 三个内置门（Allowlist / TypeSafe / OpenAIDecisions） |
| `02-bounded-autonomy.md` | 23 | 80 | 自动/人工边界 |
| `03-configurability.md` | 60 | 100 | 可配置性总览（保留，订正） |
| `04-rbac-permissions.md` | — | **150** | 🆕 **13 个 `resource:action` 权限全表**（定义 `app/gateway/authz.py:63-86`，权威清单 `:161-175`）：`threads:read/write/delete`、`runs:create/read/cancel`、`projects:read/write/delete`、`memory:read/write`、`agents:read/write` |
| `05-mcp-scope.md` | — | **100** | 🆕 `mcp_scope.py` 的 `v2:` 作用域键 + thread incarnation；personal MCP 的归属 |

### 3.3 `execution/` — 执行边界

| 文件 | 现有 | 目标 | 内容 |
|---|---:|---:|---|
| `01-sandbox-modes.md` | 26 | 100 | 七种模式、三种隔离级别 |
| `02-path-containment.md` | 47 | 100 | 6 层路径校验 + Bash 子命令审计 |
| `03-resource-limits.md` | 32 | 70 | CPU/内存/磁盘、per-thread |
| `04-gaps-and-comparison.md` | 68 | 90 | 剩余风险、行业对比 |
| `05-execution-limits.md` | 46 | 90 | 循环检测、并发 64、超时 |
| `06-extension-execution-lease.md` | — | **60** | 🆕 `extension_execution_leases`（迁移 `0048`）、MCP durable task |

### 3.4 `data/` — 数据治理

| 文件 | 现有 | 目标 | 内容 |
|---|---:|---:|---|
| `01-storage-and-isolation.md` | 33 | 120 | per-user 布局（订正路径）、`USER.md`、per-user `skills/` |
| `02-redaction.md` | 24 | 80 | 输出/错误脱敏 |
| `03-upload-and-scanning.md` | 27 | 80 | 上传安全矩阵、Skills 扫描 |
| `04-credentials.md` | 23 | **120** | 🆕 `DEER_FLOW_CREDENTIALS_KEY`、MultiFernet 轮换、**丢失即永久不可读** |
| `05-pii-redaction.md` | — | **80** | 🆕 `pii_redaction_middleware` |
| `06-retention-and-residency.md` | — | **100** | 🆕 `trash_retention_days`、`blob_storage`、`knowledge_base` 的数据驻留边界 |

### 3.5 `audit/` — 审计与追责

| 文件 | 现有 | 目标 | 内容 |
|---|---:|---:|---|
| `01-audit-chain.md` | 107 | 210 | 三层审计；**订正 guardrail 已入 journal**（带字段清单）+ **承接** guardrail 审计缺口（只覆盖 `wrap_tool_call`）——见 §4.3 |
| `02-observability.md` | 45 | 120 | SSE、心跳、OTEL、**承接**「聚合仪表盘/内置告警」两条缺口——见 §4.3 |
| `03-event-coverage.md` | — | **160** | 🆕 **事件覆盖矩阵** + **承接** `observability/07` 搬来的 4 条证据缺口（SandboxAudit 结构化、操作完整性、终态原子性、删除即失效）+ `observability/02` 的「已知缺口」节——见 §4.3 |

### 3.6 `cost/` — 成本与容量

| 文件 | 现有 | 目标 | 内容 |
|---|---:|---:|---|
| `01-cost-attribution.md` | 40 | 120 | Token 用量、subagent 合并、`stream_usage` + **承接** agent 级 SLO/error budget 缺口——见 §4.3 |
| `02-deployment-and-ops.md` | 35 | 80 | 热更新、健康检查、迁移 |
| `03-budgets-and-limits.md` | — | **110** | 🆕 **承接** `orchestration-ladder/03` 搬来的「不理想化清单」+ 九层限额的治理视角表（谁能管/能配吗/默认值/缺口）+ 实时成本预算缺口——见 §4.4 |
| `04-multi-instance.md` | — | **100** | 🆕 `multi_instance` 8 条拒绝规则 + 多实例部署的完整治理要求（SQL/事件后端/SSE/孤儿流恢复）——见 §4.3 |

### 3.7 `lifecycle/` — 生命周期与变更控制

| 文件 | 现有 | 目标 | 内容 |
|---|---:|---:|---|
| `01-agent-lifecycle.md` | 32 | 90 | 创建、热更新、停用删除 |
| `02-change-control.md` | 44 | 100 | 插件授予、skill mutation 七步流 |
| `03-agent-sprawl.md` | 40 | 80 | 蔓延风险与缺失控制 |
| `04-config-versioning.md` | — | **70** | 🆕 `config_version` 63、升级闸门、无 kill switch |

### 3.8 `compliance/` — 合规对照

| 文件 | 现有 | 目标 | 内容 |
|---|---:|---:|---|
| `01-mapping.md` | 43 | **200** | 🆕 逐条映射总表：控制项 → DeerFlow 机制 → 证据位置 → 状态（已覆盖/部分/缺口） |
| `02-gdpr.md` | — | 80 | 数据主体权利、删除、跨境 |
| `03-soc2-iso27001.md` | — | 70 | 访问控制、日志留存、变更管理 |
| `04-eu-ai-act.md` | — | 70 | 2026-08 生效项、透明度义务 |

### 3.9 顶层

| 文件 | 现有 | 目标 | 内容 |
|---|---:|---:|---|
| `00-overview.md` | 64 | 150 | 12 维度矩阵订正 + 「对应章节」列、成熟度自评 |
| `README.md` | 62 | 120 | 按 IT 关键问题重排导航 |

## 4. 搬迁方案：把散落的治理内容收进来

两个 enterprise 目录形成后，必须回答：**原来散落在别处的治理内容，哪些该搬进来？**

**决定原则：搬，不搞指路。** 同一主题分散两处就是技术债——读者要跳两个地方，
维护者要改两遍，迟早不一致。只要内容的主体是治理判断，就搬进来；
只有纯机制实现的才留在原处。

### 4.1 三类内容的判据

| 类型 | 判据 | 处理 |
|---|---|---|
| **治理判断** | 「够不够」「缺什么」「谁能管」「能不能过评审」 | **搬进本卷** |
| **机制实现** | 「怎么写的」「怎么配」「代码在哪」 | 留在 `internals/`、`concepts/`、`enterprise-operations/` |
| **混合体** | 一篇里两种都有 | **切分**：治理部分搬走，机制部分留下 |

### 4.2 扫描结果：一篇混合体要切分，两篇要搬迁

扫描 15 个顶层目录、约 230 篇文档，结论：

| 文件 | 行数 | 性质 | 处置 |
|---|---:|---|---|
| `observability/07-production-checklist.md` | 95 | **混合体** | **切分**（见 4.3） |
| `observability/02-run-events-and-journal.md` 的「已知缺口」节 | ~15 | 治理 | **搬** 到 `audit/03-event-coverage.md` |
| `orchestration-ladder/03-资源预算与公平性-*.md` 的「不理想化清单」节 | ~10 | 治理 | **搬** 到 `cost/03-budgets-and-limits.md` |
| `observability/04-console-and-cost.md` | 89 | 机制（Console 端点 + 计价） | **留**，成本治理判断在本卷 |
| `internals/runtime/04-journal.md` | — | 机制 | **留** |
| `concepts/sandbox/*` | — | 机制 | **留** |
| `internals/harness-hooks/05-guardrail-plugin.md` | — | 机制 | **留** |
| `getting-started/05-environment.md` | — | 配置参考 | **留** |
| `enterprise-operations/security/*` | — | 机制 | **留** |

### 4.3 切分方案：`observability/07-production-checklist.md`

这篇 95 行是典型混合体，逐节判定：

| 节 | 内容 | 性质 | 去向 |
|---|---|---|---|
| 上线前必开 | 9 项配置（SQL 后端、事件后端、trace 关联、追踪、计价、关 docs、断路器、多实例 SSE、孤儿流恢复） | 运维操作 | **留在 observability**，但**多实例三项**另在本卷 `cost/04` 详述 |
| 日常看什么 | Console 端点与信号 | 纯可观测 | 留 |
| 排障路径 | 从 trace_id / run_id 定位 | 纯可观测 | 留 |
| **已知缺口（诚实版）** | 9 条缺口：聚合仪表盘、内置告警、guardrail 审计、SandboxAudit 结构化、agent 级 SLO、实时成本预算、操作完整性、终态原子性、删除即证据失效 | **★ 纯治理** | **整节搬走** |
| 告警配方 | cron 打 Console + Langfuse 阈值 | 运维操作 | 留 |

**「已知缺口」9 条的落点**：

| 缺口 | 搬到 |
|---|---|
| 聚合仪表盘、内置告警 | `audit/02-observability.md` |
| guardrail deny 审计（2.2 已接入但只覆盖 `wrap_tool_call`） | `audit/01-audit-chain.md` |
| SandboxAudit 结构化（纯文本，接 SIEM 需解析） | `audit/03-event-coverage.md` |
| agent 级 SLO / error budget | `cost/01-cost-attribution.md` |
| 实时成本预算告警 | `cost/03-budgets-and-limits.md` |
| Agent 操作完整性验证（部分改善未闭合） | `audit/03-event-coverage.md` |
| 终态事件原子性（两个事务，需 outbox） | `audit/03-event-coverage.md` |
| 事件删除即证据失效 | `audit/03-event-coverage.md` |

搬完后 `observability/07` 保留「上线/看/排障/告警」四节，开头加一句指向本卷缺口清单。

### 4.4 切分方案：`orchestration-ladder/03-资源预算与公平性-*.md`

这篇 ~200 行是机制分析（九层限额怎么叠加、谁先触发、超限长什么样），**主体留下**。
但第 189 行的「**四、不理想化清单（"无限制"本身是发现）**」是治理判断，搬走。

**九层限额表本身不搬**——它是机制核验，本卷 `cost/03` 引用它并做治理视角归纳
（谁能管 / 能配吗 / 默认值 / 缺口）。**这不是复制**：原文按「叠加顺序」组织，
治理视角按「可管理性」组织，是两种视图。

### 4.5 为什么这些不搬

看起来「该搬」但实际是机制的，一律留下：

| 文件 | 为什么留 |
|---|---|
| `concepts/sandbox/*` | 沙箱 ABC 与七种实现——「怎么做的」，不是「够不够」 |
| `internals/harness-hooks/05-guardrail-plugin.md` | Provider 协议与自定义写法——实现手册 |
| `internals/runtime/04-journal.md` | RunJournal 回调与 token 累加——内部机制 |
| `getting-started/05-environment.md` | 环境变量全表——配置参考 |
| `observability/04-console-and-cost.md` | Console 三个端点 + `models[*].pricing` 计价——机制 |
| `enterprise-operations/security/*` | 认证/沙箱/Guardrail 机制——已明确分工 |

### 4.6 搬迁后的目录变化

**`observability/`**：11 篇 → 11 篇（07 瘦身，缺口节移除）

**`orchestration-ladder/`**：14 篇 → 14 篇（03 移除「不理想化清单」节）

**`enterprise-it-governance/`**：承接全部搬入的治理内容，篇目见 §3

### 4.7 搬迁清单（执行时逐条打勾）

| # | 动作 | 文件 |
|---|---|---|
| 1 | 从 `observability/07` 移除「已知缺口」整节 | `observability/07-production-checklist.md` |
| 2 | 将该节 9 条缺口按 4.3 表分落到本卷 4 篇 | `audit/01`、`audit/02`、`audit/03`、`cost/01`、`cost/03` |
| 3 | `observability/07` 开头加一句指向本卷缺口清单 | 同上 |
| 4 | 从 `orchestration-ladder/03` 移除「四、不理想化清单」节 | `orchestration-ladder/03-*.md` |
| 5 | 将「不理想化清单」内容并入本卷 `cost/03` | `cost/03-budgets-and-limits.md` |
| 6 | `orchestration-ladder/03` 开头加一句指向本卷治理归纳 | 同上 |
| 7 | 校验：搬动后原文件无断链、本卷无重复叙述 | `check_digest.py` |

## 5. 写作纪律

沿用 `_digested` 语料的既定纪律，本卷额外强调：

1. **只讲能做什么、缺什么，不做采购建议。** 保留成熟度自评与缺口分析（事实判断），
   但不写面向读者的采购祈使句（形如「贵公司应当采购……」）。
2. **每条断言带源码证据位置**（`file.py:NNN`），缺口也要写明「缺口在哪个维度」。
3. **四类陈述分清**：运行时事实 / 主仓要求 / 应用仓建议 / 仓库自定。本卷基本只涉及前两类。
4. **与 `enterprise-operations/` 不重复**：机制细节指过去，本卷只做判断。
   **但治理内容必须搬进来，不能只指路**——同一主题分散两处就是技术债（见 §4）。
5. **不修改项目源代码**（`_digested` 通则）。

## 6. 校验与验收

| 项 | 命令 | 通过标准 |
|---|---|---|
| 断链/路径/行号 | `python3 _digested/_upstream-sync/tools/check_digest.py` | exit 0 |
| 三目录铁律 | `git diff --name-only -z v2.2.0 ethan \| tr '\0' '\n' \| grep -vE '^(_digested\|_faq_on_digested\|_deerflow_application_agent_ready_development)/' \| grep -c .` | 输出 `0` |
| 行号越界独立抽查 | 见 `_upstream-sync/UPDATE_PLAN_8.md` §P7 脚本 | 越界 0 |
| `file:line` 到 v2.2.0 树里核对 | 见 `_upstream-sync/UPDATE_PLAN_8.md` §P7 脚本 | 全中 |
| **质量闸门** | `python3 _digested/enterprise-it-governance/tools/check_quality.py` | **exit 0**（阻塞 0） |
| **锚点存在性** | `python3 _digested/enterprise-it-governance/tools/verify_anchors.py` | **exit 0**（120+ 锚点全在范围内） |

## 7. 执行顺序与提交

分三批提交，每批各自可校验：

| 批次 | 内容 | 搬迁任务 | 预计净增 |
|---|---|---|---:|
| **A** | `identity/` 全量（含 4 篇新建）+ `authorization/` 全量（含 2 篇新建） | 无 | ~850 |
| **B** | `data/` + `audit/` + `compliance/`（含 4 篇新建） | **§4.7 第 1–3 条**：切分 `observability/07`，9 条缺口分落 `audit/01`·`02`·`03` 与 `cost/01`·`03` | ~1000 |
| **C** | `cost/` + `lifecycle/` + `execution/` + `00-overview.md` + `README.md` | **§4.7 第 4–6 条**：切分 `orchestration-ladder/03`，不理想化清单并入 `cost/03` | ~450 |

**搬迁任务与内容写作同批完成**——切分出的内容直接落到目标篇，不设「先留占位、后补内容」的中间态。

每批提交前跑完整校验表（含 §4.7 第 7 条），提交信息记录「新增哪几篇、搬入哪几节、订正哪几条 2.2 断言」。

### 7.x 已知的历史不变量偏离（非本次任务范围）

`ethan` 分支相对 `v2.2.0` 有一处落在 `_digested/` 之外的差异：

| 文件 | 引入提交 | 性质 |
|---|---|---|
| `backend/tests/support/detectors/blocking_io_changed.py` | `b56fe3f81`（perf: 改用 `git cat-file --batch` 批量取基线） | 既有提交，非本卷工作 |

这与「`ethan` 只在三个文档目录内偏离 `main`」的约定不符，但**不由本次整理引入，也不在本次范围内**。
需要单独决定是保留（若该性能改进需要保留）还是回退。记录在此以免反复重查。

### 7.y 已核实的关键事实修正（B/C 批）

以下断言经 v2.2.0 源码核实后**修正或补全**，全部已落入正文：

| 原文档断言 | 核实结果 | 影响篇目 |
|---|---|---|
| 「无 per-run 预算上限」 | **错**。`token_budget` 存在，双阈值（0.8 warn / 1.0 hard-stop），默认关闭 | `cost/03` |
| 「无自动数据保留策略」 | **部分错**。项目回收站有 `trash_retention_days`（默认 30 天），但**只在启动时清扫** | `data/06` |
| 「凭证以明文存在」 | **不完整**。落库凭据是 Fernet 加密（`DEER_FLOW_CREDENTIALS_KEY`），多实例未设该 env 会拒绝启动 | `data/04` |
| 「上传只有类型白名单」 | **遗漏三项配额**：10 文件 / 50MB 单文件 / 100MB 总量 | `data/03` |
| 「Skills 扫描只有 LLM 一层」 | **错**。静态规则 + LLM 两层，且无法解析时 fail-closed 为 block | `data/03` |
| 「SandboxAudit 非结构化」 | **错**。已是结构化 JSON，但**只写 gateway.log、不落库** | `audit/02` |
| 「conversion 白名单 8 类」 | **错**，实为 7 类 | `data/03` |

同时新增三条**盲区**发现（已写入 `audit/03`）：
1. subagent 内的 guardrail 拒绝在 journal 里不可见（无 `__run_journal`）
2. allow 决策不落库（有意设计），导致「证明被授权」比「证明被拒绝」更难
3. 文件类工具（`read_file`/`write_file`）完全不走 SandboxAudit

## 8. 风险

| 风险 | 影响 | 缓解 |
|---|---|---|
| 企业视角写飘成营销文 | 可信度下降 | 每条断言必须有源码证据；缺口如实列 |
| 与 `enterprise-operations/` 重复 | 维护双份 | 机制**指路**、治理**搬进来**（§4.1 判据）；混合体切分 |
| 工作量约 2100 行 | 单次做不完 | 分三批，每批独立可交付 |
| 2.2 确实**没有**的能力被误写成「有」 | 误导决策 | 「缺口」章节与「能力」章节分别列，不混写 |
| 合规映射表变成自我认证 | 法律风险 | 只做「机制 ↔ 控制项」的对应关系陈述，**不宣称合规** |

## 9. 质量保障

质量不是写完了再看看，而是**每篇交付前必须过的闸门**。下面四条闸门对应四类具体的
失败模式，每条都有可执行的检查方式。

**闸门已自动化**：`_digested/enterprise-it-governance/tools/check_quality.py` 实现 §9.2–§9.7 的全部检查，
当前跑出 26 处阻塞、27 处告警——这些就是本卷开工前的质量基线，也是终点的对照。

### 9.1 已发现的质量问题（现状基线）

不是假想风险，是扫描出来的实数：

| 问题 | 实测 | 影响 |
|---|---|---|
| **无证据断言** | 27 篇中 **18 篇零处 `file:line`**，平均 0.9 处/百行 | 不可核查，等于观点 |
| **语料基准线** | `observability/02` 17 处/百行、`security/03` 4.4、`journal/04` 5.7 | 目标线定在 **≥3 处/百行** |
| **同批自相矛盾** | `lifecycle/03` 写 ≤3，`execution/05` 写 64 | 读者不知道该信哪个 |
| **缺口缺乏精确边界** | 「无 PII 脱敏」不准确——有 `pii_redaction_middleware`，但 `config.example.yaml:2372` 明确写它**不覆盖记忆提取出口** | 说「无」会误导；说「有」也误导 |

### 9.2 闸门一：每条事实必须有可核验来源

**规则**：任何关于 DeerFlow 行为的陈述，必须能落到下列之一——

| 来源类型 | 写法 | 例子 |
|---|---|---|
| 源码锚点 | `` `path/file.py:NNN` `` | `` `packages/harness/deerflow/config/subagents_config.py:17` `` |
| 配置契约 | `` `config.example.yaml:NNN-NNN` `` | `` `config.example.yaml:3509-3602` `` |
| 上游文档 | `backend/docs/*.md` | `backend/docs/SSO.md` |
| 代码注释原话 | 引用注释时**必须带行号** | `config.example.yaml:2372` 写"does not cover this path" |

**硬指标**：每篇 **≥3 处 `file:line`**，且集中在**判断性段落**（矩阵表、缺口表、结论句）。
介绍性的过渡文字不需要锚点。

**核查方式**：交付前跑
```bash
# 逐篇统计证据密度
for f in <篇目>; do
  ev=$(grep -oE '`[a-zA-Z_/]+\.py:[0-9]+' "$f" | wc -l)
  echo "$f: $ev 处 / $(wc -l < "$f") 行"
done
```
并按 §6 的「关键事实抽查」逐条到 v2.2.0 树里验证行号**确实指向该断言**。

### 9.3 闸门二：缺口表述必须双向精确

**这是本卷最容易出错的地方。** 「有」和「没有」都可能错，正确答案往往是第三态。

**规则**：每个缺口按三态之一表述，**必须写清边界条件**——

| 态 | 写法模板 | 例子 |
|---|---|---|
| **无** | 「DeerFlow 无 X」+ 已确认搜索过 | kill switch：`grep -r "kill_switch" backend/` 零命中 |
| **有但不覆盖** | 「有 X，但**不覆盖 Y**」+ 行号 | PII 脱敏存在，但 `config.example.yaml:2372`：不覆盖记忆提取出口 |
| **部分闭合** | 「X 已改善，但 Y 未闭合」+ 两侧证据 | 操作完整性：有 `evidence_seal_state`，但**不**能证明 agent 只做了声称的事 |

**禁止**：只写「有」或「没有」而不写边界。**特别禁止**把「有但不覆盖」简化成「有」——
这会让人以为风险已消除。

### 9.4 闸门三：跨篇一致性

**问题**：拆分后已出现 `lifecycle/03`（≤3）与 `execution/05`（64）矛盾。
同一事实在多篇出现时，必须同源。

**规则**：

1. **单一事实源**：并发上限、超时、保留期、权限数量这类数字，**全文只在一篇定义**，
   其他篇引用时用相对链接，不复制数字。
2. **数字型事实建表**：维护 §9.5 的事实登记表，交付前逐篇核对。
3. **矛盾即阻塞**：发现两篇说法不同，**必须查源码定论**，不能留「两说并存」。

### 9.5 事实登记表（交付前逐条核对）

这些数字在语料里最容易漂移，每次改动后重跑核对：

| 事实 | 正确值 | 唯一来源 | 已核 |
|---|---|---|---|
| Subagent 单响应并发 | 64 | `packages/harness/deerflow/config/subagents_config.py:17` | ✅ |
| per-run 总量上限 | `max_total_per_run` 存在 | `packages/harness/deerflow/config/subagents_config.py:50` | ✅ |
| Guardrail 决策入 journal | 是，带 6 字段 | `packages/harness/deerflow/guardrails/middleware.py:171`（定义 `:131`） | ✅ |
| RBAC 权限数 | 11 | `app/gateway/authz.py:67-86` | ✅ |
| 登录限速默认 | 5 次 / 锁 300s | `config.example.yaml` auth 段 | 待核 |
| 沙箱模式数 | 7（6 provider 类） | `concepts/sandbox/*` | ✅ |
| PII 脱敏覆盖 | 有，**不覆盖**记忆提取出口 | `config.example.yaml:2372` | ✅ |
| kill switch | **无** | 全库 grep 零命中 | ✅ |

### 9.6 闸门四：可读性与体例

| 项 | 要求 |
|---|---|
| frontmatter | `title` / `description` / `topics` 三项齐全，与语料既有体例一致 |
| 标题层级 | 单页内 `#` 唯一，`##` 为节，`###` 为子节 |
| 表格优先 | 矩阵、对照、配置项一律用表，不用长句罗列 |
| 图 | 只在能压缩复杂关系时用（`figures/*.svg`），不为装饰加图 |
| 语气 | 陈述事实与边界；**不写**「贵司应该…」；成熟度自评与缺口分析保留 |
| 长度 | 单篇 60–200 行；超过 200 行考虑拆分，低于 40 行考虑合并 |

### 9.7 合规映射的额外约束

`compliance/` 是本卷法律风险最高的部分：

1. **只陈述对应关系**，不写「DeerFlow 符合 GDPR 第 X 条」。
   正确写法：「GDPR 第 17 条（删除权）↔ DeerFlow 的 `trash_retention_days` + 事件删除接口
   ↔ 证据见 `file:line` ↔ 状态：**部分覆盖**（事件删除会让证据变 `partial`）」
2. **缺口必须显式标注**，不能用「部分覆盖」含糊带过。
3. **每篇开头声明**：本文不构成合规结论，结论须由审计方给出。

### 9.8 交付前检查清单

每批提交前逐条确认：

- [ ] `check_digest.py` exit 0（断链、行号越界、锚点、环境变量）
- [ ] `_digested/enterprise-it-governance/tools/check_quality.py` exit 0（本文 §9.2–§9.7 的自动化闸门）
- [ ] `_digested/enterprise-it-governance/tools/verify_anchors.py` exit 0（所有 `file:line` 存在且在范围内）
- [ ] 三目录铁律输出 `0`
- [ ] 每篇 ≥3 处 `file:line`，且指向的断言正确
- [ ] §9.5 事实登记表全部已核，无新旧矛盾
- [ ] 所有缺口表述为三态之一，边界条件写明
- [ ] 无「贵司应该」类采购建议
- [ ] `compliance/` 每篇有免责声明
- [ ] frontmatter 三项齐全，单篇 60–200 行
- [ ] 搬迁任务（如本批有）执行完毕，原文件无残留断链
