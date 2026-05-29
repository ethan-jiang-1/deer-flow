# Testing — 测试策略与质量保障

DeerFlow 的测试体系围绕一个核心原则展开：**Harness 层的测试不能依赖 App 层**。这体现在 CI 强制的 `test_harness_boundary.py`、`TestGatewayConformance` 的跨路径一致性验证，以及 Playwright E2E 的完整用户流程覆盖。

> **约束：不修改项目源代码。** 本 `_digest/` 下所有内容仅作研究记录。详见 [根 README](../README.md)。

## 阅读顺序

| 文件 | 内容 |
|------|------|
| **00-overview.md** | 全景：测试金字塔、三层体系、CI 流程 |
| **01-harness-boundary.md** | AST import 扫描 + Blockbuster 双层 blocking IO 检测（运行时 + 静态） |
| **02-gateway-conformance.md** | `TestGatewayConformance` — SDK/Gateway 返回格式的 Pydantic 一致性验证 |
| **03-e2e-and-unit.md** | Playwright E2E + Vitest 前端单元 + pytest 后端 provider 单元测试 |

## 测试金字塔

```
          ┌──────┐
          │ E2E  │  Playwright — 完整用户流程 (~15)
          ├──────┤
          │ Gate │  TestGatewayConformance — SDK/Gateway 一致性 (10)
          ├──────┤
          │ Unit │  Vitest (frontend) + pytest (backend) (150+)
          ├──────┤
          │Bound │  test_harness_boundary.py + blocking_io/ (2 gate + 4 regression)
          └──────┘
```

## 源文件索引

| 组件 | 路径 |
|------|------|
| Harness boundary 测试 | `backend/tests/test_harness_boundary.py` |
| Blocking IO 运行时 gate | `backend/tests/support/detectors/blocking_io_runtime.py` |
| Blocking IO 静态检测 | `backend/tests/support/detectors/blocking_io_static.py` |
| Blocking IO 回归锚点 | `backend/tests/blocking_io/` |
| Gateway conformance 测试 | `backend/tests/test_client.py::TestGatewayConformance` |
| Frontend 单元测试 | `frontend/tests/unit/` |
| Playwright E2E | `frontend/tests/e2e/` |
| Backend 单元测试 | `backend/tests/test_*.py`（150+ 文件） |

## 关键问题

- 怎么保证 harness 层不 import app 层？→ `01-harness-boundary.md`
- 怎么检测 event loop 上的同步阻塞 IO？→ `01-harness-boundary.md`（Blockbuster + AST 静态扫描）
- SDK 和 Gateway 的返回格式为什么会不一致？怎么防？→ `02-gateway-conformance.md`
- E2E 测试怎么验证 SSE 流式响应？→ `03-e2e-and-unit.md`
