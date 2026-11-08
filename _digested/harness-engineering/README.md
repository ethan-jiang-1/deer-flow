---
title: "Harness 工程评估"
description: "从 coding agent 的视角评估 DeerFlow 的 harness 工程质量：agent 文档体系、证据文化、测试工程，以及跨 sync #1 → #8 的关键改善与总评。"
type: index
topics: [harness, engineering, agent-docs, assessment]
---

# Harness 工程评估

> **定位**：回答一个问题——**如果把我（一个 coding agent）扔进 DeerFlow 仓库，我能不能高效、不出错地理解和修改它？** 从 agent 文档体系、工程证据文化、测试工程与反馈三环四条线取证，并给出跨 sync #1 → #8 的关键改善与总评。
> **边界**：这是 DeerFlow 的专项评估，不做通用 agent-friendly 标准调研（见 [harness/](../harness/README.md)），也不做运行时机制解剖（见 [internals/](../internals/README.md)）；结论只覆盖本仓库。

**一句话结论**：DeerFlow 把「给 agent 写文档」当作工程问题来解，处于同类开源项目第一梯队；最大改善发生在 #4→#5（AGENTS.md 从 4 个到 25 个），v2.2.0 窗口预算门禁两次真实咬合（`#6759` 98,441 > 98,304、`#7522` 99,004 → 80,817）且均未调阈值。总评：Agent 文档覆盖 5 / 文档保鲜 4 / 证据文化 4.5 / 测试工程 4.5 / 人类文档 3；残留风险是编号与顺序类文档漂移（实例见 [01](01-agent-docs-system.md)）。

## 阅读路径

1. **先看**：[01-agent-docs-system.md](01-agent-docs-system.md) — 分层 AGENTS.md、上下文预算 CI、可执行文档测试，以及编号漂移案例。
2. **再看**：[02-engineering-evidence.md](02-engineering-evidence.md) — 契约文档、实验包、基准与测试工程如何构成可复核证据。
3. **深入**：[03-feedback-loops.md](03-feedback-loops.md) — 反馈三环，以及产品记忆（模型级）与工程学习（仓库级）的纪律分离。

## 本篇目

| 文件 | 主题 | 深度 |
|---|---|---|
| [01-agent-docs-system.md](01-agent-docs-system.md) | 分层 AGENTS.md 网络、上下文预算强制与可执行文档测试 | 深入 |
| [02-engineering-evidence.md](02-engineering-evidence.md) | 契约文档、可复现实验包、基准测试与测试工程 | 深入 |
| [03-feedback-loops.md](03-feedback-loops.md) | 失败标记、先账后投影、仓库级学习与两次记忆分歧 | 深入 |

**配图**：[feedback-loops.svg](figures/feedback-loops.svg) — 反馈三环与两条学习通道（嵌入 [03](03-feedback-loops.md)）。

## 宪章与约定

- 本目录无独立宪章；写作纪律沿用 [根 README](../README.md)：结论给可复核路径，跨同步轨迹以 `*AGENTS.md` 恰名口径计数（详见 [01](01-agent-docs-system.md)）。
- 评估基线：sync #1 → #8（`162fb214` → `58fc5bd5b`，2026-07-04 → 2026-11-04）；v2.1.0 → v2.2.0 窗口本身有 1,239 commits。

## 相关目录

- [harness/](../harness/README.md) — 通用 agent-friendly 标准、60 条审计清单与 DSH 28 维镜片；本目录是其 DeerFlow 专项纵深。
- [orchestration-ladder/](../orchestration-ladder/README.md) — 跨原语统一视角，补足「运行时保证什么」的另一半。
- [../README.md](../README.md) — 根索引：全部目录的阅读地图。
