---
title: "Graph Engineering 支持度判定 — DeerFlow 的能力边界"
description: "以 graph_engineering 研究层框架为标尺，逐项判定 DeerFlow 对图工程（固定元图 / 动态任务 DAG / 两层自愈 / Session 外状态机）的支持档位。"
topics: [graph, dag, langgraph, orchestration, subagent]
---

# Graph Engineering 支持度判定 — DeerFlow 的能力边界在哪

> **2026-10-01 判定**。依据：源码（`ethan` 分支 / v2.1.0-rc0 口径）+ `_faq_on_digested/07-09` + 研究层
> [`graph_engineering`](/Users/bowhead/ai_dev_sdlc_aidc/02_research/01_agent_engineering/graph_engineering/README.md) 的框架。
> 回答一个具体问题：**DeerFlow 对 graph engineering 支持到哪儿？** 不做理想化叙事，按实际能力钉边界——支持多大多写多大，缺席就写缺席。

## 0. 一句话结论

DeerFlow 是 graph engineering 的**最小完整实现**：把"固定元图"做实（而且是两节点的极小元图），把全部"动态"下放到**工具层的涌现式子代理派发**。**没有任何 dynamic workflow DAG**——没有任务 DAG 数据结构、没有拓扑校验、没有 L2 改图。这是架构取舍，不是能力缺失（§3）。

## 1. 支持度地图

三档：✅ 完整支持 / ◐ 部分支持 / ❌ 缺席。标尺 = 研究层四大支柱 + 议题 09 的"固定元图 / 数据 DAG"两分 + 两层自愈。

| # | 研究层标尺（能力） | 档位 | 源码事实 | 锚点 |
|---|---|---|---|---|
| 1 | 固定元图（静态编译、确定性控制面） | ✅ 极小形态 | 唯一的图是 `create_agent()` 编译的 model↔tools 循环：**2 个固定节点** + 编译期展开的 middleware 钩子节点。不是 Planner/Dispatcher/Aggregator/Gate 多角色元图 | [_faq_on_digested/07](../../_faq_on_digested/07_graph-nodes/answer.md) 铁律节；`agents/factory.py` |
| 2 | 检查点持久化与恢复 | ✅ | langgraph-checkpoint sqlite/postgres，delta/full 双 channel mode，手工 compaction 与 run admission 共享同一 checkpoint 写边界 | `runtime/checkpoint_state.py`；`agents/factory.py` |
| 3 | 物理沙箱隔离 | ✅ 超配 | Local/Docker/K8s/BoxLite/E2B/Tenki/OpenSandbox 七实现；网络策略、挂载上传预算、取消语义齐备 | `sandbox/`；[concepts/sandbox/](sandbox/README.md) |
| 4 | 渐进式工具/技能装配 | ✅ | Skill Registry + deferred discovery + DeferredToolFilter + `skill_context` channel | `skills/`；middleware catalog #25 |
| 5 | L1 局部自愈（节点内微循环） | ✅ | ToolErrorHandling（异常→error ToolMessage→模型自纠）+ LoopDetection（doom-loop 熔断）+ goal continuation（有界续跑轮数，默认 8） | middleware #5/#12；[internals/runtime/goal-continuation.md](../internals/runtime/goal-continuation.md) |
| 6 | **动态任务分解（Task DAG as data）** | ◐ 弱 | 分解真实存在，但以**涌现形式**活在模型上下文里：`task` 工具调用流；`todos` 扁平清单**无依赖边**；`delegations` 只是台账（同 id latest-wins、封顶截断）。**没有**可校验、可切片、可重放的 task_dag 结构 | `tools/builtins/task_tool.py`；`agents/thread_state.py` |
| 7 | Fan-out 并发派发 | ◐ | `task` 工具支持后台执行（SubagentExecutor + registry + 轮询/取消/超时），并发上限 = SubagentLimitMiddleware，批次走 durable batch（batch_task/batch_status/cancel_batch）。**`Send()` 只用于 tools 节点内部并行执行多个 tool call**，不做跨节点拓扑派发 | `task_tool.py`；FAQ07 §3.1 |
| 8 | 工件契约与验收门禁 | ◐ | ThreadState 有 `artifacts` channel（merge_artifacts 去重合并）；子代理边界有 acceptance checks + receipt citations 校验。但无强类型 Failure Envelope、无 Schema 化交付契约 | `thread_state.py`；`subagents/acceptance_checks.py` |
| 9 | Session 外外部状态机 | ◐ run 级 | scheduler 持久队列（queued/launching/running + lease fencing + 崩溃恢复）、MCP durable task、subagent durable batch——它们编排**运行**，不编排任务图；checkpoint 恢复的是对话线程，不是任务拓扑 | backend AGENTS.md scheduler / MCP 节 |
| 10 | HITL 门禁（图级 interrupt/resume） | ◐ 弱 | `ask_clarification` → `jump_to="end"`（靠下一轮对话续），全库**零处**使用图级 `interrupt()`；scheduled task 的暂停/恢复是 occurrence 级，不是图节点级 | FAQ07 场景 C；grep `interrupt(` |
| 11 | **L2 拓扑自愈（改图 / 子图切片 / 重规划预算）** | ❌ | 全库无 replan / 拓扑校验 / 切片操作 / 失败信封。"重规划" = lead agent 读 error ToolMessage 后**在自己的对话上下文里**自发再派任务——不可审计、无预算、无熔断结构 | grep `replan\|dag\|topolog` 仅命中注释 |
| 12 | 黑板状态机（全局共享状态 + 版本快照） | ❌ 有替代物 | 无跨节点黑板；全局状态 = 对话 messages + 少量 channel。隔离靠每子代理独立 checkpoint namespace + 沙箱文件树，不是共享黑板 | `stream_subgraphs` 命名空间（#4399） |

