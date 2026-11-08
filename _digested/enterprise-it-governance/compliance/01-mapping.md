---
title: "合规对照"
description: "GDPR / SOC2 / ISO27001 / EU AI Act 逐条映射。"
topics: [governance, compliance]
---

# 合规对照

GDPR / SOC2 / ISO27001 / EU AI Act 逐条映射。

## 合规考量

### GDPR 相关

| 要求 | DeerFlow 现状 | 差距 |
|------|-------------|------|
| **数据访问权** | Per-user 存储 → 技术上可导出 `users/{user_id}/` | 无内建导出工具 |
| **数据删除权** | `DELETE /api/threads/{id}` → 删除 thread 数据 | 无批量删除；memory 无自动过期 |
| **数据处理记录** | 审计日志 + tracing → 能追溯 agent 操作 | 日志非结构化，需手动解析 |
| **数据最小化** | 无数据分类标签；memory 提取全量对话事实 | 无敏感数据自动识别 |
| **跨境传输** | 取决于 LLM provider（API 调用→数据传输到 provider） | 使用海外 provider（Anthropic/OpenAI）时自动触发跨境 |

### SOC2 / ISO27001

| 控制域 | DeerFlow 能力 | 证据 |
|--------|-------------|------|
| **访问控制** | JWT + per-user isolation | `security/01-auth.md` |
| **审计日志** | SandboxAudit + RunJournal + tracing | `../audit/README.md` |
| **变更管理** | Config 版本控制（git）+ hot-reload | `configuration/` |
| **风险评估** | 沙箱隔离 + guardrail + 循环检测 | `00-overview.md` 12 维度矩阵 |
| **供应商管理** | LLM provider 依赖（Anthropic/OpenAI/等） | 需要自行评估各 provider 合规状态 |

**核心差距：** DeerFlow 有技术控制，但缺乏合规文档（SOC2 report、ISO27001 证书）。如果你的企业需要通过这些审计，DeerFlow 是**你可以纳入合规范围的基础设施组件**，但本身不出具合规证明。

### EU AI Act（2026 年 8 月生效）

DeerFlow 作为一个通用 Agent 框架，不属于高风险 AI 系统（不直接用于关键基础设施、执法、教育评分等）。但**你的 use case 可能是**。如果你用 DeerFlow 构建面向消费者的金融服务 agent，那它就在 EU AI Act 范围内。

需要评估的要素：
- Agent 自主性级别（DeerFlow 的 bounded autonomy → 可配置）
- 人工监督机制（ClarificationMiddleware 提供对话式交互，非权限审批）
- 透明性（模型回复的 AI 标签、用户被告知在与 AI 交互的程度）

