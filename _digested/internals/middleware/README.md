---
title: "Agent Middleware 体系"
description: "LangGraph agent loop 与 LLM/tool 执行之间的中间层：39 个 middleware 条目位、6 种 hook 点，控制着 agent 的每一次 model 调用和 tool 执行。"
type: index
topics: [middleware, hooks, chain-assembly, agent-loop]
---

# Agent Middleware 体系

> **定位**：回答「middleware 是认真设计还是随意堆砌、6 种 hook 何时触发、洋葱链怎么 compose、自定义 middleware 怎么挂、和 Claude Code Hooks 有何异同」。
> **边界**：loop 本身在 [../agent-loop/](../agent-loop/README.md)；面向扩展作者的 hook API 视角在 [../harness-hooks/04-agent-middleware-hooks.md](../harness-hooks/04-agent-middleware-hooks.md)；具体配置字段在 [../configuration/](../configuration/README.md)。

## 阅读路径

1. **先看**：[00-overview.md](00-overview.md) — 设计哲学、Flask 对比与批判性分析。
2. **再看**：[01-hooks-and-flow.md](01-hooks-and-flow.md) — 6 种 hook 的触发时机与执行顺序。
3. **深入**：[02-chain-assembly.md](02-chain-assembly.md) — 两条装配路径与 `@Next`/`@Prev` 定位。

## 本篇目

| 文件 | 主题 | 深度 |
|---|---|---|
| [00-overview.md](00-overview.md) | 设计哲学、Flask 对比、哪些设计漂亮/哪些可疑、入口处思考 | 概览 |
| [01-hooks-and-flow.md](01-hooks-and-flow.md) | 6 种 hook、正向/反向顺序、洋葱组合、graph node vs inline、异常传播 | 概览 |
| [02-chain-assembly.md](02-chain-assembly.md) | 共享基础层 16 + lead-only 23、`RuntimeFeatures`、`@Next`/`@Prev`、config 驱动 | 深入 |
| [03-catalog.md](03-catalog.md) | 39 个条目位完整清单，按 hook 点分组，含位置编号与配置项 | 深入 |
| [04-claude-code-comparison.md](04-claude-code-comparison.md) | 与 Claude Code Hooks 的概念映射、设计哲学与互相借鉴 | 深入 |

## 宪章与约定

- 本目录无独立宪章；写作纪律沿用 [根 README](../README.md)。hook 执行流的成文文档在上游 [backend/docs/middleware-execution-flow.md](../../../backend/docs/middleware-execution-flow.md)。

## 相关目录

- [internals 父级](../README.md) — 13 个内部机制子目录的总入口。
- [agent-loop](../agent-loop/README.md) — 循环主体与 extension points。
- [harness-hooks](../harness-hooks/README.md) — 配置热加载、反射加载与扩展接入口。
- [model-layer](../model-layer/README.md) — middleware 调用的模型工厂与 streaming。
- [runtime](../runtime/README.md) — middleware 产生的流如何被发布与记录。

## 速览

- **39 个条目位（v2.2）**：共享基础层 16 + lead-only 23；含 2.2 新增的 TerminalResponse / ModelLengthFinishReason / SafetyFinishReason。
- **6 种 hook**：before/after agent、before/after model、wrap model call、wrap tool call；正向/反向顺序由 LangChain compose 决定。
- **基类与装配**：全部继承 `langchain.agents.middleware.AgentMiddleware`（`langchain>=1.3`）；`build_middlewares()`（v2.1 起公开，旧 `_build_middlewares` 已不存在）与 SDK 侧 `_assemble_from_features()` 两条装配路径，实现散在 `agents/middlewares/`、`guardrails/middleware.py`、`sandbox/middleware.py`。
- **LoopDetection 的告警不进 `after_model`**：为保住 OpenAI/Moonshot 的 tool-call pairing（见 [00](00-overview.md)）。
