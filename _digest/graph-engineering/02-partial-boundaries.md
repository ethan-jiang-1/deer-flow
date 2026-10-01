---
title: "部分支持的边界 — 四处各撑到哪儿"
description: "◐ 档逐项剖析：动态分解、Fan-out、Session 外状态机、HITL 各自的能力边界与越过边界后的表现。"
topics: [graph, dag, subagent, hitl]
---

# 02 · 部分支持的边界 — 四处各撑到哪儿

> §01 地图里的 ◐ 档不是同一档"半个支持"：四处各缺不同的东西，越过边界的表现也不同。逐项钉死。

## 1. 动态分解撑到"模型自觉"为止（地图 #6）

lead agent 想拆就拆、想串就串，拆分质量完全取决于模型当下表现。依赖关系只存在于对话语义中——**模型忘了就是忘了**。

- 越过边界的表现：没有静态校验器能拦住环状依赖，因为**根本没有边**；`todos` 是给模型自己看的便签，不是给调度器看的数据。
- 已有的最接近物：`delegations` 台账（append-only、同 id latest-wins、封顶截断）——它是**记录**，不是**计划**；记录已经发生了什么，不声明接下来依赖什么。

## 2. 并发 Fan-out 撑到"工具层"为止（地图 #7）

后台执行、容量上限、durable batch 都是真实的（SubagentExecutor + registry + 轮询/取消/超时；batch_task/batch_status/cancel_batch）。但派发出去的是"**一堆独立任务**"，不是"**一张图上的节点**"。

- 越过边界的表现：**汇聚没有 Fan-in 节点**——结果合并靠 lead agent 读 ToolMessage 后自己综合；`acceptance checks` 是子代理边界上的点检，不是图上带通过/失败分支的 Gate；失败的任务不会触发任何拓扑级响应，只会变成一条 error ToolMessage。

## 3. Session 外撑到"run 生命周期"为止（地图 #9）

scheduler 持久队列 / MCP durable task / subagent durable batch 解决的是"**进程死了活儿别丢**"（lease fencing、崩溃恢复、预算闸门）——方向上正是研究层议题 03 的正解。但它们调度的单位是 **run**，不是任务节点。

- 越过边界的表现：恢复一个 run 等于恢复一段对话，**不等于恢复一张任务图的执行位**——没有"哪些节点已完成、哪些冻结、哪些待重试"的状态可以恢复，因为那些状态不存在。

## 4. HITL 撑到"对话回合"为止（地图 #10）

`ask_clarification` → `jump_to="end"`，run 终止、用户答复开启新轮——语义上等价于人在环。

- 越过边界的表现：没有"**图停在某个节点、带着完整状态等审批、approve 后原位续跑**"的机制。langgraph 的 `interrupt()` 原语在依赖里可用，但全库零处使用。这正是研究层蓝图 §9 里 HITL Gate 节点的含义——DeerFlow 的等价物退回到了对话层。

## 小结

| ◐ 项 | 撑到哪儿 | 缺的下一步 |
|------|---------|-----------|
| 任务分解 | 模型自觉（对话语义） | `task_dag` 状态通道 + 依赖边 |
| Fan-out | 工具层独立任务 | 拓扑派发 + Fan-in Gate |
| Session 外 | run 生命周期 | 任务图执行位的持久化 |
| HITL | 对话回合 | 图级 `interrupt()` 原位续跑 |

这些"缺的下一步"的具体落点见 [04-extension-path.md](04-extension-path.md)。
