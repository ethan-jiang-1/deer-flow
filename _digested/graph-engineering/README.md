---
title: "Graph Engineering — 图工程支持度判定与编排手册"
description: "以研究层 graph_engineering 框架为标尺判定 DeerFlow 的支持档位（01-06）；面向「用 DeerFlow 编排 workflow」的操作面、扩展点与注入设计（07-09）。"
type: index
topics: [graph, dag, langgraph, orchestration, subagent]
---

# Graph Engineering — 图工程支持度判定与编排手册

> **定位**：回答两个问题——① 以研究层 `graph_engineering` 的框架为标尺，DeerFlow 对图工程支持到哪儿？② 今后要用 DeerFlow 编排 workflow，手上有哪些旋钮、从哪儿注入、缺口怎么补？给研究者与要落地编排的开发者看。
> **边界**：只做「图工程标尺 / 元图之上、节点之间」的判定与注入，不铺元图内部（见 [concepts/lead-agent/](../concepts/lead-agent/README.md)），也不重述跨原语组合语义（见 [orchestration-ladder/](../orchestration-ladder/README.md)）；LangGraph 图模型逐行追踪在 `_faq_on_digested/07-09`。

**一句话结论**：**DeerFlow 是 graph engineering 的最小完整实现**——把「固定元图」做实（两节点极小元图），把全部动态性下放到工具层的涌现式子代理派发；**没有任何 dynamic workflow DAG**（无任务 DAG 数据结构、无拓扑校验、无 L2 改图）。这是架构取舍，不是能力缺失（[03](03-why-no-dag.md)）。

## 阅读路径

1. **先看**：[01-support-map.md](01-support-map.md) — 12 项三档支持度地图与源码锚点，先建立「有什么 / 缺什么」的坐标。
2. **再看**：[03-why-no-dag.md](03-why-no-dag.md) — 为什么「没有 DAG」是刻意取舍；用它判断哪些「缺」其实不必补。
3. **深入**：[07-orchestration-surface.md](07-orchestration-surface.md) — 今天就能用的 Run 字段、durable batch 与 R1–R11 组合配方。

## 本篇目

| 文件 | 主题 | 深度 |
|---|---|---|
| [01-support-map.md](01-support-map.md) | 12 项三档支持度地图 + 源码锚点速查 | 概览 |
| [02-partial-boundaries.md](02-partial-boundaries.md) | 四处「部分支持」各撑到哪儿、越界后会发生什么 | 深入 |
| [03-why-no-dag.md](03-why-no-dag.md) | 为什么「没有 DAG」是刻意取舍；对研究层的反例价值 | 深入 |
| [04-extension-path.md](04-extension-path.md) | 缺口即路线图：五个生长点、注入方案判读与红线 | 深入 |
| [05-delegation-mechanics.md](05-delegation-mechanics.md) | 委派机制端到端：路由、派发、隔离、验收、durable batch | 深入 |
| [06-langgraph-capability-surface.md](06-langgraph-capability-surface.md) | LangGraph 能力面三分类：已用 / 可用未用 / 结构不可用 | 深入 |
| [07-orchestration-surface.md](07-orchestration-surface.md) | 编排操作面：Run 全字段、batch 语义、R1–R11 配方与陷阱 | 深入 |
| [08-orchestration-extension-points.md](08-orchestration-extension-points.md) | 六个编排注入入口（按侵入深度）+ 契约、部署面与选型 | 深入 |
| [09-task-dag-injection-design.md](09-task-dag-injection-design.md) | task_dag 注入设计：分层、交付形态、兼容矩阵与 MVP | 深入 |

**配图**（`figures/`，SVG 浏览器直接打开）：[support-dashboard](figures/support-dashboard.svg)（01 支持度仪表盘）、[boundary-ladder](figures/boundary-ladder.svg)（02 边界天梯）、[two-absorptions](figures/two-absorptions.svg)（03 两种吸收）、[growth-bridges](figures/growth-bridges.svg)（04 五个生长点）、[delegation-pipeline](figures/delegation-pipeline.svg)（05 委派全链路）、[dependency-as-policy](figures/dependency-as-policy.svg)（05 依赖=策略）、[capability-funnel](figures/capability-funnel.svg)（06 能力漏斗）、[run-units](figures/run-units.svg)（06 运行单位）、[recipe-map](figures/recipe-map.svg)（07 配方地图）、[extension-entrypoints](figures/extension-entrypoints.svg)（08 扩展入口）、[injection-layers](figures/injection-layers.svg)（09 注入分层）。

## 宪章与约定

- **本目录如何生长**：DeerFlow 源码没有 dynamic workflow DAG，因此本目录判定的是**能力边界**而非实现解剖；若上游引入 `task_dag` 状态通道 / dispatcher / 失败信封（见 [04](04-extension-path.md)），对应 ❌/◐ 行升级为实现解剖，并随之长出新的编号文件。[07](07-orchestration-surface.md)–[09](09-task-dag-injection-design.md) 是第三层：07 清点今天能用的旋钮，08 给注入入口排序，09 把生长点收敛成可落地设计。
- **复查基准**：2026-11-08 对 v2.2.0（`58fc5bd5b`）全量复查，12 项档位判定一条未改；改动只涉及依赖版本、行号与 `jump_to` 生长点，细节见 01/06。
- 写作纪律沿用 [根 README](../README.md)：不做理想化叙事——支持多大多写多大，缺席就写缺席。

## 相关目录

- [concepts/lead-agent/](../concepts/lead-agent/README.md) — 元图内部：两节点怎么跑、ThreadState、middleware 洋葱链。
- [orchestration-ladder/](../orchestration-ladder/README.md) — 跨原语统一视角：完成语义、状态三分法、资源预算、组合模式与冷恢复。
- [../README.md](../README.md) — 根索引：全部目录的阅读地图。
