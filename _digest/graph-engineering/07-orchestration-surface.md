---
title: "编排操作面 — 用 DeerFlow 跑工作流的 API 与配方"
description: "面向'今后用 DeerFlow 编排 workflow'的操作手册:Run 控制全字段、durable batch 引擎语义、十条现状组合配方、观测面与边界陷阱,全部证据锚定。"
topics: [orchestration, api, batch, recipes, workflow]
---

# 07 · 编排操作面 — API 全景 + 现状组合配方

> 2026-10-02 深挖成稿。本文回答:**今天拿起 DeerFlow 编排工作流,手上有哪些旋钮、哪些配方能用、边界在哪**。依据:`app/gateway/run_models.py`(RunCreateRequest 逐字段)、`thread_runs.py`/`runs.py`/`subagent_batches.py`/`scheduled_tasks.py` 路由、`subagents/batch_service.py`(逐行)、`runtime/goal.py`、`runtime/AGENTS.md`。

## 0. 一句话

**今天就能编排**:顺序链、独立并行(即时或 durable)、带确定性验收的任务、run 级事务与恢复、定时触发、目标续跑、原语级图级 interrupt/resume、跨线程读授权。**还编排不了**:依赖拓扑、汇聚 Gate、失败重规划——那是 [09](09-task-dag-injection-design.md) 的注入设计要解决的。

## 1. Run 控制 — RunCreateRequest 全字段(编排者的旋钮箱)

`app/gateway/run_models.py::RunCreateRequest`(`extra="forbid"`,HTTP 与内部启动共用):

| 字段 | 编排含义 |
|------|---------|
| `input` | 图输入(`{"messages": [...]}`);`None` + command = 续跑 |
| `command` | **LangGraph Command 透传**——`{"resume": ...}` 即恢复挂起的 interrupt(services.py:1571: `graph_input = Command(resume=command["resume"])`) |
| `checkpoint_id` / `checkpoint` | 从指定检查点续跑(**fork 点**;delta 模式下被 worker 线性化为当前 head 整体替换,见 §5 陷阱) |
| `interrupt_before` / `interrupt_after` | **节点级暂停**,支持 `["*"]` 全节点 → `agent.interrupt_before_nodes`(worker.py:1229) |
| `multitask_strategy` | 同线程并发策略:`reject`(默认)/ `rollback`(回滚在跑的 run)/ `interrupt` |
| `on_disconnect` | SSE 断开行为:`cancel`(默认)/ `continue` |
| `stream_mode` / `stream_subgraphs` | 流模式与子图帧(命名空间帧 `values|<ns>`) |
| `conversation_references` | **跨线程读授权**(≤3 个 thread id/URL,只在本 run 内有效,供 `read_conversation` 工具;SDK 客户端可从 `context.` 提升) |
| `context` | DeerFlow 运行时覆盖:`model_name`、`thinking_enabled`、`is_plan_mode`、`subagent_enabled`、`max_concurrent_subagents`、`max_total_subagents` 等 |
| `assistant_id` | 选择 agent(Custom Agent) |
| 占位拒绝 | `webhook`/`on_completion`/`after_seconds`/`feedback_keys` 均为兼容占位——**完成回调不支持**,编排者必须轮询或持流 |

**端点全景**(编排相关):`POST /threads/{id}/runs`(+`/stream` `/wait`)、`POST .../runs/{run_id}/cancel`、`GET .../join`、`POST .../runs/stream`(挂到已有 run)、`POST .../runs/regenerate|edit-regenerate/prepare`、`GET .../runs/{run_id}/events|workspace-changes`、`GET .../token-usage`;全局 `/runs/stream|wait|messages`;batch:`GET /subagent-batches[/{id}|/{id}/items]` + `POST .../pause|resume|cancel` + `POST .../items/{item_id}/retry` + `GET .../results.jsonl`;scheduled:`CRUD + pause/resume/trigger + preview-cron`;另有 `mcp_tasks.py` 长任务面。

## 2. Durable batch 引擎 — 编排的持久底座(`batch_service.py` 逐行语义)

| 语义 | 机制 |
|------|------|
| 认领 | `claim_items(lease_owner, lease_seconds, limit)` 按可用容量(`max_running - 在跑`)批量认领 |
| 续租 | 每 `lease_seconds/3` 续租;续租失败 → 立刻取消执行 |
| 重试预算 | admission 失败(队列拒绝/超时,发生在模型执行前)→ **重排队不耗尝试**;真实失败/租约过期才耗 `max_attempts` |
| 幂等性 | 提示词注入:`"Durable batch item key: {key}… Keep side effects idempotent and use the item key as the idempotency identity."` |
| 崩溃恢复 | worker 崩溃 → 租约到期 → 另一 worker 认领**同一稳定 item key** 重跑 |
| 取消 | **durable 取消**:cancel_batch 落库,本机执行即刻取消,他机 worker 在续租周期内观察到;HTTP 控制请求可由任一 worker 安全持有 |
| 组装期防护 | 工具装配阻塞(MCP cache)期间被取消/丢租 → 重新校验后才启动,不跑用户已取消的活 |
| 验收 | 完成项跑 acceptance check,**检查期间保持租约**直到 drain;checker 故障是 advisory(不丢结果不触发重试) |
| 配置旋钮 | `max_items_per_batch`、`max_live/running_items`(batch 级覆盖)、`max_attempts`、`lease_seconds`、`poll_interval_seconds`、`max_result_chars` |

