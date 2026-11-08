---
title: "CI 与自动化测试"
description: "从本地实验到 CI 流水线：GitHub Actions 模板、@requires_llm 标记、环境隔离、Token 预算、决策矩阵。"
topics: [testing, ci, automation, github-actions, isolation]
---

# CI 与自动化测试

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
```

三条关键规则：
- **LLM 测试在 CI 中全部跳过**——`@requires_llm` 标记检查 `CI=true` 或缺少 `OPENAI_API_KEY`
- **只跑纯 Python 测试**——mock 一切，零外部依赖
- **阻塞 IO 门禁**——`make test-blocking-io` 在 `backend/**` 变更时触发（`make test` 默认 `--ignore=tests/blocking_io`，严格套件单独跑）

### 🆕 同步 #6：duration-aware 测试分片（#5137）

- **`backend/Makefile` 新目标**：`make test-shard SPLITS=4 GROUP=2` 用 pytest-split 的 `least_duration` 算法按真实墙钟成本均衡分片；`make test-shard-durations` 从完整离线套件重生成基线后提交。分片只**读** `.test_durations`（不 `--store-durations`），并发 CI job 不会竞争写。
- **`backend/.test_durations`**（1.3 万行）：分片依据的时长基线文件，测试集有实质变化后需重新生成。

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

`.github/workflows/` 在 v2.1.0 共 16 个 workflow，上面的 sync 小节只覆盖了一部分。其余几个的触发与 job 内容：

| workflow | 触发 | 内容 |
|------|------|------|
| `lint-check.yml` | `push.branches: ['main','*-dev']` + `pull_request`（`branches: ['*']`） | 3 个 job：`agent-guidance`（`python scripts/check_agent_guidance.py`——PR 传 `--base-ref/--head-ref`，push 传 `--before/--after`，都带 `--github-annotations`）· `lint-backend`（`uv lock --check` 后 `make lint` = `ruff check .` + `ruff format --check .`）· `lint-frontend`（`pnpm format` / `pnpm lint` / `pnpm typecheck` / `BETTER_AUTH_SECRET=local-dev-secret pnpm build`） |
| `frontend-unit-tests.yml` | `push.branches: ['main','*-dev']` + 所有 PR | Node `24` + `corepack prepare pnpm@10.26.2 --activate` + `pnpm install --frozen-lockfile`，然后 `make test`（= `pnpm test` → rstest） |
| `e2e-tests.yml` | `push.branches: ['main','*-dev']` + PR，`paths: frontend/**` | 同款 Node/pnpm 安装，`npx playwright install chromium --with-deps`，跑 `pnpm exec playwright test` 与 `-c playwright.auth.config.ts` 两套，上传 `playwright-report`（保留 7 天） |
| `replay-e2e.yml` | `push.branches: ['main','*-dev']` + PR，`paths` 含 `frontend/**` 与 replay 相关后端文件 | 两个 job：`backend-replay-golden`（`uv run pytest tests/test_replay_golden.py -v`）与 `fullstack-replay-render`（真前端 + replay gateway + Chromium，`playwright.real-backend.config.ts`）；都不需要 API key |
| `container.yaml` | `push.tags: ["v*"]` | 三个镜像（backend / frontend / provisioner）推 GHCR + build provenance attestation；backend 镜像 `build-args: UV_EXTRAS=postgres`；每个 job 都 `needs: verify-versions`，版本源漂移则整批不发布 |
| `chart.yaml` | `push.tags: ["v*"]` + `pull_request`（`deploy/helm/deer-flow/**`、`config.example.yaml`、本文件、三个 check 脚本） | PR/tag 上跑 `validate-chart`（helm lint + template render + `check_chart_sandbox_service.sh` + `check_chart_skill_upload_size.sh` + `check_config_version.sh`）；tag 上再 `publish-chart` 推 OCI chart |
| `verify-versions.yml` | `workflow_call`（**不可单独触发**） | 可复用 workflow：读出 tag 版本（`GITHUB_REF_NAME#v`）后调用 `scripts/verify_versions.sh "$TAG_VERSION"`；被 `container.yaml` 和 `chart.yaml` 在 `v*` tag 上调用 |
| `lark-cli-images.yaml` | `workflow_dispatch`（输入 `lark_cli_version`）+ `push.tags: ["lark-cli-v*"]` | 发布两个 Lark sandbox 运行时镜像（Pattern A init / Pattern B broker）；跟随 `larksuite/cli` 版本而非 DeerFlow `v*`，因此**不**接 `verify-versions` |

**版本号四处锁死**：`scripts/verify_versions.sh` 实际校验 **4 个值**——`deploy/helm/deer-flow/Chart.yaml` 的 `version` + `appVersion`、`backend/pyproject.toml` 的 `version`、`frontend/package.json` 的 `version`（无参数时要求四者互等；带参数时要求都等于该参数）。`scripts/bump_version.sh <version>` 一次改齐这四处并**自动回跑** `verify_versions.sh` 自检，但它刻意不碰 `CHANGELOG.md`、也不打 tag。v2.1.0 时四处都是 `2.1.0`。注意 `verify-versions` 只在 **tag 发布链路**上跑，普通 push/PR 不会校验版本一致。

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
| 🆕 Skill review CI | `.github/workflows/skill-review-ci.yml`（`push` 显式钉 `2.1.x-dev`，不用 `*-dev` 通配） |
| 🆕 沙箱镜像验证 | `.github/workflows/sandbox-image-smoke.yml` + `sandbox-network-proxy-image.yaml` |
| 🆕 Nightly build | `.github/workflows/nightly.yaml`（images + Helm chart） |
| 发行镜像 / chart | `.github/workflows/container.yaml`、`.github/workflows/chart.yaml`、`.github/workflows/lark-cli-images.yaml` |
| 版本一致性门禁 | `scripts/verify_versions.sh`（4 个值）+ `.github/workflows/verify-versions.yml`（`workflow_call`）+ `scripts/bump_version.sh` |
| Makefile test 目标 | `backend/Makefile` |
| conftest 全局 fixture | `backend/tests/conftest.py` |
| e2e 环境隔离 fixture | `backend/tests/test_client_e2e.py` — `e2e_env` |
| @requires_llm 标记 | `backend/tests/test_client_e2e.py` |
