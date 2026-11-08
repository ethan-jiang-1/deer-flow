---
title: "CI 与自动化测试"
description: '从本地实验到 CI 流水线：GitHub Actions 模板、@requires_llm 标记、环境隔离、Token 预算、决策矩阵。'
topics: [testing, ci, automation, github-actions, isolation]
verified_against: v2.2.0
last_verified: 2026-11-08
---

# CI 与自动化测试

> **v2.2.0 概览**：`.github/workflows/` 现在有 19 个文件（14 个 `.yml` + 5 个 `.yaml`），比 v2.1.0 的 16 个多三条车道：**`backend-windows-live-policy.yml`**（Windows 上的 live 门策略与字节精确性）、**`extension-package-check.yml`**（每个示例扩展包的打包/契约/自带测试）、以及 **`skill-review-ci.yml` 内新增的 `skill-tests` job**（根 `tests/skills/` 从"不进 CI"变成 PR 阻塞项）。同时 e2e 从单 job 变 **4 分片**、`backend-unit-tests.yml` 注入一个新的 Postgres 环境变量、`lint-check.yml` 新增 `label-declarations` job。

## DeerFlow 自己的 CI 是怎么跑的

源码：`.github/workflows/backend-unit-tests.yml`

```yaml
name: Unit Tests
on:
  push:
    branches: [ 'main', '*-dev' ]
  pull_request:
    types: [opened, synchronize, reopened, ready_for_review]

jobs:
  default-install-collection:   # 证明文档里的 contributor 路径（uv sync --group dev，不带 extra）能收集全量测试
    if: github.event.pull_request.draft == false    # 两个 job 都跳过 draft PR
    runs-on: ubuntu-latest
    timeout-minutes: 10
    steps:
      - uses: actions/checkout@v6
      - uses: actions/setup-python@v6
        with: { python-version: '3.12' }
      - uses: astral-sh/setup-uv@v7
        with: { version: "0.11.1" }   # 与 backend/Dockerfile 的 UV_IMAGE 同版本，由 test_ci_uv_version_pin.py 钉住
      - run: uv sync --group dev
      - run: uv run pytest --collect-only -q

  backend-unit-tests:
    if: github.event.pull_request.draft == false
    runs-on: ubuntu-latest
    timeout-minutes: 15
    strategy:
      fail-fast: false          # 🆕 失败分片照常报告，不取消兄弟分片
      matrix:
        shard: [1, 2, 3, 4]     # 🆕 后端单测拆 4 个并行分片（#5137）
    services:
      postgres: ...             # postgres:17
      redis: ...                # redis:7-alpine
    steps:
      - uses: actions/checkout@v6
      - uses: actions/setup-python@v6
        with: { python-version: '3.12' }
      - uses: astral-sh/setup-uv@v7
        with: { version: "0.11.1" }
      - run: uv sync --group dev --extra postgres   # working-directory: backend
      - run: make test-shard SPLITS=4 GROUP=${{ matrix.shard }}  # 🆕 working-directory: backend
        env:
          # 🆕 2.2：把 CI 的 Postgres service 显式喂给 workflow 级测试
          DEERFLOW_TEST_WORKFLOW_POSTGRES: ${{ env.TEST_POSTGRES_URI }}
```

三条关键规则：
- **LLM 测试在 CI 中全部跳过**——`@requires_llm` 标记检查 `CI=true` 或缺少 `OPENAI_API_KEY`
- **只跑纯 Python 测试**——mock 一切，零外部依赖
- **阻塞 IO 门禁**——`make test-blocking-io` 在 `backend/**` 变更时触发（`make test` 默认 `--ignore=tests/blocking_io`，严格套件单独跑）

### 🆕 2.2：`DEERFLOW_TEST_WORKFLOW_POSTGRES` 的防静默降级