## 3. 组合配方(今天就能用,每条含边界)

| # | 模式 | 怎么做 | 能力边界 |
|---|------|--------|---------|
| R1 | **顺序链** | 单子代理内部串行完成(路由政策的正解);或 lead 逐个 `task` | 依赖正确性 = 模型自觉;无机器校验 |
| R2 | **并行 fan-out(即时)** | 一轮多个 `task` 调用:ToolNode 对每个 tool call 并行(Send),`SubagentLimitMiddleware` 限并发/总量(按 run 划界的台账) | 派发的是独立任务;有输出依赖/状态重叠 = 政策硬否决区,靠 prompt 遵守 |
| R3 | **并行 fan-out(durable)** | `batch_task`(items + 可选验收标准)→ §2 引擎;`batch_status` 轮询、pause/resume、单 item retry、JSONL 导出 | item 间无依赖;结果是截断存储 + preview |
| R4 | **验收门** | `task`/`batch_task` 带 `acceptance_criteria`(`file:<path> exists|non-empty`、`file_written:`、`tests_passed:<command>`)→ `acceptance_verdict`(UNVERIFIED fail-closed) | **verdict 无自动消费者**——lead 读到后自己决定;没有 Gate 分支 |
| R5 | **HITL(产品级)** | `ask_clarification` → `Command(goto=END)` + `human_input` artifact;下一轮对话续 | 回合级;非交互上下文(scheduler)自动抑制并指示继续 |
| R6 | **HITL(原语级)** | `interrupt_before: ["model"]`(或 `["*"]`)→ run 挂起 → `command: {resume: ...}` 恢复 | **原语齐备、无产品消费**;自定义客户端可用;resume 重进对话循环而非任务位置 |
| R7 | **run 事务** | `cancel`(带回滚恢复 pre-run 快照);`regenerate`/`edit-regenerate`(带血缘校验的分支重放);`multitask_strategy: rollback` | delta 模式禁 fork:resume 被线性化(§5);full 模式保留分支 |
| R8 | **长程目标** | `set_goal(objective, max_continuations≤8)` → JSON 评估器(`satisfied`/`reason`/`evidence_summary`/`blocker`)自动续跑,双上限(总续跑 + 无进展续跑) | 评估器是模型判定;satisfied=false 且无 blocker 进展 → 停 |
| R9 | **定时** | scheduled-tasks API(cron 预览/CRUD/trigger);occurrence 队列 + lease + 恢复;非交互上下文 | 单实例默认;multi-instance 需共享 PG + 心跳 + db 事件后端 |
| R10 | **跨线程组合** | `conversation_references` 授予本 run 只读 ≤3 个线程 | 仅读;显式授权,run 结束失效 |
| R11 | **状态手术** | `POST /threads/{id}/compact`(压缩);手工 state 更新走 `reserve_checkpoint_write` + 变异图——**middleware 贡献的通道可写**(Overwrite 替换式),回滚/压缩均保留 | 未知通道静默丢弃;必须用有效 schema |

## 4. 观测面(编排者的传感器)

- **run 事件流**:`GET runs/{id}/events`(生命周期 + 进度快照);`GET threads/{id}/messages/page`(seq 有序消息页);
- **子代理步骤**:`list_events(task_id, after_seq)` 前向游标分页(`subagent.start/step/end`,文本与 args 封顶截断);
- **文件改动**:`workspace-changes`(pre/post 快照 diff,change review);
- **用量**:`token-usage`(按线程);信封里的 `subagent_token_usage`;
- **血缘**:`trace_id`(X-Trace-Id 全链)与 `run_id`(服务端盖戳);
- **batch**:items 状态 + verdict + JSONL 导出。

## 5. 边界与陷阱(编排者必读)

1. **delta 模式下 `checkpoint_id` 续跑 ≠ fork**:worker 把它线性化为当前 head 的整体状态替换(#4458)——想"从第 3 步分叉重试"在 delta 模式不存在;full 模式才有真分支。
2. **子代理无独立恢复**:执行状态不进 checkpoint;只有信封 + 台账 + step 事件留存。编排恢复的单位是 run/thread,不是任务。
3. **共享沙箱**:并行 `task`/batch 写同一文件 = 路由政策硬否决的场景;系统不会替你隔离。
4. **verdict 不驱动任何东西**:验收判定只是证据;分支逻辑得自己写(09 §门层)。
5. **完成回调不存在**:占位字段显式拒绝;用 `/wait`、SSE 持流或轮询 events。
6. **预算/状态字段单写者纪律**:并行写无 reducer 通道是 last-value 竞态——注入设计必须遵守(09 §预算层)。

> 配方的缺口(依赖拓扑/Gate/重规划)如何在全部契约内补上 → [09-task-dag-injection-design.md](09-task-dag-injection-design.md);往哪个入口注入 → [08-orchestration-extension-points.md](08-orchestration-extension-points.md)。
