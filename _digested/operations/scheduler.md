---
title: "Scheduled Tasks 定时任务"
description: "Cron 和一次性定时任务：配置、REST API、lease 分布式锁、执行生命周期、启动协调、调试指南。"
topics: [scheduler, cron, automation, background-tasks]
---

# Scheduled Tasks 定时任务

`ScheduledTaskService` 是一个后台轮询器，按 cron 表达式、一次性时间或固定间隔（interval）触发 agent run。通过 Gateway REST API 管理。

源码：`app/scheduler/service.py`，`deerflow/scheduler/schedules.py`，`app/gateway/routers/scheduled_tasks.py`

## 配置

```yaml
scheduler:
  enabled: false              # 主开关（默认关闭）
  multi_instance: false       # 多实例 lease 感知恢复（需 Postgres + run_ownership.heartbeat_enabled + run_events.backend=db）
  poll_interval_seconds: 5    # 轮询间隔 (1-300)
  lease_seconds: 120          # 租约有效期 (5-3600)
  max_concurrent_runs: 3      # 全局并发上限 (1-32)，含 manual triggers，经 Postgres advisory lock 共享
  queue_timeout_seconds: 3600 # 排队等待超时 (60-604800)
  min_once_delay_seconds: 60  # 一次性任务最小延迟 (1-86400)；也是 interval every_seconds 的下限 🆕
  recursion_limit: 1000       # 调度 run 的 LangGraph recursion_limit（dispatch 时读取，clamp 到 max_recursion_limit）
```

**重启生效**：除 `recursion_limit` 外，所有 scheduler 字段都在 `STARTUP_ONLY_FIELDS` 中注册。`recursion_limit` 是段内唯一例外——它在每次 dispatch 时经 `_resolve_scheduler_recursion_limit()` 从 `get_app_config()` 读取（`gateway/services.py`），所以改 YAML 后**下一个调度 run 立即生效，无需重启 poller**；超 `max_recursion_limit` 会被 clamp 并记 WARNING，config 加载失败则回退到默认 1000。API 端点（CRUD）不受 `enabled` 影响——关闭时仅轮询停止。

## 快速使用

```bash
# 每天早上 9 点生成日报
curl -X POST /api/scheduled-tasks \
  -H "Content-Type: application/json" \
  -d '{
    "title": "Daily Report",
    "prompt": "Summarize today'\''s activity and generate a report.",
    "schedule_type": "cron",
    "schedule_spec": {"cron": "0 9 * * *"},
    "timezone": "Asia/Shanghai",
    "context_mode": "fresh_thread_per_run"
  }'

# 一次性任务：30 分钟后执行
curl -X POST /api/scheduled-tasks \
  -d '{
    "title": "One-time deploy",
    "prompt": "Deploy v2.3.1 to production",
    "schedule_type": "once",
    "schedule_spec": {"run_at": "2026-07-07T18:30:00+08:00"},
    "timezone": "Asia/Shanghai"
  }'

# 🆕 固定间隔：每 15 分钟一次（interval 类型）
curl -X POST /api/scheduled-tasks \
  -d '{
    "title": "Queue depth check",
    "prompt": "Check the ingestion queue depth and alert if above threshold.",
    "schedule_type": "interval",
    "schedule_spec": {"every_seconds": 900},
    "assistant_id": "ops-agent"
  }'
```

## 三种调度类型 🆕

`schedule_type` 除 `once` / `cron` 外新增第三种 **`interval`**（#5291）：

| 类型 | schedule_spec | 触发语义 |
|------|---------------|---------|
| `once` | `{run_at}` | 单次，到期后任务终态 |
| `cron` | `{cron}` | wall-clock：按 croniter 在 timezone 内算下一个本地时刻 |
| `interval` 🆕 | `{every_seconds}` | 相对上次 dispatch 的 UTC now+N 秒，**无 missed-beat 补跑** |

