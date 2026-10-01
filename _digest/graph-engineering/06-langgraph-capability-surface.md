---
title: "LangGraph 能力面 — 依赖提供什么,DeerFlow 用了什么"
description: "langgraph 1.2.9 / langchain 1.x 的 DAG 能力在 DeerFlow 语境下的三分类:已用(含证据)/可用未用/结构不可用,以及 DeerFlow 对依赖的修正性补丁。"
topics: [langgraph, langchain, send, command, interrupt, capability]
---

# 06 · LangGraph 能力面 — 依赖提供什么,DeerFlow 用了什么

> 深挖版判定(2026-10-02)。用户语境:"DeerFlow 依赖的 LangGraph 也有更多 DAG 支持(静态/动态)——这些都在 DeerFlow 语境下,因为这个语境规定了 harness 的运行状态。" 本文把依赖能力按 **已用 / 可用未用 / 结构不可用** 三分类钉死。依据:venv 实装源码(`langgraph` 1.2.9 / `langchain` 1.2.15 / `langgraph-prebuilt` 1.0.11)+ deerflow 全库 import/调用 grep。

## 1. 已用面(证据清单)

| 依赖能力 | DeerFlow 用法 | 证据 |
|---------|--------------|------|
| `Command(update=...)` 状态更新 | 遍地:所有内置工具的返回路径(`task_tool.py:626`、`view_image_tool`、`present_file_tool` 等十余处) | grep `Command(` |
| `Command(goto=END)` 动态跳转 | `ask_clarification` 短路:`Command(update={tool_message}, goto=END)`,ToolMessage 带 `artifact={human_input: payload}` 结构化载荷 | `clarification_middleware.py:516` |
| `Command(resume=...)` 续跑输入 | Gateway run 请求支持 `command.resume` → `graph_input = Command(resume=...)` | `services.py:1571` |
| `interrupt_before` / `interrupt_after` 节点级中断 | **Gateway API 字段**(`run_models.py:48`,描述 "Nodes to interrupt before")→ `run_agent(...)` → `agent.interrupt_before_nodes`,支持 `["*"]` | `services.py:1725`、`worker.py:1229-1231` |
| `Send()` 动态 fan-out | 仅经 langchain factory 内部使用:tools 节点内并行执行多个 tool call;**deerflow 自身代码零处调用** | `langchain/agents/factory.py:1734`;grep `\bSend(` in deerflow = 0 |
| `StateGraph` 构图 | 仅两处:`agents/factory.py` 经 `create_agent`(主元图)+ `runtime/checkpoint_state.py::build_state_mutation_graph`(单 no-op 节点变异图,复用 checkpoint 机制做整体状态替换:回滚恢复/上下文压缩/delta 线性化) | grep `StateGraph` |
| `DeltaChannel` / `BinaryOperatorAggregate` | delta 检查点模式:O(N) 存储;`merge_message_writes` 线性折叠保持 add_messages 全语义 | `thread_state.py`、`checkpoint_state.py` |
| 子图 checkpoint namespace | 子代理**故意不传** checkpoint 坐标键,让 LangGraph 从复制的父 ContextVar 继承非根子图命名空间(1.2.6+ 显式传 thread_id 会开新根 lineage) | `subagents/AGENTS.md` Checkpoint lineage 节 |
| Checkpointer(sqlite/postgres/memory) | 全模式 + `CachedHistorySaver` 包装 + **上游缺陷修正补丁**(`checkpoint_patches.py`:delta 历史折叠、稳定消息 ID、首写丢弃修复、Overwrite 解包) | runtime AGENTS.md |

## 2. 可用未用(依赖里有,DeerFlow 不碰)

| 能力 | 依赖侧状态 | 未用的原因判读 |
|------|-----------|---------------|
| `interrupt()` 函数原语(节点内动态 HITL) | `langgraph.types.interrupt` 可导入,配合 `Command(resume=...)` 成对 | deerflow 全库零处调用。产品级 HITL 走 `ask_clarification`(goto=END + 下轮对话);`interrupt_before/after` 已暴露却无人传值——**原语齐备,产品语义缺失** |
| `Send()` 跨节点 fan-out | 原生支持(动态 Map-Reduce) | deerflow 不构图,没有可 Send 的目标节点;子代理派发走工具层。**这是"动态面降级到工具层"的最直接表达** |
| `Command(goto=<非END节点>)` | 支持 | 唯一使用是 END 短路。langchain 侧还有上游限制:wrap_model_call 内**不支持** Command goto(`factory.py:201-203` 明确报错)——middleware 层连这半个能力都被上游封死 |
| `add_conditional_edges` / 自定义构图 | 全套可用 | DeerFlow 不写图拓扑——两节点元图的全部路由都由 langchain factory 的 `model_to_tools`/`tools_to_model` 决策树提供 |
| `interrupt_before=["*"]` 全节点暂停 | 参数支持 `Literal["*"]` | 已接线,无调用方 |

