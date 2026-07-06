---
title: "Testing — 测试策略与实践"
description: "Agent 测试是所有 AI 应用中最棘手的部分。这里整理了 DeerFlow 自己的测试基建 + 外部最佳实践。"
type: index
---

# Testing — 测试策略与实践

Agent 测试是所有 AI 应用中最棘手的部分。这里整理了 DeerFlow 自己的测试基建 + 外部最佳实践。

## DeerFlow 自己的测试体系

核心原则：**Harness 层测试不能依赖 App 层**（CI 强制）。

| 文件 | 内容 |
|------|------|
| `00-overview.md` | 测试金字塔：Boundary / Unit / Gate / E2E |
| `01-harness-boundary.md` | Harness/App 边界检查（AST 扫描）+ Blocking IO 检测 |
| `02-gateway-conformance.md` | SDK ↔ Gateway 格式一致性（`TestGatewayConformance`） |
| `03-e2e-and-unit.md` | Playwright E2E + Vitest 前端 + pytest 后端 |

## 补充内容

- **所有交互手段一览**（CLI/WebUI/Python REPL/curl/IM Channels）：`_faq_on_digested/cli-and-sdd/interaction-methods-and-testing.md`
- **Agent 测试策略**（FakeToolCallingModel、@requires_llm、流式事件断言、从实验到 CI）：同上文件 Part B + Part C
- **外部最佳实践**（trajectory eval、LLM-as-judge、interrupt_before 单步评测、eval harness 模式）：同上文件
