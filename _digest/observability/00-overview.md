---
title: "诊断与观察全景"
description: "DeerFlow 有五层观测栈（日志 → 事件流 → 追踪 → 控制台 → 实时流），全部是组件级、无聚合仪表盘。这里画一次 run 从请求到 trace 的完整数据流。"
topics: [observability, logging, tracing, debugging]
---

# 诊断与观察全景

DeerFlow 没有"一个监控大盘"这种聚合视图——它的观测能力是**组件级**的，分布在五层里。理解这五层各自干什么、落在哪、怎么串联，是上线前诊断能力的地基。

## 五层观测栈

| 层 | 机制 | 粒度 | 落在哪 | 谁看 |
|----|------|------|--------|------|
| **1. 日志** | `logging_config.py` + `trace_context.py` + `TraceMiddleware` | 请求/进程级 | stderr（Docker 捕获） | 开发者、`grep` |
| **2. 事件流** | `RunJournal` → `RunEventStore` | run 级结构化事件 | memory / JSONL / DB | 审计、回放、`/events` 调试端点 |
| **3. 追踪** | LangSmith / Langfuse / Monocle | LLM + tool + node span | 外部平台 | 调用链、延迟、成本 |
| **4. 控制台/成本** | `GET /api/console/*` | 跨线程聚合 | SQL（sqlite/postgres） | 运营、预算、`active_runs` 卡死检测 |
| **5. 实时流** | `StreamBridge` SSE | 逐 chunk 增量 | 前端 / IM channel | 用户、实时进度 |

跨层有一条**关联主线**：`trace_id`（`deerflow_trace_id`）。它把日志、HTTP 响应头、Langfuse trace 三者串在一起，是"出问题时从哪个点都能定位到同一次请求"的钥匙（详见 `01`）。

## 一次 run 的完整数据流

```
HTTP POST /api/threads/{id}/runs/stream
  │
  ├─ TraceMiddleware ─ 绑定 trace_id（继承 X-Trace-Id 或生成 uuid4().hex）
  │     ├─ 写响应头 X-Trace-Id（在 http.response.start，覆盖 SSE 流式响应）
  │     ├─ 注入每条日志的 trace_id 字段
  │     └─ 注入 Langfuse metadata 的 deerflow_trace_id
  │
  └─ worker.run_agent()
        ├─ RunJournal（LangChain callback handler）
        │     ├─ 标准化为 RunEvent → RunEventStore（run.start → llm.* → run.end）
        │     └─ 累计 token 用量 → RunRow（total_tokens / token_usage_by_model）
        ├─ build_tracing_callbacks() → LangSmith/Langfuse handler → 外部 trace（一次 run 一个根 trace）
        └─ StreamBridge → SSE（metadata / updates / events / messages-tuple / error / end）
                              → 前端 / IM channel

run 结束后：
  ├─ RunRow（status / duration / error / total_tokens / token_usage_by_model）
  │     └─ Console API 可查（stats / runs / usage，配 pricing 后算成本）
  └─ 终端事件（run.delivery receipt 等）落 RunEventStore
```

## 关键架构事实

- **两层附着**：追踪 handler 挂在 **graph 根**（`make_lead_agent` / `DeerFlowClient.stream` 在 `graph.astream()` 前追加），不是模型级——这样一次 run 产生**一个**根 trace，所有 node/LLM/tool 都是子 span。图外调用者（`MemoryUpdater` 等）才用模型级 `attach_tracing=True` 回退。
- **RunJournal 是回调→事件的汇聚点**：它既喂事件流（观测），又累计 token（成本），是第 2、4 层之间的枢纽。
- **`RunRow` 是控制台的数据源**：Console API 直接查 `runs` / `threads_meta` 表，不扩宽 `RunStore` 运行时面，只读、短命查询。
- **没有聚合仪表盘**：以上全是"原料"，缺的是 dashboard、告警、异常检测。要上线，得自己拼（见 `07`）。

## 阅读路径

- 想搞清楚 **trace_id 关联 + 结构化日志** → `01-logging-and-trace-context.md`
- 想搞清楚 **run 到底发生了什么、怎么回放** → `02-run-events-and-journal.md`
- 想搞清楚 **调用链/延迟/成本外部可视化** → `03-tracing-providers.md`
- 想搞清楚 **运营数据（跑了多少、花了多少钱）** → `04-console-and-cost.md`
- 想搞清楚 **实时看什么** → `05-live-streaming.md`
- 要 **上手诊断问题** → `06-debugging-toolkit.md`
- 要 **上线前的检查清单** → `07-production-checklist.md`
