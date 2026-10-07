# spec 与实现计划：设计决策的唯一产权

## 什么时候读这里

变更足够大、需要设计文档时：DeerFlow 主仓怎么分 RFC / spec / implementation plan 三级，产权怎么划，偏离怎么登记。这是主仓 SDLC 里最值得应用仓整卷搬走的一页。

## 主仓机制

**成文标准（spec 自我声明产权）**。Projects Phase 2 的 spec 开篇即钉死权威与基线：

> **Source of truth**: **This spec governs Phase 2 in full** … every current-system claim below was re-verified against `main @ 0464502a` (2026-09-12) in this checkout.
>
> — [projects-mvp-phase2-design.md](https://github.com/bytedance/deer-flow/blob/v2.1.0/docs/superpowers/specs/2026-09-12-projects-mvp-phase2-design.md)

**成文标准（实现计划自降产权）**。配套的 implementation plan 明确自己只排序、不决策：

> **Scope rule**: every design decision, error mapping, and review-gate is owned by the spec. This document sequences files, symbols, and verification only. Where the spec and code disagree, the spec's deviation register (§10) wins.
>
> — [projects-mvp-phase2-implementation-plan.md](https://github.com/bytedance/deer-flow/blob/v2.1.0/docs/superpowers/plans/2026-09-13-projects-mvp-phase2-implementation-plan.md)

**spec 自带可执行的后续章节**。以 scheduled-tasks spec 为例：Testing Strategy 分层列出单测/集成/前端/mock E2E，并写明 real-path validation "Required before claiming feature complete"；Documentation Updates Required 逐文件列出代码落地时要同步的 README/AGENTS.md；Code Review Checklist 把评审条目编号（如 "Harness persistence does not import `app.*`"）（[scheduled-tasks-mvp-design.md](https://github.com/bytedance/deer-flow/blob/v2.1.0/docs/superpowers/specs/2026-07-01-scheduled-tasks-mvp-design.md)）。

**按切片推进、收尾重读检查单**。实现计划把工作切成依赖有序的 slice，每个 slice 收尾时跑 lint+test 并重读 spec 评审清单；并发测试被标为 hard requirement 而非可选打磨（[projects-mvp-phase2-implementation-plan.md](https://github.com/bytedance/deer-flow/blob/v2.1.0/docs/superpowers/plans/2026-09-13-projects-mvp-phase2-implementation-plan.md)）。

**机器门禁**：无——没有 workflow 强制"大变更必须先有 spec"。这是文档纪律，靠评审与习惯执行。**运行时事实的例外**：spec 修订过程中实现侧的偏差会被 spec 的 deviation register 正式吸收（Phase 2 spec 修订注记即为一例），偏离不是隐瞒而是登记。

## 应用仓适用边界

**可移用**（几乎是全套）：设计决策只写一份权威；实现计划明确无权重新设计；测试策略、文档清单、评审检查单直接写进 spec；切片收尾重读检查单。**按规模裁剪**：小变更可以只有一段意图描述 + 验证方式，不必造三份文档——产权原则（决策只在一个地方）保留，形式随规模伸缩。**应用仓建议**：coding agent 参与开发时，这条尤其重要——agent 天然倾向于在实现文件里"顺手重新设计"，spec 产权 + deviation register 是把这个倾向拉回可评审轨道的机制。

## 证据入口

- [projects-mvp-phase2-design.md](https://github.com/bytedance/deer-flow/blob/v2.1.0/docs/superpowers/specs/2026-09-12-projects-mvp-phase2-design.md) 与 [projects-mvp-phase2-implementation-plan.md](https://github.com/bytedance/deer-flow/blob/v2.1.0/docs/superpowers/plans/2026-09-13-projects-mvp-phase2-implementation-plan.md)
- [scheduled-tasks-mvp-design.md](https://github.com/bytedance/deer-flow/blob/v2.1.0/docs/superpowers/specs/2026-07-01-scheduled-tasks-mvp-design.md) Testing Strategy / Documentation Updates Required / Code Review Checklist 三节
