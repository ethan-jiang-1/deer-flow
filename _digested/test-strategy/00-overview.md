---
title: "测试体系全景"
description: "规模数字、四类 22 层测试地图、四个 Makefile 入口与执行路由表、真 API 用例清单、每层'不证明什么'，以及体系自评的已知缺口。"
topics: [testing, ci, quality-assurance]
---

# 测试体系全景

## 一句话策略

> **离线确定性是默认，真实边界是显式 opt-in；测契约不测智能；每条架构规矩都有一个钉住它的测试；门禁自身也要被测试。**

## 规模（ethan @ fb6334b2 工作树实测）

| 侧 | 数字 |
|----|------|
| 后端测试文件 | **738** 个（`backend/tests/` 根 690 + `blocking_io/` 47 + `monocle/` 1） |
| 后端测试函数 | **14,405** 个 `def test`（含 async），其中 832 处 `@pytest.mark.parametrize` |
| 前端单元测试 | **202** 个文件（node 环境 145 + dom 环境 57，按文件名后缀分流） |
| 前端 Playwright | **52** 个 spec（mock 后端 45 + auth 2 + 真后端回放 4 + 手动录制 1） |
| Router/API 测试 | 63 个文件使用 TestClient |
| 迁移/持久化契约 | 14 个 `test_migration*` + 12 个 `test_persistence*`（根目录） |
| TUI / 渠道 | 16 个 `test_tui_*`；`test_channels.py` 11167 行 352 个测试（全仓最大测试文件） |
| 配置钉住类 | 约 25 个文件解析 compose/Helm/Makefile/workflow/markdown 并断言 |
| CI 测试门禁 | 16 个 workflow 中 6 个纯测试（backend-unit 4 分片 / blocking-io / frontend-unit / e2e / replay-e2e / skill-review），另有 lint-check 与 verify-versions |
| 时长基线 | `backend/.test_durations` 13,141 行，提交入库 |

marker 计数（`backend/tests/` 内 grep marker 用法）：`asyncio` 942 处、`no_auto_user` 76 处、`integration` 10 处、`allow_blocking_io` 10 处、`live` 4 处。

**真 API 用例清单**（全部显式 opt-in，默认 CI 永不执行）：`live` marker 4 处——`test_client_live.py` 模块级 pytestmark（19 个用例）+ AIO sandbox Docker 冒烟 3 个用例；`requires_llm` skipif 门 `test_client_e2e.py` 43 个用例（文件管理子集不需要 LLM，CI 里也真跑）；`ONEAPI_E2E=1` 门 `test_deferred_tool_promotion_real_llm.py` 1 个用例；`MONOCLE_LIVE_TESTS=1` 门 monocle live 2 个用例。`test_client_live_policy.py` 的 11 个测试是 live 门自身的策略测试（子进程重收集，不触网）。其余约 1.43 万个用例全部确定性运行。

## 四个入口与四个 marker 的语义

`backend/Makefile` 定义了互不重叠的入口（原文）：

```makefile
test:
	PYTHONPATH=. PYTHONIOENCODING=utf-8 PYTHONUTF8=1 uv run pytest -m "not live" --ignore=tests/blocking_io tests/ -v

test-live:
	DEER_FLOW_RUN_LIVE_TESTS=1 PYTHONPATH=. PYTHONIOENCODING=utf-8 PYTHONUTF8=1 uv run pytest -m live tests/ -v -s

test-blocking-io:
	PYTHONPATH=. PYTHONIOENCODING=utf-8 PYTHONUTF8=1 uv run pytest tests/blocking_io -q --tb=short
```

| 入口 | 命令语义 | 跑什么 |
|------|---------|--------|
| `make test` | `pytest -m "not live" --ignore=tests/blocking_io` | 默认离线套件，无网络无凭证 |
| `make test-live` | `DEER_FLOW_RUN_LIVE_TESTS=1 pytest -m live` | 真实外部 API，显式 opt-in，永不进默认 CI |
| `make test-blocking-io` | `pytest tests/blocking_io` | Blockbuster 严格门禁，独立 CI workflow |
| `make test-shard SPLITS=4 GROUP=N` | 按 `.test_durations` 时长均衡取第 N 片（`--splitting-algorithm least_duration`） | CI 并行分片，见 `05-speed-isolation.md` |

marker 注册在 `backend/pyproject.toml` 的 `[tool.pytest.ini_options]`，四个自定义 marker 各有明确语义（无 addopts/testpaths，配置刻意极薄）：

- `live`：调用真实外部 API，需要显式 opt-in；
- `integration`：需要外部服务（如 Redis），服务不可用时自动跳过；
- `no_auto_user`：关闭 conftest 的 autouse 用户上下文 fixture（想验证"无用户上下文"行为的测试用）；
- `allow_blocking_io`：在 `tests/blocking_io/` 严格门禁内显式豁免单个测试。

