---
title: "测试体系全景"
description: "规模数字、四类 22 层测试地图、四个 Makefile 入口与执行路由表、真 API 用例清单、每层'不证明什么'，以及体系自评的已知缺口。"
topics: [testing, ci, quality-assurance]
---

# 测试体系全景

## 一句话策略

> **离线确定性是默认，真实边界是显式 opt-in；测契约不测智能；每条架构规矩都有一个钉住它的测试；门禁自身也要被测试。**

## 规模（ethan 工作树 @ v2.2.0 实测）

| 侧 | 数字 |
|----|------|
| 后端测试文件 | **1363** 个 `test_*.py`（`backend/tests/` 根 1271 + `blocking_io/` 89 + `monocle/` 3，后者含 `_helpers.py`/`conftest.py`） |
| 后端测试函数 | **23,432** 个 `def test`（含 async），其中 4,266 处 `@pytest.mark.parametrize` |
| 前端单元测试 | **348** 个文件（node 202 + dom 146，按 `*.dom.test.*` 后缀分流） |
| 前端 Playwright | **93** 个 spec / **384** 个 `test(`（mock 后端 85 spec 369 test + auth 3/10 + 真后端回放 4/4 + 手动录制 1/1） |
| Router/API 测试 | 95 个文件使用 TestClient |
| 迁移/持久化契约 | 31 个 `test_migration*` + 17 个 `test_persistence*`（根目录） |
| TUI / 渠道 | 19 个 `test_tui_*`；`test_channels.py` 14345 行 441 个测试（全仓最大测试文件） |
| 配置钉住类 | 16 个 `test_compose_*`/`test_helm_*` + 5 个 `test_nginx_*`；另有 53 个测试文件解析 compose/Helm/脚本/markdown 并断言 |
| CI 测试门禁 | 19 个 workflow（14 个 `.yml` + 5 个 `.yaml`）中 9 个跑测试（backend-unit 4 分片 / blocking-io / frontend-unit / e2e 4 分片 / replay-e2e / skill-review + 其内 `skill-tests` job / extension-package-check / windows-live-policy / sandbox-image-smoke），另有 lint-check 与 verify-versions |
| 时长基线 | `backend/.test_durations` **32,395** 行（v2.1.0 的 13,141 行的 2.5 倍，见 `05-speed-isolation.md` §1） |

marker 计数（`backend/tests/` 内 grep marker 用法）：`asyncio` 2,921 处、`no_auto_user` 84 处、`integration` 17 处、`allow_blocking_io` 9 处、`live` 5 处（文件的 marker 出现次数；带 live 的**用例**远多于 5 个，见下）。

**真 API 用例清单**（全部显式 opt-in，默认 CI 永不执行）：`live` 从 v2.1.0 的 3 个文件扩到 10+ 个文件——`test_client_live.py` 模块级 pytestmark（19 个用例）、`test_aio_sandbox_local_backend.py` 里 3 个 `@pytest.mark.live`（该文件 131 个用例中只有这 3 个真连 Docker），以及 v2.2.0 新增的一整族 `*_live.py`：`test_knowledge_contract_live.py`、`test_knowledge_management_extension_live.py`、`test_knowledge_phase1_live.py`、`test_managed_deepseek_live.py`、`test_managed_presets_live.py`、`test_qq_channel_live.py`、`test_weknora_extension_live.py`。其中 `test_managed_deepseek_live.py` 与 `test_managed_presets_live.py` 的被测门是 `DEER_FLOW_RUN_LIVE_TESTS=1` + vendor 凭证，`backend/tests/AGENTS.md` 明文限定：「A passing connectivity probe does not establish full agent compatibility」。`requires_llm` skipif 门 `test_client_e2e.py`：43 个用例中 11 个挂该装饰器（文件管理子集不需要 LLM，CI 里也真跑）；`test_deferred_tool_promotion_real_llm.py` 改用文件级 `pytestmark = pytest.mark.skipif(...)`（`:41`）；`MONOCLE_LIVE_TESTS=1` 门 monocle live 2 个用例。`test_client_live_policy.py` 的 13 个测试是 live 门自身与 CI 接线的策略测试（子进程重收集，不触网），其 5 条门策略用例被 `.github/workflows/backend-windows-live-policy.yml` 在 Windows 上逐节点点名执行。其余约 2.3 万个用例全部确定性运行。

