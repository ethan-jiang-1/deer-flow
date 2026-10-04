---
title: "测试思想与成文规矩"
description: "TDD 强制、offline-first 三分法、live 三重门、确定性纪律、真一切只换模型、no-unpinned-invariant、scar-tissue 文化——DeerFlow 把测试纪律写进 AGENTS.md 链并用测试钉住。"
topics: [testing, doctrine, agent-experience]
---

# 测试思想与成文规矩

DeerFlow 的测试思想不在某一份"测试规范"文档里，而是**分布在 `AGENTS.md` 指令链、Makefile 入口、marker 注册、PR 模板四处的成文规矩**，并且相互引用、互为执行。本篇按六条主线归纳。

## 1. TDD 是强制项，不是建议

根 `AGENTS.md`（Cross-Cutting Conventions）与 `backend/AGENTS.md` 的表述逐级加码：

> "Test-driven development — features and bug fixes ship with tests."（根）

> "**Test-Driven Development (TDD) — MANDATORY. Every new feature or bug fix MUST be accompanied by unit tests. No exceptions.** … Run both offline targets before and after your change: `make test` and `make test-blocking-io`. Tests must pass before a feature is considered complete."（`backend/AGENTS.md`）

PR 模板把这条规矩**社交化**为流程问题——`.github/pull_request_template.md:49` 起的 Bug fix 一节要求填写：

> "Bugs should be encoded as a failing test that goes red before the fix. Confirm: Test path that reproduces the bug / Did it go red on `main` and green on this branch? (yes / no)"

并给"没写 red 测试"留了显式解释栏。也就是说：先红后绿是被模板追问的默认预期，偏离才需要解释。

## 2. Offline-first 三分法与 live 三重门

默认套件即离线子集：`make test` = `-m "not live"` 且排除 `blocking_io/`，无网络、无凭证、无 token 消耗。三个真实边界各自成为显式 opt-in：

| 边界 | 门 |
|------|-----|
| 真实外部 API | `live` marker + `DEER_FLOW_RUN_LIVE_TESTS=1` + 仓库根存在 `config.yaml` |
| 阻塞 IO 严格门禁 | 独立套件 `make test-blocking-io`，独立 CI workflow |
| 真实外部服务 | `integration` marker，服务不可达自动跳过 |

live 的三重门实现在 `backend/tests/test_client_live.py`（`.github` 的 CI 环境变量、opt-in 环境变量、`config.yaml` 存在性，任一不满足则模块级 skip）。**设计含义**：一个配置齐全的 checkout 也不可能"意外"打到真实 API——确定性是结构性保证，不是使用者自觉。

配套地，这条政策本身也被测试钉住：`test_client_live_policy.py` 用子进程重收集矩阵验证 live 门的三种状态；`tests/monocle/test_deerflow.py` 的 live 门有"默认必须关闭"的元测试。

## 3. 确定性纪律：同步原语，不许 sleep

`backend/tests/AGENTS.md` 是测试目录自己的 agent 指令（测试目录有一级 `AGENTS.md`，这本身就是信号），三条硬规矩：

> "Backend tests must preserve the runtime invariants they exercise **without changing production execution topology**."

> "Use explicit synchronization such as `threading.Event` rather than sleep-based timing thresholds for worker lifecycle assertions. Every test must release blocked workers and restore any process-global monkeypatches so teardown cannot leak threads or state into later tests."

> "Stress/soak testing, AnyIO worker instrumentation, Uvicorn multi-process behavior … are separate concerns and should not be folded into these deterministic regressions."

即：**时序断言用事件不用阈值**；**teardown 必须无泄漏**；**确定性回归与压力/浸泡测试分层，不许混装**。这套规矩的落点是 `backend/tests/test_executor_starvation.py`：真实 `ThreadPoolExecutor(max_workers=1)` + 四个 `threading.Event`，`finally` 里释放 worker 并关闭执行器，全程无 sleep 断言。

## 4. E2E 哲学：真一切，只换模型

`backend/tests/_agent_e2e_helpers.py` 的 docstring 是整套替身设计的宣言：

> "The shim is what lets a real `langchain.agents.create_agent` graph run without an API key — **every other layer in those tests is real production code, which is the entire point of the test design**."

替身只出现在 **LLM 边界**上（Fake 模型 / Replay 模型 / 脚本化 Agent），HTTP、认证、SQLite、LangGraph 图、ToolNode、文件 IO 全部走生产代码。这样 user_id 传播、协议形状、工具真实副作用这类"mock 掉就测不到"的回归才能浮出水面（`test_setup_agent_e2e_user_isolation.py` 即为此设计：故意关闭 autouse 用户上下文，验证 contextvar 回退路径）。

## 5. No-unpinned-invariant：每条规矩都有钉住它的测试

全仓共有 28 个 `AGENTS.md` 文件构成指令链（后端 24 + 根/frontend/scripts 4；集合被 `test_agent_guidance_check.py` 的 `EXPECTED_GUIDANCE_PATHS` 钉死）。嵌套子系统指南的写法是一个固定句式：**陈述规矩 → 点名 pinning 测试**。三个抽样（均为原文）：