### 执行路由表（变更类型 → 命令）

| 变更类型 | 允许执行的命令 | 纪律 |
|---|---|---|
| 任何后端/前端代码 | `cd backend && make lint && make format`（前端 `pnpm check`） | 提交前格式必须干净，CI 强制 `ruff format --check` |
| 功能/修 bug | **先写红测试** → `make test` + `make test-blocking-io` 双跑 | TDD 强制；PR 模板追问 red→green（`01-doctrine.md` §1） |
| 单文件/单函数 | `python -m pytest tests/test_x.py::test_func -q`（前端 `pnpm rstest run <pattern>`） | 根 `AGENTS.md` "Run a single test" 成文承诺 |
| 改了 compose/Helm/版本 | `make test` 自动覆盖（约 25 个配置钉住测试在默认套件里） | 文档即契约（`04-enforcement-meta.md` §2） |
| 改了 SSE/协议形状 | `make test`（replay golden）+ `replay-e2e.yml`（真前端×真后端） | fake-green 防线（`03-contract-e2e.md`） |
| CI 并行 | `make test-shard SPLITS=4 GROUP=N` | 分片只读 `.test_durations`，防写竞争（`05-speed-isolation.md` §1） |
| 真实 API 验证 | `make test-live`（需要 key + config.yaml） | 慢、有副作用，永不进默认 CI |

## 测试地图：四类 22 层

> 每层末列是该层**自己声明不证明什么**——这是 DeerFlow 测试文档的显著特征：`backend/docs/BLOCKING_IO_DETECTION.md` 明说静态发现"是候选，不是运行时阻塞的证明"、运行时门禁"只覆盖 `backend/tests/blocking_io/` 实际执行到的生产路径"；`backend/tests/monocle/README.md` 明说离线 trace 示例"守护的是 trace 格式与断言器接线，不是 DeerFlow 的行为"。

### A. 单元层

| 层 | 目的 | 入口/示例 | 规模 | 不证明什么 |
|----|------|----------|------|-----------|
| 后端纯逻辑单元 | 函数/类级行为 | `make test`；`test_auth.py`、`test_patched_deepseek.py` | 约 590 个文件 | 不证明跨模块协议、不触网络 |
| 后端 Router/API | 进程内 HTTP 契约 | 裸 FastAPI app + 单 router + TestClient；`test_threads_router.py` | 63 个文件 | 不证明跨进程/浏览器侧 |
| 前端 node 单元 | 纯逻辑 | rstest `node` project，`*.test.ts` | 145 个文件 | 不证明 DOM 行为 |
| 前端 dom 单元 | 组件/hook | rstest `dom` project（happy-dom），`*.dom.test.tsx` | 57 个文件 | 不证明真实浏览器渲染 |

### B. 集成 / E2E 层

| 层 | 目的 | 入口/示例 | 规模 | 不证明什么 |
|----|------|----------|------|-----------|
| 后端 E2E（真一切只换模型） | 全栈真路径 + 假 LLM | `test_setup_agent_http_e2e_real_server.py` 等 8 个 `*e2e*` 文件 | 8 个文件 | 不证明真实模型行为（第 9 个 `*e2e*` 文件 `test_client_e2e.py` 属真 LLM + `requires_llm` 门，归入下方 client 金字塔，见 `08-upper-layer-apps.md` §七） |
| 前端 Mock E2E | UI 交互流程 | Playwright `page.route()` 全量 mock 后端 | 45 个 spec | 不证明后端真实契约（见 `03-contract-e2e.md` 的 fake-green 问题） |
| 前端 Auth E2E | 认证开启路径 | `frontend/playwright.auth.config.ts`，`DEER_FLOW_AUTH_DISABLED: "0"` | 2 个 spec | — |
| 前端真后端 E2E | 跨栈契约 | 真前端 + 真 gateway + `ReplayChatModel` | 4 个 spec | 不证明真实模型输出 |
| Live | 真实外部 API | `test_client_live.py`（三重门）、AIO sandbox Docker 冒烟 | 2 个文件 4 处 marker | 慢、有副作用，永不进默认 CI |
| Integration（真服务） | 真 Redis/Postgres 语义 | `@pytest.mark.integration`，CI 起 Postgres 17 + Redis 7 | 3 个文件 10 处 | 服务不可用即跳过 |

### C. 契约层

