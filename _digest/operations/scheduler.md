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

- 同步 #6（431892e1..769589e8）：interval 调度类型（#5291）、任务固定 custom agent（#5288）、cron 下次执行预览（#5381）、run history 按 occurrence status 过滤（#5384）+ 前端分页浏览（#5363）、前端复制任务（#5064）、occurrence 序号迁移 0022 + completion 原子性/一致性（#5035）、`service.py` 每个 occurrence 独立 trace scope（#5119）。
