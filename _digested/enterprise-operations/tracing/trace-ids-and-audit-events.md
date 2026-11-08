---
title: "Tracing — 中间件审计事件（运维侧补充）"
description: 'X-Trace-Id 无条件签发、非 HTTP 入口点绑定、loop detection / deferred tool promotion 审计事件的持久化。'
topics: [tracing, observability, loop-detection, middleware]
verified_against: v2.2.0
last_verified: 2026-11-08
---

# 中间件审计事件（运维侧补充）

> **边界**：请求级 trace id（`X-Trace-Id` / `deerflow_trace_id`）与非 HTTP 入口点绑定以 [observability/01](../../observability/01-logging-and-trace-context.md) 为 canonical；本页只保留 loop_detection / tool_promotion 两个运维侧审计细节，不再重写 trace id 机制。

## 源文件

| 文件 | 职责 |
|------|------|
| `agents/middlewares/loop_detection_middleware.py` | 循环检测决策 → `middleware:loop_detection` 审计事件 |
| `agents/middlewares/tool_promotion_audit_middleware.py` | deferred 工具晋升 → `middleware:tool_promotion` 审计事件 |
| `runtime/journal.py::record_middleware()` | 两类事件的统一持久化出口（RunJournal → run event store） |

## Loop Detection 审计（#5127 / #5344 / #5245）

`LoopDetectionMiddleware` 的 warn / hard-stop 决策以 `_LoopDecision`（action / detection_layer / tool_names / count / threshold）经 `recorder.record_middleware(tag="loop_detection", ...)` 落为 `event_type="middleware:loop_detection"` 的 run 事件：

- **只记元数据**：不含工具参数、消息内容、工具结果或参数派生 hash；审计失败仅 WARNING，绝不打断 agent run。
- **Recorder 选择**：lead-agent 走 context 里的普通 `__run_journal`；native task subagent 只拿专用的窄 recorder key（`LOOP_DETECTION_RECORDER_CONTEXT_KEY`，经父 loop 代理回父 journal）；durable batch subagent 无父 journal，不持久化。
- **Run 作用域隔离（#5344）**：hash 历史、频率窗口/计数、warning 抑制集合全部以 `(thread_id, run_id)` 为 key——同一编译图被缓存复用时每个用户 run 拿到全新预算，同一 run 的多次图重入（含隐藏 goal continuation）共享一份预算。省略 `run_id` 的嵌入调用以 `Runtime.control` 对象为锚映射到不透明生成 id（防 CPython 地址复用），`after_agent` 释放锚映射，有界 map 覆盖异常退出。生命周期细节见 `backend/docs/LOOP_DETECTION.md`。
- **跨批次 severity 优先（#5245）**：决策按严重度排序——warning 候选绝不短路同批次剩余调用的频率记账；hard limit 可立即停止扫描（整批拒绝）。hash warning 仍优先于 frequency warning；批内 burst 已衰减的频率 warning 不留陈旧抑制标记。

## Deferred 工具晋升审计（#5183）

`DeferredToolPromotionAuditMiddleware` 观察最终 `tool_search` 返回的 `Command`，把**实际生效**的晋升经 `record_tool_promotion()` 落为 `middleware:tool_promotion` 事件（source / tool_names / count / is_subagent / agent_id）：

- 必须保持在 `SkillToolPolicyMiddleware`（v2.2.0 已删除）**外层**——tool-call 包装按注册反序展开，观察 handler 的最终返回值才能排除被策略拒绝的 schema。
- `claim_tool_promotions()` 按 lead run / subagent execution 原子去重，防止并行 search 重复记账；私有 payload 不进事件。
- `McpRoutingMiddleware` 的 routing-hint 晋升复用同一 `record_tool_promotion()` 出口（`source=routing_hint`），重复 pass 不重复发事件。

## 测试覆盖

| 测试文件 | 覆盖 |
|---------|------|
| `test_trace_middleware.py` | 每个响应都带 header、ContextVar 绑定、SSE 流式、下游已设 header 不覆盖、未处理异常 500 仍带 header、`CORS_EXPOSED_HEADERS` 暴露 |
| `test_trace_entry_points.py` | 定时任务 / MCP 通知 / IM 通道三个非 HTTP 入口的一次性绑定与跨 occurrence 不泄漏 |
| `test_worker_trace_binding.py` | worker 盖章 + 调用方回声 `deerflow_trace_id` 被拒（runtime context / run metadata / checkpoint 三处一致） |
| `test_loop_detection_middleware.py` | 混合工具批次、窗口衰减、per-tool overrides、run 作用域隔离、severity 排序 |
