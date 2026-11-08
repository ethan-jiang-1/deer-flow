---
title: "持久化与恢复测试"
description: "租约、对账与唯一活跃约束：两种不杀进程的崩溃模拟习语、run ownership / scheduled-task / MCP 长任务的恢复面盘点、迁移回滚契约与跨后端等价。"
topics: [testing, persistence, recovery]
---

# 持久化与恢复测试

出发点：**进程崩溃是常态而非特例**。唯一活跃约束、租约围栏、死信预算这类语义必须被常规离线测试覆盖，而不是等生产事故来验证。DeerFlow 的恢复测试全部离线、全部进默认 CI（`make test`）。

## 一、持久化面盘点

| 持久化面 | 存储 | 核心不变量 |
|---|---|---|
| LangGraph checkpoint | SQLite/Postgres checkpointer | 压缩（compaction）后旧消息从 checkpoint 消失，历史必须能从 run 事件重建 |
| threads_meta / run store / run event store | SQL | run 事件是**追加式事实**，多 run 排序、分页、崩溃恢复都以它为源 |
| run ownership / lease | `lease_expires_at` + 心跳 | 多 worker 下孤儿 run 的对账（reconcile）与租约接管 |
| scheduled tasks | `queued/launching/running` 状态机 + `uq_scheduled_task_run_active` 唯一活跃约束 | 一次至多一个活跃 occurrence；`queued` 耐重启；lease-fenced `launching` 才可发射 |
| MCP 长任务（mcp_tasks） | lease + TaskSnapshot 状态机 | 5 次投递预算后死信；删除/失配的目标线程立即死信 |

## 二、两种崩溃模拟习语（全程离线，不杀进程）

### 习语 1：丢弃内存态，同一 store 重建 manager（"as if Worker A restarted"）

`backend/tests/test_multi_worker_run_ownership.py:566` `test_heartbeat_disabled_crashed_run_reclaimed_immediately`：run 落库时 `lease_expires_at=NULL`（单 worker 默认、心跳关闭；docstring `:570` 原文 "no heartbeat => no lease"）；"模拟崩溃"的方式是**丢弃 manager A 的本地内存状态，用同一个 store 构造全新 manager B**（`:586` 注释原文 *"(same store) as if Worker A restarted."*），然后断言 reconcile **立即**收回。同文件的纯数据库状态模拟三连：

- `:400` `test_reconciliation_claims_expired_lease_runs` 插入已过期租约的 running 行 → reconcile → 变 error；
- `:429` `test_reconciliation_skips_active_lease_runs` 活租约的 running 行 → reconcile → 保持不动；
- `:457` `test_reconciliation_claims_when_expired_owner_attempts_renewal_after_scan` —— **scan 与 claim 之间租约被续期**的竞态 → 不误收活 peer。

### 习语 2：持久化行直接构造"崩溃后"状态，再调对账

`backend/tests/test_scheduled_task_repository.py:237` `test_lease_aware_recovery_preserves_live_peer_and_reclaims_expired_peer`：不杀任何进程——直接往库里种两个 running occurrence + 两条 durable run，一条租约 +60s（活 peer）、一条 **-60s（死 peer）**；调 `reconcile_active_runs(error="restart", ...)`，断言：只 reconcile 一条；活 peer 保持 running；过期 peer 变 interrupted，其 durable run 变 error 且 `stop_reason="scheduled_task_orphan_recovered"`（`:295`）；且活任务的唯一活跃约束阻止重复排队（`:296`，`ActiveScheduledRunConflict`）。

**解释**：两种习语合起来覆盖了"物理杀进程"所覆盖的同一空间——习语 1 验证"重启后的视图"（新进程读旧库），习语 2 验证"对账算法本身"（给定任意脏状态，收敛到合法状态）。都不需要 fork、kill、sleep，Windows 也能跑。

## 三、恢复面盘点（全部离线，进 backend-unit CI）

### 1. Scheduled tasks（最大的一片）

