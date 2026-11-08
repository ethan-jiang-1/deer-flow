---
title: "为什么没有 DAG — 刻意取舍，而非缺失"
description: "元图小到不需要切片；可变性收进对话的代价清单；对研究层'固定元图+动态任务DAG'终局命题的反例价值。"
topics: [graph, dag, architecture, tradeoff]
---

# 03 · 为什么没有 DAG — 刻意取舍，而非缺失

> 判定"缺席"之前，先判定"这是不是缺陷"。结论：不是。这是对同一组生产教训的另一种吸收方式。

![同一条教训的两种吸收方式](figures/two-absorptions.svg)

## 1. 元图小到不需要切片

研究层议题 09 反对的"现场编译新图"，DeerFlow 用另一种方式吸收了：

- 元图只有 **两个节点**（model↔tools）且**永不变化**——Checkpointer 断裂、Trace 拓扑漂移这两个议题 09 的头号陷阱，在 DeerFlow 里**结构性不可能发生**；
- 可变性全部收进 lead agent 的对话上下文（todos + delegations + task 调用流）——"改图" = "改对话"；
- 代价是放弃拓扑级的表达力（见下节代价清单）。

## 2. 代价清单

即地图 #6 / #7 / #11 三行缺席的直接后果：

| 缺什么 | 直接后果 |
|--------|---------|
| task_dag 数据结构 | 重规划不可审计——"重新规划"发生在对话里，没有 diff 可看、没有版本可回滚 |
| 拓扑级断点 | checkpoint 恢复的是对话线程；任务执行位（哪些完成/冻结/待重试）无状态可恢复 |
| 重规划语义 | **注意别读错**：失败**信封**本身不弱（`subagent_status` 五值 + `stop_reason` 四值 + receipts + acceptance 都在结构化字段里，见 [01](01-support-map.md) 地图第 8 行）；缺的是信封之上的**分类学与动作建议**——没有 `failure_classification`、没有 `suggested_replanning_action`，所以模型读到"失败了"之后怎么重排，全靠对话上下文里的自发判断，不可审计、无预算 |

## 3. 对研究层的反例价值

研究层议题 09 的命题是"工业终局 = 固定元图 + 动态任务 DAG"。DeerFlow 回源后给出一个更锐利的边界反例：

> **一个生产级超级智能体底座，刻意不采用数据 DAG 也能成立。**

由此修正两分法的适用范围：

- "收敛到**固定元图**"是事实——DeerFlow 实证了这一半（尽管形态是极小元图）；
- "**数据图**是否必要，取决于形态"——对**超级智能体形态**（Harness 管环境、Agent 管算子、动态性留给模型自觉），数据 DAG 非必要；它更可能是**确定性流水线形态**（Issue→PR 蓝图一类）的必要条件。

**修正后的样本定位**：DeerFlow 2.0 实证的是"固定元图（极小形态）+ 物理沙箱 + 渐进装配 + 涌现式工具级 fan-out"；它**不是**"固定元图 + 动态任务 DAG"完整范式的实证。

**v2.2.0 复查（2026-11-04，`58fc5bd5b`）**：这个判定在 1,239 个 commit、1,068 个 PR 之后**没有被推翻**。逐项复验：`Send(` 在 `packages/harness/deerflow/` 仍是 **0 处调用**（`langchain/agents/factory.py:1881` 内部按 tool_call 逐个 `Send("tools", ...)` 仍然是唯一用法）；直接 `StateGraph(` 构造点仍只有两处（`runtime/checkpoint_state.py:63` 的单 no-op 变异图 builder、`agents/factory.py`）；`grep -ri "\bdag\b\|topolog\|replan"` 仍然只命中注释。**这反而是更强的证据**——一个跑了一千多个 commit 的生产仓库，在新增了 29 份 AGENTS.md、扩展族、knowledge 平台、多实例租约之后，依然没有长出任务 DAG。如果 DAG 是这类系统的自然收敛点，这个窗口本该是它冒出来的时机。

> 研究层侧的对应校准：议题 [08](/Users/bowhead/ai_dev_sdlc_aidc/02_research/01_agent_engineering/graph_engineering/digested/08-superagent-harness-deerflow-langgraph.md)、[09](/Users/bowhead/ai_dev_sdlc_aidc/02_research/01_agent_engineering/graph_engineering/digested/09-meta-graph-vs-dynamic-task-dag.md) 末尾的"源码校准注记"（2026-10-01），以及 `result/landscape.md` §6.1、`CURRENT.md` 缺口第 3 条。

## 4. 对本知识库的含义

- `_digested/` 不铺 graph engineering 实现维度的决定成立：无实现可消化，本目录判定的是**能力边界**；
- 若未来源码长出数据图半边，从 [01](01-support-map.md) 的 #6/#7/#11 三行开始升级——那是缺口地图，也是扩展路线（[04](04-extension-path.md)）；
- v2.2.0 窗口提供了一个**反向信号**：他们确实在给"编排"加东西，但加的方向是**原语的耐久性**（durable batch、run 幂等 `0036_run_idempotency_request`、`0048_extension_execution_leases`、多实例 leader lease），不是**图的表达力**。这印证了取舍是一条稳定的路线，而不是"还没排到"。
