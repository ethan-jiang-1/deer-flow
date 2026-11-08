---



title: "Run Ownership 与 Rollback"
description: 'Multi-worker 部署下的运行归属（lease/heartbeat/orphan recovery）、取消语义、rollback 机制、交付回执（delivery receipt）。'
topics: [runtime, ownership, rollback, multi-worker, delivery]
verified_against: v2.2.0
last_verified: 2026-11-08
---

# Run Ownership 与 Rollback

> 同步 #4（e5c62cab）新增：worker 重构 + multi-worker run ownership + rollback + 交付回执。

## 为什么需要 ownership

DeerFlow 可以多 worker / 多 pod 部署（`GATEWAY_WORKERS > 1`）。多个进程可能看到同一个 run——谁执行、谁取消、谁在 worker 崩溃后接管？回答这些需要**durable run ownership**。

> **部署硬约束**：`GATEWAY_WORKERS > 1` 时 `run_events.backend` 必须是 `db`（memory/jsonl 是进程内状态，无法跨进程协调）。启动门禁拒绝内存/JSONL 事件存储。

## Lease 与 Heartbeat

每个 run 记录 `lease_expires_at`（最后一次持久确认的归属截止）：

- 专用心跳线程 `_renew_leases()` 周期续租（每 `lease_seconds/3`）；每次续租被 `lease_expires_at` 界定时长——store 异常在租约有效期内可重试，一旦达到 expiry 就设置 `ownership_lost` fence、raise `abort_event`、取消 run task
- **Fenced worker 停止一切后续写入**（journal/delivery/status/checkpoint/metadata）——peer 的 recovery 路径拥有终态回执
- `grace_seconds` 延迟 peer 回收以容忍时钟偏差，但不是已失去续租能力的 owner 的额外执行时间
- 租约续租独立于 run 执行：`renew()` 返回 `LAPSED`（租约缺失，重新建立）vs `LOST`（被 peer 持有，放弃）——防止 Redis 重启丢 key 后全集群驱逐（与 sandbox ownership 同构）。注：2.2.0 的 `RunStore.renew_lease()` 只返回 `LeaseRenewal(renewed=bool, cancel_action=...)`，runtime 内部**没有** `LAPSED`/`LOST` 这两个名字（`grep` 0 命中）；上面的语义由上一条"租约已过期即 fence"和下半段"每 run 独立决策"共同实现，"Redis 重启丢 key 全集群驱逐"那部分属于 sandbox ownership，不在 `RunManager` 里

### 🆕 2.2.0：每 run 独立续租决策 + 本地截止守卫

2.1.0 是"一个循环里挨个续租"，一个 run 的慢 Store I/O 会拖住整轮。2.2.0 拆成三步（`01-run-manager.md` 有构件表，这里讲规则）：

1. **续租对象包含"终态未提交"的行**：`_awaits_terminal_commit()` = `scheduled_goal_cleanup_pending or terminal_commit_pending or rollback_finalization_pending`。终态已定但收尾还没提交的行，durable 状态仍是 active，必须继续续租——否则对端会在中间态把 live run 当孤儿抢走。
2. **每个 run 一个 `run-lease-check:{run_id}` 任务**，各自有独立的 `deadline`（= 上次确认的 `lease_expires_at`）。心跳 tick 不 join，所以 A 卡在 Store I/O 时 B 仍能续租；`stop_heartbeat()` / `shutdown(timeout=5.0)` 才做有界 join。
3. **本地 `call_later` 守卫**（`_arm_lease_deadline`，`manager.py:2752`）：心跳 I/O 停了、挂了、或进程正被 shutdown，最后一次确认租约到期仍会 fence 本记录（`"The last confirmed lease expired without a final terminal acknowledgment."`）。**shutdown 不是越过最后确认租约继续执行的授权。**

任何 fence 之前都会先尝试 `_release_confirmed_terminal_barrier(timeout=remaining)`（`manager.py:2728`）：等的是**本地** `_terminal_attempts` 里的 `Future`，不是读行推断——读到 `status=error` 不等于"这次 run 的终态是我提交的"。只有"没有在飞尝试 + 没有最终 ACK + 已过 deadline"才 `_mark_ownership_lost(..., require_active=False)`（`manager.py:2587`）。

**`allow_interrupted=True`**（`RunStore.update_lease` / `renew_lease` 的新关键字）：只允许续租 **interrupted** 行，唯一用途是 owner 还在跑回滚收尾；`success`/`error` 永不可续租，且实现必须保留 owner + 未过期租约谓词（不支持就 fail closed，不得静默放宽状态门）。`_renew_one_lease` 里首次续租被拒时，若 `_rollback_retry_authorized()` 成立（`_rollback_retry_authorized`，`manager.py:2816`；条件为 `rollback_finalization_pending` + 已确认 interrupted proof + 自己是 owner + 无最终 ACK）就**在同一 per-run 决策内重试一次**——这是"原子回滚准入"与"续租"之间的竞态，不是无界重试。

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