`backend-unit-tests.yml`（全文 117 行）在这一轮给分片 job 的 `env:` 块（`:115-116`）加了 **两个**映射：`DEERFLOW_TEST_WORKFLOW_POSTGRES: ${{ env.TEST_POSTGRES_URI }}` 与既有的 `DEDUPE_TEST_POSTGRES_URL: ${{ env.TEST_POSTGRES_URI }}`，把 job 的 Postgres service（`:87` 的 `TEST_POSTGRES_URI`，`postgres:17`）显式传进 `make test-shard`。workflow 自带的注释把动机写得很直白："Without this mapping those tests silently skip and the headline capability is never exercised in CI."**解释**：Postgres 相关的 workflow 测试在变量缺失时的行为是**跳过**而不是失败——service 容器已经起了，但没人把地址告诉测试，于是"覆盖了 Postgres 语义"这句话在 CI 里悄悄变成假的。显式注入把"有服务"与"测试知道有服务"这两件事重新绑定。这与 `DEDUPE_TEST_POSTGRES_URL`（迁移去重测试）是同一条纪律的第二个实例：**CI 里的服务容器必须有一个显式的环境变量把地址递进去，不能靠默认值猜**（`test-strategy/05-speed-isolation.md` §3）。

### duration-aware 测试分片（#5137，2.2 有增补）

- **`backend/Makefile` 目标**：`make test-shard SPLITS=4 GROUP=2` 用 pytest-split 的 `least_duration` 算法按真实墙钟成本均衡分片；`make test-shard-durations` 从完整离线套件重生成基线后提交。分片只**读** `.test_durations`（不 `--store-durations`），并发 CI job 不会竞争写。
- **`backend/.test_durations`**：分片依据的时长基线文件，测试集有实质变化后需重新生成。**v2.2.0 已涨到 32,395 行**（v2.1.0 页面写的"1.3 万行"是当时的值），与测试函数数从 14,405 涨到 23,432 同比例。
- **🆕 2.2：`test-shard` 前置断言基线存在**（`backend/Makefile:49-51`）——基线文件缺失时不是"默默均分"，而是 fail-loud 并提示 `make test-shard-durations`。`test_client_live_policy.py::test_duration_baseline_target_replaces_stale_entries`（`:273`）反向钉住再生命令带 `--clean-durations`（否则陈旧条目会一直留在基线里，让新用例被分到最慢那一片）。
- **🆕 2.2：本地 `make test` = `-j4` 四片并行**（`TEST_JOBS ?= 4`，`backend/Makefile:23`）。本地入口与 CI 入口现在共用同一套切分，"CI 上某一片慢了"可以在开发者机器上复现。

### 🆕 2.2 新增 workflow：Windows live 门策略（`backend-windows-live-policy.yml`）

70 行，`runs-on: windows-latest` + Python 3.12 + `uv sync --locked --group dev`。它跑的不是新测试，而是**两类在 ubuntu 上永远抓不到的回归**（workflow 顶部注释原文）：

> "These offline policy tests spawn pytest children that collect live tests, and the workspace text-cache tests pin byte-exact cache round-trips whose regression only fails on native Windows (see test_scanner_text_cache_atomic)."

执行面上它刻意**逐节点点名**而不是跑整个文件或 `make`（注释："Explicit nodes include all four collection cases and avoid make"）：

| 点名节点 | 测什么 |
|---|---|
| `test_client_live_policy.py::test_child_env_stays_isolated_but_bootable_on_windows`（`:180`） | 子 pytest 进程在 Windows 上环境隔离但可启动 |
| `::test_config_alone_does_not_enable_live_collection`（`:126`） | 只有 config.yaml 不足以收集 live 用例 |
| `::test_explicit_opt_in_collects_live_tests`（`:132`） | 显式 opt-in 才收集 |
| `::test_ci_blocks_live_collection_even_with_opt_in`（`:140`） | CI 环境下 opt-in 也拦 |
| `::test_opt_in_without_config_reports_missing_config`（`:146`） | 缺 config 时报缺失而不是静默跳过 |
| `test_scanner_text_cache_atomic.py` 全文件 | 扫描器文本缓存的**字节精确**往返（换行翻译只在原生 Windows 上失败，注释点名 PR #7110 review） |
| `test_workspace_changes.py` 全文件 | 同上族的 workspace 变更摘要 |

