---
title: "追踪三 Provider 综述"
description: "LangSmith、Langfuse 是 graph-root 挂载的 LangChain callback（一次 run 一个根 trace）；Monocle 是 process-global OTel 自动插桩（只在 Gateway lifespan 初始化）。三者都靠环境变量开关。"
topics: [tracing, observability, langsmith, langfuse, monocle]
---

# 追踪三 Provider 综述

三个 provider 的结构性差异比表面大——前两个是"callback 挂 graph 根"，第三个是"process-global 自动插桩"。深潜细节见 [operations/tracing/](../tracing/)，这里给决策用的全景。

| 维度 | LangSmith | Langfuse | Monocle |
|------|-----------|----------|---------|
| 机制 | LangChain callback | LangChain callback（v4，OTel-based） | **不是 callback**：`monocle_apptrace.setup_monocle_telemetry()` 装 process-global OTel `TracerProvider` + 自动插桩 |
| 附着点 | graph 根（`make_lead_agent` / `stream()`） | 同左 | Gateway lifespan（`app.py`），**仅此一处** |
| 覆盖路径 | 全部入口（含 embedded/TUI） | 同左 | 仅 Gateway；embedded/TUI 需自己调 `setup_monocle_tracing_if_enabled()` |
| DeerFlow 注入 | metadata | metadata + `deerflow_trace_id` | 仅 `workflow_name="deer-flow"`，其余 span 属性全由 Monocle metamodel 产出 |
| 开关 | `LANGSMITH_TRACING` 等 | `LANGFUSE_TRACING` 等 | `MONOCLE_TRACING` + `MONOCLE_EXPORTERS`（file/console/okahu/s3/blob/gcs） |
| 输出 | LangSmith 平台 | Langfuse 平台 | `.monocle/` 文件 / console / okahu / 对象存储 |

## 为什么必须挂在 graph 根

Langfuse v4 只在 `on_chain_start(parent_run_id=None)` 时把 `RunnableConfig.metadata` 提升到**根 trace**。callback 挂在模型级，每个 LLM 调用都成独立 trace，metadata 永远到不了根。所以一次 run 一个 trace、所有 node/LLM/tool 是子 span 的前提，是"挂在 graph 根"。

图外调用者（`MemoryUpdater`、`goal` 评估器、`oneshot_llm`）不在 agent graph 内，退回模型级 `attach_tracing=True`，各自独立 trace、自己注 metadata。

## 关键元数据映射（Langfuse）

| Langfuse 字段 | DeerFlow 来源 |
|--------------|--------------|
| `langfuse_session_id` | LangGraph `thread_id` |
| `langfuse_user_id` | `get_effective_user_id()`（subagent 用 `task_tool` 时捕获的 user） |
| `langfuse_trace_name` | `assistant_id` / `agent_name`（subagent 为 `subagent:<name>`） |
| `langfuse_tags` | `env:<DEER_FLOW_ENV>` + `model:<model_name>` |
| `deerflow_trace_id` | 当前请求 trace context，与 `X-Trace-Id` 对齐 |

调用方键通过 `setdefault` 优先——外部系统可注入自己的 `langfuse_session_id` 关联到外部 trace。

## 配置检测三层（`tracing_config.py`）

1. **env → `TracingConfig`**（Pydantic）：`enabled_providers`（启用且凭证齐全）vs `explicitly_enabled_providers`（flag 真但凭证可能缺）
2. **env flag 检测**：`_TRUTHY_VALUES = {1,true,yes,on}`，LangSmith 兼容三个旧命名
3. **double-checked 缓存**：`TracingConfig` 进程启动后只建一次，`reset_tracing_config()` 供测试清理

**凭证不全会抛 `ValueError`**（不是静默跳过）：设了 `LANGFUSE_TRACING=true` 但缺 key，`build_tracing_callbacks()` 第 1 步 `validate_enabled_tracing_providers()` 直接报错。

## 共存

Langfuse v4 与 Monocle 都基于 OTel——后初始化的复用已存在的 global `TracerProvider`，两边都不丢 span（有测试钉住）。LangSmith 是普通 callback，天然共存。设 `DEER_FLOW_ENV` 打环境标签，Langfuse UI 里按 tag 过滤。
