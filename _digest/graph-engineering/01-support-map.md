---
title: "支持度地图 — 12 项三档判定"
description: "以研究层四大支柱 + 议题 09 两分 + 两层自愈为标尺，逐项判定 DeerFlow 的支持档位，附源码锚点。"
topics: [graph, dag, assessment]
---

# 01 · 支持度地图 — 12 项三档判定

> 判定标尺 = 研究层四大支柱（确定性控制面 / 物理沙箱 / 渐进装配 / 动态拓扑）+ 议题 09 的"固定元图 / 数据 DAG"两分 + 两层自愈（L1/L2）。
> 三档含义：✅ 完整支持 / ◐ 部分支持 / ❌ 缺席。逐项都给源码锚点，可回溯。

## 地图

| # | 研究层标尺（能力） | 档位 | 源码事实 | 锚点 |
|---|---|---|---|---|
| 1 | 固定元图（静态编译、确定性控制面） | ✅ 极小形态 | 唯一的图是 `create_agent()` 编译的 model↔tools 循环：**2 个固定节点** + 编译期展开的 middleware 钩子节点。不是 Planner/Dispatcher/Aggregator/Gate 多角色元图 | [_faq_on_digested/07](../../_faq_on_digested/07_graph-nodes/answer.md) 铁律节；`agents/factory.py` |
| 2 | 检查点持久化与恢复 | ✅ | langgraph-checkpoint sqlite/postgres，delta/full 双 channel mode，手工 compaction 与 run admission 共享同一 checkpoint 写边界 | `runtime/checkpoint_state.py`；`agents/factory.py` |
| 3 | 物理沙箱隔离 | ✅ 超配 | Local/Docker/K8s/BoxLite/E2B/Tenki/OpenSandbox 七实现；网络策略、挂载上传预算、取消语义齐备 | `sandbox/`；[concepts/sandbox/](../concepts/sandbox/README.md) |
| 4 | 渐进式工具/技能装配 | ✅ | Skill Registry + deferred discovery + DeferredToolFilter + `skill_context` channel | `skills/`；middleware catalog #25 |
| 5 | L1 局部自愈（节点内微循环） | ✅ | ToolErrorHandling（异常→error ToolMessage→模型自纠）+ LoopDetection（doom-loop 熔断）+ goal continuation（有界续跑轮数，默认 8） | middleware #5/#12；[internals/runtime/goal-continuation.md](../internals/runtime/goal-continuation.md) |
| 6 | **动态任务分解（Task DAG as data）** | ◐ 弱 | 分解真实存在，但以**涌现形式**活在模型上下文里：`task` 工具调用流；`todos` 扁平清单**无依赖边**；`delegations` 只是台账（同 id latest-wins、封顶截断）。**没有**可校验、可切片、可重放的 task_dag 结构 | `tools/builtins/task_tool.py`；`agents/thread_state.py` |
| 7 | Fan-out 并发派发 | ◐ | `task` 工具支持后台执行（SubagentExecutor + registry + 轮询/取消/超时），并发上限 = SubagentLimitMiddleware，批次走 durable batch（batch_task/batch_status/cancel_batch）。**`Send()` 只用于 tools 节点内部并行执行多个 tool call**，不做跨节点拓扑派发 | `task_tool.py`；FAQ07 §3.1 |
| 8 | 工件契约与验收门禁 | ◐ | ThreadState 有 `artifacts` channel（merge_artifacts 去重合并）；子代理边界有 acceptance checks + receipt citations 校验。但无强类型 Failure Envelope、无 Schema 化交付契约 | `thread_state.py`；`subagents/acceptance_checks.py` |
| 9 | Session 外外部状态机 | ◐ run 级 | scheduler 持久队列（queued/launching/running + lease fencing + 崩溃恢复）、MCP durable task、subagent durable batch——它们编排**运行**，不编排任务图；checkpoint 恢复的是对话线程，不是任务拓扑 | backend AGENTS.md scheduler / MCP 节 |
| 10 | HITL 门禁（图级 interrupt/resume） | ◐ 弱 | `ask_clarification` → `jump_to="end"`（靠下一轮对话续），全库**零处**使用图级 `interrupt()`；scheduled task 的暂停/恢复是 occurrence 级，不是图节点级 | FAQ07 场景 C；grep `interrupt(` |
| 11 | **L2 拓扑自愈（改图 / 子图切片 / 重规划预算）** | ❌ | 全库无 replan / 拓扑校验 / 切片操作 / 失败信封。"重规划" = lead agent 读 error ToolMessage 后**在自己的对话上下文里**自发再派任务——不可审计、无预算、无熔断结构 | grep `replan\|dag\|topolog` 仅命中注释 |
| 12 | 黑板状态机（全局共享状态 + 版本快照） | ❌ 有替代物 | 无跨节点黑板；全局状态 = 对话 messages + 少量 channel。隔离靠每子代理独立 checkpoint namespace + 沙箱文件树，不是共享黑板 | `stream_subgraphs` 命名空间（#4399） |

## 源码锚点速查

| 论断 | 位置 |
|---|---|
| 两固定节点 + middleware 钩子节点；Send 仅用于节点内并行 | `_faq_on_digested/07_graph-nodes/answer.md`（铁律节、§3.1） |
| 唯一直接构建/触碰 StateGraph 的两处 | `runtime/checkpoint_state.py`、`agents/factory.py`（`create_agent` 编译） |
| 全库无 dag/planner/拓扑校验/replan | `grep -ri "\bdag\b\|topolog\|replan" packages/harness/deerflow app` → 仅 middleware 注释 |
| 全库无图级 `interrupt()` | `grep -rn "interrupt(" packages/harness/deerflow` → 仅 TUI 取消与 worker finalization |
| 任务派发与并发上限 | `tools/builtins/task_tool.py`、`batch_task_tool.py`、`agents/middlewares/subagent_limit_middleware.py` |
| 扁平 todos / 台账 delegations / artifacts 合并 | `agents/thread_state.py`（`todos`、`merge_delegations`、`merge_artifacts`） |
| 子代理边界验收 | `subagents/acceptance_checks.py`、`agents/middlewares/receipt_verification.py` |
