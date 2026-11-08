---
title: "Orchestration Ladder — DeerFlow 编排原语阶梯"
description: "借鉴 DSH orchestration-ladder 的挖掘方法，对 DeerFlow 做跨原语统一视角的十二篇深挖：阶梯全景、完成语义、状态三分法、资源预算、LangGraph 能力面榨取、组合模式、谱系与冷恢复、外部叙事核对、图计算本质、驾驶座手册、选择决策语义全景、goal 驾驶座。"
type: index
topics: [orchestration, primitives, completion, state, budget, langgraph, composition, lineage]
---

# Orchestration Ladder — DeerFlow 编排原语阶梯

> **定位**：借鉴 DSH 仓库 `_digested/orchestration-ladder/` 的挖掘方法，对 DeerFlow 做跨原语统一视角的深挖：八原语阶梯、完成语义、状态三分法、资源预算、LangGraph 能力面、组合与收尾、谱系与冷恢复、选择语义与 goal 驾驶座；给已经会用单个原语、需要判断「组合起来系统到底保证了什么」的读者。
> **边界**：不重复单机制 / 单原语解剖（见 [internals/](../internals/README.md)、[concepts/](../concepts/README.md)），也不做图工程标尺与注入设计（见 [graph-engineering/](../graph-engineering/README.md)）。
> **一句话结论**：DeerFlow 给的不是中心调度引擎，而是**架在两节点 react 元图之上、时间跨度与持久性各异的编排原语阶梯**——组合靠预算不靠规则、完成靠证据链不靠状态位、恢复靠重发不靠续传（[08](08-图计算的本质-DeerFlow编排的统一重述.md)）。

## 阅读路径

1. **先看**：[00-map.md](00-map.md) — 八原语统一维度矩阵、问题登记与 [ladder.svg](figures/ladder.svg)，先拿到全局坐标。
2. **再看**：[09-驾驶座手册-用已核验事实驱动DeerFlow.md](09-驾驶座手册-用已核验事实驱动DeerFlow.md) — 把 00–08 压成选原语、判完成、避预算陷阱的实践守则。
3. **深入**：[12-goal驾驶座-续轮准入评估熔断与收尾.md](12-goal驾驶座-续轮准入评估熔断与收尾.md) — 09 的机制侧对照：纪律与裁决权落点。

## 本篇目

| 文件 | 主题 | 深度 |
|---|---|---|
| [00-map.md](00-map.md) | 阶梯总图：八原语矩阵、问题登记与图版入口 | 概览 |
| [01-完成语义与崩溃窗口-接受可见静止处置.md](01-完成语义与崩溃窗口-接受可见静止处置.md) | 五时刻 × 七原语、run 终态持久化顺序、崩溃窗口与 at-least-once | 深入 |
| [02-状态三分法-持久事实派生投影与内存权限.md](02-状态三分法-持久事实派生投影与内存权限.md) | 25 行状态主表、统一恢复姿态与唯一可续跑的 checkpoint 链 | 深入 |
| [03-资源预算与公平性-并发深度总量与容量边界.md](03-资源预算与公平性-并发深度总量与容量边界.md) | 六层闸门叠加链、clamp 关系、超限三态与「默认无限制」 | 深入 |
| [04-LangGraph能力面榨取-未用原语与接入设计.md](04-LangGraph能力面榨取-未用原语与接入设计.md) | 七条榨取设计与优先级；`interrupt()`、`jump_to` 的接入面 | 深入 |
| [05-组合模式与收尾纪律-跨原语协同.md](05-组合模式与收尾纪律-跨原语协同.md) | 组合冲突矩阵、stop_reason 两套纪律、收尾顺序与通知经济学 | 深入 |
| [06-Session谱系与冷恢复-线程运行与所有权.md](06-Session谱系与冷恢复-线程运行与所有权.md) | 六层身份谱系、双轨 id、lease 双向围栏与冷恢复时序 | 深入 |
| [07-对照外部叙事-v1v2混淆与逐条核对.md](07-对照外部叙事-v1v2混淆与逐条核对.md) | 六条外部叙事逐条源码核对；最常见误传是 v1/v2 混淆 | 概览 |
| [08-图计算的本质-DeerFlow编排的统一重述.md](08-图计算的本质-DeerFlow编排的统一重述.md) | 四个真实的图、引擎做/拒绝清单、Agent 是原子 | 深入 |
| [09-驾驶座手册-用已核验事实驱动DeerFlow.md](09-驾驶座手册-用已核验事实驱动DeerFlow.md) | 实践守则：选原语决策树、完成核对、预算陷阱、多 worker 清单 | 概览 |
| [10-反向借鉴-DSH原语对DeerFlow的可吸收点.md](10-反向借鉴-DSH原语对DeerFlow的可吸收点.md) | DSH 九级原语逐个对照：三条最划算吸收与不该借鉴的 | 深入 |
| [11-选择决策语义全景-DeerFlow原语边界句与空白.md](11-选择决策语义全景-DeerFlow原语边界句与空白.md) | 模型可见边界句逐字盘点、跨原语路由与空白登记；scheduler 口径已按 v2.2.0 修正 | 深入 |
| [12-goal驾驶座-续轮准入评估熔断与收尾.md](12-goal驾驶座-续轮准入评估熔断与收尾.md) | 独立评估器裁决、双预算、blocker 枚举、熔断签名与收尾 | 深入 |

**配图**（`figures/`，SVG 浏览器直接打开）：[ladder](figures/ladder.svg)（00 阶梯全景）、[completion-lifecycle](figures/completion-lifecycle.svg)（01 完成/崩溃窗口）、[state-triads](figures/state-triads.svg)（02 状态三分）、[budget-stack](figures/budget-stack.svg)（03 预算叠加）、[extraction-priority](figures/extraction-priority.svg)（04 榨取优先级）、[composition-matrix](figures/composition-matrix.svg)（05 组合矩阵）、[lineage-layers](figures/lineage-layers.svg)（06 谱系与围栏）、[graph-essence](figures/graph-essence.svg)（08 图计算本质）、[selection-ladder](figures/selection-ladder.svg)（11 选择阶梯，v2.1.0 口径）、[goal-continuation](figures/goal-continuation.svg)（12 goal 续轮）。

## 宪章与约定

- 本目录无独立宪章；方法论与写作纪律沿用 [根 README](../README.md)：结论带 `path:line` 锚点（父侧独立抽查）、问题登记驱动、增量落盘、缺席就写缺席。
- 事实只来自本仓库源码核验；复查基准为上游 v2.2.0（`58fc5bd5b`），`selection-ladder.svg` 仍是 v2.1.0 口径，差异见 [11](11-选择决策语义全景-DeerFlow原语边界句与空白.md)。

## 相关目录

- [graph-engineering/](../graph-engineering/README.md) — 图工程标尺、操作面（07）与注入设计（08–09），「用 / 扩」的视角。
- [internals/](../internals/README.md) — 单机制深入：Agent Loop、middleware、runtime、config。
- [concepts/](../concepts/README.md) — 单原语概念：Agent、Skill、Tool、Sandbox、Sub-agent、Memory。
- [../README.md](../README.md) — 根索引：全部目录的阅读地图。
