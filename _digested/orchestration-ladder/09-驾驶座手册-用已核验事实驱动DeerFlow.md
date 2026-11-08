---
title: "驾驶座手册：用已核验事实驱动 DeerFlow 的实践守则"
description: "把 00-08 的源码结论压成可操作守则：怎么选原语、怎么写才算'完成'、预算陷阱、恢复预期、多 worker 升级清单。面向使用者（驾驶座视角），全部结论回链已核验锚点。"
topics: [playbook, practitioner, orchestration, recipes]
topic: orchestration-ladder/09
repo: /Users/bowhead/deer-flow
date: 2026-10-02
status: verified（综合页：结论全部回链 01-08 已核验锚点，不新增）
---

# 驾驶座手册：用已核验事实驱动 DeerFlow 的实践守则

> [../graph-engineering/07](../graph-engineering/07-orchestration-surface.md) 给了 R1-R11 组合配方（API 旋钮层）；本页给的是**语义层守则**——从 01-08 的源码事实推导出的"你会被什么咬、怎么不被咬"。

## 1. 选原语的决策树（按时间跨度 × 持久性需求）

```
秒级小 fan（并行翻译/校对）        → 单轮多个 task（Send 并行，[04] §1.3）
分钟级、结果要进对话               → task + acceptance_criteria（验收 verdict 你自己读，[01] §2）
小时级/跨崩溃/结果外取             → batch_task（lease 重试 + JSONL，幂等副作用自己保证，[01] §2）
无人值守定时                       → scheduled task（non_interactive：模型没有 ask_clarification，[05] §1.1）
长目标多轮自驱                     → goal（≤8 续轮、与用户 turn 共享预算，[05] §1.2）
要人拍板                           → ask_clarification（回合级）或 interrupt_before + Command(resume)（原语级，[04]）
```

**反模式**：把秒级 fan 写成 batch（durable 开销白付）；把有依赖的活写成一批 task（依赖正确性=模型自觉，无机器校验，[00-map]）。

## 2. "完成"的核对清单（别信单一状态位）

- run `success` ≠ 交付：查 `run.delivery` 回执（present_files 覆盖），回执不可验证会被**降级 error**（[01] §1）。
- run `error` ≠ 失败：可能是"成功但无法持久确认"（ownership_lost 围栏）或崩溃窗口的 orphan_recovered——**checkpoint 里可能有完整回答**（[01] 崩溃窗口表第 1 行）。
- 子代理 `completed` + `stop_reason=*_capped` = 部分结果：ledger 会把"知情重用"指令给 lead（[05] §2.3）——你的 prompt 应当遵守它。
- batch `succeeded` 只证明执行器走完；**结果不自动回任何模型上下文**，记得安排消费方（[01] §2）。
- 开发默认（`database.backend=memory`、`run_events.backend=memory`）下，上面一半证据是内存的——重启即空（[02] 危险点 2）。**生产语义讨论必须先钉后端配置**。

## 3. 预算陷阱（六层闸门的行为差异）

| 陷阱 | 事实 | 对策 |
|------|------|------|
| 静默截断 | 单响应 >3 个 task：多余的**被删掉**，模型只看到一条提示（[03] §一.2） | prompt 里教模型分批；或显式配 `max_concurrent_subagents`（≤ `subagent_runtime.max_running` 的 clamp，[03] §一.3） |
| 排队超时 | capacity 满 → FIFO 排 300s 不到即 `SubagentCapacityTimeout`（[03] §一.3） | 长任务走 batch；或调 `max_running`（**startup-only**，改了要重启） |
| goal 假续命 | 续轮共享 run 的 token/委派预算；`token_capped` 直接 stand down（[05] §1.2/§2.3） | 长目标调大 run 预算或拆 goal |
| 无限并发幻觉 | 跨 thread run 数、LLM 并发、RPM **默认全不设防**（[03] §四） | 多租户/大流量自己设 `llm_call.max_concurrent_calls` 或 nginx `limit_req` |

## 4. 恢复预期（fail-closed 心智）

重启/崩溃后：在途 run → orphan 标 error（**不会续跑**）；scheduled `queued` 行 → 存活继续；`launching/running` → 单实例标 interrupted；IM 内存 dedupe 丢 → provider 重投整条重处理（[02] 主表）。**唯一续跑的是 checkpoint 链**——设计你的工作流时把"可重发"当默认姿势：幂等副作用（batch 的 prompt 契约示范）、稳定幂等键（scheduler 的 `scheduled-task:{id}`）。

## 5. 多 worker / 上生产清单

`GATEWAY_WORKERS>1` 或多 pod 前（[06] §4 + 各篇危险点）：

1. `database.backend=postgres`（共享 runs/事件/唯一索引）；2. `run_ownership.heartbeat_enabled=true`；3. `run_events.backend=db`（内存/JSONL 事件存储直接被启动门拒绝）；4. scheduler 多实例还要求 `multi_instance=true`；5. 接受：IM follow-up 缓冲、`_runs` 视图、子代理注册表仍是 per-process（[02] 危险点 6、[05] §4.2）；6. delta checkpoint 模式下放弃 fork 类玩法（[04] §3.5）。

## 6. 想榨新能力时

按 [04] 优先级表动手：`interrupt()` 挂起式工具审批是 seam 最清晰的（ToolNode v2 的 Send 化本就为此设计）；做之前 `uv sync` 复核行号（venv 1.1.9 vs lock 1.2.9 漂移，[04] 版本事实节）。新原语必须同时接进三条 HITL 信任边界（`non_interactive` 结构剔除 / `disable_clarification` 软化 / 沙箱审批合流，[05] §1.1）。

## 回链

本页每条守则的完整证据链见对应篇目：[00](00-map.md) · [01](01-完成语义与崩溃窗口-接受可见静止处置.md) · [02](02-状态三分法-持久事实派生投影与内存权限.md) · [03](03-资源预算与公平性-并发深度总量与容量边界.md) · [04](04-LangGraph能力面榨取-未用原语与接入设计.md) · [05](05-组合模式与收尾纪律-跨原语协同.md) · [06](06-Session谱系与冷恢复-线程运行与所有权.md) · [07](07-对照外部叙事-v1v2混淆与逐条核对.md) · [08](08-图计算的本质-DeerFlow编排的统一重述.md)
