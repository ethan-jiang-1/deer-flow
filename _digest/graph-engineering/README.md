---
title: "Graph Engineering — 图工程支持度判定"
description: "以研究层 graph_engineering 框架为标尺，逐项判定 DeerFlow 对图工程（固定元图 / 动态任务 DAG / 两层自愈 / Session 外状态机）的支持档位。"
topics: [graph, dag, langgraph, orchestration, subagent]
---

# Graph Engineering — 图工程支持度判定

> 这个目录回答一个问题：**以研究层 [`graph_engineering`](/Users/bowhead/ai_dev_sdlc_aidc/02_research/01_agent_engineering/graph_engineering/README.md) 的框架为标尺，DeerFlow 对图工程支持到哪儿？**
>
> 2026-10-01 判定，依据源码（`ethan` 分支 / v2.1.0-rc0 口径）+ `_faq_on_digested/07-09`。不做理想化叙事——支持多大多写多大，缺席就写缺席。

| 文件 | 内容 |
|------|------|
| [01-support-map.md](01-support-map.md) | 12 项三档支持度地图（✅ 完整 / ◐ 部分 / ❌ 缺席）+ 源码锚点速查 |
| [02-partial-boundaries.md](02-partial-boundaries.md) | 四处"部分支持"各撑到哪儿、越过边界会发生什么 |
| [03-why-no-dag.md](03-why-no-dag.md) | 为什么"没有 DAG"是刻意取舍而非能力缺失；对研究层的反例价值 |
| [04-extension-path.md](04-extension-path.md) | 缺口即路线图：若要长出"数据任务 DAG"半边，从哪儿下手、不做什么 |

## 一句话结论

**DeerFlow 是 graph engineering 的最小完整实现**：把"固定元图"做实（而且是两节点的极小元图），把全部"动态"下放到工具层的涌现式子代理派发。**没有任何 dynamic workflow DAG**——没有任务 DAG 数据结构、没有拓扑校验、没有 L2 改图。这是架构取舍，不是能力缺失（[03](03-why-no-dag.md)）。

## 与其他目录的分工

| 位置 | 分工 |
|------|------|
| [concepts/lead-agent/](../concepts/lead-agent/README.md) | 元图**内部**：两节点怎么跑、ThreadState、middleware 洋葱链 |
| `_faq_on_digested/07-09` | LangGraph 图模型逐行源码追踪（node / 路由 / Send / reducer） |
| **本目录** | 元图**之上 / 节点之间**：图工程标尺对表、能力边界、缺口路线 |

## 本目录如何生长

- DeerFlow 源码里没有 dynamic workflow DAG 实现，因此本目录判定的是**能力边界**，不是实现解剖——这也是 `_digest/` 此前不铺这个维度的原因（无实现可消化）。
- 若上游引入 `task_dag` 状态通道 / dispatcher / 失败信封（见 [04](04-extension-path.md)），本目录对应 ❌/◐ 行升级为实现解剖，随之长出新的编号文件。