触发面很窄：`workflow_dispatch` + `schedule: '17 6 * * 1'`（每周一 UTC 06:17）+ `pull_request` 且 paths 命中 8 个具体路径（含 `deerflow/workspace_changes/**`、`test_client_live.py`、`backend/uv.lock`）。**解释**：这条车道的设计取向是"**慢但不漏**"——Windows runner 比 ubuntu 贵且不稳定，所以不进每个 PR；但它的 paths 里放了 `uv.lock`，因为依赖升级是最常改变换行/编码行为的变量。`test_client_live_policy.py::test_windows_workflow_collects_all_five_policy_checks`（`:289`）反向钉住"这条 workflow 必须逐节点点名全部 5 条策略用例"——门禁的接线本身也被门禁看住（`test-strategy/04-enforcement-meta.md` §6）。

### 🆕 2.2 新增 workflow：扩展包检查（`extension-package-check.yml`）

74 行，两个 step、都在 `for package in examples/deerflow-extension-*/` 上循环：

1. **打包/契约检查**：`uv run --project backend --no-sync python scripts/check_extension.py "$package"`（脚本 176 行）。它构建 wheel 并在**不安装其代码**的前提下检查 wheel 内容——路径穿越与反斜杠、`.dist-info/METADATA` 必须恰好一个、依赖声明是否被允许、浏览器资产与 manifest 是否能被 `deerflow.extensions.browser_assets.load_browser_assets` 与 `_validate_entry_point` 接受。用 `::group::` 把每个包折叠成一段日志，失败时一眼定位到包。
2. **自带测试**：对**带 `tests/` 目录**的包，起隔离 venv（`uv venv --python 3.12` + `uv pip install -e ../../backend/packages/extension-api` + `uv pip install -e ".[dev]"`），然后 `uv run --no-project pytest -q` + `ruff check .` + `ruff format --check .`。注释原文："Each package's own tests run in an isolated environment against this checkout's extension-api, so a contract change that breaks them fails here."

**解释**：第 2 步填的是 v2.1.0 时代的一个真实缺口——示例扩展包的测试当时"不进任何 CI workflow"。`uv run --no-project` 是关键：它保证包的测试**只能用包自己声明的依赖**，不能偷偷借宿主 backend 环境里的东西（这与 `examples/deerflow-extension-example/README.md` 里"只使用公共契约与自身声明的依赖"的说法闭环）。当前 14 个示例包中只有 `deerflow-extension-example` 带 `tests/`，其余 13 个只过第 1 步——**"有测试就跑、没测试不拦"是刻意的**，避免为了过门禁写空测试。

触发面：`pull_request` + `push`（`main`/`*-dev`），paths 命中 `examples/deerflow-extension-*/**`、`scripts/check_extension.py`、`backend/packages/extension-api/**`、`deerflow/extensions/**`、`backend/pyproject.toml`、`backend/uv.lock`。

### 🆕 2.2 增补：`skill-review-ci.yml` 的 `skill-tests` job

根 `tests/skills/`（21 个 `.py`，公共技能脚本的离线回归测试）从 v2.1.0 的"不进 CI"变成 PR 阻塞项。新 job：

```yaml
jobs:
  skill-tests:
    timeout-minutes: 10
    env:
      # Test imports must not leave .pyc files in the reviewed skill packages.
      PYTHONDONTWRITEBYTECODE: "1"
    steps:
      - run: uv sync --locked --group dev            # working-directory: backend
      - run: |
          # Fail instead of silently skipping data-analysis tests on missing extras.
          uv run --locked python -c "import duckdb, openpyxl, requests"
          uv run --locked python -m pytest ../tests/skills -q -rs
```

