---
title: "Tracing — 请求 Trace Id 与中间件审计事件"
description: "X-Trace-Id 无条件签发、非 HTTP 入口点绑定、loop detection / deferred tool promotion 审计事件的持久化。"
topics: [tracing, trace-id, observability, loop-detection, middleware]
---

# 请求 Trace Id 与中间件审计事件

LangSmith/Langfuse 之外的另外两层可观测性：请求级关联 id（`X-Trace-Id` / `deerflow_trace_id`）与运行级审计事件（run event store 中的 `middleware:*` 事件）。

## 源文件

| 文件 | 职责 |
|------|------|
| `deerflow/trace_context.py` | ContextVar 源头：`ensure_trace_id` / `resolve_trace_id` / `ensure_trace_context` / `request_trace_context` |
| `app/gateway/trace_middleware.py` | HTTP 入口：绑定 ContextVar + 回写响应头 + 未处理异常兜底 500 |
| `agents/middlewares/loop_detection_middleware.py` | 循环检测决策 → `middleware:loop_detection` 审计事件 |
| `agents/middlewares/tool_promotion_audit_middleware.py` | deferred 工具晋升 → `middleware:tool_promotion` 审计事件 |
| `runtime/journal.py::record_middleware()` | 两类事件的统一持久化出口（RunJournal → run event store） |

## Request Trace Id 无条件签发（#5119）

- `TraceMiddleware` **不做任何配置门控**：每个 HTTP 请求都绑定一个 trace id，并始终回写 `X-Trace-Id` 响应头（在 `http.response.start` 写入，覆盖 SSE 等流式响应而不消费 body）。
- `logging.enhance.enabled` 只决定日志记录是否打印 `trace_id` 字段——不影响 id 签发、响应头或 run metadata。因此中间件不读 `AppConfig`，与 `logging` 的重启生效契约解耦。
- **ContextVar 是唯一源**，其余载体都是派生输出、从不读回：worker 把 id 盖到 runtime context 与 `config["metadata"]`，`services.start_run` 盖到 run record。调用方发来的 `deerflow_trace_id`（`body.metadata` / `body.config.context`）会被替换——迁就它会让持久化 run 与响应头、日志互相矛盾；调用方应通过 `X-Trace-Id` 请求头钉住 id。
- 未处理异常由中间件自己发一个**带 header 的 plain 500**再 re-raise（替换 `ServerErrorMiddleware` 的响应——那一个响应恰恰最需要与日志关联）。该 500 位于 `CORSMiddleware` 之外，是 CORS-opaque 的（有意不复制 origin allowlist 以免两套策略漂移）；mid-stream 失败原样传播，已写入的 header 保留。

## 非 HTTP 入口点绑定

四个入口持有一个工作单元，但只有第一个在 ASGI 内：

| 入口 | 绑定点 |
|------|--------|
| Gateway HTTP | `TraceMiddleware` |
| 定时任务 occurrence | `ScheduledTaskService._attempt_queued_run` → `launch_scheduled_thread_run` |
| MCP task notification | `launch_mcp_task_notification_run` |
| IM inbound | `ChannelManager._worker_loop` |

（嵌入式 / TUI / CLI 路径由 `DeerFlowClient.stream()` 按 `next()` 步绑定。）绑定作用域是**一次工作单元**而非轮询循环——复用的 worker task 上泄漏的绑定会把后续 occurrence 都标成第一个 id。`ensure_trace_context` 继承外层作用域，使层级调度绑定与 Gateway 请求内的 manual trigger 归入同一 trace；HTTP 的 `request_trace_context` 则刻意不继承——伪造的请求头不能回退到上一个请求的 id。

## Loop Detection 审计（#5127 / #5344 / #5245）

`LoopDetectionMiddleware` 的 warn / hard-stop 决策以 `_LoopDecision`（action / detection_layer / tool_names / count / threshold）经 `recorder.record_middleware(tag="loop_detection", ...)` 落为 `event_type="middleware:loop_detection"` 的 run 事件：

- **只记元数据**：不含工具参数、消息内容、工具结果或参数派生 hash；审计失败仅 WARNING，绝不打断 agent run。
- **Recorder 选择**：lead-agent 走 context 里的普通 `__run_journal`；native task subagent 只拿专用的窄 recorder key（`LOOP_DETECTION_RECORDER_CONTEXT_KEY`，经父 loop 代理回父 journal）；durable batch subagent 无父 journal，不持久化。
- **Run 作用域隔离（#5344）**：hash 历史、频率窗口/计数、warning 抑制集合全部以 `(thread_id, run_id)` 为 key——同一编译图被缓存复用时每个用户 run 拿到全新预算，同一 run 的多次图重入（含隐藏 goal continuation）共享一份预算。省略 `run_id` 的嵌入调用以 `Runtime.control` 对象为锚映射到不透明生成 id（防 CPython 地址复用），`after_agent` 释放锚映射，有界 map 覆盖异常退出。生命周期细节见 `backend/docs/LOOP_DETECTION.md`。
- **跨批次 severity 优先（#5245）**：决策按严重度排序——warning 候选绝不短路同批次剩余调用的频率记账；hard limit 可立即停止扫描（整批拒绝）。hash warning 仍优先于 frequency warning；批内 burst 已衰减的频率 warning 不留陈旧抑制标记。

## Deferred 工具晋升审计（#5183）

`DeferredToolPromotionAuditMiddleware` 观察最终 `tool_search` 返回的 `Command`，把**实际生效**的晋升经 `record_tool_promotion()` 落为 `middleware:tool_promotion` 事件（source / tool_names / count / is_subagent / agent_id）：

- 必须保持在 `SkillToolPolicyMiddleware` **外层**——tool-call 包装按注册反序展开，观察 handler 的最终返回值才能排除被策略拒绝的 schema。
- `claim_tool_promotions()` 按 lead run / subagent execution 原子去重，防止并行 search 重复记账；私有 payload 不进事件。
- `McpRoutingMiddleware` 的 routing-hint 晋升复用同一 `record_tool_promotion()` 出口（`source=routing_hint`），重复 pass 不重复发事件。

## 测试覆盖

| 测试文件 | 覆盖 |
|---------|------|
| `test_trace_middleware.py` | 每个响应都带 header、ContextVar 绑定、SSE 流式、下游已设 header 不覆盖、未处理异常 500 仍带 header、`CORS_EXPOSED_HEADERS` 暴露 |
| `test_trace_entry_points.py` | 定时任务 / MCP 通知 / IM 通道三个非 HTTP 入口的一次性绑定与跨 occurrence 不泄漏 |
| `test_worker_trace_binding.py` | worker 盖章 + 调用方回声 `deerflow_trace_id` 被拒（runtime context / run metadata / checkpoint 三处一致） |
| `test_loop_detection_middleware.py` | 混合工具批次、窗口衰减、per-tool overrides、run 作用域隔离、severity 排序 |
