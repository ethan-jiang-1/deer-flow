---
title: "Run Ownership 与 Rollback"
description: "Multi-worker 部署下的运行归属（lease/heartbeat/orphan recovery）、取消语义、rollback 机制、交付回执（delivery receipt）。"
topics: [runtime, ownership, rollback, multi-worker, delivery]
---

# Run Ownership 与 Rollback

> 同步 #4（e5c62cab）新增：worker 重构 + multi-worker run ownership + rollback + 交付回执。

## 为什么需要 ownership

DeerFlow 可以多 worker / 多 pod 部署（`GATEWAY_WORKERS > 1`）。多个进程可能看到同一个 run——谁执行、谁取消、谁在 worker 崩溃后接管？回答这些需要**durable run ownership**。

> **部署硬约束**：`GATEWAY_WORKERS > 1` 时 `run_events.backend` 必须是 `db`（memory/jsonl 是进程内状态，无法跨进程协调）。启动门禁拒绝内存/JSONL 事件存储。

## Lease 与 Heartbeat

每个 run 记录 `lease_expires_at`（最后一次持久确认的归属截止）：

- 专用心跳线程 `_renew_leases()` 周期续租；每次续租被 `lease_expires_at` 界定时长——store 异常在租约有效期内可重试，一旦达到 expiry 就设置 `ownership_lost` fence、raise `abort_event`、取消 run task
- **Fenced worker 停止一切后续写入**（journal/delivery/status/checkpoint/metadata）——peer 的 recovery 路径拥有终态回执
- `grace_seconds` 延迟 peer 回收以容忍时钟偏差，但不是已失去续租能力的 owner 的额外执行时间
- 租约续租独立于 run 执行：`renew()` 返回 `LAPSED`（租约缺失，重新建立）vs `LOST`（被 peer 持有，放弃）——防止 Redis 重启丢 key 后全集群驱逐（与 sandbox ownership 同构）

## 取消语义（`CancelOutcome`）

`cancel()` 返回枚举：

| 值 | 含义 |
|----|------|
| `cancelled` | 本地取消成功 |
| `requested` | 非 owner worker 持久记录了第一个取消动作（owner 仍活着） |
| `taken_over` | 非 owner worker 接管了租约已过期的 run（标记为 `error`） |
| `lease_valid_elsewhere` | legacy/custom store 无 durable 取消原语（保留 409 + Retry-After） |
| `not_active_locally` | heartbeat 关闭（保留旧 409 路径） |
| `not_cancellable` | 已终态 |
| `unknown` | memory/store 都找不到 |

`RunStore.request_cancel()` 和 owner 完成（`finalize_if_not_cancelled()`）是竞争的活动行 CAS——接受的取消不会被后续 success 覆盖。

## 孤儿回收（Orphan Recovery）

- **启动 + 周期性**扫描 stale active 行，必须用 `RunStore.claim_for_takeover()`（**不是** `update_status()`）——最终 claim 原子地重查 status + lease expiry
- 接管后 mark `error` + `stop_reason=orphan_recovered`，然后 Gateway 发布 `END_SENTINEL` 并清理 stream
- 回调经 `RunManager.on_orphans_recovered` 保持 harness→app 解耦

## Rollback 流程

`worker.py::_capture_rollback_point` 在 run 开始前物化完整 pre-run 状态 + 捕获原始 `pending_writes`（经 `aget_tuple`）为不可变 `RollbackPoint`。捕获失败 = 禁用 rollback（fail-closed），绝不恢复部分状态。

**Full checkpoint 模式**：cancel-with-rollback 从 pre-run checkpoint fork（继承非消息 channel）。

**Delta checkpoint 模式**：fork 不安全（cancelled 路径可能已给 pre-run checkpoint 挂 sibling writes），所以 rollback 把每个捕获的 channel **替换到当前 head** 上：
- reducer channel 用 `Overwrite`
- 仅 current-head 的 channel 重置为 schema 默认值（无默认则 `None`）
- 只重挂捕获的 pre-run pending writes
- worker 在 `_capture_rollback_point` 和可选 linear rewrite 之间持有 `_checkpoint_thread_lock`，使 rollback 快照与 graph streaming 原子

**Edit replay**（`metadata.replay_kind="edit"`）在失败/超时/中断时同样恢复 pre-run checkpoint，并发布恢复的 `values` 快照。

## 交付回执（Delivery Receipt）

