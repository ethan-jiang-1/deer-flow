---
title: "harness — 代码仓库对 coding agent 友好度研究"
description: "本目录调研「一个仓库/项目如何做到对 coding agent（Claude Code、Codex、Cursor、DeerFlow 等）友好」：公认标准、模式与反模式，以一手来源为准，含五维评估框架、60 条审计清单与真实案例精读。"
type: index
topics: [harness, coding-agent, agents-md, ax]
---

# harness — 代码仓库对 coding agent 友好度研究

> **定位**：回答一个问题——**一个代码仓库要怎样组织，才能让 coding agent 高效工作？** 覆盖公认标准、各厂商的仓库指引机制、工具与测试接口设计、真实案例与可勾选审计清单；给要改造仓库或审计 agent 友好度的工程团队看。
> **边界**：做通用标准与横向案例研究，不替代 DeerFlow 的专项工程质量评估（见 [harness-engineering/](../harness-engineering/README.md)），也不做其运行时机制解剖（见 [internals/](../internals/README.md)）。

**一句话结论**：**AGENTS.md 已成事实标准，但友好度取决于三件事**——可预测的指令入口与分层就近、可自主闭环的确定性验证命令、以及把软指令升级为 hooks / permissions 的硬约束；AX = DX + 无状态读者、注意力预算、自主执行体三个新约束。

## 阅读路径

1. **先看**：[01-what-makes-repo-agent-friendly.md](01-what-makes-repo-agent-friendly.md) — 五维评估框架、各厂商机制对照与反模式速查，先建立判断坐标。
2. **再看**：[03-harness-consumption-deep-dive.md](03-harness-consumption-deep-dive.md) — Claude Code / Codex / Cursor / Aider / Gemini CLI / DeerFlow 各自在何时、按什么预算消费仓库。
3. **深入**：[09-dsh-eval-harness.md](09-dsh-eval-harness.md) — 自说明版 28 维记分法，以及在 deer-flow 上的红绿结果与活体实证。

## 本篇目

| 文件 | 主题 | 深度 |
|---|---|---|
| [01-what-makes-repo-agent-friendly.md](01-what-makes-repo-agent-friendly.md) | AGENTS.md 规范、厂商机制对照、五维框架与反模式 | 概览 |
| [02-ax-from-dx-to-ax.md](02-ax-from-dx-to-ax.md) | Agent Experience：DX→AX 演化、七原则、与可维护性的异同 | 深入 |
| [03-harness-consumption-deep-dive.md](03-harness-consumption-deep-dive.md) | 六种 harness 的注入时机、预算上限与失败模式 | 深入 |
| [04-tool-and-interface-design.md](04-tool-and-interface-design.md) | 工具与接口设计：命名空间、返回值预算、错误可行动性 | 深入 |
| [05-verifiability-and-test-infra.md](05-verifiability-and-test-infra.md) | 验证闭环六原则，并用本仓库测试布局印证 | 深入 |
| [06-case-studies.md](06-case-studies.md) | openai/codex、airflow、electron 等六仓库 AGENTS.md 精读 | 深入 |
| [07-audit-checklist.md](07-audit-checklist.md) | 60 条可勾选审计项：查法、合格标准、打分权重 | 概览 |
| [08-deerflow-audit.md](08-deerflow-audit.md) | 按 60 条对本仓库逐条实测：A-、Top 问题与路线图 | 深入 |
| [09-dsh-eval-harness.md](09-dsh-eval-harness.md) | DSH 28 维记分法（机制自内含）+ 红绿结果与活体实验 | 深入 |
| [10-runtime-participation-rules.md](10-runtime-participation-rules.md) | 五个运行时参与问题的分层取证与缺口登记 | 深入 |

**配图**（`figures/`，SVG 浏览器直接打开）：[dx-to-ax](figures/dx-to-ax.svg)（02 DX→AX 演化）、[context-injection-pipeline](figures/context-injection-pipeline.svg)（03 注入管线）、[tool-lifecycle](figures/tool-lifecycle.svg)（04 工具生命周期）、[verification-loop](figures/verification-loop.svg)（05 验证闭环）、[audit-framework](figures/audit-framework.svg)（07 审计框架）、[deerflow-dsh-scorecard](figures/deerflow-dsh-scorecard.svg)（09 28 维记分卡）、[participation-layers](figures/participation-layers.svg)（10 参与规则三层载体）。

## 宪章与约定

- 本目录把运行时参与规则单列为一篇宪章页：[10-runtime-participation-rules.md](10-runtime-participation-rules.md) — 能力可见性、依赖未就绪、同名隔离、清理归属、配置到树五问，为后续审计定纪律。
- 其余写作纪律沿用 [根 README](../README.md)：论断尽量给一手来源、按 `0X-*.md` 编号、图放 `figures/`。

## 相关目录

- [harness-engineering/](../harness-engineering/README.md) — DeerFlow 专项工程质量评估：文档体系、证据文化与反馈三环。
- [graph-engineering/](../graph-engineering/README.md) — 图工程支持度判定与编排注入，另一条「能力边界」评估线。
- [../README.md](../README.md) — 根索引：全部目录的阅读地图。