五个细节值得记：
- **`import duckdb, openpyxl, requests` 前置探针**（注释原文 "Fail instead of silently skipping data-analysis tests on missing extras"）——技能脚本测试用 `importorskip` 处理可选依赖，但这会让"缺 extras"变成静默跳过；这里用一个显式 import 把缺依赖变成红；
- `--locked` 保证 CI 不因隐式依赖解析而与 lock 漂移；
- `-rs` 把跳过原因打到日志（静默跳过等于覆盖归零）；
- `PYTHONDONTWRITEBYTECODE=1` 放在 **job 级 `env`** 而不是单步，是因为测试会**在技能目录里跑 CLI 子进程**，`.pyc` 落进 `skills/public/` 会污染「包内容哈希」——而技能评审的 waiver 正是按包全量 SHA-256 匹配的（见下节）。这是「测试不能改变被测产物」的一条很具体的落地；
- `timeout-minutes: 10` + `if: ... draft == false`：与 backend 各 job 同构，草稿 PR 不烧 runner；
- `push.branches` 仍是显式 `["main", "2.1.x-dev"]`（**未**改通配），paths 新增 `tests/skills/**`。

### 🆕 同步 #6：CI 其他变更

| 变更 | 位置 |
|------|------|
| Node 22 → 24（#5063） | `frontend-unit-tests.yml`、`lint-check.yml` 等所有 `setup-node` |
| Sandbox image smoke workflow 🆕 | `.github/workflows/sandbox-image-smoke.yml`（+73 行）——真实镜像冒烟验证 AIO sandbox 加固：基线镜像 + 需要 FOWNER 的 1.11.0 启动路径；先把镜像 pull 并转成不可变 `repo@sha256` 引用再跑，摘要打印 digest 保证可复现 |
| sandbox-network-proxy 镜像 workflow 🆕 | `.github/workflows/sandbox-network-proxy-image.yaml` |
| Skill review waivers（见下节） | `.github/skill-review-waivers.v1.json` + `scripts/skill_review_waivers.py` |

### 🆕 同步 #7（v2.1.0）：push 分支触发改为 `*-dev` 通配（#5765）

7 个 workflow 的 `push.branches` 在这一轮被改动（每个文件只改这一行）：**6 个由字面量 `2.0.x-dev` 改为 `*-dev` 通配**，第 7 个（`skill-review-ci.yml`）改为显式 `2.1.x-dev`。

| workflow | `push.branches` | 备注 |
|------|------|------|
| `backend-unit-tests.yml` | `[ 'main', '*-dev' ]` | |
| `frontend-unit-tests.yml` | `[ 'main', '*-dev' ]` | |
| `lint-check.yml` | `[ 'main', '*-dev' ]` | `pull_request.branches` 仍是 `[ '*' ]` |
| `backend-blocking-io-tests.yml` | `["main", "*-dev"]` | 另有 `paths: backend/**` 过滤 |
| `e2e-tests.yml` | `[ 'main', '*-dev' ]` | 另有 `paths: frontend/**` 过滤 |
| `replay-e2e.yml` | `["main", "*-dev"]` | 另有 `paths`（`frontend/**` + replay 相关后端路径）过滤 |
| `skill-review-ci.yml` | `["main", "2.1.x-dev"]` | **例外，不是通配** |

- **动机**：release/dev 分支名带版本号，改成通配后新建 `2.1.x-dev`、未来 `2.2.x-dev` 等分支自动继承全部 push 门禁，不必再逐个 workflow 加分支名。
- **例外**：`skill-review-ci.yml` 仍显式钉 `2.1.x-dev`（**有意为之**）——skill 审查与 waiver 的信任边界（见下节）需要精确控制生效分支，因此不跟随通配。
- **未变**：`label-sync.yml`（`push.branches: [main]`）、`sandbox-network-proxy-image.yaml`（`push.branches: [main]`，只发布到 main）、`sandbox-image-smoke.yml`（根本没有 `push` 触发，只有 `workflow_dispatch` + `pull_request`）、`triage.yml`（`pull_request_target`）、`verify-versions.yml`（`workflow_call`）。