🆕 2.2.0 补充两条取消面的规则：

- **取消不授权终态**：本地取消只把 `record.status` 暂存为 `interrupted` 并置 `terminal_status_persisted = (self._store is None)`；真正落地要等 `_persist_status()` 拿到 ACK。因此"取消成功返回 `cancelled`"≠"durable 行已 interrupted"。若 `action="rollback"` 且 task 仍活，`rollback_finalization_pending=True`——中断 ACK 不足以授权一次未完成的回滚，回滚自己的最终 error ACK 才算。
- **fenced cancel**：`request_fenced_cancel(run_id, *, execution_fence, user_id)` 让 runs 之外的执行方（workflow/extension 的 `ExecutionFence`）按 fence 发取消，store 的 `request_cancel` 必须显式接受 `execution_fence` 关键字，否则该入口不可用。`scheduled_goal_cleanup_pending` 时取消先返回 `cancelled`，等 worker 清掉 scheduled goal 再释放 durable 槽位。

## 孤儿回收（Orphan Recovery）

- **启动 + 周期性**扫描 stale active 行，必须用 `RunStore.claim_for_takeover()`（**不是** `update_status()`）——最终 claim 原子地重查 status + lease expiry
- 接管后 mark `error` + `stop_reason=orphan_recovered`，然后 Gateway 发布 `END_SENTINEL` 并清理 stream
- 回调经 `RunManager.on_orphans_recovered` 保持 harness→app 解耦

### 🆕 2.2.0：恢复终态从 claim 授权，不从行反推

`claim_for_takeover()` 原子提交 `status=error` 这件事本身**就是**恢复终态的授权来源。`runtime/events/terminal.py` 把这个结果钉进一次性 `RecoveryTerminalTarget`：

- `RecoveryTerminalPublisher.publish(target)`（`events/terminal.py:174`）只能消费一次（`_RecoveryTargetClaimState.consume()`，二次消费抛 `RecoveryTerminalTargetConsumed`），**不接受从之后读到的 RunRow 推导权威**——行可能已被别的路径改过。
- 发布前先 best-effort 补一条零投递 `run.delivery` receipt（`{"presented": 0, "paths": [], "by_tool": {}}`，`put_if_absent`）；补 receipt 失败只 warning，不影响终态确认。
- 终态确认走 `confirm_terminal_event(..., recovered=True)`：只写一条 `run.terminal` 事件（`content == {"status": ...}`、`metadata = {"protocol_version": 1, "recovered": true}`），**不重放任何 journal 批次**。
- 生命周期守卫 `_RecoveryRunLifecycleGuard`：存贮是 `RunRepository` 时用 `get_in_session()` 在**同一事务**里重查 `run_id` + `thread_id` + `operation_kind == "run"` + `status == "error"`；其他 store 退化为普通 `get()`。guard 失败 → `RunEventLifecycleRejected` → 返回 `CONFLICT`。
- 确认失败（`CONFLICT`/`UNKNOWN`）只 warning：**保留已提交的 RunRow**，不做补偿写。
- 测试钉在 `backend/tests/test_recovery_terminal_pool.py`（`runtime/AGENTS.md:396` 登记；PostgreSQL 接真实库）。

这条线把"孤儿回收"从"改状态 + 发 END"升级成"改状态 → 有凭据的终态证据 → 才发 END"：没有 `run.terminal` 证据的恢复终态是可被巡检发现的不完整状态，而不是静默的等价物。

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

## 🆕 线程操作 reservation 与线程删除清理（sync #7，upstream #5535）

多 worker 下的互斥不止"谁能跑这个 run"，还包括"谁能在同一线程上写 checkpoint / 分支 / 删除"。这条线用**同一张 `runs` 表**里的 durable reservation 行表达：

- `RunStore.create_thread_operation_atomic()` 写入 reservation 行，`runs.operation_kind` 区分 `run` 与内部操作：`checkpoint_write`、`artifact_write`、`artifact_archive`、`branch`、`delete`（新增种类必须走这个入口，而不是自己加锁或写 metadata 标记）。
- **所有 active 种类共享同一条"每线程至多一个 active"的 durable 唯一约束**，所以 `DELETE`、`POST /state`、compaction、branch 与 run admission 天然互斥，跨进程也成立。
- reservation 的释放只由持有者自己的路径负责（`delete_thread_operation()` 用**捕获的 owner**，不是请求时的 ambient 上下文）；live / lease-less reservation **不可中断**，只有带租约且已过期的 reservation 才能被 interrupt/rollback 立即回收。lease 续租发现丢失时会取消持有者任务，并在清理后把租约丢失的 cancellation 翻译成 `ConflictError` → Gateway 返回可重试的 409。
- 租约缺失的行保持 **fail-closed**：store 无法区分"陈旧行"与"另一个关掉 heartbeat 的 worker 里的活写者"，因此一次罕见的删除失败需要靠启动期 reconciliation 收拾；heartbeat-disabled 的多 worker 部署仍不受支持。
- **run 之外的 checkpoint 写入统一走 `services.reserve_checkpoint_write()`**（`app/gateway/services.py:141`）：它把进程内 `goal_thread_lock(thread_id)` 与 durable `checkpoint_write` reservation 组合起来（`reserve_thread_operation(kind=checkpoint_write)`）。2.2.0 实测调用点共 5 处，全在 `app/gateway/routers/threads.py`——`PUT /{thread_id}/goal`（`:1502`，含为缺失 goal 按需创建 checkpoint）、`DELETE /{thread_id}/goal`（`:1523`）、`POST /{thread_id}/compact`（`:1566`，手动压缩）、`POST /{thread_id}/state`（`:1714`，此时 `goal` 通道同时写 `GOAL_OUTCOME_CHANNEL = None` 以丢弃过期 met 记录）、以及 `/history` 的归因回写后台任务（`:1825`）。已有 run 会挡住这些写入，该 reservation 也挡住新的 reject/interrupt/rollback run，跨 worker 成立；冲突/租约丢失翻译成 `ConflictError` → 409。

