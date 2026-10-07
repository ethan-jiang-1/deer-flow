# 架构、文档与工具链也是被测契约

## 什么时候读这里

想知道 DeerFlow 主仓把哪些"本该靠 review 纪律维持的规矩"写成了会红会绿的测试。这页是"rules as code"哲学在主仓的落地清单——也是应用仓最能整页借鉴的一页。

## 主仓机制（全部为机器门禁）

**架构边界测试**。harness 永不 import app 的单向依赖由 [test_harness_boundary.py](https://github.com/bytedance/deer-flow/blob/v2.1.0/backend/tests/test_harness_boundary.py) 用 AST 扫描执行——架构图上的箭头有红绿语义，不靠 review 时人眼盯（[backend/AGENTS.md](https://github.com/bytedance/deer-flow/blob/v2.1.0/backend/AGENTS.md)）。

**指南预算 CI**。`AGENTS.md` 指南网络按目录深度设软/硬尺寸预算，由 [check_agent_guidance.py](https://github.com/bytedance/deer-flow/blob/v2.1.0/scripts/check_agent_guidance.py) 在 [lint-check.yml](https://github.com/bytedance/deer-flow/blob/v2.1.0/.github/workflows/lint-check.yml) 里执行：超硬线是 error，且只在本次 diff 触及的文件上生效——给 agent 的指令文档是受治理的资产，膨胀会挡 PR。

**文档示例进测试**。[test_middleware_documentation.py](https://github.com/bytedance/deer-flow/blob/v2.1.0/backend/tests/test_middleware_documentation.py) 直接 `exec()` 文档里的自定义 middleware 示例并断言 API 未过期、链顺序与 guard 清单一致——文档一过期 CI 就红，"保持文档同步"从美德变成断言。

**工具链版本钉住**。[test_ci_uv_version_pin.py](https://github.com/bytedance/deer-flow/blob/v2.1.0/backend/tests/test_ci_uv_version_pin.py) 强制 Dockerfile 与全部 CI 里的 uv 版本一致。它防的失效模式很具体：CI 装了更新的 uv、把 lock 重写成新版格式、CI 依然全绿（同一个 uv 读得回自己写的），而生产镜像里钉住的旧 uv 读不了提交的 lock。workflow 里的注释明说 "Must match backend/Dockerfile's UV_IMAGE tag; pinned by backend/tests/test_ci_uv_version_pin.py"（[backend-unit-tests.yml](https://github.com/bytedance/deer-flow/blob/v2.1.0/.github/workflows/backend-unit-tests.yml)）——升级 uv 因此是"一个显式、可评审、四处同步的变更"。

**共同的句式**：谁来监督监督者？——下一个测试。这四条分别钉住**结构**（import 方向）、**指令资产**（指南尺寸）、**知识**（文档示例）、**环境**（工具链）；它们都不证明业务行为正确，只证明这些不变量没被破坏。

## 应用仓适用边界

**可移用（按你的规模裁剪）**：① 如果你有多层结构（比如应用仓也有"core 不 import 入口层"之类的关系），边界测试是最便宜的一条——一个 AST 测试文件换掉永远盯不完的 review 关注点；② 文档里有代码示例就值得 exec 它——示例过期比没有更糟；③ 只要你的 CI 与生产用同一类工具链（包管理器、构建器），版本钉住测试就适用。**应用仓建议**：应用仓最小起步是①——extension 包仓天然有一条边界要钉（"不 import `deerflow.*` / `app.*`"），一个 import 扫描测试就能把这条从 README 承诺变成机器事实。

## 证据入口

- [backend/AGENTS.md](https://github.com/bytedance/deer-flow/blob/v2.1.0/backend/AGENTS.md) Harness/App Split 节（依赖规则与禁止示例）
- 上列四个测试/脚本文件与 [lint-check.yml](https://github.com/bytedance/deer-flow/blob/v2.1.0/.github/workflows/lint-check.yml)（均存在于 v2.1.0，已核验）
