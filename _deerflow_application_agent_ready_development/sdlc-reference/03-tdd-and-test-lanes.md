# TDD 与测试车道

## 什么时候读这里

写实现之前与提 PR 之前：DeerFlow 主仓的测试要求是什么等级的（成文军规还是机器门禁），测试车道怎么分，red-green 靠什么保证。

## 主仓机制

**成文标准（大写军规）**。backend 指南把 TDD 定为强制：

> ### Test-Driven Development (TDD) — MANDATORY
> **Every new feature or bug fix MUST be accompanied by unit tests. No exceptions.**
>
> — [backend/AGENTS.md](https://github.com/bytedance/deer-flow/blob/v2.1.0/backend/AGENTS.md)

配套要求：测试放 `backend/tests/` 按 `test_<feature>.py` 命名；改动前后都跑 `make test` 与 `make test-blocking-io`；测试通过才算 feature 完成。根 [AGENTS.md](https://github.com/bytedance/deer-flow/blob/v2.1.0/AGENTS.md) 把"features and bug fixes ship with tests"提升为跨模块约定。

**测试车道三分（成文标准 + 机器门禁）**。`make test` 是默认离线套件（排除 live 与 blocking-I/O）；`make test-blocking-io` 是独立的严格阻塞检测车道；`make test-live` 显式 opt-in、调用真实外部 API、可能产生费用与本地副作用，且"never run by the default backend test command or CI"，直跑 live 测试文件必须设 `DEER_FLOW_RUN_LIVE_TESTS=1`（[CONTRIBUTING.md](https://github.com/bytedance/deer-flow/blob/v2.1.0/CONTRIBUTING.md)）。

**red-green 靠自报（成文标准 + 自我声明）**。PR 模板的 bug fix 节要求把 bug 编码为失败测试并自答：

> Bugs should be encoded as a failing test that goes red before the fix.
> - Did it go red on `main` and green on this branch? (yes / no)
>
> — [pull_request_template.md](https://github.com/bytedance/deer-flow/blob/v2.1.0/.github/pull_request_template.md)

写不起 red test 时要解释替代方案。

**机器门禁**：CI 验证测试**最终绿**（见 [CI 门禁矩阵](./05-ci-gates.md)），**不验证曾经红**——没有 workflow 在 main 上重放新增测试。red-on-main 的真实性由评审与作者自报维持。

## 为什么这样分级

这套设计的诚实之处在于把"要求的等级"写穿了：TDD 是军规（措辞最强），车道划分是可机器执行的（marker 决定收集行为），而 red-green 只能到自报为止。应用仓抄这套时不要把三件事压成一句"我们有 TDD"——那会把最弱的一环（自报）藏进最强的一环（军规）后面。

## 应用仓适用边界

**可移用**：车道三分（默认离线 / 严格专项 / live 显式 opt-in 且不进 CI）；"bug → 失败测试"的编码习惯与自报格式；按改动面选择检查集（见 PR 模板 Validation 节）。**需要自建**：应用仓自己的车道边界取决于你的依赖面——内嵌形态的应用至少要区分"契约级包测试"与"装进宿主后的组合验证"（见[新仓起步](../application-development-model/01-new-application-repository.md)的诚实边界一节）。**应用仓建议**：把 red-green 自报做成 PR 模板的必填问题，它便宜且把"测试是不是真的钉住了 bug"变成评审可见的事实。

## 证据入口

- [backend/AGENTS.md](https://github.com/bytedance/deer-flow/blob/v2.1.0/backend/AGENTS.md)（TDD MANDATORY 节，tag 内容已核验）与根 [AGENTS.md](https://github.com/bytedance/deer-flow/blob/v2.1.0/AGENTS.md)
- [CONTRIBUTING.md](https://github.com/bytedance/deer-flow/blob/v2.1.0/CONTRIBUTING.md) Testing 节（三车道命令与 live 门）
- [pull_request_template.md](https://github.com/bytedance/deer-flow/blob/v2.1.0/.github/pull_request_template.md) Bug fix verification 节