## 🆕 同步 #6：Skill review CI waivers 机制

`.github/skill-review-waivers.v1.json`（schema `deerflow.skill-review-waivers.v1`）+ `scripts/skill_review_waivers.py`（295 行），由 `scripts/review_changed_public_skills.py` 消费：

- **精确匹配**：每条 waiver 匹配一条 error finding（package / source / rule_id / path / line / evidence 全对上才生效），附带被审文件的 SHA-256 和过期日期（`expires_on`），可选 `preapproved_file_sha256s`（上限 8 个）预批未来的整文件哈希。
- **信任边界**：PR 可以从 head revision 验证 waiver 编辑，但只有 **trusted base revision** 的 manifest 能真正豁免本次 CI。
- **永不豁免 blocker**：blocker 级 finding 任何情况都不能被 waiver 掉。
- **两段式合并流程**：waiver 生效需要 manifest 变更先落到 trusted base——即先合 manifest，再合 skill 变更，之后在一次 follow-up cleanup 中把消费掉的哈希从 `preapproved_file_sha256s` 提升为 `file_sha256`。直接在同一次 PR 里同时改 waiver 和 skill 是不会生效的。
- waiver 条目在 CI 输出中保持可见（不静默吞掉）。

**并行分片（#5137，同步 #6）**：unit tests 按 **4 个 shard** 跑（`matrix: shard: [1,2,3,4]`），分片不是随便均分——`make test-shard` 按 `backend/.test_durations` 里记录的**真实耗时**平衡各 shard（fail-fast 关闭，某个 shard 挂了仍完整报告该 shard 的测试）。

**沙箱镜像冒烟（同步 #6 新增）**：`sandbox-image-smoke.yml` + `sandbox-network-proxy-image.yaml` 两个 workflow 把沙箱镜像的构建/拉起纳入 CI 验证。

## 其他 workflow：lint / 前端 / 发行

`.github/workflows/` 在 v2.2.0 共 **19** 个文件（v2.1.0 为 16），下面只列与测试/门禁直接相关的。完整清单里另有 `container.yaml`、`chart.yaml`、`nightly.yaml`、`lark-cli-images.yaml`、`label-sync.yml`、`triage.yml` 等发行/运维 workflow。

