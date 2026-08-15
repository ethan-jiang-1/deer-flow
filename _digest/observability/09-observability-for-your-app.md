---
title: "写 DeerFlow 应用的可观测最佳实践"
description: "你自己的代码怎么挂到 DeerFlow 的同一条观测轨道上：日志带 trace_id、自定义事件走 emit_custom_event、审计走 journal.record_middleware、独立 LLM 调用接追踪。三条铁律 + 每个原语的准确用法 + 反模式。"
topics: [observability, best-practices, developer, logging, tracing]
---

# 写 DeerFlow 应用的可观测最佳实践

目标是：**你的代码和 DeerFlow 的代码在同一条观测轨道上跑**。DeerFlow 已经把日志（trace_id）、事件流（journal）、追踪（tracing）、实时流（SSE）四条轨道铺好了——你的自定义 middleware / tool / 独立 LLM 调用只要**挂上去**，就能和框架一起被看见，而不是另起一套。

## 三条铁律

1. **日志用 `logging.getLogger(__name__)`，不要 `print`** —— 开 `logging.enhance` 后，root handler 的 filter 会自动给每条记录注入 `trace_id`。你什么都没做，就能按 `trace_id` 串起来。
2. **自定义事件走 `emit_custom_event` / `aemit_custom_event`，不要裸写 `StreamWriter`** —— 这样事件同时进 LangGraph custom stream（UI/前端可见）**和** `astream_events` 回调。payload 必须带非空字符串 `type`。
3. **审计事件走 `journal.record_middleware(...)`，不要只 `logger.warning` 一条** —— 前者落 `RunEventStore`（可用 `/events` 端点按 SQL 查），后者掉进 stderr 日志大海。

## 原语准确用法

### 1. 读当前 trace_id

```python
from deerflow.trace_context import get_current_trace_id

trace_id = get_current_trace_id()   # 当前请求的关联 id；无绑定则 None
```

在入口处显式绑定（你自己的 worker / 定时任务 / 后台线程）：

```python
from deerflow.trace_context import request_trace_context  # 或 ensure_trace_context

with request_trace_context(inbound_trace_id):   # None → 自动生成
    run_your_thing()
```

### 2. 发自定义事件（前端/流可见）

在 graph 节点 / middleware hook 里：

```python
from langgraph.config import get_stream_writer
from deerflow.utils.custom_events import emit_custom_event, aemit_custom_event

writer = get_stream_writer()
emit_custom_event(
    {"type": "my_step_progress", "detail": "...", "task_id": "..."},
    writer=writer,
)
# async 侧：await aemit_custom_event(payload, writer=writer)
```

要点：
- `type` 是**非空字符串**，否则跳过 callback 分发（writer 仍然发）
- callback 分发是 best-effort（`try/except` 兜底），不会因 `astream_events` 消费方出错而打断 run

### 3. 记审计事件（可 SQL 查）

在 middleware 里，run-scoped `RunJournal` 通过 `runtime.context["__run_journal"]` 暴露：

```python
def record_my_audit(self, runtime, ...):
    journal = None
    if runtime is not None and getattr(runtime, "context", None):
        ctx = runtime.context
        if isinstance(ctx, dict):
            journal = ctx.get("__run_journal")
    if journal is None:            # 单测 / subagent / 无 event-store 路径下不存在 → 静默跳过
        return
    try:
        journal.record_middleware(
            tag="my_guard",            # 1–21 字符 → 事件名 middleware:my_guard
            name=type(self).__name__,
            hook="after_model",
            action="block_something",
            changes={"tool_name": "bash", "reason": "..."},
        )
    except Exception:
        logger.warning("Failed to record middleware:my_guard event", exc_info=True)  # 审计绝不打断执行
```

> `changes` 只放**名字/计数/id**，不要放敏感值（如被过滤的 tool arguments）——持久化它们反而违背安全过滤的初衷。

### 4. 独立 LLM 调用接追踪

你如果在 agent graph **之外**调模型（像 `MemoryUpdater`、goal 评估器那样），用模型级追踪回退：

```python
from deerflow.models import create_chat_model

model = create_chat_model("your-model", attach_tracing=True)   # 不在 graph 内 → 独立 trace
```

若你在 graph 根调用，把 Langfuse 元数据注入 config，让你的 trace 归到同一个 thread/session：

```python
from deerflow.tracing.metadata import inject_langfuse_metadata

inject_langfuse_metadata(
    config,
    thread_id=thread_id,
    user_id=user_id,
    assistant_id=agent_name,
    model_name=model_name,
    environment=env,
)
```

### 5. 自定义 tool 的结果元数据

让 tool 结果带 `deerflow_tool_meta`（`normalize_tool_result`），中间件链和下游消费方就能读懂"这步成没成、要不要换招"。正常 tool 经 `ToolErrorHandlingMiddleware` 自动 stamp；你自己直接构造 `ToolMessage` 时保持该字段。

## 挂上去的三种入口

| 你的代码 | 怎么挂 | 立即可见 |
|---------|--------|---------|
| 自定义 middleware（`extensions.middlewares` / `custom_middlewares`） | `get_stream_writer` + `emit_custom_event`、`runtime.context["__run_journal"]` + `record_middleware`、`logging.getLogger` | 前端事件流 + `/events` + 日志 |
| 自定义 tool | `logging.getLogger` + `get_current_trace_id()`；结果交给 `normalize_tool_result` 打 `deerflow_tool_meta` | 日志 + journal 的 `llm.tool.result` |
| 独立 LLM 调用（graph 外） | `create_chat_model(attach_tracing=True)` + `inject_langfuse_metadata` | Langfuse/LangSmith 独立 trace |

## 反模式

| ❌ 不要 | ✅ 要 |
|--------|------|
| `print(...)` 调试 | `logging.getLogger(__name__).info(...)`（自带 trace_id） |
| 裸写 `writer(payload)` | `emit_custom_event(payload, writer=writer)`（双发 + 有 `type` 校验） |
| `logger.warning` 记审计 | `journal.record_middleware(...)`（可 SQL 查） |
| 在 `changes` 里放 secret/tool 参数原文 | 只放名字/计数/id |
| 让审计/事件代码抛异常打断 run | `try/except` 兜底，失败只 warning |

## 验证清单（挂完之后怎么确认）

1. `logging.enhance.enabled: true`，跑一次，日志里出现 `trace_id`，且和响应头 `X-Trace-Id` 一致
2. 你的自定义事件在 `GET /api/threads/{id}/runs/{rid}/events` 里能查到（`middleware:my_guard` 等）
3. 你的独立 LLM 调用在 Langfuse 里是一个带 `deerflow_trace_id` 的独立 trace
4. 前端 SSE 能收到你的 `type` 事件（如果走了 `emit_custom_event`）

---

> 前置：先把 [08-direct-usage.md](08-direct-usage.md) 里的"最小接入"做了（SQL backend + `logging.enhance` + 追踪 + `DEER_FLOW_ENV`），否则上面的"立即可见"落不到存储层。
