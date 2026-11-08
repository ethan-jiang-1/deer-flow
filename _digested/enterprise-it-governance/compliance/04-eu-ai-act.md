---
title: "EU AI Act 对照"
description: "透明度、人类监督、自主性控制、日志留存四类义务对应的技术原语。重点说明 clarification 不等于合规审批、bounded autonomy 的边界在哪。"
topics: [governance, compliance, ai-act]
---

# EU AI Act 对照

> ⚠️ **本页不构成合规结论**。以下只描述「有没有对应技术机制」，
> 不判定任何系统或用途是否落入 AI Act 的某一风险类别，也不替代法律意见。

## 1. 先划清一件事

DeerFlow 是**通用 agent 框架**，不内置任何面向特定用途的风险分级。

| 判断 | 由谁做 |
|---|---|
| 这个用途属于哪个风险类别（不可接受/高/有限/最小） | **部署方** + 法律判断 |
| 该类别对应的具体义务 | **部署方** |
| 框架提供了哪些可用的技术原语 | DeerFlow（本页） |

所以本页只回答第三行。

## 2. 透明度义务

| 原语 | 状态 |
|---|---|
| 用户知道自己在和 AI 交互 | **有**（UI 层，非框架强制） |
| 模型回复的 AI 标识 | **有**（产品形态自带） |
| 输出中标注生成内容 | **无机制**——无强制水印或元数据 |
| 决策可解释性 | **部分**——journal 记录策略决策与理由码 |

**最后一条的实际价值**：`guardrails/middleware.py:171` 记录
`policy_id` / `reason_codes` / `reason_messages` / `fail_closed`，
所以「为什么这个工具调用被拦」是可查的。这比纯黑盒强，
但它覆盖的是**策略决策**，不是**模型推理**。

详见 [../audit/01-audit-chain.md](../audit/01-audit-chain.md)。

## 3. 人类监督义务

这是最需要澄清的一块，因为两个原语看起来像、实际不是。

### 3.1 clarification ≠ 合规审批

`packages/harness/deerflow/agents/middlewares/clarification_middleware.py:75-92`
的 docstring 说明它做什么：

> When the model calls the `ask_clarification` tool, this middleware:
> 1. Drops any sibling tool calls from the same AIMessage (`after_model`)
>    so they cannot execute before the user answers.
> ...
> 5. Returns a Command that interrupts execution and presents the question
> 6. Waits for user response before continuing

| 特征 | 事实 |
|---|---|
| 触发方 | **模型自己**决定要不要问 |
| 是否强制 | 否——模型不问就直接执行 |
| 谁回答 | 终端用户 |
| 是否留审批记录 | 无结构化审批事件 |
| 中断时同批工具 | **被丢弃**（`clarification_middleware.py:79-85`） |

**关键点**：clarification 是**模型主动求助**，不是**执行前的强制人工确认**。
它无法满足「高风险决策必须经人工批准才能执行」这类义务——
因为没有任何机制强制模型在危险操作前调用它。

### 3.2 Guardrail 是策略执行，不是人工审批

`guardrails/middleware.py` 在工具调用前后执行策略，可 deny 或放行。
但 deny 是**自动判定**，不产生「等待人工批准」的状态。

| 原语 | 自动判定 | 人工介入 |
|---|---|---|
| Guardrail | 是 | 否 |
| clarification | 否（模型自主） | 是（用户回答） |
| **强制审批闸门** | — | **无** |

**这一行是空白的**：DeerFlow 没有「这个操作必须等人点批准才能继续」
的原语。要继续依赖 guardrail 的自动策略，要么接受自动判定，
要么改造现有中断机制。

### 3.3 子代理的监督边界

子代理继承父级的 `user_id` / `user_role` / `authz_attributes`
（`batch_acceptance.py:38-40`），但没有独立的身份。
所以「谁批准了子代理的这个动作」在审计上**无法区分**
（见 [../identity/04-agent-identity-gap.md](../identity/04-agent-identity-gap.md)）。

## 4. 自主性控制

| 控制项 | 机制 | 边界 |
|---|---|---|
| 并发子代理数 | 执行并发默认 3（`config/subagent_runtime_config.py:12`）；截断上限 `MAX_CONCURRENT_SUBAGENT_CALLS = 64`（`subagents_config.py:17`） | 截断上限高，实际并发受执行槽位约束 |
| 单次运行的子代理总数 | `max_total_per_run`（`subagents_config.py:179`） | 可配 |
| 工具级允许/拒绝 | Guardrail 策略 | 可配 |
| 循环检测 | `tool_progress`（`config.example.yaml`） | 可配 |
| 权限门控 | 13 个权限 | 默认关闭（`app/gateway/authz.py:287`） |
| **运行时长上限** | 见 [../execution/05-execution-limits.md](../execution/05-execution-limits.md) | — |
| **成本上限** | 见 [../cost/03-budgets-and-limits.md](../cost/03-budgets-and-limits.md) | — |

**「自主性可配置」这句话的真实含义**：可配的是**边界**，
不是**是否需要确认**。框架默认让 agent 自主执行所有授权工具。

## 5. 日志与记录义务

| 记录 | 状态 |
|---|---|
| 工具调用与策略决策 | 有（journal，`guardrails/middleware.py:131`） |
| 沙箱操作 | 有（sandbox audit） |
| 模型输入输出 | 视 tracing 配置 |
| **自动日志留存期** | **无**（见 [../data/06-retention-and-residency.md](../data/06-retention-and-residency.md)） |
| 日志防篡改 | **无** |

AI Act 对高风险系统要求「在整个生命周期内自动记录」。
DeerFlow 有记录能力，但**留存期与完整性都不由框架保证**。

## 6. 缺口汇总

| 缺口 | 状态 | 边界 |
|---|---|---|
| 强制人工审批闸门 | **无** | 无「等人批准才能执行」原语 |
| clarification 的强制触发 | **无** | 模型自主决定是否问 |
| 生成内容的水印/标注 | **无机制** | 依赖产品形态 |
| 子代理的独立身份 | **无** | 继承父级身份 |
| 日志留存期 | **无** | 见 data/06 |
| 日志完整性 | **无** | 无哈希链 |
| 风险分类辅助 | **无** | 由部署方判断 |

## 7. 三条可以直接引用的结论

| # | 结论 |
|---|---|
| 1 | **clarification 是模型自主求助，不能当作合规审批**——没有强制触发机制 |
| 2 | **Guardrail 是自动策略判定，不产生人工批准状态** |
| 3 | **「人工在回路审批」这个原语在框架里不存在**，只能靠改造成本换 |

## 8. 与其他章节的关系

- 人类监督的实际能力：[../authorization/02-bounded-autonomy.md](../authorization/02-bounded-autonomy.md)
- Guardrail 机制：[../authorization/01-guardrail-layer.md](../authorization/01-guardrail-layer.md)
- Agent 身份缺口：[../identity/04-agent-identity-gap.md](../identity/04-agent-identity-gap.md)
- 事件覆盖：[../audit/03-event-coverage.md](../audit/03-event-coverage.md)