interval 边界：`every_seconds` 必须是正整数，下限是 `min_once_delay_seconds`（默认 60s，即它同时是 interval 的最小间隔），上限 30 天（`MAX_INTERVAL_SECONDS`）。PATCH 时未变动的 interval spec 不会重置 `next_run_at`（含仅改 timezone 的 PATCH）；前端表单用秒单位避免非整分钟间隔被改写。

## 两种执行模式

| 模式 | 说明 |
|------|------|
| `fresh_thread_per_run` | 每次新建线程，无上下文累积。适合周期性摘要、自动化 |
| `reuse_thread` | 同一线程，上下文累积。需要指定 `thread_id`。适合跟进任务 |

Scheduler 启动的 run 自动设置 `non_interactive=True`，移除 `ask_clarification` 工具防止卡住。

## 固定 custom agent 🆕

创建/更新任务可传可选 `assistant_id`（#5288），默认 `lead_agent`。自定义名字会归一化（字母/数字/连字符，`lead_agent` 大小写不敏感）并要求**该用户名下已存在**同名 custom agent，否则 422。workspace 表单暴露同一选择，**duplicate（复制任务）会一并复制它**。调度 run 因此可以长期跑一个专职 agent 而不是默认 lead agent。

## Cron 表达式

使用 `croniter` 库，标准 5 字段（不支持秒）：

| Preset | 表达式 | 说明 |
|--------|--------|------|
| hourly | `M * * * *` | 每小时第 M 分钟 |
| daily | `M H * * *` | 每天 H:M |
| weekly | `M H * * DOW` | 每周 DOW（0=Sun） |
| monthly | `M H DOM * *` | 每月 DOM 日 |

前端提供 preset 构建器（`frontend/src/core/scheduled-tasks/cron.ts`）。

**🆕 下次执行预览**（#5381）：`POST /api/scheduled-tasks/preview-cron` 接收 `{cron, timezone, count(1-10,默认5), start_at?}`，复用与调度完全相同的 `compute_next_run_at` 语义（先 `normalize_cron_expression`）迭代算出未来 N 个时刻，返回每个的 UTC `run_at` + 本地 `local_time`，不创建也不触发任何任务。需要 `threads:read` 权限且登录；无法产生未来时刻（含溢出）返回 422。前端表单用它即时预览 cadence。

## 租约机制

使用 `SELECT ... FOR UPDATE SKIP LOCKED` 实现轻量分布式锁：

- 每次 claim 设置 `lease_owner={hostname}:{uuid}` + `lease_expires_at=now+lease_seconds`
- 启动后释放租约（设为 NULL）
- 进程崩溃恢复：过期租约在下次轮询时被回收
- 多实例安全：`SKIP LOCKED` 确保同一行不被两个 worker 同时 claim

## 生命周期

```
调度 occurrence（每个任务最多一个非终态）:
  claim_due_tasks → create(queued) → claim_queued_run(launching) → launch → running → success/failed/interrupted

once 任务:
  created → enabled → [等待 next_run_at] → queued → launching → running → completed/failed/cancelled

cron 任务:
  created → enabled → queued → launching → running → enabled → ... (无限循环)
                    ↕
                  paused
```

启动协调（Gateway lifespan）：
- `mark_stale_active_runs()`：单实例模式下将 `queued`/`running` 的 run 行标记为 `interrupted`，并 `cancel_stuck_once_tasks()` 清理停在 `running` 但从未收到完成钩子的 `once` 任务
- `multi_instance: true` 时改用 `_reconcile_active_state()`：按租约宽限（`run_ownership.grace_seconds`）回收过期 launch claim、原子接管过期 run lease、fence 掉 stale launch 写入，不盲目打断其它实例仍活跃的 run

## 重叠策略（busy 入队）

任务已有活跃 run 时**不再跳过**，而是把本次触发持久化为 `queued` 队列行（`645ca08f`）：

