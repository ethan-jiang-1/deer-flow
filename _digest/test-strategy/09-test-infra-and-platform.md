---
title: "测试基建与平台工程"
description: "support/ 助手层与静态检测器族、测试依赖的 dev 组治理、pre-commit 与 CI 执行预算（并发取消/超时）、跨平台精确 skip 习语、按路径加载的跨包测试、无覆盖率门禁的取舍。"
topics: [testing, infrastructure, ci, cross-platform]
---

# 测试基建与平台工程

这一篇消化"让 1.4 万个测试在任何开发者机器上都能跑起来"的基建层：support/ 助手、静态检测器族、依赖治理、本地与 CI 的执行预算。前面各篇讲"测什么、怎么测"，这一篇讲"靠什么跑得起来"。

## 一、support/：测试自己的"标准库"

`backend/tests/support/`（含 `support/detectors/`）是测试代码自己的工具层，每件工具解决一类"没有它测试就无法跨环境运行"的问题：

| 助手 | 解决什么 |
|---|---|
| `support/shell.py` | Windows 上找能跑 POSIX 脚本的 shell。docstring 详解为什么必须 Git Bash：`System32\bash.exe`（WSL 启动器）与 Store 别名桩都叫 `bash`，且 CreateProcess 先搜 System32——**连字面 `["bash", ...]` argv 都拦不住**，必须主动发现 Git Bash 路径 |
| `support/symlinks.py` | symlink 种植助手——Windows 无开发者模式/特权进程时 `symlink_to` 抛 `OSError: [WinError 1314]`；套件**在创建点精确 skip** 而不是报错，有特权的宿主（CI/Linux/开发者模式）跑完整断言 |
| `support/skill_export_platform.py` | 平台守卫的**镜像**——生产代码在无 fd 目录遍历能力的平台（Windows 为主）对技能导出一律 422；测试侧镜像同一判定，注释原话："skip exactly where that guard fires, and the mirror lives here so the per-file copies cannot drift" |
| `support/detectors/repo_root.py` | 仓库根解析 fail-loud（被 `test_detector_repo_root.py` 钉住，`04-enforcement-meta.md` §6） |

**精确 skip 是一个成体系的习语**，三个要件：(a) skip 点精确到守卫触发的位置，不在套件入口一刀切；(b) skip 判定与生产代码的同一守卫**镜像或复用**，防止 skip 语义漂移；(c) 有能力的平台照常硬断言，skip 只降级环境、不降级断言。`integration` marker 的探测式自跳过（`05-speed-isolation.md` §3）是这个习语的 marker 级版本。

## 二、静态检测器族：发现工具与门禁的分工

`backend/tests/support/detectors/` 住着一族静态检测器，配两个 Makefile 入口：

| 入口 | 脚本 | 输出 |
|---|---|---|
| `make detect-blocking-io`（根转发 backend） | `scripts/detect_blocking_io_static.py` | `.deer-flow/blocking-io-findings.json` |
| `make detect-thread-boundaries` | `scripts/detect_thread_boundaries.py` | `.deer-flow/thread-boundary-inventory.json` |

- **blocking-io 静态检测**（`support/detectors/blocking_io_static.py`）：发现阻塞 IO 候选——工作流是"发现 → 人工评审 → 加 runtime anchor"（`01-doctrine.md` §6），**候选永远不是证明**；
- **线程边界盘点**（`support/detectors/thread_boundaries.py`）：静态盘点 backend 的 async/executor/thread/event-loop 边界。docstring 原文："parses source without importing application modules... never invokes a tool, instantiates a model, or calls an external service"——**检测器自身也守 hermetic 纪律**，绝不为了分析而执行生产代码；
- **评审期求交**（`support/detectors/blocking_io_changed.py`）：把 git diff 与静态发现求交——finding 在 diff 新增行上、**或相对 merge-base 是新发现**时报告（docstring："the latter catches exposure created without"），专门捕捉"没改阻塞行、但新 async 调用者让它变 async-可达"的隐性回归。

