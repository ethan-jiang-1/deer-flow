---
title: "工程证据文化"
description: "DeerFlow 的契约文档、可复现实验包、基准测试与测试工程——以及它们对 coding agent 的实际价值。"
topics: [contract-docs, experiments, benchmark, testing]
---

# 工程证据文化

## 1. 契约文档（随 feature 交付，写成行为契约）

`docs/` 下现有 56 个 `.md`（含子目录；v2.1.0 为 79 → 132 口径的旧统计已随目录重组失效，这里按 v2.2.0 实际文件重数）。增量仍集中在**随 feature 交付的行为契约**，不是功能介绍：

| 文档 | 内容性质 |
|------|----------|
| `docs/task-continuity.md` | 存储路径、生命周期、retention 上限、回滚/分支行为、故障语义的精确契约 |
| `backend/docs/THREAD_LIFECYCLE.md` | thread 生命周期状态机 |
| `backend/docs/LOOP_DETECTION.md` | loop 检测的事件与状态契约 |
| `backend/docs/checkpoint-retention-contract.md` | checkpoint 哪些能删哪些不能删的可达性契约 |
| `docs/database-forward-revision-recovery.md` | 专门解释两个重复 0019 migration 的前向恢复 |
| `docs/capability-center.md`（15 KiB，v2.2.0 新增） | 能力中心：一条能力从声明到授权到执行的完整契约 |
| `docs/full-stack-plugins.md`（32 KiB，v2.2.0 新增） | 全栈插件契约（Gateway 路由 + 前端页面 + 数据归属） |
| `docs/skill-evolution-host.md`（12 KiB，v2.2.0 新增） | skill 自演化宿主的边界与不变量 |
| `docs/RELEASE_SOP.md`（6 KiB，v2.2.0 新增） | 发版 SOP：把 `RELEASING.md` 的规则落成可照做的步骤 |

最后一份值得单独说：上游同时合入了两个 `0019_*` migration（版本号冲突），他们的处理是**写一篇文档解释为什么会发生、已部署库如何前向恢复**，而不是悄悄改名。对 agent 来说，这种"事故自解释"文档比十篇教程有价值。

RFC 体系 + `docs/plans/` + `docs/superpowers/{specs,plans}/` 构成"设计→计划→证据"的完整链条。**注意 v2.2.0 的实际形态**：`backend/docs/rfc-*.md` 只剩 3 份（`rfc-create-deerflow-agent` / `rfc-extract-shared-modules` / `rfc-grep-glob-tools`），RFC 的重心已转到 `docs/plans/*-rfc.md`（例如 `docs/plans/2026-07-10-pluggable-authorization-rfc.md`，被 `middlewares/AGENTS.md` 直接引用）；`docs/pr-evidence/` 目录在 v2.2.0 **已删除**（旧 digest 引用的这条路径不再存在）。

## 2. 可复现实验包（诚实报告阴性结果）

`docs/experiments/` 下两个实验包：`task-continuity-20260912/`（50+ 文件，完整协议、脚本、结果、对比图、验证记录）与 `aio-teardown-retry-20261017/`（3 个文件的最小包：`README.md` + `probe.py` + `evidence.json`）——**实验包的形态按问题大小伸缩**，不强制统一脚手架。task-continuity 最有价值的是它的**阴性结论**：

> vector 检索 vs keyword 对比 net −5.0pp，CI [−15.0, +5.0]，McNemar p=0.625——未证明稳定收益，**所以生产实现只做 lexical 检索**。

文档明确声明"实验数字描述的是独立 replay 原型，不代表生产实现"——先划定证据边界再给结论。这种自我否定式写作对 agent 极友好：不需要反向工程"为什么不用 embedding"。

`backend/scripts/benchmark/` 有 **8 个常驻基准目录 + 1 个独立脚本**（v2.2.0 实测；v2.1.0 是 5 个）：`checkpoint/` / `concurrency/` / `context_snapshot/` / `deermem_eviction/` / `deermem_scope_isolation/` / `goal_loop_stop/` / `sandbox/` / `scheduled_tasks/`，外加 `skill_export.py`（单文件工具，不是基准套件）。**形态仍不统一**：

