---
title: "速度与隔离工程"
description: "时长基线分片与只读防竞态、node/dom 成本分流、collection-only CI job、conftest 的五个 autouse 重置、sys.modules 破循环导入、bench 纪律与跨平台可移植性——让 1.4 万个测试跑得快且互相不污染的工程。"
topics: [testing, ci, performance, isolation]
---

# 速度与隔离工程

14,408 个后端测试函数要维持"agent 一次思考轮内能跑完相关子集"的反馈速度，同时 738 个文件在一个进程里共享全局状态而互不污染——这需要两套专门的工程。

## 1. 速度：把真实耗时当作一等数据

### 时长基线分片

`backend/Makefile` 的 `test-shard` 把套件按**真实墙钟成本**切分：CI 跑 4 个分片（`--splitting-algorithm least_duration`），均衡依据是提交入库的 `backend/.test_durations`（13,141 行）。三个细节显示这套设计经过竞态思考：

- **分片只读基线**（Makefile 注释原话）："Shards only READ that file (no `--store-durations`), so concurrent CI jobs cannot race writes on it"——4 个并行 CI job 不会写竞争同一文件；
- 基线过期由 `make test-shard-durations` 显式再生（本地或周期任务，跑完提交）；
- CI 矩阵 `fail-fast: false`：失败分片照常报告，不连坐取消兄弟分片——**诊断信息优先于节省**。

### 成本感知的环境分流（前端）

`frontend/rstest.config.ts` 分两个 project：`node`（绝大多数纯逻辑测试）与 `dom`（happy-dom，仅 `*.dom.test.*` 文件）。选环境不靠自觉，靠**文件名后缀**——配置注释把经济学写明："A DOM environment costs roughly 3x the runtime of the node suite"。`frontend/AGENTS.md:43` 补充判据：只有"行为存在于真实 React 之下"的测试（effect 顺序、卸载清理、store 变化重渲染）才配付 3 倍成本。**实践中**，仅需要渲染输出的测试直接用 `renderToStaticMarkup` 在 node 环境解决（如 `frontend/tests/unit/core/reasoning-trigger.test.ts`）——这是从测试实践归纳的惯例，AGENTS.md 未成文。车道细节见 `06-frontend-and-tui.md` §一。

### Collection 也是回归面

CI 的 `backend-unit-tests.yml` 有一个 `default-install-collection` job：按文档的 contributor 路径装依赖（`uv sync --group dev`，不带 extras），然后只做 `pytest --collect-only`。它验证的是**可选依赖（postgres 驱动等）的 import 必须保持惰性**——否则"文档承诺的最小安装"会在收集阶段就碎，文档与现实的契约又碎了一块。

### 单测入口文档化

根 `AGENTS.md` 的 "Run a single test" 一节给出单文件/单函数级命令（`python -m pytest tests/path/to/test.py::test_func -q`；前端 `pnpm rstest run <pattern>`）。**反馈闭环的最小颗粒度是文档承诺的一部分**。

## 2. 隔离：五个 autouse fixture 与一套 monkeypatch 纪律

`backend/tests/conftest.py` 的隔离策略是"**进程级单例全部按测试重置，环境变量按测试 monkeypatch**"。值得注意 conftest 刻意保持很薄（184 行：`sys.path` 注入 + 循环导入 mock + provisioner 加载 fixture + 5 个 autouse 重置——**没有**环境变量清洗、没有 API key 抹除、没有 HOME 重定向）；pytest 配置同样极薄（`backend/pyproject.toml` 只注册 4 个 marker，无 addopts/testpaths）。"无 API key"是构造性的——离线套件根本不配置真实 provider——而运行时门控（live 三重门、`MONOCLE_LIVE_TESTS`）全部在模块级实现，靠策略测试反向钉住（残余风险见 `00-overview.md` 已知缺口 §1）：

| autouse fixture（行号） | 重置什么 | 防什么泄漏 |
|------|---------|-----------|
| `conftest.py:81` `_reset_skill_storage_singleton` | SkillStorage 单例（前后各一次） | 技能存储跨测试污染 |
| `conftest.py:96` `_reset_frozen_checkpoint_channel_mode` | 进程级冻结的 checkpoint 模式 | 生产语义是"重启才生效"，一个进程里建多个 app 的测试套件必须解冻 |
| `conftest.py:114` `_restore_title_config_singleton` | `TitleConfig` 恢复出厂默认 | 加载过真 `config.yaml` 的测试把单例留在脏状态，后续测试**顺序依赖** |
| `conftest.py:139` `_isolate_trace_context` | trace id 绑定为未绑定态 | 一个测试的 trace 悄悄满足下一个测试关于 id 的断言 |
| `conftest.py:158` `_auto_user_context` | 注入默认测试用户进 contextvar | 持久层读 `user_id` 的 RuntimeError；用 `no_auto_user` marker 显式退出（82 处使用）——想验证"无用户上下文"行为的测试恰恰需要退出 |