## 四个入口与四个 marker 的语义

`backend/Makefile` 定义了互不重叠的入口（原文，`:24-59`）。v2.2.0 的关键变化：**裸 `make test` 不再是单进程 `pytest`，而是驱动四个分片的并行编排**——`make test` 内部调 `$(MAKE) -k -j$(TEST_JOBS) test-shard-1..4`（`TEST_JOBS ?= 4`），单分片逻辑统一收敛到 `test-shard`：

```makefile
test:
	$(MAKE) --no-print-directory -k -j$(TEST_JOBS) $(TEST_SHARD_TARGETS)

$(TEST_SHARD_TARGETS):
	$(MAKE) --no-print-directory test-shard SPLITS=4 GROUP=$(patsubst test-shard-%,%,$@)

test-live:
	DEER_FLOW_RUN_LIVE_TESTS=1 PYTHONPATH=. PYTHONIOENCODING=utf-8 PYTHONUTF8=1 uv run pytest -m live tests/ -v -s

test-blocking-io:
	PYTHONPATH=. PYTHONIOENCODING=utf-8 PYTHONUTF8=1 uv run pytest tests/blocking_io -q --tb=short

test-shard:
	@test -f "$(DURATIONS_FILE)" || \
		(echo "error: $(DURATIONS_FILE) is missing; run 'make test-shard-durations' to regenerate the duration baseline" >&2; exit 1)
	PYTHONPATH=. PYTHONIOENCODING=utf-8 PYTHONUTF8=1 uv run pytest -m "not live" --ignore=tests/blocking_io --splits $(SPLITS) --group $(GROUP) --splitting-algorithm least_duration --durations-path=$(DURATIONS_FILE) tests/ -q

test-shard-durations:
	PYTHONPATH=. PYTHONIOENCODING=utf-8 PYTHONUTF8=1 uv run pytest -m "not live" --ignore=tests/blocking_io --store-durations --clean-durations --durations-path=$(DURATIONS_FILE) tests/ -q
```

| 入口 | 命令语义 | 跑什么 |
|------|---------|--------|
| `make test` | `-k -j4` 并行驱动 4 个 `test-shard-*`；任一失败仍等其余分片并整体非零 | 默认离线套件，无网络无凭证 |
| `make test-shard SPLITS=4 GROUP=N` | `pytest -m "not live" --ignore=tests/blocking_io` + `--splitting-algorithm least_duration`；**先检查 `.test_durations` 存在**（缺失即 fail-loud 提示跑 `make test-shard-durations`） | CI 并行分片，见 `05-speed-isolation.md` §1 |
| `make test-shard-durations` | `--store-durations --clean-durations` 重生成时长基线 | 本地/周期任务 |
| `make test-live` | `DEER_FLOW_RUN_LIVE_TESTS=1 pytest -m live` | 真实外部 API，显式 opt-in，永不进默认 CI |
| `make test-blocking-io` | `pytest tests/blocking_io` | Blockbuster 严格门禁，独立 CI workflow |

marker 注册在 `backend/pyproject.toml` 的 `[tool.pytest.ini_options]`（`:86-92`），四个自定义 marker 各有明确语义（无 addopts/testpaths，配置刻意极薄）：

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
| 改了 compose/Helm/版本 | `make test` 自动覆盖（16 个 `test_compose_*`/`test_helm_*` + 5 个 `test_nginx_*` 在默认套件里） | 文档即契约（`04-enforcement-meta.md` §2） |
| 改了 SSE/协议形状 | `make test`（replay golden）+ `replay-e2e.yml`（真前端×真后端） | fake-green 防线（`03-contract-e2e.md`） |
| CI 并行 | `make test-shard SPLITS=4 GROUP=N` | 分片只读 `.test_durations`，防写竞争（`05-speed-isolation.md` §1） |
| 真实 API 验证 | `make test-live`（需要 key + config.yaml） | 慢、有副作用，永不进默认 CI |

## 测试地图：四类 22 层