`test_scheduled_task_repository.py`（**36** 个测试，v2.1.0 为 23）、`test_scheduled_task_claims.py`、`test_scheduled_task_queue.py`、`test_scheduled_task_dispatch_race.py`（发射竞态）、`test_scheduled_task_postgres.py`、`test_scheduler_completion_atomicity.py` / `test_scheduler_completion_consistency.py`（完成原子性）、`test_scheduler_occurrence_ordering.py`、`test_scheduled_occurrence_sequence.py`，加上迁移契约 `test_migration_0007/0015/0022/0023`。`backend/AGENTS.md` 用一整段把状态机语义写成规格（`queued` 耐重启、`launching` 短租约围栏、budget count 与 UPDATE 分离语句必须在 count 前串行化——Postgres advisory lock / SQLite `BEGIN IMMEDIATE`），每一个断言都有对应测试。`uq_scheduled_task_run_active` 部分唯一索引（`backend/tests/test_scheduled_task_service.py:880` 与 `:980` 两处——v2.1.0 页面写的 `:794` 是另一个测试 `test_manual_trigger_with_active_run_returns_conflict_without_launching` 的 docstring 区，跑过一次偏移）是"恢复逻辑写错导致双跑"的数据库层硬失败。

### 2. Run ownership / lease

`test_multi_worker_run_ownership.py`（**104** 个测试，v2.1.0 为 94）、`test_gateway_run_recovery.py`、`test_run_worker_rollback.py` / `test_run_worker_delivery.py`、`test_run_manager.py` / `test_run_repository.py`、`test_migration_0004_run_ownership_dedupe.py`。

### 3. MCP 长任务（lease / 取消围栏 / 幂等 / 死信）

`backend/packages/harness/deerflow/mcp/AGENTS.md:4` 定义协议中立的 `McpTaskDriver` 契约与 `TaskSnapshot` 六状态（`submitted/working/input_required/completed/failed/cancelled`）；通知重试用**与投递失败计数分离的幂等 attempt 计数**、封顶指数退避、5 次失败后死信；严格 existing-thread admission 对删除/失配的目标线程**立即死信**；远端 poll hint 封顶 24 小时。

`backend/tests/test_mcp_task_service.py`（**4847 行、105 个测试**——v2.1.0 页面写的"36 个 async 测试"已过期，2.2 把这一族补到了三倍；桩基齐备，共 9 个：`FakeRepository` / `FailingApplyRepository` / `FailingCreateRepository` / `BlockingCreateRepository` / `DuplicateCreateRepository` / `DriftedThreadCreateRepository` / `FakeDriver` / `HangingDriver` / `BlockingCancelDriver`，集中在 `:38-186`）。典型锚点（行号均为 v2.2.0 实测，v2.1.0 页面的旧值整体偏移了 200–500 行）：

| 行号 | 测试 | 钉住的语义 |
|---|---|---|
| `:206` | `test_submit_persists_remote_handle_before_returning` | 远端 handle 必须先落库再返回（否则崩溃即失联） |
| `:248` | `test_submit_cancels_remote_task_when_persistence_fails` | 落库失败 → 反向补偿取消远端 |
| `:294` | `test_submit_compensates_remote_task_when_thread_incarnation_drifted` | thread incarnation 漂移时也要补偿 |
| `:379` | `test_submit_repeated_cancellation_does_not_interrupt_compensation` | 补偿不被重复取消打断 |
| `:600` | `test_cancel_task_persists_request_without_calling_remote` | 取消持久化但不调远端 |
| `:736` | `test_notification_delivery_waits_for_successful_agent_run` | 通知投递等待成功 run |
| `:937` | `test_reserved_notification_busy_thread_preserves_snapshot` | busy 线程保留快照 |
| `:1048` | `test_permanently_rejected_notification_is_dead_lettered` | 永久拒绝立即死信 |
| `:1304` | `test_notification_retry_budget_dead_letters_before_creating_another_run` | 重试预算耗尽时**先死信再建 run**（顺序也是契约） |
| `:1443` | `test_run_once_caps_remote_poll_hint_to_one_day` | poll hint 封顶一天 |
| `:1514` | `test_run_once_uses_exponential_backoff_and_caps_transient_errors` | 指数退避封顶 |
| `:1607` | `test_persisted_snapshot_errors_are_bounded_on_submit_and_poll` | 快照错误在 submit 与 poll 两侧都有界 |
| `:1800` | `test_run_once_releases_claim_when_driver_is_missing_or_fails` | driver 缺失/失败释放 claim |
| `:1826` | `test_run_once_isolates_unexpected_failure_to_its_claimed_task` | 意外失败隔离到自己的 claim |

