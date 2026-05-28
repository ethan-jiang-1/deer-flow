# Agent Loop — 技术内核

DeerFlow 的核心是一个 agent loop：model 产生 tool_calls → 执行 tools → model 再产生 tool_calls → ... 直到 model 输出纯文本。这个循环本身不复杂，复杂的是**循环每一圈上挂了多少东西**。

## 阅读顺序

| 文件 | 内容 |
|------|------|
| **00-loop-anatomy.md** | Agent loop 本身：谁在循环、怎么循环、边界在哪 |
| **01-middleware-as-loop.md** | 中间件不是 loop 外的东西——它就是 loop 本身的结构 |
| **02-extension-points.md** | 从内到外的扩展点：怎么加 tool、怎么加 middleware、怎么加 subagent |

## 关键问题

- Agent 的 "一圈 step" 到底发生了什么？→ `00-loop-anatomy.md`
- 这个 loop 是自己写的还是 LangGraph 的？→ `00-loop-anatomy.md` 核心发现
- middleware 跟 loop 是什么关系？→ `01-middleware-as-loop.md`
- 我想往里加东西，应该从哪个层面加？→ `02-extension-points.md`
- Subagent 的 loop 跟主 agent 的 loop 有什么不同？→ `00-loop-anatomy.md` Subagent 部分
- 前后端之间的 SSE stream 怎么跟 loop 绑定的？→ `00-loop-anatomy.md` Stream Bridge 部分

## 核心结论（先看完再读详细篇）

1. **DeerFlow 没有手写 while 循环** —— loop 由 LangGraph 的 compiled graph 驱动（model node ↔ tools node 交替），recursion_limit=100
2. **middleware 不是 loop 外面的装饰，它就是 loop 的**结构——每个 hook 点（before_model / after_model / wrap_tool_call 等）精确嵌入 graph 的执行路径
3. **三层循环嵌套**：主 agent loop（astream）→ middleware 洋葱链（每圈都穿一遍）→ subagent loop（独立线程上的独立 astream）
4. **18 个 middleware 的装配逻辑分散在两处**：`build_lead_runtime_middlewares`（基础设施层）+ `_build_middlewares`（用户功能层），两者以 append 顺序合并
5. **Loop Detection 的警告不放在 after_model 里**是有意为之——为了不破坏 OpenAI/Moonshot 的 tool-call pairing 校验。这是整个系统最精妙的设计决策之一

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