三个工具合起来是同一哲学：**静态工具负责"看见"，CI 门禁只认"运行时证明"**——发现输出落在 ignored 的 `.deer-flow/` 不进 git，避免"清单本身变成需要维护的假契约"。

## 三、测试依赖的 dev 组治理

`backend/pyproject.toml` 的 dev 组里，每个测试依赖都带一段"为什么在这"的注释——**测试依赖本身是被治理的资产**：

| 依赖 | 角色 / 注释要点 |
|---|---|
| `blockbuster` | blocking-io 门禁的运行时引擎 |
| `pytest-split` | `test-shard` 分片的机制本体（`05-speed-isolation.md` §1） |
| `hypothesis` | 属性测试（全树仅 `test_delta_channel_state.py` 一处，定点武器） |
| `pytest-asyncio` | async 测试（942 处 marker） |
| `monocle_apptrace` | "kept in the dev group so the tracing tests can import it without forcing it onto installs" |
| `redis` | "pin it in the dev group so the stream-bridge tests can always import/exercise the redis bridge without forcing it into production installs" |
| `textual` | "kept in the dev group so the terminal workbench can be run and tested locally / in CI" |

同样值得注意的是**刻意不引入**的东西：无 pytest-timeout（超时预算交给 CI 的 `timeout-minutes`，见 §四）；无 freezegun（时间确定性靠注入固定值，`05-speed-isolation.md` §5）；**无 pytest-cov、全仓无任何 `--cov` 配置**。最后这条不是疏忽：这个体系的质量门禁是**结构性**的（import 防火墙、契约双端钉、门禁自测、配置钉住），不靠"覆盖率百分比"这种容易被 gaming 的代理指标——门禁回答的是"结构还成立吗"，不是"跑过了多少行"。

## 四、本地与 CI 的执行预算

- **pre-commit**（`.pre-commit-config.yaml`）：ruff lint/format（与 backend 依赖**同一 ruff 版本**）、`uv lock --check`（lock 漂移在本地提交时即拦——CI 的 uv 版本钉住在本地有个前置哨兵，`04-enforcement-meta.md` §3）、frontend eslint/prettier；
- **CI concurrency**：每个测试 workflow 带 `concurrency: group: unit-tests-<PR号>` + `cancel-in-progress: true`——同一 PR 的新 push 自动取消旧 run，不烧已过时的分片；
- **CI timeout**：collection job 10 分钟、单分片 15 分钟、e2e/replay 25 分钟——超时预算显式成文，超时即红，不给"慢测试"留灰色地带；
- **包管理器也在 CI 钉住**：e2e workflow `corepack prepare pnpm@10.26.2 --activate` + `pnpm install --frozen-lockfile`——与 uv 版本钉住同族。

速度纪律因此有四层：时长基线入库（`05-speed-isolation.md` §1）→ 分片只读防竞态 → 并发取消与超时预算 → 本地 pre-commit 把格式/lock 挡在提交前。

## 五、跨包测试的按路径加载习语

两处"测试目标不是包，而是仓库里的一个文件"的场景用了同一习语——`importlib.util.spec_from_file_location` 按路径构造模块：

- `backend/tests/conftest.py` 的 `provisioner_module` fixture：把 `docker/provisioner/app.py` 当可 import 模块加载，`test_provisioner_kubeconfig` / `test_provisioner_pvc_volumes` 共享——docstring："any change to the provisioner entry-point path or module name only needs to be updated in one place"；
- 根 `tests/skills/skill_loader.py`：按路径加载各技能的生成脚本（`08-upper-layer-apps.md` §三）。

**解释**：provisioner 是 docker 侧的独立小程序，技能脚本不是包——都"住"在正常 import 语义之外。与其为此改变生产布局（把它们变成包），不如测试侧固化统一加载入口，把"路径变化只改一处"变成显式设计。
