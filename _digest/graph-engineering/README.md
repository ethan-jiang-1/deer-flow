---
title: "Graph Engineering — 图工程支持度判定与编排手册"
description: "以研究层 graph_engineering 框架为标尺判定 DeerFlow 的支持档位(01-06);面向'用 DeerFlow 编排 workflow'的操作面、扩展点与注入设计(07-09)。"
topics: [graph, dag, langgraph, orchestration, subagent]
---

# Graph Engineering — 图工程支持度判定与编排手册

> 这个目录回答两个问题:① **以研究层 [`graph_engineering`](/Users/bowhead/ai_dev_sdlc_aidc/02_research/01_agent_engineering/graph_engineering/README.md) 的框架为标尺,DeerFlow 对图工程支持到哪儿?**(01-06) ② **今后要用 DeerFlow 编排 workflow,手上有哪些旋钮、从哪儿注入、缺口怎么补?**(07-09)
>
> 2026-10-01 判定 / 2026-10-02 深挖修订,依据源码(`ethan` 分支 = **锚点 #7 / v2.1.0**,2026-09-24;rc0→v2.1.0 的 10 个 release commit 已逐一核对:图元图、沙箱、子代理、检查点、factory 等主锚点均未触及,仅 `runtime/events/store/*` 与 `runs/store/memory.py` 有事件/运行存储改动——[06 §4](06-langgraph-capability-surface.md) 的 run 单位行据此仍是同构契约(存储后端内部实现变化,不改运行单位的状态/隔离/身份/恢复语义))+ `_faq_on_digested/07-09` + 逐文件回源。不做理想化叙事——支持多大多写多大,缺席就写缺席。

| 文件 | 内容 |
|------|------|
| [01-support-map.md](01-support-map.md) | 12 项三档支持度地图(✅ 完整 / ◐ 部分 / ❌ 缺席)+ 源码锚点速查。**v2 深挖修订**(#7/#8/#9/#10/#11 五行经逐文件核实修正) |
| [02-partial-boundaries.md](02-partial-boundaries.md) | 四处"部分支持"各撑到哪儿、越过边界会发生什么 |
| [03-why-no-dag.md](03-why-no-dag.md) | 为什么"没有 DAG"是刻意取舍而非能力缺失;对研究层的反例价值 |
| [04-extension-path.md](04-extension-path.md) | 缺口即路线图(v2):五个生长点对齐现有资产 + 对研究层注入方案的批判性判读 + 红线 |
| [05-delegation-mechanics.md](05-delegation-mechanics.md) | 🆕 委派机制端到端解剖:路由决策(依赖=策略硬否决)、派发契约、三护栏轴、共享沙箱、状态信封、确定性验收、durable batch |
| [06-langgraph-capability-surface.md](06-langgraph-capability-surface.md) | LangGraph 依赖能力面三分类:已用(含证据)/可用未用(interrupt()、跨节点 Send)/结构不可用(delta 禁 fork);运行单位状态契约表 |
| [07-orchestration-surface.md](07-orchestration-surface.md) | 🆕 编排操作面:RunCreateRequest 全字段、durable batch 引擎语义、十一条组合配方(R1–R11)、观测面与边界陷阱 |
| [08-orchestration-extension-points.md](08-orchestration-extension-points.md) | 🆕 扩展点地图:六个参与编排的注入入口(按侵入深度排序)+ 每入口契约/部署面/风险 + 选型决策树 |
| [09-task-dag-injection-design.md](09-task-dag-injection-design.md) | 🆕 task_dag 注入设计:分层架构(状态/决策/执行/门/预算)、三种交付形态、与 delta/full·回滚·压缩·流式的兼容矩阵、MVP 切片与验收判据 |

## 一句话结论

**DeerFlow 是 graph engineering 的最小完整实现**：把"固定元图"做实（而且是两节点的极小元图），把全部"动态"下放到工具层的涌现式子代理派发。**没有任何 dynamic workflow DAG**——没有任务 DAG 数据结构、没有拓扑校验、没有 L2 改图。这是架构取舍，不是能力缺失（[03](03-why-no-dag.md)）。

## 与其他目录的分工

| 位置 | 分工 |
|------|------|
| [concepts/lead-agent/](../concepts/lead-agent/README.md) | 元图**内部**:两节点怎么跑、ThreadState、middleware 洋葱链 |
| [orchestration-ladder/](../orchestration-ladder/README.md) | **跨原语统一视角**:完成语义/状态三分法/资源预算/组合模式/谱系与冷恢复(借鉴 DSH ladder 方法,与本目录 06 互补) |
| `_faq_on_digested/07-09` | LangGraph 图模型逐行源码追踪(node / 路由 / Send / reducer) |
| **本目录** | 元图**之上 / 节点之间**:图工程标尺对表、能力边界、缺口路线 |
| 研究层 [`harness_langgraph_ecosystem/`](/Users/bowhead/ai_dev_sdlc_aidc/02_research/01_agent_engineering/graph_engineering/harness_langgraph_ecosystem/README.md) | 生态横向对比(LangGraph 原生 / Deep Agents / DeerFlow / GPT Researcher);其 03 号文件以本目录为事实权威,本目录 04 对其注入方案做批判性判读——双向校准环 |

## 本目录如何生长

- DeerFlow 源码里没有 dynamic workflow DAG 实现，因此本目录判定的是**能力边界**，不是实现解剖——这也是 `_digest/` 此前不铺这个维度的原因（无实现可消化）。
- 若上游引入 `task_dag` 状态通道 / dispatcher / 失败信封（见 [04](04-extension-path.md)），本目录对应 ❌/◐ 行升级为实现解剖，随之长出新的编号文件。
- [07](07-orchestration-surface.md)–[09](09-task-dag-injection-design.md) 是第三层：07 清点**今天就能用的编排旋钮**，08 给**注入入口**排序，09 把 04 的五个生长点收敛成**在现有契约内可落地的注入设计**。三者合起来回答"要自己编排，从哪儿下手"。

## 图版索引（figures/，SVG 浏览器直接打开）

| 图 | 内容 | 嵌入于 |
|----|------|--------|
| [support-dashboard.svg](figures/support-dashboard.svg) | 12 项三档支持度总览仪表盘 | [01](01-support-map.md) |
| [boundary-ladder.svg](figures/boundary-ladder.svg) | 四处部分支持的边界天梯(撑到哪儿/墙外是什么) | [02](02-partial-boundaries.md) |
| [two-absorptions.svg](figures/two-absorptions.svg) | 同一条教训的两种吸收(DAG 阵营 vs DeerFlow 极简) | [03](03-why-no-dag.md) |
| [growth-bridges.svg](figures/growth-bridges.svg) | 五个生长点:现有资产→补齐物→研究层概念 | [04](04-extension-path.md) |
| [delegation-pipeline.svg](figures/delegation-pipeline.svg) | 委派机器端到端(task/batch 双泳道全链路) | [05](05-delegation-mechanics.md) |
| [dependency-as-policy.svg](figures/dependency-as-policy.svg) | 依赖=策略否决决策树 + 共享线程沙箱(两个反直觉修正) | [05](05-delegation-mechanics.md) |
| [capability-funnel.svg](figures/capability-funnel.svg) | LangGraph 能力面:依赖提供→语境过滤→三分类 | [06](06-langgraph-capability-surface.md) |
| [run-units.svg](figures/run-units.svg) | 运行单位状态契约矩阵(thread/run/execution/batch item) | [06](06-langgraph-capability-surface.md) |
| [recipe-map.svg](figures/recipe-map.svg) | 组合配方地图 R1–R11(能力域 × 即时/durable) | [07](07-orchestration-surface.md) |
| [extension-entrypoints.svg](figures/extension-entrypoints.svg) | 六个扩展入口侵入深度天梯 + 选型决策树 | [08](08-orchestration-extension-points.md) |
| [injection-layers.svg](figures/injection-layers.svg) | 注入设计:五层架构·交付形态·MVP 切片·兼容摘要 | [09](09-task-dag-injection-design.md) |
