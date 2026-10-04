---
title: "架构即测试与元治理"
description: "harness/app import 防火墙、compose/Helm/版本钉住、CI 工具链版本被测试钉住、AGENTS.md 尺寸预算门禁、skill-review 豁免清单的信任边界、门禁自身的自测——规矩变成可执行回归的地方。"
topics: [testing, governance, ci, architecture]
---

# 架构即测试与元治理

有一类测试不验证功能行为，而是**把"本该由纪律维持的规矩"变成可执行的回归**。DeerFlow 把这个思路用到了自觉的程度：架构边界、部署配置、CI 工具链、甚至 agent 指令文档本身，都有钉住自己的测试。

## 1. Harness/App import 防火墙

分层规则是"harness（`packages/harness/deerflow/`，可发布的框架包）永不 import app（`app/`，应用层）"。`backend/tests/test_harness_boundary.py:37` 用 AST 扫描实现：解析 harness 包下每个 `.py` 的 import 语句，发现 `from app.` / `import app.` 即列违规、测试失败。**架构图上的箭头由测试执行**，而不是靠 review 时人眼盯。

## 2. 部署配置即测试

"文档写了什么"与"交付物是什么"的一致性（`01-doctrine.md` 第 7 节）在整个部署面展开为一族测试：

| 测试 | 钉住的契约 |
|------|-----------|
| `test_compose_default_bind_host.py` | README 承诺的回环默认部署 ↔ 两个 compose 文件的每个发布端口显式 bind 地址 |
| `test_compose_default_workers.py` | 单 Uvicorn worker 默认（run 状态在进程内，多 worker 会撕裂） |
| `test_compose_extensions_config_writable.py` + `test_helm_extensions_config_writable.py` + `test_extensions_config_atomic_write.py` | `extensions_config.json` 运行时可写的挂载（compose 与渲染后的 Helm 双侧），含 Linux 拒绝在 mount point 上 `rename()` 的 `EBUSY` 回退路径 |
| chart CI 的三个检查脚本 | Service 类型门禁、上传大小策略、chart config_version 与 `config.example.yaml` 的漂移 |

周期面上，`nightly.yaml` 定时跑 `helm lint` + `helm template --include-crds` + config_version 漂移检查——发布配置的渲染验证不只 PR 时跑，慢一拍的漂移也有网。
| `scripts/verify_versions.sh`（`verify-versions.yml`） | `backend/pyproject.toml`、`frontend/package.json`、Helm Chart.yaml 的版本四处一致，drift **阻断一切发布** |

这族测试的共同叙事：**部署描述（compose/Helm/chart/版本号）也是代码，也会回归，也需要门禁**。

部署门的另一面是**冒烟分层**——"能启动 ≠ 能工作"在每一层都被显式执行：

| 冒烟层 | 机制 | 门禁位置 |
|---|---|---|
| 生产栈启动 | `make up` 等待 Gateway `/health` probe 才打成功横幅；readiness 失败必须暴露 Compose 状态与 Gateway 日志（根 `AGENTS.md`） | 本地/发布流程 |
| 沙箱真镜像 | `sandbox-image-smoke.yml`：先把 baseline 与回归镜像转成 **immutable repo@sha256** 引用，再 `pytest -m live tests/test_aio_sandbox_local_backend.py` 真镜像冒烟 | paths 触发的 PR workflow |
| 浏览器工具真人验收 | `backend/tests/manual_browser_live_check.py`：本地起藏 `SECRET-TOKEN-4917` 的登录表单 → 隔离 config 跑真实 agent turn（navigate→type→submit→read）→ 断言 tool trace 与最终回答含 token；无 key 直接 SKIP 返回 0 | 手动 |
| 最小安装可收集 | `backend-unit-tests.yml` 的 `default-install-collection` job：按文档贡献者路径 `uv sync --group dev` 后只做 `pytest --collect-only`（细节见 `05-speed-isolation.md` §1） | 每个 PR |
| TUI 打包冒烟 | 设计文档定位："A skipped-by-default live TUI smoke test can run only when a valid local config and credentials are present."（`docs/superpowers/specs/2026-06-13-deerflow-tui.md:219`） | 手动 |

## 3. CI pinning CI：工具链版本也是被测契约

`backend/tests/test_ci_uv_version_pin.py` 是元治理里最精彩的一例。它的 docstring 先论证 uv 为什么"不是一个构建工具，而是一个带契约的运行时依赖"：`ExtensionManager` 的工作就是驱动 uv 子进程，依赖其 CLI 行为与 `uv.lock` 序列化格式；随后指出最锋利的失效模式——**CI 装了更新的 uv，把 lock 重写成新版格式，CI 依然全绿（同一个 uv 能读回自己写的），而生产镜像里钉住的旧 uv 读不了提交的 lock**。结论："Upgrading uv should be one explicit change that touches the Dockerfile, the workflows, and this test together"。同一哲学的泛化表述：**测试环境的工具链必须与生产一致，且这个一致性本身要有一个名字叫测试的东西看住**。同族的还有前端包管理器：e2e workflow `corepack prepare pnpm@10.26.2 --activate` + `pnpm install --frozen-lockfile`；本地 pre-commit 另有 `uv lock --check` 前置哨兵（`09-test-infra-and-platform.md` §四）。

