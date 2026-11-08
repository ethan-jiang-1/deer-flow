---
title: "Testing — 测试策略与实践"
description: "Agent 测试的实操层：DeerFlow 自己的测试基建 + 开发者测试模式 + CI 与 record/replay。"
type: index
topics: [testing, ci, agent-testing]
---

# Testing — 测试策略与实践

> **定位**：Agent 测试是所有 AI 应用里最棘手的部分。这里分两层：DeerFlow 自己怎么测自己（00–03，可参考），你写 DeerFlow 应用时怎么测（04–09，可抄）。
> **边界**：不覆盖测试体系的思想与分类学（见 [test-strategy](../test-strategy/README.md)），不覆盖上线后的观察与诊断（见 [observability](../observability/README.md)），单个仓库的测试纪律以根 `AGENTS.md` 为准。

## 阅读路径

1. **先看**：[00-overview.md](00-overview.md) — 四层测试体系（Boundary / Unit / Gate / E2E）与 v2.2.0 规模。
2. **再看**：[04-agent-test-patterns.md](04-agent-test-patterns.md) — 写应用最常用的模式：FakeToolCallingModel、tool call 验证、sub-agent 与流式测试。
3. **深入**：[07-record-replay.md](07-record-replay.md) — ReplayChatModel：输入哈希、volatile 归一化、caller-aware key 与 golden shape 断言。

## 本篇目

| 文件 | 主题 | 深度 |
|---|---|---|
| [00-overview.md](00-overview.md) | 测试金字塔与规模数字 | 概览 |
| [01-harness-boundary.md](01-harness-boundary.md) | Harness/App 边界 AST 扫描 + Blocking IO 双层检测 | 深入 |
| [02-gateway-conformance.md](02-gateway-conformance.md) | SDK ↔ Gateway 格式一致性（11 个方法） | 概览 |
| [03-e2e-and-unit.md](03-e2e-and-unit.md) | Playwright E2E 四车道 + Rstest 前端 + pytest 后端分片 | 深入 |
| [04-agent-test-patterns.md](04-agent-test-patterns.md) | FakeToolCallingModel、tool call 验证、sub-agent、流式、中间件测试模板 | 深入 |
| [05-testing-skills-and-workflows.md](05-testing-skills-and-workflows.md) | Skill 加载、workflow 行为序列（trajectory）、`interrupt_before` 单步评测 | 概览 |
| [06-ci-and-automation.md](06-ci-and-automation.md) | CI 流水线、`@requires_llm`、环境隔离、Token 预算、决策矩阵 | 深入 |
| [07-record-replay.md](07-record-replay.md) | ReplayChatModel 深度：哈希、归一化、caller-aware key、golden 断言 | 深入 |
| [08-testing-patterns-reference.md](08-testing-patterns-reference.md) | 12 节可复用模式：FakeRedis、FrozenDatetime、竞态替身、故障注入 Fake、Textual pilot | 概览 |
| [09-what-to-copy-from-deerflow-ci.md](09-what-to-copy-from-deerflow-ci.md) | 可复制到自建项目的 CI 模板、fixture、replay 与验收模板 | 概览 |

## 速览

- **规模（v2.2.0）**：1,363 个后端测试文件 / 23,432 个 `def test`、348 个前端 unit（node 202 / dom 146）、93 个 Playwright spec；`blocking_io/` 89 个文件 + 4 条 gate 元测试。
- **四层**：Boundary（import 边界 AST 扫描）→ Unit → Gate（Gateway 一致性）→ E2E（Playwright 4 分片 + pytest 4 分片时长感知）。
- **两条轨道**：00–03 是「DeerFlow 怎么测自己」的参考；04–09 是「你该怎么测」的模板，两者共用同一批 Fake / Replay 资产。

## 宪章与约定

- 本目录无独立宪章；写作纪律沿用 [根 README](../README.md)。测试**思想与成文规矩**在 [test-strategy/01-doctrine.md](../test-strategy/01-doctrine.md)。
- 数字口径：规模数字以 00 篇的 v2.2.0 统计为准，正文里的旧数保留并标注版次。

## 相关目录

- [test-strategy/](../test-strategy/README.md) — 体系研究：思想、分类学、机制咬合与上层应用测试面。
- [concepts/skills-tools/](../concepts/skills-tools/README.md) — 05 篇测试的 skill 加载与 SkillScan 机制。
- [observability/](../observability/README.md) — 测试之后：上线怎么观察。
- [_faq_on_digested/06_cli-and-sdd/](../../_faq_on_digested/06_cli-and-sdd/) — CLI 实验、交互手段与外部最佳实践（LLM-as-judge、trajectory eval、record/replay）。
- [根 README](../README.md) — 全局阅读地图与关键词检索。