## 2. "部分支持"的四处，各撑到哪儿

- **动态分解撑到"模型自觉"为止**（#6）：lead agent 想拆就拆、想串就串，拆分质量完全取决于模型当下表现。越过边界的表现：依赖关系只存在于对话语义中，模型忘了就是忘了；没有静态校验器能拦住环状依赖，因为根本没有边。
- **并发 fan-out 撑到"工具层"为止**（#7）：后台执行、容量上限、durable batch 都是真实的，但派发是"一堆独立任务"，不是"一张图上的节点"。汇聚没有 Fan-in 节点——结果的合并靠 lead agent 读 ToolMessage 后自己综合；acceptance checks 是子代理边界上的点检，不是图上的 Gate。
- **Session 外撑到"run 生命周期"为止**（#9）：scheduler / MCP durable task / durable batch 解决的是"进程死了活儿别丢"（lease fencing、恢复、预算），这是议题 03 的正解方向；但它们调度的单位是 run，不是任务节点——恢复一个 run 等于恢复一段对话，不等于恢复一张任务图的执行位。
- **HITL 撑到"对话回合"为止**（#10）：反问用户后 run 终止、用户答复开启新轮，语义上等价于人在环，但没有"图停在某个节点、带着完整状态等审批、approve 后原位续跑"的机制——那正是研究层蓝图 §9 里 HITL Gate 的含义。

## 3. 为什么"没有 DAG"是刻意取舍而非缺失

1. **元图小到不需要切片**。议题 09 反对的"现场编译新图"，DeerFlow 用另一种方式吸收了：元图只有两个节点且永不变化，可变性全部收进 lead agent 上下文（todos + delegations + task 调用流）。改"图" = 改对话，天然免除了 Checkpointer 断裂与 Trace 拓扑漂移——代价是放弃拓扑级的表达力。
2. **代价清单**（即 #6/#7/#11 三行缺席的直接后果）：重规划不可审计（发生在对话里）、无拓扑级断点（checkpoint 恢复对话不恢复任务图）、失败升级无结构化信封（error ToolMessage 是弱契约）。
3. **对研究层的反例价值**：一个生产级超级智能体底座，刻意不采用数据 DAG 也能成立。这说明"动态任务 DAG as data"对**超级智能体形态**（Harness 管环境、Agent 管算子、动态性留给模型自觉）不是必要条件；它更可能是**确定性流水线形态**（Issue→PR 蓝图一类）的必要条件。研究层 08/09 已附源码校准注记。

## 4. 对本知识库的取舍含义

- **不立 graph engineering 维度目录的决定成立**：DeerFlow 源码里没有 dynamic workflow DAG 的实现可消化，铺一个空维度违背 `_digest/` 的证据文化。本文件即该维度的完整判定记录。
- 若未来引入 `task_dag` state channel / dispatcher middleware / 失败信封，从 §1 的 **#6、#7、#11** 三行开始生长——那是缺口地图，也是扩展路线图。

## 5. 源码锚点速查

| 论断 | 位置 |
|---|---|
| 两固定节点 + middleware 钩子节点；Send 仅用于节点内并行 | `_faq_on_digested/07_graph-nodes/answer.md`（铁律节、§3.1） |
| 唯一直接构建/触碰 StateGraph 的两处 | `runtime/checkpoint_state.py`、`agents/factory.py`（`create_agent` 编译） |
| 全库无 dag/planner/拓扑校验/replan | `grep -ri "\bdag\b\|topolog\|replan" packages/harness/deerflow app` → 仅 middleware 注释 |
| 全库无图级 `interrupt()` | `grep -rn "interrupt(" packages/harness/deerflow` → 仅 TUI 取消与 worker finalization |
| 任务派发与并发上限 | `tools/builtins/task_tool.py`、`batch_task_tool.py`、`agents/middlewares/subagent_limit_middleware.py` |
| 扁平 todos / 台账 delegations / artifacts 合并 | `agents/thread_state.py`（`todos`、`merge_delegations`、`merge_artifacts`） |
| 子代理边界验收 | `subagents/acceptance_checks.py`、`agents/middlewares/receipt_verification.py` |
