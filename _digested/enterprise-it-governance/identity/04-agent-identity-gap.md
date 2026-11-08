---
title: "Agent 身份：缺失的一环"
description: "Agent 没有独立身份，继承用户权限——企业治理的首要缺口。"
topics: [governance, identity]
---

# Agent 身份：缺失的一环

Agent 没有独立身份，继承用户权限——企业治理的首要缺口。

## Agent 身份：缺失的一环

2026 年行业共识是 **Agent 应该有自己的身份（Non-Human Identity, NHI）**，独立于触发它的用户。原因：

```
用户 Alice → 触发 Agent → Agent 执行操作 → 审计记录显示 "Alice 做了 X"

但实际上是 Agent 决策了 X，Alice 只是说了 "帮我整理文件"
```

DeerFlow 目前没有 NHI 概念。Agent 操作被审计为**用户操作**。这带来了几个问题：

- **权限最小化做不到** — Agent 继承了用户的所有权限，即使任务只需要其中的一小部分
- **责任归属模糊** — 如果 agent 做了用户没预料到的事（如 LLM 自发决定删文件），审计记录显示是用户干的
- **多 agent 协作无区分** — Lead agent、subagent、ACP agent 的操作都归因到同一个 user

**行业方向：** 参考 Oasis AAM Framework、Microsoft Agent Governance Toolkit 的 Agent DID（Decentralized Identifier）和 Zero Standing Privileges（无静态权限，每次操作申请临时授权）。DeerFlow 与这些方案不矛盾——可以在上层加。