> 每层末列是该层**自己声明不证明什么**——这是 DeerFlow 测试文档的显著特征：`backend/docs/BLOCKING_IO_DETECTION.md` 明说静态发现"是候选，不是运行时阻塞的证明"、运行时门禁"只覆盖 `backend/tests/blocking_io/` 实际执行到的生产路径"；`backend/tests/monocle/README.md` 明说离线 trace 示例"守护的是 trace 格式与断言器接线，不是 DeerFlow 的行为"。

### A. 单元层

| 层 | 目的 | 入口/示例 | 规模 | 不证明什么 |
|----|------|----------|------|-----------|
| 后端纯逻辑单元 | 函数/类级行为 | `make test`；`test_patched_deepseek.py`、`test_mcp_task_service.py` | 1163 个根级测试文件不用 TestClient（与下行差集是近似口径：该层再排除配置钉住与 `blocking_io/`） | 不证明跨模块协议、不触网络 |
| 后端 Router/API | 进程内 HTTP 契约 | 裸 FastAPI app + 单 router + TestClient；`test_threads_router.py` | 95 个文件（根级）用 TestClient | 不证明跨进程/浏览器侧 |
| 前端 node 单元 | 纯逻辑 | rstest `node` project（`frontend/rstest.config.ts:29`），`*.test.ts` 且不匹配 `*.dom.test.*` | 202 个文件 | 不证明 DOM 行为 |
| 前端 dom 单元 | 组件/hook | rstest `dom` project（happy-dom，`rstest.config.ts:38`），`*.dom.test.ts(x)` | 146 个文件 | 不证明真实浏览器渲染 |

### B. 集成 / E2E 层

| 层 | 目的 | 入口/示例 | 规模 | 不证明什么 |
|----|------|----------|------|-----------|
| 后端 E2E（真一切只换模型） | 全栈真路径 + 假 LLM | `test_setup_agent_http_e2e_real_server.py` 等 | 10 个 `*e2e*` 文件（v2.2.0 新增 `test_mcp_task_ordinary_e2e.py`、`test_runtime_lifecycle_e2e.py`、`test_sandbox_orphan_reconciliation_e2e.py`、`test_three_way_skills_mount_e2e.py`、`test_present_files_e2e_user_isolation.py`） | 不证明真实模型行为（`test_client_e2e.py` 属真 LLM + `requires_llm` 门，见本页"真 API 用例清单"） |
| 前端 Mock E2E | UI 交互流程 | Playwright `page.route()` 全量 mock 后端 | 85 个 spec / 369 个 `test(` | 不证明后端真实契约（见 `03-contract-e2e.md` 的 fake-green 问题） |
| 前端 Auth E2E | 认证开启路径 | `frontend/playwright.auth.config.ts`，`DEER_FLOW_AUTH_DISABLED: "0"` | 3 个 spec / 10 个 `test(` | — |
| 前端真后端 E2E | 跨栈契约 | 真前端 + 真 gateway + `ReplayChatModel` | 4 个 spec / 4 个 `test(` | 不证明真实模型输出 |
| Live | 真实外部 API | `test_client_live.py`（三重门）、AIO sandbox Docker 冒烟、v2.2.0 新增 7 个 `*_live.py` | 9 个文件带 live marker；`requires_llm` 门另覆盖 `test_create_deerflow_agent_live.py` 与 `test_client_e2e.py` | 慢、有副作用，永不进默认 CI |
| Integration（真服务） | 真 Redis/Postgres 语义 | `@pytest.mark.integration`，CI 起 Postgres 17 + Redis 7 | 3 个文件 17 处（`test_stream_bridge.py` 独占 16 处，其余为 `test_e2b_capacity_store_redis.py`、`test_sandbox_ownership_store.py`） | 服务不可用即跳过 |

### C. 契约层

