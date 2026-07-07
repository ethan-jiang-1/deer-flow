---
title: "Agent Loop — 技术内核"
description: "DeerFlow 的核心是一个 agent loop：model 产生 tool_calls → 执行 tools → model 再产生 tool_calls → ... 直到 model 输出纯文本。这个循环本身不复杂，复杂的是**循环"
type: index
---

# Agent Loop — 技术内核

DeerFlow 的核心是一个 agent loop：model 产生 tool_calls → 执行 tools → model 再产生 tool_calls → ... 直到 model 输出纯文本。这个循环本身不复杂，复杂的是**循环每一圈上挂了多少东西**。

**回答的核心问题**：agent loop 到底在哪（谁的代码在循环）、middleware 怎么嵌入 loop、想扩展应该从哪个层面加。

> **约束：不修改项目源代码。** 本 `_digest/` 下所有内容仅作研究记录。详见 [根 README](../README.md)。

## 阅读顺序

| 文件 | 内容 |
|------|------|
| **00-loop-anatomy.md** | Agent loop 本身：谁在循环、怎么循环、边界在哪 |
| **01-middleware-as-loop.md** | 中间件不是 loop 外的东西——它就是 loop 本身的结构 |
| **02-extension-points.md** | 从内到外的扩展点：怎么加 tool、怎么加 middleware、怎么加 subagent |
| **03-code-trace.md** | 代码路径追踪：从 `run_agent()` 到 Pregel `tick()` 的完整调用链，每步标注谁负责 |
| **04-error-handling-and-debugging.md** | 🆕 错误处理与调试：loop detection、LLM 重试、tool 元数据、日志、认证、大文件 |

## 关键问题

- Agent 的 "一圈 step" 到底发生了什么？→ `00-loop-anatomy.md`
- 这个 loop 是自己写的还是 LangGraph 的？→ `00-loop-anatomy.md` 核心发现 + `03-code-trace.md` 精确代码路径
- middleware 跟 loop 是什么关系？→ `01-middleware-as-loop.md`
- 我想往里加东西，应该从哪个层面加？→ `02-extension-points.md`
- Subagent 的 loop 跟主 agent 的 loop 有什么不同？→ `00-loop-anatomy.md` Subagent 部分
- 前后端之间的 SSE stream 怎么跟 loop 绑定的？→ `00-loop-anatomy.md` Stream Bridge 部分
- **loop 的 while 循环代码到底在哪？** → `03-code-trace.md` Layer D：PregelLoop.tick()
- **DeerFlow 真的利用了 LangChain 的 middleware 吗？** → `03-code-trace.md` Layer E：100% 利用

## 核心结论（先看完再读详细篇）

1. **DeerFlow 没有手写 while 循环** —— loop 在 LangGraph 的 `PregelLoop.tick()` 里（`langgraph/pregel/_loop.py`）。DeerFlow 的 `async for chunk in agent.astream()` 是**消费端**，不是循环本身
2. **DeerFlow 100% 利用了 LangChain 的 middleware hook 体系** —— 29 个 middleware 全部是标准 `AgentMiddleware` 子类，没有自己发明 hook 协议
3. **middleware 不是 loop 外面的装饰，它就是 loop 的**结构——每个 hook 点（before_model / after_model / wrap_tool_call 等）精确嵌入 graph 的执行路径
4. **三层循环嵌套**：Pregel superstep loop（LangGraph）→ middleware 洋葱链（LangChain compose + DeerFlow 实现）→ subagent loop（DeerFlow 独立线程）
5. **Loop Detection 的警告不放在 after_model 里**是有意为之——为了不破坏 OpenAI/Moonshot 的 tool-call pairing 校验

## 源文件索引

| 组件 | 路径 |
|------|------|
| Agent loop 入口 | `packages/harness/deerflow/runtime/runs/worker.py:run_agent()` |
| Lead agent 工厂 | `packages/harness/deerflow/agents/lead_agent/agent.py:_make_lead_agent()` |
| Middleware 装配 | `packages/harness/deerflow/agents/lead_agent/agent.py:_build_middlewares()` |
| Runtime middlewares | `packages/harness/deerflow/agents/middlewares/tool_error_handling_middleware.py:build_lead_runtime_middlewares()` |
| Subagent 执行器 | `packages/harness/deerflow/subagents/executor.py:SubagentExecutor._aexecute()` |
| Loop 检测 | `packages/harness/deerflow/agents/middlewares/loop_detection_middleware.py` |
| RunManager | `packages/harness/deerflow/runtime/runs/manager.py` |
| StreamBridge | `packages/harness/deerflow/runtime/stream_bridge/` |
| 前端 SSE 消费 | `frontend/src/core/threads/hooks.ts` |
| Middleware 定位装饰器 | `packages/harness/deerflow/agents/features.py:@Next/@Prev` |
| **LangChain create_agent** | `langchain/agents/factory.py` (v1.2.15, 1870 行) — 构建 StateGraph、compose 洋葱链 |
| **LangGraph Pregel** | `langgraph/pregel/__init__.py` + `_loop.py` — BSP superstep 循环 |
| **LangChain AgentMiddleware** | `langchain/agents/middleware/types.py` (v1.2.15) — 基类、6 种 hook、ModelRequest/ModelResponse 类型 |
