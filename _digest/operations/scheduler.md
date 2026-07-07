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
  poll_interval_seconds: 5    # 轮询间隔 (1-300)
  lease_seconds: 120          # 租约有效期 (5-3600)
  max_concurrent_runs: 3      # 全局并发上限 (1-32)
  min_once_delay_seconds: 60  # 一次性任务最小延迟 (1-86400)
```

**重启生效**：所有 scheduler 字段都在 `STARTUP_ONLY_FIELDS` 中注册。API 端点（CRUD）不受 `enabled` 影响——关闭时仅轮询停止。

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
once 任务:
  created → enabled → [等待 next_run_at] → running → completed/failed/cancelled

cron 任务:
  created → enabled → running → enabled → running → ... (无限循环)
                    ↕
                  paused
```

启动协调（Gateway lifespan）：
- `mark_stale_active_runs()`：将 `queued`/`running` 的 run 行标记为 `interrupted`
- `cancel_stuck_once_tasks()`：将租约已清除但从未收到完成钩子的 `once` 任务标记为 `cancelled`

## 重叠策略

MVP 仅支持 `skip`：任务已有活跃 run 时跳过本次触发。Cron 任务跳过并进阶 `next_run_at`；once 任务跳过即标记 `failed`。手动触发返回 HTTP 409。

## 调试

| 症状 | 检查 |
|------|------|
| 任务不触发 | `scheduler.enabled: true`？需重启 Gateway |
| 任务不触发 | `status` 是否为 `enabled`（非 `paused`/`completed`） |
| 任务不触发 | `next_run_at <= now` 且 `lease_expires_at` 为空或已过期 |
| 任务卡在 running | 租约过期→下次轮询回收；租约有效→worker 正在执行 |
| 全局不调度 | `count_active_runs() >= max_concurrent_runs` 已满 |

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
| Migration | `persistence/migrations/versions/0003_scheduled_tasks.py` |
| Frontend | `frontend/src/core/scheduled-tasks/cron.ts` |

测试：9 个测试文件覆盖 ORM、repository、claim、调度、服务层、路由、Gateway 生命周期。