## 4. AGENTS.md 治理：给 agent 的指令也是受门禁的资产

28 个 `AGENTS.md` 文件构成目录级指令链，它们不是自由生长的散文，而是受预算与结构约束的资产：

- `scripts/check_agent_guidance.py` 强制尺寸预算：根文件软/硬 16/20 KB，模块级 28/32 KB，更深层 40/48 KB，**整条祖先链累计 80/96 KB**——直接约束"agent 指令的 token 成本"；
- `backend/tests/test_agent_guidance_check.py` 把治理规则本身钉死：`EXPECTED_GUIDANCE_PATHS` 精确集合（28 个路径）、按目录深度的预算表、棘轮语义（超预算的存量文件只能缩不能涨）、祖先链累积、exact-basename 发现规则（不误抓 `GITHUB_AGENTS.md`）、禁止"Subsystem Index"式索引文档、以及"本地与 CI 各只有一个入口"；
- `lint-check.yml` 的 `agent-guidance` job 在每个 PR 上跑这套检查（带 GitHub annotations）。

**解释**：这是把"指令文档的质量"从 review 惯例提升为 CI 门禁——与代码同等待遇、同一套红绿语义。

这套门禁越厚，越需要一条防盲信的评审哲学成文（`docs/agents/maintainer-orchestrator-design.md:42` 原文）：

> "**Evidence over a green check.** CI status is a signal, not a verdict. A green rollup never excuses reading the changed code path, and a failing required check is itself a finding. Tests passing does not prove the changed branch is exercised."

评审证据本身也物化进仓库：`docs/pr-evidence/` 存档 e2e 截图，让"证据"可引用、可追溯，而不只是口头声明。

## 5. Skill-review 豁免清单：信任边界设计

`skills/public/` 的确定性审查（SkillScan）允许豁免，但豁免机制本身按安全系统设计（根 `AGENTS.md` + `scripts/AGENTS.md` + `scripts/review_changed_public_skills.py`）：

- 每条豁免**精确匹配一个当前 error finding**（package/source/rule/path/line/evidence 逐字段），钉住文件全量 SHA-256，带过期日期；
- **blocker 级 finding 永不可豁免**；被豁免的错误仍按原严重度打印在 CI 输出里（豁免是"带理由的例外"，不是"消音器"）;
- **只有 trusted base revision 的 manifest 能压制当前 PR 的 finding**——PR head 的 manifest 会被解析校验，但不能为本 PR 自授权；
- "预批准未来 SHA-256"机制让依赖豁免的变更需要**两次 merge**（先落 manifest、进 trusted base，再落技能变更）。

这是"反自证"原则在仓库治理上的完整落地：**任何"让我通过"的机制，都不能由被检查者当场书写**。

## 6. 门禁自测：怀疑你的执法者

最后一层是对测试基建自身的测试——绿门禁可能失效到"不再咬人"：

| 自测 | 验证什么 |
|------|---------|
| `backend/tests/blocking_io/test_gate_smoke.py` | Blockbuster 门禁真的会咬：注入故意阻塞的探针必须触发拦截；`allow_blocking_io` 豁免必须真的关闸（"a green gate that no longer catches anything is worse than no gate at all"） |
| `backend/tests/test_client_live_policy.py` | live 三重门的政策矩阵：子进程重收集，验证 CI/opt-in/缺 config.yaml 三态下的收集行为 |
| `tests/monocle/test_deerflow.py` 的 live 门元测试 | `MONOCLE_LIVE_TESTS` 必须**默认关闭**——"plain run never spends model tokens" 是被断言的性质 |
| `backend/tests/test_detector_repo_root.py` | 静态检测器的仓库根解析必须 fail-loud——防止路径解析失败后"静默地什么都没扫" |
| `backend/tests/test_agent_guidance_check.py` | 上文的 AGENTS.md 治理器本身 |

## 这一层的方法论（解释）

五节连起来是一条递进：**架构规则**（import 方向）→ **交付物一致性**（部署配置、版本）→ **验证环境一致性**（工具链）→ **指令资产**（AGENTS.md）→ **执法者自身**（门禁自测）。每一环都回答同一个问题的不同变体："谁来监督监督者？"DeerFlow 的答案一律是：**下一个测试**。这也解释了为什么这个仓库的规矩能长期不腐化——规矩的执行不依赖记忆、review 惯例或个人权威，而是依赖一组每 PR 都跑的红绿检查。