- 每个任务最多一个非终态 occurrence（`queued`/`launching`/`running`），由唯一索引 `uq_scheduled_task_run_active` 保证。
- `queued` 持久化、跨重启存活；`launching` 是短租约 fence 的 claim，是唯一可调用正常 Gateway launch 路径的状态；`running` 关联 durable run。每次 occurrence 还携带稳定 run-admission 幂等 key，恢复的 launch 重试复用同一个 durable run。
- 重复触发 coalesce 到同一个活跃行；同线程 FIFO：更早的 `queued`/`launching`/`running` 行都算 blocker。
- `scheduler.queue_timeout_seconds`（默认 3600s）bound 持久等待：超时把 occurrence 标 `failed` 并进阶 `next_run_at`，防止立刻无限 requeue。
- `reuse_thread` 触发 `ConflictError` 时把 `launching` 移回 `queued`；非冲突 launch 错误成为终态 `failed`。
- 等待行**不占用** `max_concurrent_runs`；只有原子队列 claim（`claim_queued_run`）才执行全局预算。
- 手动触发：失败不消耗任务的 scheduled future（`once` 任务 `run_at` 还在未来时不会被翻成 `failed`）；pause 可原子取消已 `queued` 行，但手动触发在 pause 下仍可排队运行。

## 全局并发预算

`max_concurrent_runs` 是**全局共享**上限，覆盖 `launching`/`running` 行（`1dd6ba1a` + `645ca08f`）：

- admission 与执行容量分离：到期 occurrence 即使所有执行槽都忙也会先持久化，`claim_queued_run()` 在数据库锁下应用全局预算（Postgres 用 advisory lock 使多实例共享同一 cap）。
- **manual triggers 同样受限**：手动触发走同一 admission + claim 路径，预算满时返回 `outcome="queued"`（HTTP 200 `triggered:true`），run 排队而非立即启动——不再能绕过全局上限。

## Occurrence 序号与 completion 原子性 🆕

同步 #6（`cd0e74ed`，#5035）为调度账本补上了一致性基建：

- **migration `0022_scheduled_occurrence_seq`**：`scheduled_tasks.last_occurrence_seq`（server_default 0）+ `scheduled_task_runs.occurrence_seq`（可空，历史行保留 NULL——调用方时钟无法重建 admission 顺序或证明历史 launch 是否计数）+ `launch_accounted` 标志，`(task_id, occurrence_seq)` 唯一索引给出持久、单调的 per-task occurrence 顺序，幂等 launch 记账不依赖时钟。
- **completion 原子化**：`handle_run_completion` 不再"先 update run、再读 task、再 update task"三步走，改为单次 `task_repo.complete_run(task_run_id, run_id, status, ...)`——run 终态与父任务推进（once: success→completed / interrupted→cancelled / failed→failed、清 last_error、increment_run_count）在同一事务提交，消除"run 已成功但父任务停在旧状态"的中间态。
- **重启对账读已提交结果**：`cancel_stuck_once_tasks` 与多实例 `reconcile_stuck_once_tasks` 不再盲目把卡住的 once 任务翻成 `cancelled`，而是在父任务行锁下（`populate_existing`）重读最新 run 行，按已提交终态映射父任务（`_finalise_once_task_from_run()`，单实例/多实例共用一份映射）；活跃 occurrence（queued/launching/running）不动。
- **每个 occurrence 独立 trace scope**：poller 是非 HTTP 入口，没有 TraceMiddleware——`_launch_queued_occurrence` 外包一层 `ensure_trace_context()`（#5119），每个 occurrence 有自己的 trace id 而不是共享整个 poll cycle；手动触发在 Gateway 请求内，保留请求的 trace。
- 对应测试：`test_scheduler_completion_atomicity.py`、`test_scheduler_completion_consistency.py`（947 行）、`test_scheduled_occurrence_sequence.py`、`test_migration_0022_scheduled_occurrence_seq.py`。

## 仓储层契约（投影 / 异常 / 关键 API）

服务层（`app/scheduler/service.py`）与路由只依赖两个仓储的返回字典和领域异常，SQL 细节不向上泄漏。上文的队列/租约/预算语义是**行为**层；这一节记录**仓储 API 与异常**这一层。

### 父投影：`projection.py`