**`DELETE /api/threads/{id}` 是这套机制的第一个"清理型"使用者**（此前只有写路径）：

| 步骤 | 行为 |
|------|------|
| 1 | 先拿 durable `delete` reservation，整个清理过程持有它 |
| 2 | 删文件系统 thread 数据（legacy 非文件系统安全 ID 跳过路径插值，只删元数据/checkpoint） |
| 3 | 删 checkpoints（best-effort） |
| 4 | `RunStore.delete_by_thread()`（SQL 实现 `RunRepository`，memory 实现 `MemoryRunStore`；这是**可选能力**，不在 `RunStore` 抽象接口里，`threads.py:785` 用 `getattr` 探测、缺失即跳过）：只删 `operation_kind == "run"` 的历史 run 行——**第 1 步的 reservation 行必须活到 `reserve_thread_operation()` 退出**，否则 DELETE 会在请求中途丢掉自己的跨 worker 互斥；批量删故意不 bump change clock |
| 5 | 删 `RunEventStore.delete_by_thread()`：这是**用户可见的会话历史，不是缓存**——不清的话被删线程的 feed 仍能经 `GET /threads/{id}/messages` 读回来 |
| 6 | 删 feedback（`FeedbackRepository.delete_by_thread()`，按 owner）；memory 后端的 `feedback_repo` 为 `None`，走可选访问器 |
| 7 | 删 `threads_meta` 行（SQLite 后端必须，否则 `/threads/search` 仍列出该线程） |
| 8 | 关闭该线程残留的 browser session（best-effort；Playwright 未安装时静默跳过） |

第 3-8 步（checkpoints 及之后）全部 **best-effort**：单项异常只记 debug 日志，不打断整体删除。第 2 步（文件系统）**不是** best-effort——`_delete_thread_data()` 把 `delete_thread_dir()` 的 `ValueError` 映射成 422、`FileNotFoundError` 视为成功、其余异常映射成 500，会直接中止删除（路由只额外捕获 `ConflictError`）。所有者身份在请求开头解析一次（文件系统 bucket、runs/events/feedback、thread_meta 用**同一个** `user_id`，`threads.py:756`），不允许各步骤各自解析作用域。

**边界（重要）**：本清理只删除"已存在的行"，**不负责阻止一个已被准入的写者在线程删除后把状态写回来**——那是 thread incarnation 的独立契约，upstream 在 `threads.py` 的 docstring 里明确把这两件事分开。

> 🆕 2.2.0 更正：`threads_meta.incarnation` 在 v2.2.0 **已有消费者**，但**不在 run 这条线上**。它走的是 `mcp_scope.py` 的 MCP 会话作用域：`mcp_session_scope_key(user_id, thread_id, thread_incarnation)` 在 incarnation 非 NULL 时把键编码成 `"v2:" + JSON tuple`（legacy NULL 保持老式 `user:thread`，滚动升级不撕裂既有会话），并配套 `is_valid_thread_incarnation()` / `mcp_scope_belongs_to_thread()` / `runtime_thread_incarnation(runtime)`；`tools/builtins/{task,batch_task,background_tasks}_tool.py` 与 `subagents/executor.py` 把父上下文里捕获的 incarnation 显式传给子任务。**run admission / 租约 / fence 仍然不读这两列**——2.2.0 新增的 fencing 全部基于 `owner_worker_id` + `lease_expires_at` + `terminal_commit_proof`（`RunManager` 内）与 runs 之外的 `ExecutionFence`。所以"整个 expand-phase 只写不读"这句话在 2.2.0 已不成立，但"run 归属不依赖 incarnation"仍然成立。

---
> **See also:** [01-run-manager.md](01-run-manager.md)（RunManager/RunStore 契约）· [04-journal.md](04-journal.md)（RunJournal）· [concepts/workspace-changes.md](../../concepts/workspace-changes.md)
