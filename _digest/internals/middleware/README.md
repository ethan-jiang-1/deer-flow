---
title: "Agent Middleware 体系"
description: "LangGraph agent loop 和 LLM/tool 执行之间的中间层。29 个 middleware，6 种 hook 点，控制着 agent 的每一次 model 调用和 tool 执行。"
type: index
---

# Agent Middleware 体系

LangGraph agent loop 和 LLM/tool 执行之间的中间层。29 个 middleware，6 种 hook 点，控制着 agent 的每一次 model 调用和 tool 执行。

**回答的核心问题**：middleware 是认真设计的还是随意堆砌的？6 种 hook 分别在什么时候触发？洋葱链怎么 compose？我怎么加一个自己的 middleware？跟 Claude Code Hooks 有什么异同？

> **约束：不修改项目源代码。** 本 `_digest/` 下所有内容仅作研究记录。详见 [根 README](../README.md)。

## 阅读顺序

| 文件 | 内容 |
|------|------|
| **00-overview.md** | 设计哲学、Flask 对比、漂亮 vs 愚蠢的批判性分析、入口处思考 |
| **01-hooks-and-flow.md** | 6 种 hook 点详解、正向/反向执行顺序、洋葱组合、graph node vs inline |
| **02-chain-assembly.md** | 两条装配路径、RuntimeFeatures、@Next/@Prev 定位、config 驱动 |
| **03-catalog.md** | 29 个 middleware 完整清单，按 hook 点分组 |
| **04-claude-code-comparison.md** | 与 Claude Code Hooks 的全面对比：概念映射、设计哲学、互相借鉴 |

## 关键问题

- 这套 middleware 是认真设计的还是乱想的？→ `00-overview.md` 批判性分析
- 和 Claude Code Hooks 是不是一回事？→ `04-claude-code-comparison.md` 概念映射
- 和 Flask middleware 有什么异同？→ `00-overview.md` Flask 对比表
- Agent 的一轮 step 经过哪些 hook？→ `01-hooks-and-flow.md`
- 我想加一个 middleware 怎么做？→ `02-chain-assembly.md` @Next/@Prev
- 为什么 LoopDetection 的警告不在 after_model 里注入？→ `00-overview.md` 漂亮的地方
- middleware 抛异常会发生什么？→ `01-hooks-and-flow.md` 错误传播

## 源文件索引

| 组件 | 路径 |
|------|------|
| 基类 | `langchain.agents.middleware.AgentMiddleware` (LangChain >= 1.2.15) |
| Lead agent 装配 | `deerflow/agents/lead_agent/agent.py:_build_middlewares()` |
| SDK 装配 | `deerflow/agents/factory.py:_assemble_from_features()` |
| RuntimeFeatures | `deerflow/agents/features.py` |
| @Next/@Prev 装饰器 | `deerflow/agents/features.py:42-63` |
| 所有 middleware 实现 | `deerflow/agents/middlewares/` + `deerflow/guardrails/middleware.py` + `deerflow/sandbox/middleware.py` |