## 3. 结构不可用(DeerFlow 语境主动禁用/约束)

这一节是"语境规定运行状态"的核心——**DeerFlow 的 harness 决策把依赖的部分图能力定性为不可用**:

| 约束 | 机制 | 后果 |
|------|------|------|
| **delta 模式禁 fork / time-travel** | 上游 delta 历史回放会把被放弃兄弟分支的 pending_writes 重放进 fork(#4458);worker 用 `_linearize_delta_checkpoint_resume` 把 fork 改写成当前 head 上的整体状态替换 | LangGraph 的分支/时间旅行在 delta 模式**结构性失效**——这是 DeerFlow 对依赖能力的主动收缩,full 模式保留 |
| checkpoint 模式进程冻结 | `freeze_checkpoint_channel_mode`,restart-required,同进程二次不同模式直接抛错 | 通道 schema 编译进图,模式是进程级契约而非线程级选项 |
| 禁止裸 checkpoint 写 | `Never bypass CheckpointStateAccessor`;`checkpointer.aput` 手写会破坏 delta 血缘 | 所有状态手术必须走单节点变异图,拓扑面被锁死成"一个 no-op 节点" |
| 子代理一次性执行 | `checkpointer=False` 编译 | 子代理没有独立断点/恢复——执行位的概念在子代理层不存在 |
| run 级事务化 | `_capture_rollback_point`(开跑前物化全量状态+pending_writes)→ cancel-with-rollback / edit-replay 失败恢复 → delta 线性化 | run 是事务单元:要么提交(新 checkpoint),要么整体回滚到 pre-run 快照 |

## 4. 运行单位的状态契约(语境的最终形态)

| 单位 | 持久化 | 隔离 | 身份 | 恢复语义 |
|------|--------|------|------|---------|
| **thread** | checkpoint(sqlite/pg,delta/full) | 独立沙箱 + 数据目录 | thread_id + 通道模式标记 | 对话级:任意时刻续跑;delta 禁 fork |
| **run** | RunStore 行 + lease + RunEventStore | run_id 划界的委托预算/事件 | trace_id + run_id(服务端盖戳) | 事务级:取消回滚 / 编辑重放恢复 pre-run 快照 |
| **subagent execution** | **无独立 checkpoint**;结果信封 + delegations 台账 + step 事件 | 隔离事件环 + ContextVar 边界 + 共享沙箱 lease | execution_id(注册表) vs tool_call_id(关联键),双身份分离 | 一次性;超时/取消后靠信封里的部分结果兜底 |
| **batch item** | 持久行 + 租约 | owner-scoped 路径/授权 | batch_id + key | durable:租约恢复、重试预算、取消栅栏 |

**判读**:这张表就是"DeerFlow 语境"的实体——每个单位的持久化/隔离/身份/恢复契约都由 harness 层决定,而不是由 LangGraph 决定。LangGraph 在这个语境里被降级为 **thread 单位的执行引擎**,它的图能力(fork、Send、interrupt、动态构图)要么未被需要,要么被上层契约主动禁用。

## 5. 总判读

**DeerFlow 不是"没用 LangGraph",而是"用了它的控制面,冻结了它的拓扑面,把它的动态面降级到工具层"**——并且:
1. 它在依赖**之上打补丁**(`checkpoint_patches.py` 修上游 delta 回放缺陷、稳定消息 ID 等)——关系是修正性的,不只是消费性的;
2. 它把 LangGraph 图能力中最有价值的三个(interrupt_before/resume、Send、fork)分别处理为:**暴露但无人用**、**封在工具层之下**、**delta 模式结构性禁用**;
3. 对"如何更好地支持企业":依赖侧的 HITL 原语对(`interrupt_before` + `Command(resume)`)已经端到端可达——**给 Gate 语义补上产品层的消费,是全部缺口里离现有资产最近的一个**。