| 层 | 目的 | 入口/示例 | 规模 | 不证明什么 |
|----|------|----------|------|-----------|
| Record/Replay Golden | SSE 事件形状漂移 | `test_replay_golden.py` + 提交的 golden JSON | 2 个文件 + `backend/tests/fixtures/replay/` 2 个 fixture | 只断言形状不断言值（`02-deterministic-llm.md`） |
| 跨语言契约 JSON | Python/TS 双端钉住同一文档 | `contracts/` 下 9 份根契约 + `contracts/skill_review/` 4 份 schema | v2.2.0 从 5 份根契约扩到 9 份（新增 `knowledge_sources.v1.json`、`scheduled_goal_notes_contract.json`、`scheduled_task_errors_contract.json`、`thread_goal_contract.json`、`thread_origin_contract.json`、`ui_locales.v1.json`），18 个测试文件引用 | — |
| Gateway 一致性 | SDK 路径 ↔ Gateway Pydantic 模型 | `TestGatewayConformance`（`test_client.py:4256`） | 1 个测试类 11 个测试方法（`:4264`-`:4445`） | 不起真 Gateway 进程 |
| 迁移契约 | upgrade/downgrade 可回滚 | `test_migration_*.py` 逐 revision 断言已审定的回滚契约 | 31 个文件（v2.1.0 为 14） | — |

### D. 门禁与外围层

| 层 | 目的 | 入口/示例 | 规模 | 不证明什么 |
|----|------|----------|------|-----------|
| Blocking-IO 门禁 | 事件循环安全 | `make test-blocking-io`，Blockbuster 包裹整个 runtest 协议 | 89 个文件（v2.1.0 为 47，翻倍） | 只保护被 anchor 覆盖的路径 |
| 架构/元治理测试 | 规矩即测试 | `test_harness_boundary.py`、`test_agent_guidance_check.py`、`test_ci_uv_version_pin.py` | 约 10 个文件 | 见 `04-enforcement-meta.md` |
| 配置钉住 | 文档=交付物 | `test_compose_default_bind_host.py` 等 | 16 个 compose/Helm + 5 个 nginx 专门文件，另有 53 个测试文件会解析部署描述 | — |
| Monocle 行为测试 | trace 断言 | `tests/monocle/`，离线示例 + live 双测 | 1 个测试文件 4 个测试（1 元测试 + 1 离线示例 + 2 live） | 默认整体跳过（依赖独立安装） |
| Bench 逻辑测试 | 基准脚本纯逻辑 | `test_bench_*.py`，合成 fixture | 22 个文件（v2.1.0 为 16，新增 deermem eviction 一族 8 个） | 不跑真实评测 |
| Skills 测试 | 公共技能脚本 | 根 `tests/skills/`，importlib + FakeResp | 21 个文件——**v2.2.0 起进 CI**（`skill-review-ci.yml` 的 `skill-tests` job） | 只证明脚本逻辑，不证明技能产出质量 |
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

对照"离线确定性应该结构性成立"的理想态，DeerFlow 自己的体系有四处未闭合：

1. **无进程级环境兜底**：`backend/tests/conftest.py` 刻意很薄（184 行，无环境变量清洗、无 HOME 重定向），离线保证完全依赖 **marker 选择** + 门策略测试反向钉住——防住了"live 用例意外跑"，但防不住"没打 live 标记的测试代码里调了真实 API"（一个写错的测试 + 宿主机上的 key = 意外计费）。补一个 conftest 级网络/key 守卫可以把这个残余风险也结构化掉；
2. **替身缺"上下文感知"档位**：全树的 fake 模型都是静态剧本（预编程响应队列），没有"读上一轮工具结果决定下一步"的动态工厂。测"中间件重试/回退会根据上一轮结果改变模型行为"这类分支时，要么写多套剧本、要么重录 replay fixture；
3. **TUI 无自动打包冒烟**：TUI 的 live 冒烟按设计文档是 skipped-by-default 的手动项（`06-frontend-and-tui.md` §三）；`deerflow --print/--json` 的 headless 全链路（config 解析 → client → checkpointer → 输出）其实可以用 `FakeToolCallingModel` 桩掉模型做成零 token 冒烟进 CI；
4. **示例包只有模板有测试**（v2.2.0 部分收口）：`examples/deerflow-extension-example/` 的测试**仍不进 `pytest` 车道**，但 `.github/workflows/extension-package-check.yml` 现在对每个 `examples/deerflow-extension-*/` 包做隔离 venv 下的构建/契约检查（`scripts/check_extension.py`）；14 个示例包中只有 `deerflow-extension-example` 带 `tests/` 目录（`08-upper-layer-apps.md` §二）。