`deerflow/persistence/scheduled_task_runs/projection.py` 两个纯函数，**必须在持有父任务行锁的同一事务内调用**，自身不 commit（`projection.py:1` docstring）：

| 函数 | 精确语义 | 谁调用 |
|------|----------|--------|
| `can_project(task, occurrence)`（`projection.py:14`） | occurrence 是否有资格写父任务的"当前投影"（`last_run_at`/`last_run_id`/`last_thread_id`/`next_run_at`/`status`/`last_error`）。`occurrence_seq is None` → 仅当 `task.last_occurrence_seq == 0` 返回 True：**未序号化的历史行只在任务完全没有序号化历史时才有投影权**（调用方时钟无法排序）；有 `occurrence_seq` → 要求 `occurrence_seq == task.last_occurrence_seq`，即只有该任务最新一次 admission 能投影。 | `scheduled_tasks/sql.py:379`（`release_queued_admission_lease`）、`:438`（`update_after_launch`）、`:490`（`complete_run`）、`:693`（`cancel_stuck_once_tasks`）、`:762`（`reconcile_stuck_once_tasks`）；`scheduled_task_runs/sql.py:112`（`_associate_task_with_run`）、`:445`（`expire_queued_runs`）、`:498`（`fail_launching_run`） |
| `account_launch(task, occurrence, run_id)`（`projection.py:21`） | launch 记账，返回是否真的 `run_count += 1`。**记账与投影资格解耦**：`can_project` 为 False 的 stale occurrence 仍会记账（`scheduled_tasks/sql.py:434-440` 先记账、后判投影）。`launch_accounted is True` → 返回 False 不重复计数；`launch_accounted is None`（migration 0022 前的历史行）走**一次性 legacy 修复**：若 `task.last_run_id == run_id`，只把标志置 True 而**不**计数（旧的 `last_run_id` 推断已计过），否则计数；随后 `flag_modified(task, "updated_at")` **只标记脏、不改时间戳值**——stale occurrence 可以改计数，但不能改当前投影的时间戳。 | `scheduled_task_runs/sql.py:111`（`_associate_task_with_run`）、`scheduled_tasks/sql.py:436`（`update_after_launch`）、`:489`（`complete_run`） |

新 occurrence 一律以 `launch_accounted=False` 落库（`scheduled_task_runs/sql.py:169`），只有 migration 0022 迁移过来的历史行是 NULL。

### 领域异常与翻译

| 异常 | 定义 | 抛出条件 | 调用方如何翻译 |
|------|------|----------|----------------|
| `ActiveScheduledRunConflict(task_id)` | `scheduled_task_runs/sql.py:36` | `ScheduledTaskRunRepository.create()` 中，**仅当 `coordinate_with_task=True`**：(a) 持有父行锁后主动查询发现该任务已有 `queued`/`launching`/`running` occurrence（`:191-201`，先于唯一索引报错的协调检查）；(b) INSERT commit 抛 `IntegrityError` 回滚后**复查**，只有"本次 status 属 active **且**任务确有 active 行"才翻译成它（`:219-228`），否则原样 re-raise——主键/序号冲突不等于活跃槽冲突。唯一索引 `uq_scheduled_task_run_active` 是 DB 兜底，直接调仓储的 legacy 交错得到同一异常。 | `service.py:178` 重读 `get_active_run()`；scheduled 触发额外 `_release_admission_lease()`（`release_dispatch_lease(status="enabled")`）；重读仍无活跃行 → `_active_run_conflict_result`（`outcome="conflict"`）→ 路由 **409**；有活跃行 → `_existing_active_result`：`queued` → `outcome="queued"`（HTTP 200 `triggered:true`，run 入队），`launching`/`running` → 409（`service.py:443-466`、`routers/scheduled_tasks.py:451-457`） |
| `ScheduledTaskAdmissionRejected(task_id, reason=...)` | `scheduled_task_runs/sql.py:50` | 同样要求 `coordinate_with_task=True`，在父行锁下校验调用方拿到的任务快照：`reason="not_found"`——任务行不存在，或 `expected_task_user_id` 不匹配（`:177-179`）；`reason="stale"`——`expected_task_lease_owner` 已给且 `task.lease_owner` 不符（`:180-183`），或 `expected_task_status` 不符（`:185-187`），或 `coerce_iso(task.updated_at)` 与 `expected_task_updated_at` 不一致（`:188-190`）。手动触发传 status/updated_at 快照，scheduled 触发传 `lease_owner`（`service.py:172-176`）。 | `service.py:185`：`not_found` → `outcome="not_found"` → 路由 **404**；其余（stale）→ `outcome="conflict"` → **409**「scheduled task changed before trigger admission」（`service.py:186-200`） |
| `ActiveScheduledTaskMutationConflict(status)` | `scheduled_tasks/sql.py:23` | `ScheduledTaskRepository.update(..., require_mutable=True)`（`:244`）在父行锁下：`task.status == "running"`（`:257-259`）或任一 active occurrence 存在（`:260-270`）时抛出。 | 路由直接捕获并返回 409，detail 由 `_active_occurrence_conflict_detail(status)` 生成（`routers/scheduled_tasks.py:40-44`、`:368`、`:428`）——`queued` 时额外提示"可 pause 取消排队中的 occurrence" |