| workflow | 触发 | 内容 |
|------|------|------|
| `lint-check.yml` | `push.branches: ['main','*-dev']` + `pull_request`（`branches: ['*']`） | **4 个** job（v2.2.0 新增第 4 个）：`agent-guidance`（`python scripts/check_agent_guidance.py`——PR 传 `--base-ref/--head-ref`，push 传 `--before/--after`，都带 `--github-annotations`）· `lint-backend`（`uv lock --check` 后 `make lint` = `ruff check .` + `ruff format --check .`）· `lint-frontend`（`pnpm format` / `pnpm lint` / `pnpm typecheck` / `BETTER_AUTH_SECRET=local-dev-secret pnpm build`）· 🆕 `label-declarations`（`python scripts/check_label_declarations.py`，见 `test-strategy/04-enforcement-meta.md` §4bis） |
| `frontend-unit-tests.yml` | `push.branches: ['main','*-dev']` + 所有 PR | Node `24` + `corepack prepare pnpm@10.26.2 --activate` + `pnpm install --frozen-lockfile`，然后 `make test`（= `pnpm test` → rstest） |
| `e2e-tests.yml` | `push.branches: ['main','*-dev']` + PR；paths 从"只有 `frontend/**`"扩到 10 条（加 bookmark 插件夹具、`extension-api/**`、`deerflow/extensions/**`、`config/plugin_settings.py`、`backend/pyproject.toml`、`backend/uv.lock`、`examples/deerflow-extension-bookmarks/**`） | **v2.2.0 改为 4 分片**：`matrix.shard: [1,2,3,4]`，每片跑 `pnpm exec playwright test --shard=${{ matrix.shard }}/4 --workers=1 --reporter=github,html`；auth 恢复套件**只在 shard 1 跑且不受兄弟分片失败影响**（`if: ${{ !cancelled() && matrix.shard == 1 }}`，注释："Keep auth coverage unsharded and run it even if the first shard fails"）；新增 Python+uv 安装步骤（`uv sync --locked`）因为 bookmark 浏览器测试要起**真的 Python action/router 夹具**；`timeout-minutes` 从 15 提到 25；报告按分片上传为 `playwright-report-<n>`（保留 7 天） |
| `replay-e2e.yml` | `push.branches: ['main','*-dev']` + PR，`paths` 含 `frontend/**` 与 replay 相关后端文件 | 两个 job：`backend-replay-golden`（`uv run pytest tests/test_replay_golden.py -v`）与 `fullstack-replay-render`（真前端 + replay gateway + Chromium，`playwright.real-backend.config.ts`）；都不需要 API key |
| `container.yaml` | `push.tags: ["v*"]` | 三个镜像（backend / frontend / provisioner）推 GHCR + build provenance attestation；backend 镜像 `build-args: UV_EXTRAS=postgres`；每个 job 都 `needs: verify-versions`，版本源漂移则整批不发布 |
| `chart.yaml` | `push.tags: ["v*"]` + `pull_request`（`deploy/helm/deer-flow/**`、`config.example.yaml`、本文件、三个 check 脚本） | PR/tag 上跑 `validate-chart`（helm lint + template render + `check_chart_sandbox_service.sh` + `check_chart_skill_upload_size.sh` + `check_config_version.sh`）；tag 上再 `publish-chart` 推 OCI chart |
| `verify-versions.yml` | `workflow_call`（**不可单独触发**） | 可复用 workflow：读出 tag 版本（`GITHUB_REF_NAME#v`）后调用 `scripts/verify_versions.sh "$TAG_VERSION"`；被 `container.yaml` 和 `chart.yaml` 在 `v*` tag 上调用 |
| `lark-cli-images.yaml` | `workflow_dispatch`（输入 `lark_cli_version`）+ `push.tags: ["lark-cli-v*"]` | 发布两个 Lark sandbox 运行时镜像（Pattern A init / Pattern B broker）；跟随 `larksuite/cli` 版本而非 DeerFlow `v*`，因此**不**接 `verify-versions` |

**版本号现在锁五处（v2.2.0）**：v2.1.0 时是"四处"——`deploy/helm/deer-flow/Chart.yaml` 的 `version` + `appVersion`、`backend/pyproject.toml`、`frontend/package.json`。v2.2.0 加了第五个来源 `backend/packages/harness/pyproject.toml`（`deerflow-harness` 自己的版本），并且把 `backend/uv.lock` 纳入判定——`scripts/verify_versions.sh:9` 注释："`backend/uv.lock` — root + harness entries, via `uv lock --check`"。**解释**：harness 是独立发布的包（`uv add deerflow-harness --path ...` 是下游最常见的接入方式），它自己的版本号与 Gateway 版本脱钩过一次就会让下游装到"API 相同、行为不同"的组合；而 lock 里两个 PEP 440 条目是这条链上唯一会被 uv 自动改写的产物，因此用 `uv lock --check` 而不是正则读版本号来判定（`:48-49` 注释："`uv lock --check` below is what passes or fails the lock"）。

`scripts/bump_version.sh <version>` 一次改齐这五处 + `uv lock`，并**自动回跑** `verify_versions.sh` 自检，但它刻意不碰 `CHANGELOG.md`、也不打 tag。**v2.2.0 起它要求 `uv` 在 `PATH` 上**（因为要重跑 lock）；`verify_versions.sh` 同样要求 uv，且失败时输出 `::error::` 注解让 GitHub 直接定位到行。注意 `verify-versions` 仍只在 **tag 发布链路**（以及 `chart.yaml` 的 PR validate）上跑，普通 push/PR 不会校验版本一致——版本漂移的本地前置哨兵是 pre-commit 的 `uv lock --check`（`test-strategy/09-test-infra-and-platform.md` §4）。