第五个 fixture 值得多看一眼：**默认注入、显式退出**的方向选择，让 99% 的测试零样板，而"无上下文"这种少数场景成为被 marker 标记的可搜索事件。

### sys.modules 破循环导入

`conftest.py:21-40` 在任何测试 import 之前，向 `sys.modules` 注入 `deerflow.subagents.executor` 的 MagicMock，切断生产代码里的循环链（`subagents.__init__ → executor → thread_state → agents.__init__ → lead_agent.agent → subagent_limit_middleware → executor`）。这不是权宜 hack——`backend/AGENTS.md` 把它成文为惯例："If a module causes circular import issues in tests, add a `sys.modules` mock in `tests/conftest.py`"。

### 文件系统与环境变量：per-test tmp

环境隔离不走 session 级 fixture，而是 per-test `monkeypatch` 纪律：36 个文件把 `DEER_FLOW_HOME` 指到 `tmp_path`（整个 `.deer-flow` 家目录搬家），16 个文件生成独立 `config.yaml` 并设 `DEER_FLOW_CONFIG_PATH`；进程级单例（`_app_config`、`_engine`、`_session_factory` 等）在需要时显式置空（`test_replay_golden.py:26` 的 `_reset_process_singletons` 是范本）。

## 3. 外部服务的跳过语义

`integration` marker 的注册语义是"skipped when unavailable"，实现上是**探测式自跳过**：`importorskip("redis")` 探依赖、`skipif` 探 `DEER_FLOW_TEST_REDIS_URL` 可达性；Postgres 侧由 CI 提供服务（`DEDUPE_TEST_POSTGRES_URL` 指向 CI 的 Postgres 17 service），迁移契约测试在 `DEERFLOW_TEST_POSTGRES_URL` 存在时对真 Postgres 断言、否则 SQLite 兜底。**解释**：外部依赖的"有无"是被显式声明的测试维度，而不是隐式的环境运气。

## 4. Bench：另一套纪律，同一套原则

`backend/scripts/benchmark/` 是独立于测试套件的基准体系（`backend/AGENTS.md` 专节规定），但它服从同一套原则的加强版：

> "The offline test suite must not require network access, provider credentials, or the LongMemEval dataset."

- 数据集按不可变 revision + SHA-256 钉住，评测命令**不得静默下载**；合成样本必须自我声明是合成；
- 不提交上游数据集文本、凭证、完整 provider 请求；离线选择用固定时钟与确定性排序；
- 对应的 16 个 `test_bench_*` 测试只验证基准脚本的**纯逻辑**（合成 fixture），把"评测代码本身的正确性"与"评测运行"分离。评测面还有两块：trace 行为断言的 Monocle（`02-deterministic-llm.md` 级 3，`MONOCLE_LIVE_TESTS=1` 显式开门）与技能评审器自带的 evals manifest（`08-upper-layer-apps.md` §三）。

## 5. 跨平台与杂项纪律

- **Windows 收集兼容**：POSIX-only marker 用 `os.name` 守卫（`backend/AGENTS.md`："guard POSIX-only markers with `os.name` for Windows collection"）；测试树里有专门的 NTFS DACL/PowerShell `Get-Acl` 助手与 Git-Bash 发现逻辑（避开 WSL 的 `bash.exe`）。
- **属性测试的单点存在**：全树仅 `backend/tests/test_delta_channel_state.py` 使用 Hypothesis——属性测试被当作**定点武器**（delta 通道状态机这种天然性质密集的目标），不是默认风格。
- **无 freeze 时间库**：时间相关确定性靠注入固定值与 `threading.Event` 同步实现，不引入 freezegun 一类全局补丁——与"测试不改生产执行拓扑"的总纪律一致。

## 速度与隔离的关系（解释）

这两套工程其实互为前提：**没有隔离，速度没有意义**（顺序依赖的套件快了也红绿不定）；**没有速度，隔离会被绕过**（跑一次几分钟的套件必然有人加 hack 抄近路）。DeerFlow 把两者放在同一份 Makefile 与同一个 conftest 里维护，并用"时长基线提交入库"这个动作把速度从优化目标升格为**被版本控制的资源**。