`create()` 还有两处非异常行为：只要父任务存在，就在同一事务里用 `UPDATE ... RETURNING last_occurrence_seq+1` **分配 occurrence 序号**（`:202-212`，故意不推进 `updated_at`）；`release_task_lease_status` 只在协调成功时把父任务从 `running` 释放（`:214-218`）。

### `ScheduledTaskRepository` 关键方法

| 方法 | file:line | 契约要点 |
|------|-----------|----------|
| `_lock_task` | `scheduled_tasks/sql.py:82` | 父行锁。SQLite 忽略 `FOR UPDATE`，先执行 `UPDATE ... SET updated_at = updated_at` 拿数据库写锁，再 `session.get(..., with_for_update=True)`；admission / mutation / pause / delete 共用这一个序列化点 |
| `claim_due_tasks` | `:288` | 原子 claim 到期任务：FIFO（`next_run_at, id` 升序）+ `with_for_update(skip_locked=True)`；排除**任何**有 active occurrence 的任务；`status="running"` 且租约过期的分支用于回收"claim 后进程死亡"的任务；成功后写 `lease_owner`/`lease_expires_at`/`status="running"`。`limit <= 0` 直接返回空 |
| `release_dispatch_lease` | `:344` | owner-fenced 释放短租约（`expected_lease_owner` 不符则 rollback + False），设父状态并清租约 |
| `release_queued_admission_lease` | `:366` | 恢复"queue 行已插入但父租约未释放"的崩溃窗口；要求父任务 `running` 且有 `lease_owner`，且存在一个 `queued` 行**满足 `can_project`** |
| `update_after_launch` | `:389` | owner-fenced；校验 occurrence 属于该任务且 `occurrence.run_id in (None, last_run_id)`，否则 fencing 掉（WARNING + False）；有 occurrence 时调 `account_launch` 并抑制无 occurrence 回退路径的 `run_count` 自增；`can_project` 为假时**提前 commit 返回 True**（记账已生效）；`protect_terminal` 防止快完成回调被 launch 写覆盖 |
| `complete_run` | `:462` | **completion 原子化的唯一入口**：status 必须属 `TERMINAL_RUN_STATUSES` 否则 `ValueError`；occurrence 不存在/不属于该任务/`run_id` 不匹配/父任务 owner 不符 → rollback + False；同一事务内写 occurrence 终态 + `account_launch` + `can_project` 决定父任务推进（`once` 用 `ONCE_TASK_STATUS_BY_RUN_STATUS`） |
| `claim_dispatch_lease` | `:512` | 手动触发的短 pre-launch 预留；`skip_locked`，只接受租约为空或已过期的行，不校验状态 |
| `pause_with_queue_cancellation` / `delete_with_queue_cancellation` | `:157` / `:202` | 原子取消 `queued` occurrence 并 pause/delete；返回 `"not_found"` / `"executing"`（`launching`/`running`，拒绝操作）/ `"paused"` / `"deleted"` |
| `cancel_stuck_once_tasks` / `reconcile_stuck_once_tasks` | `:647` / `:702` | 结果感知的 once 恢复：`_fetch_latest_run`（`:557`，有序号行则按 `occurrence_seq` 降序、否则 legacy 时钟排序）+ `_has_active_occurrence`（`:590`）+ `can_project` 三重门；`_finalise_once_task_from_run`（`:608`）只做 success→completed / failed→failed / interrupted→cancelled / skipped→cancelled 映射 |
| `_coerce_datetime` | `:39` | 仓储边界把序列化时间戳（str，含 `Z` 后缀）还原为 UTC aware datetime 后再绑定 `DateTime` 字段；非法字符串抛 `ValueError`，其它类型抛 `TypeError`（`AGENTS.md` 的 "Repository boundaries coerce serialized timestamps" 即此） |

