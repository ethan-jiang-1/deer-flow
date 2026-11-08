---
title: "Testing — 测试策略与实践"
description: "Agent 测试是所有 AI 应用中最棘手的部分。DeerFlow 自己的测试基建 + 开发者测试模式 + 外部最佳实践。"
type: index
---

# Testing — 测试策略与实践

Agent 测试是所有 AI 应用中最棘手的部分。这里分两层：DeerFlow 自己怎么测自己（参考），开发者怎么测 DeerFlow 应用（实操）。

## DeerFlow 自己的测试体系

| 文件 | 内容 |
|------|------|
| `00-overview.md` | 测试金字塔：Boundary / Unit / Gate / E2E（v2.2.0 规模：1,363 个后端测试文件 / 23,432 个 `def test` + 348 前端 unit + 93 Playwright spec） |
| `01-harness-boundary.md` | Harness/App 边界检查（AST 扫描）+ Blocking IO 双层检测（89 个 `blocking_io/` 文件、4 条 gate 元测试） |
| `02-gateway-conformance.md` | SDK ↔ Gateway 格式一致性（`TestGatewayConformance` 在 v2.2.0 覆盖 11 个方法） |
| `03-e2e-and-unit.md` | Playwright E2E（4 分片）+ Rstest 前端（node 202 / dom 146）+ pytest 后端（4 分片时长感知） |

## 开发者测试模式（写 DeerFlow 应用时用）

| 文件 | 内容 |
|------|------|
| `04-agent-test-patterns.md` | 🔑 核心模式：FakeToolCallingModel、tool call 验证、sub-agent 测试、流式输出、中间件测试模板 |
| `05-testing-skills-and-workflows.md` | 测试 Skill 加载、Workflow 行为序列（trajectory）、interrupt_before 单步评测 |
| `06-ci-and-automation.md` | CI 流水线、@requires_llm 标记、环境隔离、Token 预算、决策矩阵 |
| `07-record-replay.md` | 🆕 ReplayChatModel 深度：输入哈希、volatile 归一化、caller-aware key、golden shape 断言 |
| `08-testing-patterns-reference.md` | 12 节可复用测试模式：FakeRedis、FrozenDatetime、Fake evaluator、Textual pilot、hermetic replay，以及 v2.2.0 新增的竞态替身 / 可变时钟 / 故障注入 Fake / 前端裸标识符核对 |
| `09-what-to-copy-from-deerflow-ci.md` | 🆕 借鉴 DeerFlow 自己的实践：CI 模板、FakeToolCallingModel、隔离 fixture、record/replay、验收模板 |

## 补充

- 测试体系的策略研究（思想、分类学、机制咬合）→ `_digested/test-strategy/`
- CLI 实验 + 交互手段 → `_faq_on_digested/cli-and-sdd/interaction-methods-and-testing.md`
- 外部最佳实践（LLM-as-judge、trajectory eval、record/replay）→ 同上文件
