---
title: "IT 治理视角"
description: "IT 部门负责人关心的不是 "middleware 怎么写的"，而是 "这东西上线之后会不会出事"。安全、合规、审计、成本、运维——这些非功能需求在 Agent 时代变得更紧迫，因为 agent 不是被动回答问题，而是**主动执行操作**。"
type: index
---

# IT 治理视角

IT 部门负责人关心的不是 "middleware 怎么写的"，而是 "这东西上线之后会不会出事"。安全、合规、审计、成本、运维——这些非功能需求在 Agent 时代变得更紧迫，因为 agent 不是被动回答问题，而是**主动执行操作**。

**回答的核心问题**：从 IT 管理者角度看，DeerFlow 在 12 个治理维度上的能力与差距——访问控制、沙箱治理、策略执行、审计可观测、合规生命周期。

> **约束：不修改项目源代码。** 本 `_digest/` 下所有内容仅作研究记录。详见 [根 README](../README.md)。

## 阅读顺序

| 文件 | 内容 |
|------|------|
| **00-overview.md** | IT 治理全景：Agent 时代的 12 个 IT 管理维度，DeerFlow 能力映射，成熟度评估 |
| **01-access-control.md** | 访问控制：认证、用户隔离、凭证管理、no-auth 模式风险 |
| **02-sandbox-governance.md** | 沙箱治理：三种模式安全画像、6 层路径防穿透、资源限制、per-thread 隔离 |
| **03-policy-enforcement.md** | 策略执行：Guardrails 体系、SandboxAudit、循环检测、subagent 并发限制、bounded autonomy |
| **04-audit-observability.md** | 审计与可观测：审计日志、Tracing、token 用量追踪、StreamBridge SSE 事件、成本归属 |
| **05-compliance-lifecycle.md** | 合规与生命周期：数据隔离/GDPR、路径脱敏、文件上传安全、配置生命周期、Agent 蔓延风险 |

## 关键问题（IT 管理者关心的）

- 一个 prompt 能搞出 `rm -rf /` 吗？→ `02-sandbox-governance.md` 6 层防线
- 怎么限制 agent 只能调某些 tool？→ `03-policy-enforcement.md` Guardrails
- 用户之间数据隔离吗？→ `01-access-control.md` per-user isolation
- agent 干了什么能审计到吗？→ `04-audit-observability.md` 审计链路
- 有没有防死循环/无限制消费？→ `03-policy-enforcement.md` LoopDetection + TokenUsage
- 能满足合规要求吗（GDPR/SOC2）？→ `05-compliance-lifecycle.md` 合规考量
- no-auth 模式有什么风险？→ `01-access-control.md` 风险评估

## 跨目录索引

IT 治理视角的文档**整合**了以下目录的内容，不重复叙述细节，而是从管理视角给出判断和差距分析：

| 原文档位置 | 被整合到 |
|-----------|---------|
| [security/01-auth.md](../security/01-auth.md) | [01-access-control.md](01-access-control.md) |
| [security/02-sandbox-isolation.md](../security/02-sandbox-isolation.md) | [02-sandbox-governance.md](02-sandbox-governance.md) |
| [security/03-guardrail.md](../security/03-guardrail.md) | [03-policy-enforcement.md](03-policy-enforcement.md) |
| [security/04-trust-boundary.md](../security/04-trust-boundary.md) | [00-overview.md](00-overview.md) (defense-in-depth) |
| [concepts/sandbox/abstract-interface-and-three-impls.md](../../concepts/sandbox/abstract-interface-and-three-impls.md) | [02-sandbox-governance.md](02-sandbox-governance.md) |
| [architecture/10-persistence.md](../../internals/persistence/db-checkpointer-store-backends.md) | [04-audit-observability.md](04-audit-observability.md) |
| [configuration/00-overview.md](../../getting-started/00-config-overview.md) | [05-compliance-lifecycle.md](05-compliance-lifecycle.md) |
| [middleware/03-catalog.md](../../internals/middleware/03-catalog.md) | 各主题文档引用 |
