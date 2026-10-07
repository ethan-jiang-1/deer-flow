# 运维反馈与失败回写

## 什么时候读这里

发布之后：部署侧的问题怎么进来（support bundle）、agent 参与评审时被允许做什么（maintainer orchestrator）、以及事故怎样沉淀成机制。这页是主仓 SDLC 闭环的收口。

## 主仓机制

**脱敏的问题报告包（成文标准 + 工具）**。`make support-bundle` 生成脱敏的 issue summary、AI 辅助填报草稿与可选证据 zip。设计上的克制值得注意：草稿**刻意不编造**复现步骤、预期行为或问题摘要（REQUIRED 占位符留给填写者）；bundle 明确不含 `.env`、原始对话消息与 workspace 文件（[CONTRIBUTING.md](https://github.com/bytedance/deer-flow/blob/v2.1.0/CONTRIBUTING.md)）。

**agent 评审的信任边界（成文标准，skill 设计文档）**。maintainer-orchestrator 把 agent 评审钉在**评论面**——只发 issue/PR 评论，不写代码、不管理分支、不关闭/打标 artifact、不发版；公开评论要求 confidence 与 severity **双轴同时达标**，低于门槛的发现进维护者私有通道；并且：

> **Evidence over a green check.** CI status is a signal, not a verdict. A green rollup never excuses reading the changed code path, and a failing required check is itself a finding. Tests passing does not prove the changed branch is exercised.
>
> — [maintainer-orchestrator-design.md](https://github.com/bytedance/deer-flow/blob/v2.1.0/docs/agents/maintainer-orchestrator-design.md)

设计文档给出的可迁移原则就三条：让 agent 停在**可逆表面**（评论）直到被信任；公开输出按置信度×严重度双轴门控、其余走私有通道；要求 agent 证明它评审的是**当前 diff**。

**失败回写成机制（实现归纳，有实例无门禁）**。可核验的实例：uv 版本漂移风险 → 版本钉住测试（见[架构契约](./06-architecture-docs-contracts.md)）；migration 插队事故 → 修复 migration + 回归测试（见[迁移链](./08-schema-migrations.md)）；指南膨胀 → 预算 CI。**边界**：这类回写有多个实例但**没有全仓强制的 postmortem/ADR 门禁**——"失败必须沉淀成机制"是文化惯性，不是可检查的流程。诚实的读法：主仓的学习发生在仓库（规则/门禁/契约），不依赖个人记忆，但回写是否发生取决于人。

## 应用仓适用边界

**可移用**：support-bundle 的形态（脱敏 + 不编造的 AI 草稿 + 明确的包含/排除清单）——应用仓接用户报障时同样需要"用户能安全地贴出来"的报告物；agent 评审的三原则原样适用于任何想引入 AI 评审的仓。**最值得想清楚的一条**：你的仓要不要把"事故 → 测试/门禁"写成显式要求（哪怕是 PR 模板里的一行"这个 bug 的回归测试在哪"）。主仓靠惯性做到了；应用仓可以在制度里明说，这是比主仓更进一步的机会。

## 证据入口

- [CONTRIBUTING.md](https://github.com/bytedance/deer-flow/blob/v2.1.0/CONTRIBUTING.md) Troubleshooting Bundle 节
- [maintainer-orchestrator-design.md](https://github.com/bytedance/deer-flow/blob/v2.1.0/docs/agents/maintainer-orchestrator-design.md)（safety model / posting bar / principles / adapting 各节）
