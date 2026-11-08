---
title: "反向借鉴：DSH 编排原语对 DeerFlow 的可吸收点"
description: "把 DSH orchestration-ladder 的九级原语阶梯逐个对照 DeerFlow 的现有缝，回答'DSH 的哪个做法值得 DeerFlow 吸收、从哪里进、代价是什么'。纯综合页：DeerFlow 侧锚点回链 01-09，DSH 侧引用其 digest。"
topics: [cross-pollination, dsh, primitives, design-ideas]
topic: orchestration-ladder/10
repo: /Users/bowhead/deer-flow
date: 2026-10-02
status: verified（综合页）
---

# 反向借鉴：DSH 编排原语对 DeerFlow 的可吸收点

> 用户命题："借鉴 DSH 的挖掘精神、态度与思考模式。"方法已兑现为十篇；本页把**做法层**的借鉴收口——DSH 九级原语（todo/plan/subagent/workflow/ralph/goal/jobs/schedule/teams）逐个问：DeerFlow 有没有对应物？没有的话值不值得有、从哪条缝进？

## 对照与判定

| DSH 原语 | DeerFlow 对应物 | 判定与入口 |
|---------|----------------|-----------|
| `todo_write`（上下文内计划留痕） | plan mode 的 `write_todos`（ThreadState todos 通道） | **已有**，无需借鉴 |
| plan mode（方案先行、批准后执行） | `is_plan_mode` + TodoList middleware | **已有**；DSH 的"批准门"语义可作 04 §3.1 挂起式审批的参照 |
| subagent / fork（有界委派、fork 继承历史省 KV） | `task`；**无 fork 对应物**（子代理永远 fresh prompt） | **值得借鉴**：DSH fork 的 KV 前缀复用论证（不选模型、继承历史）对 DeerFlow 的批量同源任务（如逐文件审查）是真优化。入口：`task` 工具加 `inherit_context` 选项 → 把父 run 的近期 messages 作为种子注入子代理 prompt（不动 LangGraph 层，纯工具层） |
| `workflow`（模型写 JS 编排脚本扇出） | **无**；最接近的是 batch（静态 items） | **谨慎借鉴**：DeerFlow 哲学是"动态性归模型 turn"（[08]），脚编排会引入第二个决策面。若要，入口是 04 §3.2 的 `Command(goto=[Send])`——middleware 返回值即"迷你脚本"，无需 JS 引擎 |
| `ralph`（fresh-agent 循环、轮间只传有界报告） | goal（同 run 续轮、共享预算） | **已有不同解**；DSH ralph 的"轮间有界报告"值得吸收进 goal——目前续轮注入的是完整可见对话（截断到 12k chars / 30 条，`goal.py:38`-`39`），换成五字段有界报告可省 token 且防跑偏 |
| goal（跨轮长目标） | goal（对位物） | **互为镜像**；DSH 的 wrapup 收尾纪律是 DeerFlow 所缺（[05] §3.2：goal 满足不扫任何尾）——吸收点：满足时对未终态 delegations entry 做一次对账收尾 |
| jobs（任意工作后台化 + 可取消句柄） | run 本身 + `mcp_tasks`；**普通 task 无持久句柄**（[01] §2） | DSH 的"job id = 观察与取消的统一句柄"是干净抽象；DeerFlow 的双轨 id（[06] §1）已具备材料，缺的是把 execution_id 暴露成模型可轮询的工具 |
| schedule（定时） | scheduler（更完整：lease/队列/幂等） | **DeerFlow 反超**，无可借鉴 |
| agent-teams（具名队友 + 任务板 + mailbox） | **无**；委派账本只记账 | **远期借鉴**：DSH 自己也标注 experimental。若要，DeerFlow 的 natural 入口是 ThreadState 加 `blocked_by` 通道 + 写时 DFS 环校验——但 [08] 的结论提醒：这违背"组合靠预算不靠规则"的前提，应先榨尽 04 的 interrupt() 优先级再说 |

## 三条最划算的吸收（按投入产出排序）

1. **委派 fork 的 KV 复用**（工具层，小改）：同源批量任务的最大成本项。
2. **goal 轮间有界报告**（`make_goal_continuation_message` 改造，小改）：直接套 DSH ralph 的五字段格式。
3. **goal 满足时的 ledger 对账**（中改）：堵住 [05] §3.3 的"in_progress 永挂"缺陷，同时吸收 DSH 的收尾纪律精神。

## 不该借鉴的

DSH 的中心化倾向（teams 任务板、workflow 脚本平面）与 DeerFlow 的"harness 最小化"路线冲突——[08] 已论证 DeerFlow 把确定性全花在准入/预算/收尾上。借鉴其**纪律**（有界传递、收尾对账、句柄统一），不借鉴其**结构**（新调度平面）。

## 回链

DSH 侧：`/Users/bowhead/deepseek-harness/_digested/orchestration-ladder/00-map.md`（阶梯总表）。DeerFlow 侧：[00](00-map.md) · [01]-[09]。
