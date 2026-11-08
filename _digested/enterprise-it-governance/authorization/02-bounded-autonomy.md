---
title: "Bounded Autonomy"
description: "DeerFlow 的自动/人工边界在哪里。"
topics: [governance, authorization]
---

# Bounded Autonomy

DeerFlow 的自动/人工边界在哪里。

## Bounded Autonomy：DeerFlow 的自动/人工边界

业界最佳实践是把 agent 操作分成 observe/recommend/execute 三级。DeerFlow 目前的边界：

| 操作级别 | DeerFlow 行为 |
|---------|-------------|
| **Observe（读）** | Agent 可以自由读文件、ls、grep——无人工审批 |
| **Execute（写/删/运行）** | Agent 可以自由执行——除非被 Guardrail 或 SandboxAudit 拦截 |
| **高危操作** | Guardrail deny / SandboxAudit block——agent 收到 error，可以换个方法 |
| **人机交互** | `ask_clarification` tool → ClarificationMiddleware → Command(goto=END) → 等人回复 |

**关键区别：** DeerFlow 的 "人机交互" 是 agent 主动问问题（"你想用哪个文件？"），不是权限决策对话框（"agent 要删文件，允许吗？"）。如果你需要高危操作人工审批——目前需要自定义 Guardrail provider 来实现。

