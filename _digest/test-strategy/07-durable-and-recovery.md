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

`backend/tests/test_multi_worker_run_ownership.py:562` `test_heartbeat_disabled_crashed_run_reclaimed_immediately`：run 落库时 `lease_expires_at=NULL`（单 worker 默认、心跳关闭）；"模拟崩溃"的方式是**丢弃 manager A 的本地内存状态，用同一个 store 构造全新 manager B**（`:582` 注释原文 *"as if Worker A restarted"*），然后断言 reconcile **立即**收回。同文件的纯数据库状态模拟三连：

- `:396` 插入已过期租约的 running 行 → reconcile → 变 error；
- `:425` 活租约的 running 行 → reconcile → 保持不动；
- `:453` **scan 与 claim 之间租约被续期**的竞态 → 不误收活 peer。

### 习语 2：持久化行直接构造"崩溃后"状态，再调对账

`backend/tests/test_scheduled_task_repository.py:233` `test_lease_aware_recovery_preserves_live_peer_and_reclaims_expired_peer`：不杀任何进程——直接往库里种两个 running occurrence + 两条 durable run，一条租约 +60s（活 peer）、一条 **-60s（死 peer）**；调 `reconcile_active_runs(error="restart", ...)`，断言：只 reconcile 一条；活 peer 保持 running；过期 peer 变 interrupted，其 durable run 变 error 且 `stop_reason="scheduled_task_orphan_recovered"`（`:291`）；且活任务的唯一活跃约束阻止重复排队（`:292`，`ActiveScheduledRunConflict`）。

**解释**：两种习语合起来覆盖了"物理杀进程"所覆盖的同一空间——习语 1 验证"重启后的视图"（新进程读旧库），习语 2 验证"对账算法本身"（给定任意脏状态，收敛到合法状态）。都不需要 fork、kill、sleep，Windows 也能跑。

## 三、恢复面盘点（全部离线，进 backend-unit CI）

### 1. Scheduled tasks（最大的一片）

`test_scheduled_task_repository.py`（23 个测试）、`test_scheduled_task_claims.py`、`test_scheduled_task_queue.py`、`test_scheduled_task_dispatch_race.py`（发射竞态）、`test_scheduled_task_postgres.py`、`test_scheduler_completion_atomicity.py` / `test_scheduler_completion_consistency.py`（完成原子性）、`test_scheduler_occurrence_ordering.py`、`test_scheduled_occurrence_sequence.py`，加上迁移契约 `test_migration_0007/0015/0022/0023`。`backend/AGENTS.md` 用一整段把状态机语义写成规格（`queued` 耐重启、`launching` 短租约围栏、budget count 与 UPDATE 分离语句必须在 count 前串行化——Postgres advisory lock / SQLite `BEGIN IMMEDIATE`），每一个断言都有对应测试。`uq_scheduled_task_run_active` 部分唯一索引（`backend/tests/test_scheduled_task_service.py:794` docstring）是"恢复逻辑写错导致双跑"的数据库层硬失败。

### 2. Run ownership / lease

`test_multi_worker_run_ownership.py`（94 个测试）、`test_gateway_run_recovery.py`、`test_run_worker_rollback.py` / `test_run_worker_delivery.py`、`test_run_manager.py` / `test_run_repository.py`、`test_migration_0004_run_ownership_dedupe.py`。

### 3. MCP 长任务（lease / 取消围栏 / 幂等 / 死信）

`backend/packages/harness/deerflow/mcp/AGENTS.md:4` 定义协议中立的 `McpTaskDriver` 契约与 `TaskSnapshot` 六状态（`submitted/working/input_required/completed/failed/cancelled`）；通知重试用**与投递失败计数分离的幂等 attempt 计数**、封顶指数退避、5 次失败后死信；严格 existing-thread admission 对删除/失配的目标线程**立即死信**；远端 poll hint 封顶 24 小时。

`backend/tests/test_mcp_task_service.py`（1419 行、36 个 async 测试，桩基齐备：`FakeRepository` / `FailingApplyRepository` / `HangingDriver` / `BlockingCancelDriver`），典型锚点：补偿不被重复取消打断（`:303`）、取消持久化但不调远端（`:519`）、幂等投递等待成功 run（`:620`）、busy 线程以最新事件替换 claim（`:756`）、永久拒绝立即死信（`:823`）、重试预算死信（`:899`）、poll hint 封顶一天（`:996`）、指数退避封顶（`:1067`）、快照错误有界（`:1137`）、driver 缺失/失败释放 claim（`:1329`）、意外失败隔离到自己的 claim（`:1353`）。外围 12 个 `test_mcp_task_*` 文件覆盖 repository/ordinary driver/e2e/postgres/tool_caller 等。

### 4. Checkpoint / 压缩 / 摘要

`test_summarization_middleware.py`（59 个测试）、`test_checkpoint_{cache_config,cache_memory,cache_provider,cache_redis,mode,patches,state,lineage,retention_contract}.py`、`test_cached_history_saver{,_integration}.py`。压缩语义（保留近期消息、channel versions 只 bump 受影响通道）全部有契约测试。

## 四、迁移契约与跨后端等价

- **14 个 `backend/tests/test_migration_*.py` 逐 revision 断言"已审定的回滚契约"**——每个迁移的 upgrade/downgrade 都是显式契约，不是"up 能跑就行"；
- **真 Postgres 语义**：迁移契约测试在 `DEERFLOW_TEST_POSTGRES_URL` 存在时对真 Postgres 断言、否则 SQLite 兜底；CI 的 `backend-unit-tests.yml` 起 Postgres 17 + Redis 7 service 容器并显式注入 `DEDUPE_TEST_POSTGRES_URL`（workflow 注释明言：没有这个映射 "those tests silently skip"——**防静默降级**也是 CI 设计的一部分，见 `05-speed-isolation.md` §3）；
- **跨后端等价**：`ThreadMetaStore`（`backend/packages/harness/deerflow/persistence/thread_meta/base.py:59`）的搜索语义在 memory/SQLite/PostgreSQL 上必须一致（`backend/tests/test_thread_meta_repo.py`）；
- **替身边界**：ownership store 契约明文拒绝 fake Redis——"there is no fake-redis tier because a fake would not execute the Lua exclusions"（`backend/packages/harness/deerflow/sandbox/AGENTS.md:82`），Redis 层是 `@pytest.mark.integration` + CI 起真服务。**替身不可替换被测语义**（`01-doctrine.md` §5）在持久化层的落地。

## 五、启示

1. **崩溃不需要真崩溃**："丢内存态重建" + "持久化行直接构造脏状态"两种习语，把 SIGKILL 级场景做成毫秒级确定性断言；
2. **竞态要单独成测试**：`:453`（scan-claim 之间续期）这类"窗口期竞态"被显式写成用例，而不是靠压测碰运气——与 `backend/tests/AGENTS.md`"确定性回归与压力/浸泡分层"的纪律呼应；
3. **唯一活跃约束是防重入的最后防线**：`uq_scheduled_task_run_active` 与 `ActiveScheduledRunConflict` 让"恢复逻辑写错导致双跑"变成数据库层的硬失败，不依赖上层代码自觉；
4. **追加式事件日志作为真理源**：run 事件的持久化让"checkpoint 不再持有旧消息"的历史重建成为可能——#3352 的跨栈回归守卫（`03-contract-e2e.md`）正是建立在这个投影上的。
