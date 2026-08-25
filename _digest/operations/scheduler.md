---
title: "Scheduled Tasks 定时任务"
description: "Cron 和一次性定时任务：配置、REST API、lease 分布式锁、执行生命周期、启动协调、调试指南。"
topics: [scheduler, cron, automation, background-tasks]
---

# Scheduled Tasks 定时任务

`ScheduledTaskService` 是一个后台轮询器，按 cron 表达式或一次性时间触发 agent run。通过 Gateway REST API 管理。

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
  min_once_delay_seconds: 60  # 一次性任务最小延迟 (1-86400)
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
```

## 两种执行模式

| 模式 | 说明 |
|------|------|
| `fresh_thread_per_run` | 每次新建线程，无上下文累积。适合周期性摘要、自动化 |
| `reuse_thread` | 同一线程，上下文累积。需要指定 `thread_id`。适合跟进任务 |

Scheduler 启动的 run 自动设置 `non_interactive=True`，移除 `ask_clarification` 工具防止卡住。

## Cron 表达式

使用 `croniter` 库，标准 5 字段（不支持秒）：

| Preset | 表达式 | 说明 |
|--------|--------|------|
| hourly | `M * * * *` | 每小时第 M 分钟 |
| daily | `M H * * *` | 每天 H:M |
| weekly | `M H * * DOW` | 每周 DOW（0=Sun） |
| monthly | `M H DOM * *` | 每月 DOM 日 |

前端提供 preset 构建器（`frontend/src/core/scheduled-tasks/cron.ts`）。

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
| GET | `/api/scheduled-tasks/{id}/runs` | 运行历史（分页） |
| GET | `/api/threads/{id}/scheduled-tasks` | 线程关联任务 |

## 实现文件

| 层 | 文件 |
|----|------|
| Config | `deerflow/config/scheduler_config.py` |
| Schedule math | `deerflow/scheduler/schedules.py` |
| ORM | `deerflow/persistence/scheduled_tasks/` + `scheduled_task_runs/` |
| Service | `app/scheduler/service.py` |
| Router | `app/gateway/routers/scheduled_tasks.py` |
| Migration | `persistence/migrations/versions/0003_scheduled_tasks.py`、`0015_scheduled_task_enqueue.py` |
| Frontend | `frontend/src/core/scheduled-tasks/cron.ts` |

测试：13 个 `test_scheduled_task*` 文件覆盖 ORM、repository、claim、调度、服务层、路由、Gateway 生命周期，其中 `test_scheduled_task_queue.py`（新增）与 `test_migration_0015_scheduled_task_enqueue.py` 专测 busy 入队/队列预算/租约 fence。