| 形态 | 目录 | 说明 |
|------|------|------|
| 有 README | `context_snapshot`、`deermem_eviction`、`deermem_scope_isolation`、`goal_loop_stop`、`sandbox`、`scheduled_tasks` | 6 个（v2.1.0 只有 2 个） |
| 有入库结果文件（`.json`/`.jsonl`/`.csv`） | `context_snapshot`、`deermem_scope_isolation`、`scheduled_tasks` | 3 个 |
| 裸脚本（bench + summarize） | `checkpoint`、`concurrency` | 无 README、无结果 |

`backend/tests/` 下共 **22 个 `test_bench_*.py`**（v2.1.0 是 16 个），其中 deermem_eviction 独占 9 个（`_contracts`/`_dataset`/`_grading`/`_policy`/`_protocol`/`_published_results`/`_qa`/`_report`/`_results`），**deermem 的基准结果确实被测试锁定**——发布值、契约、评分、数据集逐层校验。但这条"结果被测试锁住"的性质**不要推广到全部 8 个**：`checkpoint`/`concurrency` 连 README 都没有，`scheduled_tasks` 的结果文件由 `test_bench_scheduled_budget_evidence.py` 只覆盖一部分。

## 3. 测试工程

- **迁移级测试**：revision 从 **50 个**（`0001_baseline`…`0048_extension_execution_leases`；其中 `0019` 有两份——`0019_projects` 与 `0019_thread_incarnations`，正是那篇前向恢复文档讲的冲突）配 **31 个** `test_migration_*.py`。**不是每个 revision 都有测试**：v2.2.0 相对 v2.1.0 新增 23 个 revision（`0026_mcp_task_lease_tokens`…`0048_extension_execution_leases`），其中 18 个有覆盖、5 个没有独立文件（`0030_notification_claim_tokens`、`0039_user_disabled`、`0043_runtime_im_notices`、`0045_completed_run_evidence`、`0048_extension_execution_leases`），靠领域级测试间接覆盖。合并口径的例子：`0019_projects` + `0020_threads_meta_project_id` → `test_migration_0019_0020_projects.py`；`0023_user_preferences` 无独立测试。另有持久化前向兼容测试（`test_persistence_forward_revision_compat.py`）
- **blocking_io 分离**：阻塞 I/O 测试独立成套（`make test-blocking-io`，#5105），默认套件不含——避免假阳性
- **CI 分片**：backend unit tests 并行 4 shards（#5137，`make test-shard SPLITS=4 GROUP=n`）+ `.test_durations` 时长档案；分片按**真实墙钟成本**均衡，且 `.test_durations` 对 shard 只读，避免并发写竞争（`.github/workflows/backend-unit-tests.yml:52`-`58`）
- **record/replay e2e**：外呼依赖录制回放（见 [testing/07-record-replay.md](../testing/07-record-replay.md)）
- **并发正确性实证**：OAuth 多 worker Postgres claim 用真实并发基准验证（#5026），不是只靠单测

## 4. 对 coding agent 的实际价值

1. **契约文档 = agent 的行为规范**：改 sandbox 时先读 `sandbox/AGENTS.md` + 相关 contract 文档，能直接拿到不变量清单，不需要从测试反推
2. **实验包 = 决策依据**：agent 被问到"为什么 X 不用 Y"时，答案在文档里且带统计证据
3. **测试锚点 = 验证出口**：每条契约都能落到具体测试文件，agent 修改后可立即自证
4. **事故文档 = 陷阱地图**：0019 冲突这类坑被主动写出来，agent 不会再踩

## 5. 残留差距

- 用户侧文档（README、docs site）仍是跟随式更新，入门体验与内部文档的密度差距在拉大（v2.2.0 的 README 从 1,951 行涨到 4,081 行，差距被主动压缩了不少，但仍是先改代码后补文档）
- **迁移测试的绝对缺口在扩大**：v2.1.0 是 28 个 revision 配 14 个 `test_migration_*.py`（缺 14 个），v2.2.0 是 50 个 revision 配 31 个（缺 19 个）。覆盖率数字好看，但每轮新增 revision 里总有几份没有任何迁移测试，靠领域级测试间接覆盖
- 契约文档与 AGENTS.md 之间有内容重叠（如 task continuity 在 docs/ 和 AGENTS.md 双写），两处漂移风险需要人工纪律
- benchmark 结果文件里有大量生成物入库（jsonl/png），仓库噪声对 agent 检索有轻微干扰
