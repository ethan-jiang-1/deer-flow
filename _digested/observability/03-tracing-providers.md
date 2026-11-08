---
title: "追踪三 Provider 综述"
description: "LangSmith、Langfuse 是 graph-root 挂载的 LangChain callback（一次 run 一个根 trace）；Monocle 是 process-global OTel 自动插桩（只在 Gateway lifespan 初始化）。三者都靠环境变量开关。"
topics: [tracing, observability, langsmith, langfuse, monocle]
---

# 追踪三 Provider 综述

三个 provider 的结构性差异比表面大——前两个是"callback 挂 graph 根"，第三个是"process-global 自动插桩"。深潜细节见 [operations/tracing/](../operations/tracing/)，这里给决策用的全景。

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
| `langfuse_tags` | `env:<DEER_FLOW_ENV>` + `model:<有效模型名>`（🆕 v2.2.0 语义收紧，见下） |
| `deerflow_trace_id` | 当前请求 trace context，与 `X-Trace-Id` 对齐 |

调用方键通过 `setdefault` 优先——外部系统可注入自己的 `langfuse_session_id` 关联到外部 trace。

### 🆕 v2.2.0：`model:` tag 跟随"实际会跑的模型"

v2.1.0 的 `model:<name>` 打的是**请求里写的**模型名。v2.2.0 改成打**装配（assembly）之后实际生效**的模型：

- Gateway 路径 `runtime/runs/worker.py:1400`：`effective_model = _assembled_model_name(agent_result) or record.model_name`，注释写明 "Trace the model that will run, rather than the model name originally requested"；随后 `inject_langfuse_metadata(..., model_name=effective_model, ...)`（`worker.py:1402-1410`）。
- 注入点时机也变了：`inject_langfuse_metadata` 现在在**模型选择之后、调用 graph 之前**执行（v2.1.0 是在构造 graph 前就地 merge）——见 `tracing/AGENTS.md` 的 "after model selection, before invoking the graph"。
- 覆盖内置 Gateway lead-agent 与嵌入式 client 两条路径（含默认模型与 fallback 选择）；**自定义裸 graph factory 仍回落到请求的模型名**。
- 顺带：`worker.py:1510-1511` 在装配模型与 `record.model_name` 不一致时调 `run_manager.update_model_name()`，所以 `RunRow.model_name` 也跟实际模型对齐——Langfuse tag 与 Console 的成本归属看的是同一个名字。

**为什么重要**：按 `model:` tag 做 Langfuse 成本看板时，v2.1.0 会把"请求了 A 但 fallback 到 B"的 run 记到 A 名下。升级后这类 run 会**换桶**，历史看板和新数据不可直接比。

## 配置检测三层（`tracing_config.py`）

1. **env → `TracingConfig`**（Pydantic）：`enabled_providers`（启用且凭证齐全）vs `explicitly_enabled_providers`（flag 真但凭证可能缺）
2. **env flag 检测**：`_TRUTHY_VALUES = {1,true,yes,on}`，LangSmith 兼容三个旧命名
3. **double-checked 缓存**：`TracingConfig` 进程启动后只建一次，`reset_tracing_config()` 供测试清理

**凭证不全会抛 `ValueError`**（不是静默跳过）：设了 `LANGFUSE_TRACING=true` 但缺 key，`build_tracing_callbacks()` 第 1 步 `validate_enabled_tracing_providers()` 直接报错。

## 共存

Langfuse v4 与 Monocle 都基于 OTel——后初始化的复用已存在的 global `TracerProvider`，两边都不丢 span（有测试钉住）。LangSmith 是普通 callback，天然共存。设 `DEER_FLOW_ENV` 打环境标签，Langfuse UI 里按 tag 过滤。

## 代码级契约（`tracing/` 四模块，v2.2.0 实测）

包入口 `tracing/__init__.py` 只导出 4 个名字：`build_tracing_callbacks` / `build_langfuse_trace_metadata` / `inject_langfuse_metadata` / `setup_monocle_tracing_if_enabled`。三个实现模块分工明确（另有 `AGENTS.md` 描述装配约定）：`factory.py` 65 行、`metadata.py` 114 行、`monocle.py` 69 行、`__init__.py` 10 行——**v2.1.0→v2.2.0 只有 `AGENTS.md` 变了（4 行），代码零改动**。

### `factory.py::build_tracing_callbacks()`（65 行）

唯一的 callback 装配点（graph 根调用它）：

1. 先 `validate_enabled_tracing_providers()` —— **凭证不全直接抛 `ValueError`**，不静默降级；
2. `enabled_providers` 为空 → 返回 `[]`（LangSmith 本体没开时整条路径零开销）；
3. 逐 provider 构造，**每家的构造异常被包成带 provider 名的 `RuntimeError`**（`LangSmith tracing initialization failed: …` / `Langfuse tracing initialization failed: …`），不会静默吞掉；
4. Langfuse 的构造分两步：先用 `secret_key/public_key/host` 初始化 `Langfuse()` **客户端单例**（langfuse>=4 的凭证注入点），再把 `CallbackHandler(public_key=...)` 挂到该单例上——callback 本身不持密钥；
5. **Monocle 不出现在返回的 callback 列表里**（它不是 callback provider）。若 `MONOCLE_TRACING` 开着但本进程没初始化过，这里只打一条 debug 提示，告诉 embedded/TUI 调用方要自己调 `setup_monocle_tracing_if_enabled()`。

### `metadata.py`：两个入口 + 4 个保留键

- `build_langfuse_trace_metadata(...)` **在 Langfuse 未启用时返回 `{}`**——所以调用方可以无条件 merge，不必自己判断 provider。返回的键就是 Langfuse v4 `_parse_langfuse_trace_attributes` 认识的那 4 个保留键（`langfuse_session_id` / `langfuse_user_id` / `langfuse_trace_name` / `langfuse_tags`），外加**总是**写入 `deerflow_trace_id`（来自 `resolve_trace_id()`，把 Langfuse trace 与日志行/`X-Trace-Id` 对上）。`user_id` 缺省回落 `DEFAULT_USER_ID`（no-auth 模式下 Users 页仍可用）；`langfuse_trace_name` 缺省 `"lead-agent"`；tags 只在有值时给出 `env:<…>` / `model:<…>`。
- `inject_langfuse_metadata()` 是**就地 merge**（改 `config["metadata"]`），用 `setdefault` 让**调用方已提供的键优先**（外部系统可自行指定 `langfuse_session_id` 关联到外部 trace）。它被 `runtime/runs/worker.py` 与嵌入式 `client.py` **共用**，目的就是防止两条路径漂移；Langfuse 未启用时是 no-op。

### `monocle.py`：一次性的进程级 setup

`setup_monocle_tracing_if_enabled()` 用模块级 `_setup_completed` 标志保证**幂等**（返回 bool 表示是否真的执行了 setup），初始化时固定 `setup_monocle_telemetry(workflow_name="deer-flow", monocle_exporters_list=…)`；`is_monocle_setup_completed()` 供 `factory.py` 判断"要不要提示调用方自己初始化"。
