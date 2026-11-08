---
title: "Agent Loop — 技术内核"
description: "DeerFlow 的核心是一个 agent loop：model 产生 tool_calls → 执行 tools → 直到输出纯文本；复杂的是循环每一圈上挂了多少东西——middleware 洋葱链、Pregel superstep 与 subagent 三层嵌套。"
type: index
topics: [agent-loop, langgraph, middleware, extension-points]
---

# Agent Loop — 技术内核

> **定位**：回答「loop 到底在哪（谁的代码在循环）、middleware 怎么嵌进 loop、想扩展应从哪一层加」，给要改 agent 行为或排查循环问题的开发者。
> **边界**：不逐个介绍 middleware 条目（去 [../middleware/](../middleware/README.md)）；不覆盖运行管道与 SSE 传输（去 [../runtime/](../runtime/README.md)）；不覆盖模型适配（去 [../model-layer/](../model-layer/README.md)）。

## 阅读路径

1. **先看**：[00-loop-anatomy.md](00-loop-anatomy.md) — 谁在循环、怎么循环、边界在哪。
2. **再看**：[01-middleware-as-loop.md](01-middleware-as-loop.md) — middleware 不是 loop 外面的装饰，它就是 loop 的结构。
3. **深入**：[03-code-trace.md](03-code-trace.md) — 从 `run_agent()` 到 Pregel `tick()` 的完整调用链。

## 本篇目

| 文件 | 主题 | 深度 |
|---|---|---|
| [00-loop-anatomy.md](00-loop-anatomy.md) | 循环主体、LangGraph compiled graph、三层嵌套、subagent 与 Stream Bridge 的绑定 | 概览 |
| [01-middleware-as-loop.md](01-middleware-as-loop.md) | middleware 洋葱链如何构成 loop、hook 点在执行路径上的位置 | 概览 |
| [02-extension-points.md](02-extension-points.md) | 从内到外：加 tool / middleware / subagent 的选择 | 深入 |
| [03-code-trace.md](03-code-trace.md) | `run_agent()` → `agent.astream()` → `PregelLoop.tick()` 逐层追踪 | 深入 |
| [04-error-handling-and-debugging.md](04-error-handling-and-debugging.md) | loop detection 双层检测、LLM 重试、tool 错误元数据、日志与调优 | 深入 |

## 宪章与约定

- 本目录无独立宪章；写作纪律沿用 [根 README](../README.md)。

## 相关目录

- [internals 父级](../README.md) — 13 个内部机制子目录的总入口。
- [middleware](../middleware/README.md) — 6 种 hook 点与 39 个条目位的完整目录。
- [runtime](../runtime/README.md) — `run_agent()` 所在的运行管道、流发布与 journal。
- [model-layer](../model-layer/README.md) — loop 每圈调用的模型工厂与 streaming。
- [harness-hooks](../harness-hooks/README.md) — 面向扩展作者的 hook 接线与动态加载。

## 速览

- **loop 不在 DeerFlow 里**：`async for chunk in agent.astream()` 是消费端，真正的 `while` 在 LangGraph 的 `PregelLoop.tick()`。
- **三层嵌套**：Pregel superstep loop（LangGraph）→ middleware 洋葱链（LangChain compose + DeerFlow 实现）→ subagent loop（DeerFlow 独立线程）。
- **100% 复用标准 hook**：39 个条目位全部是 `AgentMiddleware` 子类或标准类实例的组合，没有自造 hook 协议。
- **Loop Detection 的警告故意不进 `after_model`**：避免破坏 OpenAI/Moonshot 的 tool-call pairing 校验（依据见 [00](00-loop-anatomy.md)）。
- **源码入口**：`runtime/runs/worker.py:run_agent()`、`agents/lead_agent/agent.py:_make_lead_agent()` / `build_middlewares()`、`subagents/executor.py:_aexecute()`；loop 本体在 `langgraph/pregel/_loop.py`，`@Next/@Prev` 在 `agents/features.py:42-63`。