`RunJournal` 为终态 `run.delivery` 事件记录非空 artifact 更新（每个工具 `Command` 一次）。Slice 1 字段：

```
produced_paths · presented_paths · matched_paths
verification · stage · satisfied
```

- 交付要求从 run 的 **workspace 快照**推导（非客户端请求项）：`/mnt/user-data/outputs` 下每个创建/修改的常规文件都是候选 artifact
- 至少一个候选被 journal 归属到 `present_files` 才满足；缺失匹配 presentation = run error；成功 presentation 但回执不能持久验证也降级为 error
- 内部 process-feedback 文件不算（workspace 扫描器排除 `TOOL_RESULTS_DIRNAME` 和 `BROWSER_FRAMES_DIRNAME`）
- **孤儿恢复**先原子 claim 过期租约，再用同一 singleton 写 backfill 零交付回执——防止 stale 恢复扫描覆盖 live run 的详细回执

## Workspace Changes 集成

`workspace_changes/` 子系统（见 [P3 digest](../../concepts/workspace-changes.md)）：worker 在 run 前/后对 thread 的 `workspace` + `outputs` 目录做快照扫描（`asyncio.to_thread` offload），有变化时写 `workspace_changes` event（category `workspace`）。文本 diff 限大小；二进制/大文件/敏感路径只持久化 metadata。

## Thread 分支与 run 历史归属（同步 #5）

两个新能力落在「thread/run 身份」这条线上，与 ownership 一样都是为了让**跨 worker / 跨事件页 / 跨重启**时归属仍然精确。

### 分支会话区分（`943d148e`，distinguish branched conversations）

`POST /api/threads/{id}/branches`（`gateway/routers/threads.py`）从已完成的 assistant turn 派生新主线程。此前分支与主线在「最近会话」里难以区分；现在：

- **标题序号**：分支继承源线程 display_name 并追加 ` (2)`、` (3)` …（`_default_branch_title` + `_next_branch_title_sequence`，非分支源从 2 起，分支源递增）；显式改名不被覆盖。序号存 metadata `branch_title_sequence`，兄弟间跳过已占用标题避免冲突。
- **分支元数据**（thread_meta）：`deerflow_branch: true` + `branch_parent_thread_id` + `branch_parent_checkpoint_id` + `branch_parent_message_id` + `branch_created_at`，使前端能重建 lineage。
- **前端 lineage**：`frontend/src/core/threads/thread-branch-tree.ts::flattenThreadBranches()` 把加载到的平铺线程页投影成安全的视觉树——只有**已加载的、同 pin 分区**的 parent 才能拥有 child，缺失/畸形/跨 pin/自环/成环的 parent 都保持顶层，局部分页或坏 metadata 不会藏起会话；`recent-chat-list.tsx` 用 `└─`/`├─` 缩进 stem 渲染分支层级与父标题。

### 精确历史归属（`e8410ceb`，preserve exact history attribution）

AI 消息的 `run_id` 归属过去在事件分页边界外会丢。修复围绕 `RunEventStore.find_latest_ai_message_run_ids()`（`runtime/events/store/base.py`）：

- **complete-or-error 契约**：默认实现反向按 1000 行分页走 `list_messages()`，保留首页 high-watermark 经排他 `before_seq` 游标推进，整页无安全推进 `seq` 时**抛错**而非静默漏；JSONL store 覆盖为一次完整 thread-log 读（避免每页重扫每个 run 文件）；memory/db 走有界路径。`normalize_message_ids()` / `match_ai_message_run_id()` 为公共 helper。
- **Gateway 迁移**：`POST /api/threads/{id}/history` 用它把 legacy AI 消息补上 `run_id`（写回 `run_message_ids` metadata 缓存）。穷举 miss 保留 human-boundary fallback；不完整 lookup **移除**未证明的合成 id（宁可不完整，不可确定性错误）。metadata-only write-on-read 缓存存 `run_message_ids` + 所需 `run_durations`——有 duration 不等于证明归属。写前必须拿 `checkpoint_write` reservation，再**重审计** + 批量 reload 所需 run 行才持久化。
- **终局 fence**：worker 保持 durable run 行在最终 duration checkpoint 写之前仍 active，使 peer 迁移无法在 terminalization 期间进入（`runtime/runs/worker.py`）。

---
> **See also:** [01-run-manager.md](01-run-manager.md)（RunManager/RunStore 契约）· [04-journal.md](04-journal.md)（RunJournal）· [concepts/workspace-changes.md](../../concepts/workspace-changes.md)
