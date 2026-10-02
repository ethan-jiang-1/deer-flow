---
title: "Orchestration Ladder — DeerFlow 编排原语阶梯"
description: "借鉴 DSH orchestration-ladder 的挖掘方法，对 DeerFlow 做跨原语统一视角的十篇深挖：阶梯全景、完成语义、状态三分法、资源预算、LangGraph 能力面榨取、组合模式、谱系与冷恢复、外部叙事核对、图计算本质、驾驶座手册。"
topics: [orchestration, primitives, completion, state, budget, langgraph, composition, lineage]
---

# Orchestration Ladder — DeerFlow 编排原语阶梯

> 方法论借鉴自 DSH 仓库 `_digested/orchestration-ladder/`：**不做理想化叙事、每个结论带 path:line 锚点（父侧独立抽查）、问题登记驱动、增量落盘、缺席就写缺席**。所有事实只来自本仓库源码核验。

| 文件 | 内容 |
|------|------|
| [00-map.md](00-map.md) | 阶梯总图：八原语统一维度矩阵（全行锚定）+ 问题登记（全绿）+ [figures/ladder.svg](figures/ladder.svg) |
| [01-完成语义与崩溃窗口](01-完成语义与崩溃窗口-接受可见静止处置.md) | 五时刻 × 七原语证据表、run 终态十步持久化顺序、九行崩溃窗口表、at-least-once 清单 |
| [02-状态三分法](02-状态三分法-持久事实派生投影与内存权限.md) | 25 行状态主表；恢复姿态 = 标错对账/静默丢失，唯一可续跑是 checkpoint 链 |
| [03-资源预算与公平性](03-资源预算与公平性-并发深度总量与容量边界.md) | 六层闸门叠加链、clamp 关系、超限三态、"默认无限制"三处 |
| [04-LangGraph能力面榨取](04-LangGraph能力面榨取-未用原语与接入设计.md) | 七条榨取设计 + 优先级表（interrupt() 最高）；venv 1.1.9 依赖漂移 |
| [05-组合模式与收尾纪律](05-组合模式与收尾纪律-跨原语协同.md) | 组合冲突矩阵（结构性禁止/软化/自由）、stop_reason 两套聚合纪律、goal 无 wrapup、通知三通道 |
| [06-Session谱系与冷恢复](06-Session谱系与冷恢复-线程运行与所有权.md) | 六层身份谱系、双轨 id（关联键≠所有权键）、lease 双向围栏、冷恢复时序 |
| [07-对照外部叙事](07-对照外部叙事-v1v2混淆与逐条核对.md) | 六条叙事逐条核对；最常见误传 = v1/v2 版本混淆 |
| [08-图计算的本质](08-图计算的本质-DeerFlow编排的统一重述.md) | 四个真实的图、引擎做/拒绝清单、Agent 是原子、代码-语言倒置样本 |
| [09-驾驶座手册](09-驾驶座手册-用已核验事实驱动DeerFlow.md) | 使用守则：选原语决策树、"完成"核对清单、预算陷阱、多 worker 清单 |
| [10-反向借鉴](10-反向借鉴-DSH原语对DeerFlow的可吸收点.md) | DSH 九级原语逐个对照：三条最划算吸收（委派 fork KV 复用 / goal 有界报告 / ledger 对账）与不该借鉴的 |

## 一句话结论

DeerFlow 给的不是中心调度引擎，而是**架在两节点 react 元图之上、时间跨度与持久性各异的编排原语阶梯**；其三个前提是：**组合靠预算不靠规则、完成靠证据链不靠状态位、恢复靠重发不靠续传**（[08](08-图计算的本质-DeerFlow编排的统一重述.md)）。

## 与其他目录的分工

| 位置 | 分工 |
|------|------|
| [../graph-engineering/](../graph-engineering/README.md) | 图工程标尺、操作面旋钮（07）、注入设计（08-09）——"用/扩"的视角 |
| [../internals/](../internals/README.md)、[../concepts/](../concepts/README.md) | 单机制/单原语解剖 |
| **本目录** | **跨原语统一视角**：组合起来时系统到底保证了什么 |

## 图版索引（figures/，SVG 浏览器直接打开）

| 图 | 内容 | 嵌入于 |
|----|------|--------|
| [ladder.svg](figures/ladder.svg) | 八原语阶梯全景 + 完成证据分层 + 状态三分色带 + 预算叠加链 | [00-map](00-map.md) |
| [completion-lifecycle.svg](figures/completion-lifecycle.svg) | 五时刻时间轴、run 终态六步顺序、崩溃窗口速查、"成功却报错"路径 | [01](01-完成语义与崩溃窗口-接受可见静止处置.md) |
| [state-triads.svg](figures/state-triads.svg) | 三分法三栏对比、恢复姿态、明码标价的丢失窗口、六危险点 | [02](02-状态三分法-持久事实派生投影与内存权限.md) |
| [budget-stack.svg](figures/budget-stack.svg) | 六层闸门纵向叠加链、超限三态、"默认无限制"三处 | [03](03-资源预算与公平性-并发深度总量与容量边界.md) |
| [extraction-priority.svg](figures/extraction-priority.svg) | 榨取优先级天梯（高→不做）、interrupt 持久化真身 | [04](04-LangGraph能力面榨取-未用原语与接入设计.md) |
| [composition-matrix.svg](figures/composition-matrix.svg) | 组合冲突色块矩阵、stop_reason 两套纪律、通知三通道 | [05](05-组合模式与收尾纪律-跨原语协同.md) |
| [lineage-layers.svg](figures/lineage-layers.svg) | 六层身份谱系、双向围栏、冷恢复四步时序、四类断点 | [06](06-Session谱系与冷恢复-线程运行与所有权.md) |
| [graph-essence.svg](figures/graph-essence.svg) | 四个真实的图、引擎做/拒绝、Agent 是原子、代码-语言倒置 | [08](08-图计算的本质-DeerFlow编排的统一重述.md) |

## 阅读路径

5 分钟：00-map + ladder.svg → 15 分钟：+ 09 驾驶座手册 → 深入：按问题登记表选篇。
