---
title: "扩展路线 — 缺口即路线图"
description: "若要长出'数据任务 DAG'半边：五个生长点的最小落点、对应研究层议题，以及明确不做什么。"
topics: [graph, dag, roadmap, extension]
---

# 04 · 扩展路线 — 缺口即路线图

> 前提（[03](03-why-no-dag.md)）：DeerFlow 刻意不做数据 DAG。本文件回答"如果要补，从哪儿下手"——每个生长点给出最小落点，并钉死不该做什么。

## 五个生长点

| # | 缺口（地图行） | 最小落点 | 对应研究层议题 |
|---|---------------|---------|---------------|
| 1 | `task_dag` 状态通道（#6） | `ThreadState` 新增 channel + merge reducer（仿 `merge_delegations`：append-only、同 id latest-wins、封顶）；schema 先于语义——只存节点/依赖/状态三要素 | 议题 09 `State.task_dag` |
| 2 | 拓扑派发（#7） | dispatcher 读 task_dag 的就绪集（入度=0 的节点），经**现有** SubagentRuntime / durable batch 派发；`Send()` 从"节点内工具并行"升级为跨节点 fan-out 不必一步到位 | 议题 08 Dispatcher |
| 3 | Fan-in Gate（#7/#8） | 汇聚 = "就绪集为空且全部 SUCCESS"的确定性判定 + acceptance checks 从边界点检升格为 Gate 判定（Pass / Fail 分支进 task_dag 状态） | 蓝图 §9 集成测试门禁 |
| 4 | 失败信封 + L2 预算（#11） | `subagents/status_contract.py` 已有结构化 status/stop_reason **雏形**——升级为带 `failure_classification` + `suggested_replanning_action` 的信封；配 Kahn 拓扑校验器（改图前无环校验）+ 全局重规划预算硬上限（≤2） | 议题 07 全部三节 |
| 5 | 图级 HITL（#10） | langgraph `interrupt()` 原语已在依赖里、未使用——在 Gate 节点挂 interrupt/resume，替代"run 终止等下一轮对话" | 蓝图 §9 HITL Gate |

> 关键洞察：五个生长点里**没有一个是"换图引擎"**。全部是在现有两节点元图 + 工具层之上加"数据与判定"，骨架不动。

## 明确不做什么

回扣议题 09 的三大陷阱，这条路线的红线：

1. **不现场编译新图**——不允许任何 `builder.add_node()` 出现在请求路径；元图保持两节点 + middleware 钩子；
2. **不把任务图塞进拓扑**——task_dag 是 `ThreadState` 里的**数据**，不是 LangGraph 节点；改图 = 状态手术（对未完成节点插入/切片），外层流转逻辑不变；
3. **不做全量重新生图**——L2 只允许对失败节点的局部切片（冻结已成功节点），并有全局预算熔断转 HITL。

## 验收判据

路线推进时，用 [01](01-support-map.md) 的地图行做验收：每个生长点合入后，对应行从 ◐/❌ 升级为 ✅，并在本目录长出对应的实现解剖编号文件。若某步让 #1 的"两固定节点"铁律失效（元图开始随请求变化），立即回退——那意味着走进了议题 09 的陷阱。