**解释（这一族为什么在 2.2 涨了三倍）**：v2.1.0 的 36 个测试基本是"每个状态转移一条"；2.2 的 105 个多出来的部分是**补偿/失败/竞态三类**的组合爆炸——上面 14 条里有 7 条直接测"某一步失败后会怎样"。MCP 远端任务的生命周期里每一步都可能失败，而"失败后留了什么"才是真正决定会不会重复执行的因素。这与同篇 `_repository_race_helpers.py` 的存在是同一个判断。外围 12 个 `test_mcp_task_*` 文件（总计 13 个 `test_mcp_task_*.py`，含 service 本体；另有 50 个 `test_mcp*.py`）覆盖 repository/ordinary driver/e2e/postgres/tool_caller 等。

### 4. Checkpoint / 压缩 / 摘要

`test_summarization_middleware.py`（**64** 个测试，v2.1.0 为 59）、`test_checkpoint_{cache_config,cache_memory,cache_provider,cache_redis,mode,patches,state,lineage,retention_contract}.py`、`test_cached_history_saver{,_integration}.py`。压缩语义（保留近期消息、channel versions 只 bump 受影响通道）全部有契约测试。

## 四、迁移契约与跨后端等价

- **31 个 `backend/tests/test_migration*.py`（v2.1.0 为 14）逐个 revision 断言「已审定的回滚契约」**——每个迁移的 upgrade/downgrade 都是显式契约，不是"up 能跑就行"；
- **未知 revision 路径也被覆盖**：迁移链历史上发生过 id 复用分叉（`0019_thread_incarnations`），恢复程序成文于 `docs/database-forward-revision-recovery.md`——"Current tests remove 0019 from the mocked local revision set to exercise the same unknown-revision path"（该文原话）；`backend/tests/test_persistence_forward_revision_compat.py`（"Forward-compatibility tests for an old Gateway against migration 0019"）钉住启动时对旧形态 **fail-loud 拒绝**而非静默改 schema；
- **真 Postgres 语义**：迁移契约测试在 `DEERFLOW_TEST_POSTGRES_URL` 存在时对真 Postgres 断言、否则 SQLite 兜底；CI 的 `backend-unit-tests.yml` 起 Postgres 17 + Redis 7 service 容器并显式注入 `DEDUPE_TEST_POSTGRES_URL`（workflow 注释明言：没有这个映射 "those tests silently skip"——**防静默降级**也是 CI 设计的一部分，见 `05-speed-isolation.md` §3）；
- **跨后端等价**：`ThreadMetaStore`（`backend/packages/harness/deerflow/persistence/thread_meta/base.py:59`）的搜索语义在 memory/SQLite/PostgreSQL 上必须一致（`backend/tests/test_thread_meta_repo.py`）；
- **替身边界**：ownership store 契约明文拒绝 fake Redis——"there is no fake-redis tier because a fake would not execute the Lua exclusions"（`backend/packages/harness/deerflow/sandbox/AGENTS.md:82`），Redis 层是 `@pytest.mark.integration` + CI 起真服务。**替身不可替换被测语义**（`01-doctrine.md` §5）在持久化层的落地。

## 五、启示

1. **崩溃不需要真崩溃**："丢内存态重建" + "持久化行直接构造脏状态"两种习语，把 SIGKILL 级场景做成毫秒级确定性断言；
2. **竞态要单独成测试**：`:457`（scan-claim 之间续期）这类"窗口期竞态"被显式写成用例，而不是靠压测碰运气——与 `backend/tests/AGENTS.md`"确定性回归与压力/浸泡分层"的纪律呼应；
3. **唯一活跃约束是防重入的最后防线**：`uq_scheduled_task_run_active` 与 `ActiveScheduledRunConflict` 让"恢复逻辑写错导致双跑"变成数据库层的硬失败，不依赖上层代码自觉；
4. **追加式事件日志作为真理源**：run 事件的持久化让"checkpoint 不再持有旧消息"的历史重建成为可能——#3352 的跨栈回归守卫（`03-contract-e2e.md`）正是建立在这个投影上的。