### `ScheduledTaskRunRepository` 的预算与队列原语

| 方法 | file:line | 契约要点 |
|------|-----------|----------|
| `EXECUTING_RUN_STATUSES` / `count_active_runs` | `scheduled_task_runs/sql.py:24` / `:248` | 预算只统计 `launching` + `running`；**等待中的 `queued` 行不占槽**（与上文"等待行不占用 max_concurrent_runs"一致） |
| `claim_queued_run` | `:304` | 预算与状态迁移在同一事务：Postgres 先取 `pg_advisory_xact_lock(4694001)`（`:25`、`:317-320`）使多实例共享同一 cap；SQLite 用 `BEGIN IMMEDIATE` 先占写锁（`:331`，注释解释 deferred 事务会在 UPDATE 才占写锁、导致各 claimer 读到同一旧计数而集体超卖）。超预算或行不可认领（非 `queued`、或同线程有更早的 active 行）→ rollback + 返回 **None**（不抛异常）；成功则 `status="launching"`、写租约、`attempt_count += 1` |
| `list_queued_runs` | `:255` | 队列 drain 视图：排除"同线程有更早 active 行"的 queued 行（同线程 FIFO blocker）；排序 `attempt_count` 升序 → `created_at` → `id`，避免永久繁忙的线程独占有限 drain 批次。服务层 `limit=max(16, max_concurrent_runs*4)`（`service.py:484`） |
| `requeue_claimed_run` | `:371` | `launching` + 同 owner → 退回 `queued` 并清租约、记 error（reuse_thread 的 `ConflictError` 走这里，`service.py:315-321`）；owner 不符则不动 |
| `renew`/`expire`/`fail`/`recover` 族 | `:396` `expire_queued_runs`、`:474` `fail_launching_run`、`:523` `reconcile_launched_run`、`:571` `recover_expired_launch_claims`、`:625` `update_status`、`:688` `mark_stale_active_runs`、`:738` `reconcile_active_runs` | 一律**父任务先锁**（`_lock_task` 或 `with_for_update`），occurrence 后锁；`update_status(protect_terminal=...)` 在终态行上只回填 `run_id`/`started_at` 这类"完成写入不可能知道"的字段，owner 不匹配但 `run_id` 相同的 stale launcher 仍被允许回填 |

## 调试

| 症状 | 检查 |
|------|------|
| 任务不触发 | `scheduler.enabled: true`？需重启 Gateway |
| 任务不触发 | `status` 是否为 `enabled`（非 `paused`/`completed`） |
| 任务不触发 | `next_run_at <= now` 且 `lease_expires_at` 为空或已过期 |
| 任务卡在 running | 租约过期→下次轮询回收；租约有效→worker 正在执行 |
| 全局不调度 | `count_active_runs() >= max_concurrent_runs` 已满（多实例下经 advisory lock 共享同一 cap） |
| 任务卡在 queued | 预算已满在等槽；或 `queue_timeout_seconds` 内无槽→超时标 `failed` |
| 多实例误判 stale | 确认 `multi_instance: true` 且满足 Postgres + heartbeat + db 事件存储前置条件，否则启动拒绝 |