## 为你的 DeerFlow 应用搭 CI

### 最小可用的 workflow

```yaml
# .github/workflows/agent-tests.yml
name: Agent Tests
on: [pull_request]

jobs:
  test:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-python@v5
        with: { python-version: '3.13' }

      - name: Install DeerFlow
        run: |
          git clone https://github.com/bytedance/deer-flow.git /tmp/deer-flow
          uv add deerflow-harness --path /tmp/deer-flow/backend/packages/harness

      - name: Run unit tests (no LLM)
        run: uv run pytest tests/ -m "not llm" -v

      - name: Run LLM tests (PR only, needs secret)
        if: github.event_name == 'pull_request'
        env:
          DEEPSEEK_API_KEY: ${{ secrets.DEEPSEEK_API_KEY }}
        run: uv run pytest tests/ -m "llm" -v
```

### @requires_llm 标记

```python
import os
import pytest

requires_llm = pytest.mark.skipif(
    os.getenv("CI", "").lower() in ("true", "1")
    or not os.getenv("DEEPSEEK_API_KEY"),
    reason="Needs LLM API key — skipped in CI or when key is unset"
)

@requires_llm
def test_agent_generates_report():
    client = DeerFlowClient()
    result = client.chat("生成项目报告", thread_id="ci-1")
    assert len(result) > 100
```

### pytest 标记注册

```ini
# pyproject.toml
[tool.pytest.ini_options]
markers = [
    "llm: tests that need a real LLM API call",
    "slow: tests that take > 10 seconds",
]
```

## 测试环境隔离

每个测试要有独立的文件系统和配置：

```python
@pytest.fixture
def isolated_deerflow(tmp_path, monkeypatch):
    """每个测试独立——不污染全局状态。"""
    # 1. 隔离数据目录
    monkeypatch.setenv("DEER_FLOW_HOME", str(tmp_path / "deer-data"))

    # 2. 重置所有单例缓存
    monkeypatch.setattr("deerflow.config.paths._paths", None)
    monkeypatch.setattr("deerflow.sandbox.sandbox_provider._default_sandbox_provider", None)

    # 3. 注入纯内存配置（不读磁盘 config.yaml）
    config = AppConfig.model_validate({
        "models": [{
            "name": "test-model",
            "use": "langchain_openai:ChatOpenAI",
            "model": "gpt-4o",
            "api_key": os.getenv("OPENAI_API_KEY", "sk-test"),
        }],
        "sandbox": {
            "use": "deerflow.sandbox.local:LocalSandboxProvider",
            "allow_host_bash": False,
        },
    })
    monkeypatch.setattr("deerflow.client.get_app_config", lambda: config)

    # 4. 禁用非必要中间件（减少 LLM 调用和副作用）
    monkeypatch.setattr("deerflow.config.title_config._title_config",
                        TitleConfig(enabled=False))
    monkeypatch.setattr("deerflow.agents.middlewares.memory_middleware.get_memory_config",
                        lambda: MemoryConfig(enabled=False))

    return tmp_path
```

## Token 预算和超时控制

```python
def test_agent_stays_within_budget():
    client = DeerFlowClient()

    total_tokens = 0
    for e in client.stream("简单回答：1+1=?", thread_id="budget-test"):
        if e.type == "end":
            total_tokens = e.data["usage"]["total_tokens"]

    assert total_tokens < 500  # 简单问题不该超过 500 token

def test_agent_completes_within_timeout():
    import signal, time

    start = time.time()
    client.chat("hello", thread_id="timeout-test")
    elapsed = time.time() - start
    assert elapsed < 30  # 简单回复 30 秒内
```

