---
title: "harness — 代码仓库对 coding agent 友好度研究"
description: "本目录调研「一个仓库/项目如何做到对 coding agent（Claude Code、Codex、Cursor、DeerFlow 等）友好」：公认标准、模式与反模式，以一手来源为准，含五维评估框架、60 条审计清单与真实案例精读。"
---

# harness — 代码仓库对 coding agent 友好度研究

> 本目录回答一个问题：**一个代码仓库要怎样组织，才能让 coding agent 高效工作？** 所有论断尽量给出一手来源（官方文档 / 规范原文 / 厂商工程博客）的 markdown 链接。专题配图见各篇 `figures/`。

## 阅读路径

| 你想… | 去这里 | 重点 |
|--------|--------|------|
| 快速了解框架与反模式 | [01-what-makes-repo-agent-friendly.md](01-what-makes-repo-agent-friendly.md) | AGENTS.md 规范 + 各厂商机制对照表 + 五维评估框架 + 反模式速查表 |
| 理解概念背景 | [02-ax-from-dx-to-ax.md](02-ax-from-dx-to-ax.md) | DX→AX 演化、Builder.io 七原则、AX 与可维护性异同（图：[dx-to-ax](figures/dx-to-ax.svg)） |
| 深挖各 harness 怎么消费仓库 | [03-harness-consumption-deep-dive.md](03-harness-consumption-deep-dive.md) | Claude Code / Codex / Cursor / Aider / Gemini CLI / DeerFlow 的注入时机、预算上限、失败模式（图：[context-injection-pipeline](figures/context-injection-pipeline.svg)） |
| 设计面向 agent 的接口 | [04-tool-and-interface-design.md](04-tool-and-interface-design.md) | 命名空间、返回值 token 预算、错误可行动性、聚合操作、工具数量（图：[tool-lifecycle](figures/tool-lifecycle.svg)） |
| 建设测试基建 | [05-verifiability-and-test-infra.md](05-verifiability-and-test-infra.md) | 验证闭环六原则 + deer-flow 真实测试布局印证（图：[verification-loop](figures/verification-loop.svg)） |
| 看真实仓库怎么做 | [06-case-studies.md](06-case-studies.md) | openai/codex、apache/airflow、electron、temporal-sdk-java、deer-flow 精读与横向对比 |
| 动手审计一个仓库 | [07-audit-checklist.md](07-audit-checklist.md) | 60 条可勾选检查项（每条含查法/合格标准/依据）+ 打分与权重建议（图：[audit-framework](figures/audit-framework.svg)） |
| 看 deer-flow 的实测得分 | [08-deerflow-audit.md](08-deerflow-audit.md) | 按 07 篇 60 条对本仓库逐条实证审计：总评 A-、五维得分、Top 问题与整改路线图 |
| 用 DSH 的镜片给本仓库打分 | [09-dsh-eval-harness.md](09-dsh-eval-harness.md) | 按 DSH `_eval_harness` 协议（覆盖面×约束力两轴、封顶、红绿、MG 档）给 deer-flow v2.1.0 的 28 维打分：开发侧 10 红 / 7 绿、运行时侧 6 红 / 5 绿，两侧均 MG1、达标线未达；EV2 负例控制 0/0 与模型可见面不落盘是两根钉子；含切片走查、gap 清单与施工顺序，并与 08 篇的 A- 对照（图：[deerflow-dsh-scorecard](figures/deerflow-dsh-scorecard.svg)） |

## 关键结论速览

1. **指令文件已成为事实标准**：[AGENTS.md](https://agents.md/) 规范被 6 万+ 开源项目采用，Claude Code、Codex、Cursor、Gemini CLI、Aider 等均原生或可配置读取；无必填字段，最靠近被编辑文件的文件优先。
2. **上下文是有限资源**：Anthropic 的 [context engineering](https://www.anthropic.com/engineering/effective-context-engineering-for-ai-agents) 与 Chroma 的 [context rot](https://www.trychroma.com/research/context-rot) 研究表明，token 越多、注意力越稀释 → 指令要少而精、具体、可验证。
3. **闭环反馈是核心**：给 agent 确定性的构建/测试命令，让它能自主验证自己的修改，是各规范（如 AGENTS.md 测试指令、Codex review 规则"格式检查留给 CI"）的共同要求。
4. **软指令 ≠ 硬约束**：Claude Code 官方明确 CLAUDE.md 是"上下文而非强制配置"，必须生效的用 hooks / settings enforce —— 这是安全护栏维度的分界线。
5. **AX = DX + 三个新约束**：无状态读者、注意力预算、自主执行体（见 [02 篇](02-ax-from-dx-to-ax.md)）。

## 与本仓库的关系

deer-flow 本身就是这套标准的范本之一（根 `AGENTS.md` 定位层 + 嵌套模块指南 + `CLAUDE.md` 薄 shim + 离线测试子集），[06 篇案例 5](06-case-studies.md) 有精读；[07 篇](07-audit-checklist.md)可直接用于对本仓库逐条打分。

## 文件命名约定

- `README.md` — 本目录阅读指南
- `0X-*.md` — 按推荐阅读顺序编号
- `figures/*.svg` — 手写 SVG 图（浏览器直接打开渲染）
