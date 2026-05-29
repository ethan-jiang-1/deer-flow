# Testing — 测试策略与质量保障

DeerFlow 的测试体系围绕一个核心原则展开：**Harness 层的测试不能依赖 App 层**。这体现在 CI 强制的 `test_harness_boundary.py`、`TestGatewayConformance` 的跨路径一致性验证，以及 Playwright E2E 的完整用户流程覆盖。

**回答的核心问题**：harness/app 边界怎么在 CI 里强制？SDK 和 Gateway 的返回格式怎么保证一致？E2E 覆盖了哪些流程？blocking_io 门控设计是什么意思？

> **约束：不修改项目源代码。** 本 `_digest/` 下所有内容仅作研究记录。详见 [根 README](../README.md)。

## 阅读顺序

| 文件 | 内容 |
|------|------|
| **00-overview.md** | 全景：测试金字塔（单元/集成/E2E）、测试框架选型、CI 流程 |
| **01-harness-boundary.md** | `test_harness_boundary.py` 深入：AST 分析原理、CI 强制执行、架构决策的代码化 |
| **02-gateway-conformance.md** | `TestGatewayConformance` 模式：SDK 和 Gateway 的返回格式一致性保证 |
| **03-e2e-playwright.md** | Playwright E2E：用户流程覆盖、SSE stream 测试、CI 集成 |
| **04-unit-and-integration.md** | Vitest 单元测试 + Python pytest 集成测试模式 |

## 关键问题

- 怎么保证 harness 层不 import app 层？→ `01-harness-boundary.md`
- SDK 和 Gateway 的返回格式为什么会不一致？怎么防？→ `02-gateway-conformance.md`
- E2E 测试怎么验证 SSE 流式响应？→ `03-e2e-playwright.md`
- blocking_io 门控是什么意思？→ `00-overview.md`

## 源文件索引

| 组件 | 路径 |
|------|------|
| Harness boundary 测试 | `backend/tests/test_harness_boundary.py` |
| Gateway conformance 测试 | `backend/tests/test_client.py:TestGatewayConformance` |
| Playwright E2E | `frontend/e2e/` |
| Vitest 配置 | `frontend/vitest.config.ts` |
| Playwright 配置 | `frontend/playwright.config.ts` |