在 CI 中更严格：

```yaml
- name: Run agent with timeout
  timeout-minutes: 5
  run: uv run python ci_agent_task.py
```

## 分层 CI 策略

| 层 | 什么时候跑 | 跑什么 | 耗时 |
|----|----------|--------|------|
| L1 | 每个 commit | 纯 Python 单元测试（mock 一切） | < 30s |
| L2 | PR | `@requires_llm` 的核心行为测试 | < 5 min |
| L3 | Nightly | 完整 agent workflow e2e | < 30 min |
| L4 | 发版前 | 对抗测试、安全扫描、长对话 | < 2 hr |

## 决策矩阵：我该测什么

| 你写的是… | 最小该测的 | 最好也测的 |
|-----------|----------|----------|
| 一个 SKILL.md | prompt 里有没有 skill 名字 | agent 是否按 skill 步骤执行 |
| 一个自定义 SOUL.md | prompt 里有没有 SOUL 内容 | agent 的行为是否符合 SOUL 约束 |
| 一个自定义 sub-agent | 工具白名单是否生效 | 真实 LLM 下的任务完成度 |
| 一个 custom mount | agent 能否读写 mount 路径 | 路径安全边界（.. 遍历、宿主路径） |
| 一个 workflow | 中间件链顺序 | agent 的 tool call 序列 |
| 一个 CI 集成 | `@requires_llm` 正确跳过 | 真实 LLM 端到端 |

## 关键源码

| 内容 | 位置 |
|------|------|
| CI workflow | `.github/workflows/backend-unit-tests.yml`（4 shard 并行，`.test_durations` 平衡） |
| 阻塞 IO workflow | `.github/workflows/backend-blocking-io-tests.yml` |
| Skill review CI | `.github/workflows/skill-review-ci.yml`（`push` 显式钉 `2.1.x-dev`，不用 `*-dev` 通配）；v2.2.0 新增 `skill-tests` job 跑根 `tests/skills/`（21 个 `.py`） |
| 🆕 Windows live 门策略 | `.github/workflows/backend-windows-live-policy.yml`（`windows-latest`，5 个点名策略节点 + 文本缓存字节精确性） |
| 🆕 扩展包检查 | `.github/workflows/extension-package-check.yml` + `scripts/check_extension.py`（176 行），覆盖 14 个 `examples/deerflow-extension-*/` |
| 🆕 标签声明配对 | `scripts/check_label_declarations.py`（273 行）+ `.github/labels.yml` ↔ `triage.yml`；回归 `backend/tests/test_label_declarations.py` |
| 🆕 沙箱镜像验证 | `.github/workflows/sandbox-image-smoke.yml` + `sandbox-network-proxy-image.yaml` |
| 🆕 Nightly build | `.github/workflows/nightly.yaml`（images + Helm chart） |
| 发行镜像 / chart | `.github/workflows/container.yaml`、`.github/workflows/chart.yaml`、`.github/workflows/lark-cli-images.yaml` |
| 版本一致性门禁 | `scripts/verify_versions.sh`（**5 个字段** + `uv lock --check`）+ `.github/workflows/verify-versions.yml`（`workflow_call`）+ `scripts/bump_version.sh` |
| Makefile test 目标 | `backend/Makefile` |
| conftest 全局 fixture | `backend/tests/conftest.py` |
| e2e 环境隔离 fixture | `backend/tests/test_client_e2e.py` — `e2e_env` |
| @requires_llm 标记 | `backend/tests/test_client_e2e.py` |
| live 门策略门禁 | `backend/tests/test_client_live_policy.py`（13 个测试，含 Windows workflow 接线断言） |
| 测试支撑助手 | `backend/tests/support/`（`compose.py` / `local_sockets.py` / `nginx_conf.py` / `postgres.py` / `workflow_gateway.py` 为 v2.2.0 新增，见 `test-strategy/09-test-infra-and-platform.md` §1） |