| 层 | 目的 | 入口/示例 | 规模 | 不证明什么 |
|----|------|----------|------|-----------|
| Record/Replay Golden | SSE 事件形状漂移 | `test_replay_golden.py` + 提交的 golden JSON | 2 个文件 + 2 个 fixture | 只断言形状不断言值（`02-deterministic-llm.md`） |
| 跨语言契约 JSON | Python/TS 双端钉住同一文档 | `contracts/slash_skill_contract.json` 等 | 3 份契约 + 双端测试 | — |
| Gateway 一致性 | SDK 路径 ↔ Gateway Pydantic 模型 | `TestGatewayConformance`（`test_client.py`） | 1 个测试类 | 不起真 Gateway 进程 |
| 迁移契约 | upgrade/downgrade 可回滚 | `test_migration_*.py` 逐 revision 断言已审定的回滚契约 | 14 个文件 | — |

### D. 门禁与外围层

| 层 | 目的 | 入口/示例 | 规模 | 不证明什么 |
|----|------|----------|------|-----------|
| Blocking-IO 门禁 | 事件循环安全 | `make test-blocking-io`，Blockbuster 包裹整个 runtest 协议 | 47 个文件 | 只保护被 anchor 覆盖的路径 |
| 架构/元治理测试 | 规矩即测试 | `test_harness_boundary.py`、`test_agent_guidance_check.py`、`test_ci_uv_version_pin.py` | 约 10 个文件 | 见 `04-enforcement-meta.md` |
| 配置钉住 | 文档=交付物 | `test_compose_default_bind_host.py` 等 | 约 25 个文件 | — |
| Monocle 行为测试 | trace 断言 | `tests/monocle/`，离线示例 + live 双测 | 1 个文件 4 个测试（1 元测试 + 1 离线示例 + 2 live） | 默认整体跳过（依赖独立安装） |
| Bench 逻辑测试 | 基准脚本纯逻辑 | `test_bench_*.py`，合成 fixture | 16 个文件 | 不跑真实评测 |
| Skills 测试 | 公共技能脚本 | 根 `tests/skills/`，importlib + FakeResp | 5 个文件 | 不进 CI |
| 验收清单 | 子代理确定性验收 | RFC #4651，`test_acceptance_checks.py` | 1 个文件 10 个测试类 | — |
| 手工测试计划 | 人工矩阵 | `backend/docs/AUTH_TEST_PLAN.md`；未执行缺口也成文：`backend/docs/AUTH_TEST_DOCKER_GAP.md` 逐例记录 6 个 TC-DOCKER 用例为何未跑、其 auth 行为被哪些非 Docker 测试覆盖 | 2 份文档 | — |

补位关系：**前端/TUI 车道细节**见 `06-frontend-and-tui.md`；**持久化与恢复测试**见 `07-durable-and-recovery.md`；**上层应用（扩展/技能/MCP/渠道/下游应用）的完整测试面**见 `08-upper-layer-apps.md`；**支撑这一切的基建层**（support/ 助手、检测器族、依赖治理、CI 预算）见 `09-test-infra-and-platform.md`。

## 地图怎么看（解释）

这个分类学里最有信息量的不是"有哪些层"，而是**层与层之间的互补关系**：

- Mock E2E 快而宽，但会"fake green"——所以有 Record/Replay 两层跨栈契约补位（`03-contract-e2e.md`）；
- 离线单测快而确定，但覆盖不到真实执行拓扑——所以有"真一切只换模型"的 E2E 层（`02-deterministic-llm.md`）；
- 单元/集成都绿也可能整体坏——所以有部署配置钉住与元治理层（`04-enforcement-meta.md`）；
- 每一层的"不证明什么"都由文档显式声明，层的价值恰恰在于它承认自己证明不了的东西由别的层负责。

## 体系的已知缺口（自评）

对照"离线确定性应该结构性成立"的理想态，DeerFlow 自己的体系有三处未闭合：

1. **无进程级环境兜底**：`backend/tests/conftest.py` 刻意很薄（184 行，无环境变量清洗、无 HOME 重定向），离线保证完全依赖 **marker 选择** + 门策略测试反向钉住——防住了"live 用例意外跑"，但防不住"没打 live 标记的测试代码里调了真实 API"（一个写错的测试 + 宿主机上的 key = 意外计费）。补一个 conftest 级网络/key 守卫可以把这个残余风险也结构化掉；
2. **替身缺"上下文感知"档位**：全树的 fake 模型都是静态剧本（预编程响应队列），没有"读上一轮工具结果决定下一步"的动态工厂。测"中间件重试/回退会根据上一轮结果改变模型行为"这类分支时，要么写多套剧本、要么重录 replay fixture；
3. **TUI 无自动打包冒烟**：TUI 的 live 冒烟按设计文档是 skipped-by-default 的手动项（`06-frontend-and-tui.md` §三）；`deerflow --print/--json` 的 headless 全链路（config 解析 → client → checkpointer → 输出）其实可以用 `FakeToolCallingModel` 桩掉模型做成零 token 冒烟进 CI。

另有一个上层应用侧的缺口：`examples/deerflow-extension-example/` 的测试不进任何 CI workflow（`08-upper-layer-apps.md` §二）。
