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

---
> **See also:** [01-run-manager.md](01-run-manager.md)（RunManager/RunStore 契约）· [04-journal.md](04-journal.md)（RunJournal）· [concepts/workspace-changes.md](../../concepts/workspace-changes.md)