## API 端点

| 方法 | 路径 | 说明 |
|------|------|------|
| GET | `/api/scheduled-tasks` | 列出用户任务 |
| POST | `/api/scheduled-tasks` | 创建任务 |
| GET | `/api/scheduled-tasks/{id}` | 获取任务 |
| PATCH | `/api/scheduled-tasks/{id}` | 更新任务（可 re-arm 终态 once 任务） |
| POST | `/api/scheduled-tasks/{id}/pause` | 暂停 |
| POST | `/api/scheduled-tasks/{id}/resume` | 恢复 |
| POST | `/api/scheduled-tasks/{id}/trigger` | 手动触发 |
| DELETE | `/api/scheduled-tasks/{id}` | 删除 |
| GET | `/api/scheduled-tasks/{id}/runs` | 运行历史（分页 `limit`(1-200,默认50)/`offset`；🆕 `status` 按 occurrence 状态过滤，#5384） |
| POST | `/api/scheduled-tasks/preview-cron` 🆕 | 预览 cron 未来 N 个执行时刻 |
| GET | `/api/threads/{id}/scheduled-tasks` | 线程关联任务 |

## 实现文件

| 层 | 文件 |
|----|------|
| Config | `deerflow/config/scheduler_config.py` |
| Schedule math | `deerflow/scheduler/schedules.py` |
| ORM | `deerflow/persistence/scheduled_tasks/` + `scheduled_task_runs/` |
| Service | `app/scheduler/service.py` |
| Router | `app/gateway/routers/scheduled_tasks.py` |
| Migration | `persistence/migrations/versions/0003_scheduled_tasks.py`、`0015_scheduled_task_enqueue.py`、`0022_scheduled_occurrence_seq.py` 🆕 |
| Frontend | `frontend/src/core/scheduled-tasks/cron.ts`、`frontend/src/core/scheduled-tasks/run-history.ts` 🆕（分页 run history hook）、duplicate 表单（#5064）🆕 |

测试：16+ 个 `test_scheduled_task*` / `test_scheduled_*` 文件覆盖 ORM、repository、claim、调度、服务层、路由、Gateway 生命周期。busy 入队/队列预算/租约 fence 由 `test_scheduled_task_queue.py` 与 `test_migration_0015_scheduled_task_enqueue.py` 专测；🆕 `test_scheduler_completion_atomicity.py` + `test_scheduler_completion_consistency.py`（completion 原子性/一致性）、`test_scheduled_occurrence_sequence.py` + `test_migration_0022_scheduled_occurrence_seq.py`（occurrence 序号）、`test_scheduled_task_cron_preview.py`（cron 预览）、`test_scheduled_task_run_status_filter.py`（状态过滤）。前端复制任务（#5064）把现有任务（含 pinned `assistant_id`、interval spec）填回创建表单作为草稿，由用户确认后才创建。

## 变更记录

- 文档补充（源码消化，非 upstream 变更）：新增「仓储层契约（投影 / 异常 / 关键 API）」小节——`projection.py` 的 `can_project`/`account_launch` 精确语义与全部调用点、`ActiveScheduledRunConflict`/`ScheduledTaskAdmissionRejected`/`ActiveScheduledTaskMutationConflict` 的抛出条件与服务层/路由翻译、`ScheduledTaskRepository` 与 `ScheduledTaskRunRepository` 关键方法契约（原子 claim、advisory-lock 预算、queue drain 排序、owner fence）。
- 同步 #6（431892e1..769589e8）：interval 调度类型（#5291）、任务固定 custom agent（#5288）、cron 下次执行预览（#5381）、run history 按 occurrence status 过滤（#5384）+ 前端分页浏览（#5363）、前端复制任务（#5064）、occurrence 序号迁移 0022 + completion 原子性/一致性（#5035）、`service.py` 每个 occurrence 独立 trace scope（#5119）。