- `backend/packages/harness/deerflow/mcp/AGENTS.md:30`：LangGraph 把 `ToolRuntime` 注入名为 `runtime` 的工具参数，上游改名风险由 `test_mcp_context_headers.py::test_adapter_tool_receives_the_runtime_langgraph_injects` 钉住——"pins the injection rule against an upstream rename by disabling the ambient fallback and driving a real adapter tool through a real graph"。
- `backend/packages/harness/deerflow/skills/AGENTS.md`：SkillScan 静态分析器的代表性漏报被 `test_skillscan_native.py` 的 `test_python_declared_false_negatives_stay_unreported` **刻意钉住不许修复**——漏报边界本身是契约。
- `backend/packages/harness/deerflow/sandbox/AGENTS.md:82`：ownership store 契约"两个后端定义一次"，redis 层跑真服务——"there is no fake-redis tier because **a fake would not execute the Lua exclusions**"。

第三例把"替身选型"上升成了原则：**当替身无法执行被测语义的核心部分（Lua 原子性）时，宁可在 CI 里起真服务，也不造一个骗过测试的 fake**。

## 6. Scar-tissue：门禁从真实事故生长

`backend/tests/blocking_io/` 的 47 个 anchor 不是规划出来的，是**事故驱动**逐个长出来的——git 历史显示每个 anchor 对应一个真实生产 bug：tiktoken 在事件循环上阻塞（PR #3402/#3411）、custom-agent router 文件 IO（#3457）、UploadsMiddleware 扫描（#3311）、JsonlRunEventStore（#3313）。`backend/docs/BLOCKING_IO_DETECTION.md` 把这套工作流写成循环：

> "The static detector is the discovery tool … A static finding is a candidate, not proof." → 人工评审选出高危路径 → 加 runtime anchor → "Let CI prevent that path from regressing."

并且每个 anchor 要满足**手工变异验证**纪律——设计文档（`docs/superpowers/specs/2026-09-12-projects-mvp-phase2-design.md` 的 Blocking-IO anchors 一节）的原话：

> "The anchor must fail when the offload is removed (the suite's existing mutation-verified style)."

门禁自身也被怀疑：`test_gate_smoke.py` 注入一个故意阻塞的探针证明门禁真的会咬人，它的 docstring（`backend/tests/blocking_io/test_gate_smoke.py:11`）是整套元治理文化的题眼：

> "a green gate that no longer catches anything is **worse than no gate at all**."

门禁的技术实现有两处值得记录：`backend/tests/blocking_io/conftest.py:26` 用 `hookwrapper` 包住**整个 `pytest_runtest_protocol`**（setup+call+teardown 全覆盖，async fixture/lifespan 里的阻塞也抓），且仅当 item 路径在 `blocking_io/` 下才激活；`backend/tests/support/detectors/blocking_io_runtime.py` 的 `BlockBuster(scanned_modules=("app", "deerflow"))` 只抓**调用栈穿过生产代码**的同步阻塞 IO（pytest/langchain/三方库不在扫描范围，避免误报）。评审期还有一件武器 `backend/tests/support/detectors/blocking_io_changed.py`：把 git diff 与静态发现**求交**，回答"这次改动引入了哪些阻塞 IO 候选"——其中 merge-base 后的新发现也计数，专门捕捉"没改阻塞行、但新 async 调用者让它变 async-可达"这类隐性回归。

## 7. 文档即契约（docs-as-contract）

"文档写了什么"与"交付物是什么"必须一致，且这个一致性由测试执行。最有代表性的例子是 `test_compose_default_bind_host.py`——README 承诺默认部署"仅回环可达"，而 compose 曾把入口发布为裸端口（Docker 会绑 `0.0.0.0`）。该测试 docstring 的定性：

> "The shipped artifact therefore did not match its own documented default, and an operator running it on a LAN or cloud host got a wider surface than the docs implied without changing anything."

此后"每个发布端口必须显式 bind 地址"成为被 CI 强制的回归。同族还有 compose/Helm 的 extensions_config 可写性、默认 worker 数、CI 的 uv 版本与 Dockerfile 一致（详见 `04-enforcement-meta.md`）。

## 测试方法论本身是一等文档

与功能文档并列，测试方法论有专门文档：`backend/docs/REPLAY_E2E.md`（回放 E2E 的原理/录制流程/已知局限）、`backend/docs/BLOCKING_IO_DETECTION.md`（静态/运行时分工与维护工作流）、`backend/docs/AUTH_TEST_PLAN.md`（中文手工测试矩阵）。每份重大设计文档自带 "Testing Strategy" 章节，**测试计划在实现之前成文**：

- `docs/superpowers/specs/2026-07-01-scheduled-tasks-mvp-design.md:515`："## Testing Strategy"——Backend unit（cron/DST/lease expiry/claim）→ integration → frontend unit → Playwright mocked → Real-path validation（claim feature complete 之前必过）；
- `docs/superpowers/specs/2026-09-12-projects-mvp-phase2-design.md:486`："## 13. Testing Strategy"，unit/integration 分列 + **"Concurrency (hard requirement)"** 独立小节（`:514`，6 组竞态测试逐条列出）+ 同文件 Blocking-IO anchors 一节（`:531`）要求 *"The anchor must fail when the offload is removed (the suite's existing mutation-verified style)"*；
- `docs/plans/2026-07-10-pluggable-authorization-rfc.md:474`："## 13. Test strategy (TDD, per AGENTS.md)"，逐文件列最小覆盖，含安全边界保证项（"a tool removed at assembly cannot be invoked even when the prompt tries to call it"）；
- `docs/superpowers/specs/2026-07-31-frontend-performance-remediation-design.md:32`："Add deterministic tests or executable measurements for every fix so later changes cannot silently restore the same cost."

**解释**：这相当于把"分轨决策"提前到设计阶段——每个 feature 的"哪些并发场景是 hard requirement、哪些路径要加 blocking-io anchor、DOM 断言与后端断言怎么分工"在写代码前就有了成文合同。
