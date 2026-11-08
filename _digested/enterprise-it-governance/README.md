---
title: "IT 治理视角"
description: "IT 部门负责人关心的不是 "middleware 怎么写的"，而是 "这东西上线之后会不会出事"。安全、合规、审计、成本、运维——这些非功能需求在 Agent 时代变得更紧迫，因为 agent 不是被动回答问题，而是**主动执行操作**。"
type: index
---

# IT 治理视角

IT 部门负责人关心的不是 "middleware 怎么写的"，而是 "这东西上线之后会不会出事"。安全、合规、审计、成本、运维——这些非功能需求在 Agent 时代变得更紧迫，因为 agent 不是被动回答问题，而是**主动执行操作**。

**回答的核心问题**：从 IT 管理者角度看，DeerFlow 在 12 个治理维度上的能力与差距——访问控制、沙箱治理、策略执行、审计可观测、合规生命周期。

> **约束：不修改项目源代码。** 本 `_digested/` 下所有内容仅作研究记录。详见 [根 README](../README.md)。

## 阅读顺序

| 文件 | 内容 |
|------|------|
| **00-overview.md** | IT 治理全景：Agent 时代的 12 个 IT 管理维度，DeerFlow 能力映射，成熟度评估 |
| **identity/README.md** | 访问控制：认证、用户隔离、凭证管理、no-auth 模式风险 |
| **execution/README.md** | 沙箱治理：三种模式安全画像、6 层路径防穿透、资源限制、per-thread 隔离 |
| **authorization/README.md** | 策略执行：Guardrails 体系（🆕 三道工具级风险门）、SandboxAudit、循环检测、subagent 并发限制、bounded autonomy |
| **audit/README.md** | 审计与可观测：审计日志、Tracing、token 用量追踪、StreamBridge SSE 事件、成本归属、🆕 guardrail 决策入 RunJournal / completed-run evidence |
| **data/README.md** | 合规与生命周期：数据隔离/GDPR、路径脱敏、文件上传安全、配置生命周期、Agent 蔓延风险、🆕 插件变更控制与 skill mutation 发布闸门 |

## 关键问题（IT 管理者关心的）

- 一个 prompt 能搞出 `rm -rf /` 吗？→ `execution/README.md` 6 层防线
- 怎么限制 agent 只能调某些 tool？→ `authorization/README.md` Guardrails
- 🆕 名单门不够用，想要模型判定的风险门？→ `authorization/README.md` 三个内置门
- 🆕 插件能拿到什么权限、怎么收回？→ `data/README.md` 扩展与插件的变更控制
- 用户之间数据隔离吗？→ `identity/README.md` per-user isolation
- agent 干了什么能审计到吗？→ `audit/README.md` 审计链路
- 有没有防死循环/无限制消费？→ `authorization/README.md` LoopDetection + TokenUsage
- 能满足合规要求吗（GDPR/SOC2）？→ `data/README.md` 合规考量
- no-auth 模式有什么风险？→ `identity/README.md` 风险评估

## 与 `enterprise-operations/` 的分工

本目录回答「**能不能被企业 IT 管起来**」，`../enterprise-operations/` 回答「**怎么装、怎么配、怎么运维**」。

| | 本目录（治理视角） | `enterprise-operations/`（实现视角） |
|---|---|---|
| 读者 | IT 负责人、安全评审、合规 | 平台工程师、SRE |
| 问题 | 能不能接 Okta？离职账号怎么回收？被拒绝的操作能不能导报告？ | 认证中间件怎么走？Docker 怎么起？nginx 怎么配？ |
| 产出 | 能力矩阵 + 证据位置 + 缺口 | 机制说明 + 配置项 + 操作步骤 |

## 跨目录索引

治理文档**判断**机制是否足够，机制本身在下列位置，此处不重复叙述：

| 机制细节所在地 | 治理判断所在地 |
|-----------|---------|
| [enterprise-operations/security/01-auth.md](../enterprise-operations/security/01-auth.md) | [identity/README.md](identity/README.md) |
| [enterprise-operations/security/02-sandbox-isolation.md](../enterprise-operations/security/02-sandbox-isolation.md) | [execution/README.md](execution/README.md) |
| [enterprise-operations/security/03-guardrail.md](../enterprise-operations/security/03-guardrail.md) | [authorization/README.md](authorization/README.md) |
| [enterprise-operations/security/04-trust-boundary.md](../enterprise-operations/security/04-trust-boundary.md) | [00-overview.md](00-overview.md)（defense-in-depth） |
| [enterprise-operations/security/06-extension-boundary.md](../enterprise-operations/security/06-extension-boundary.md) | [authorization/README.md](authorization/README.md)、[lifecycle/README.md](lifecycle/README.md) |
| [concepts/sandbox/abstract-interface-and-seven-impls.md](../concepts/sandbox/abstract-interface-and-seven-impls.md) | [execution/README.md](execution/README.md) |
| [internals/persistence/db-checkpointer-store-backends.md](../internals/persistence/db-checkpointer-store-backends.md) | [audit/README.md](audit/README.md) |
| [getting-started/00-config-overview.md](../getting-started/00-config-overview.md) | [data/README.md](data/README.md) |
| [internals/middleware/03-catalog.md](../internals/middleware/03-catalog.md) | 各主题文档引用 |
