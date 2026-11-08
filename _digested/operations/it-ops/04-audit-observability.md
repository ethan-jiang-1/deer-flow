---
title: "审计与可观测"
description: "Agent 干了什么？什么时候干的？花了多少钱？出问题了能回溯吗？"
topics: [governance, compliance, audit]
---

# 审计与可观测

Agent 干了什么？什么时候干的？花了多少钱？出问题了能回溯吗？

DeerFlow 有审计和观测的基础设施，但大部分是**组件级**的（logger、tracing span、SSE event），缺的是**聚合视图**（dashboard、告警、异常检测）。IT 管理者需要自己拼这些组件。

## 审计链路

### 三层审计

| 层 | 机制 | 覆盖范围 | 格式 |
|----|------|---------|------|
| **Tool 执行审计** | `SandboxAuditMiddleware` → `logger.info("[SandboxAudit] ...")` | bash 命令 | 纯文本日志 |
| **Run 生命周期** | `RunJournal` → `record_middleware()` | run 状态变更 | 结构化（Python dict → DB/内存） |
| **Tracing** | Langfuse/LangSmith callback | LLM 调用 + tool 调用 + graph node | OpenTelemetry span |

### SandboxAudit 审计日志

每次 bash 执行都会记录：
- 原始命令（LLM 产出的）
- 分割后的子命令
- 高危/中危模式匹配结果
- 决策（block / warn / pass）

**缺失：** 日志不是结构化 JSON。接入 SIEM/SOAR 需要额外解析。Guardrail deny 事件只走 `logger.warning()`，不写 RunJournal。

### RunJournal

`deerflow/runtime/journal.py` — `RunJournal` 是 run 结构化事件的汇聚点。有 `record_middleware(event_type="middleware:...")` 方法，预留了 `"guardrail"` tag。但目前 guardrail 没有调用它。

### Tracing（Langfuse / LangSmith）

`deerflow/tracing/` — 通过环境变量启用：

| 环境变量 | 作用 |
|---------|------|
| `LANGFUSE_TRACING=true` | 启用 Langfuse tracing |
| `LANGSMITH_TRACING=true` | 启用 LangSmith tracing |

两个关键设计决策：

1. **Graph root 挂载** — tracing callback 挂在 graph invocation root（不是 model 实例），确保一次 run 产生一个 trace，所有 LLM/tool/graph node 调用作为子 span。
2. **attach_tracing 的 true/false** — graph 内调用者传 `attach_tracing=False`（防止重复 span），graph 外调用者（MemoryUpdater 等）保持默认 `True`。

Trace 属性映射：

| Langfuse 字段 | DeerFlow 来源 |
|--------------|-------------|
| `langfuse_session_id` | LangGraph `thread_id` |
| `langfuse_user_id` | `get_effective_user_id()` |
| `langfuse_trace_name` | `assistant_id` / `agent_name`（默认 `lead-agent`） |
| `langfuse_tags` | `env:<DEER_FLOW_ENV>` + `model:<model_name>` |

### Agent 操作完整性验证

**当前没有。** 无法确认 agent 是否只做了它声称要做的操作。MCP/ACP 等外部集成增加了验证难度。

## 可观测

### SSE 事件流

`StreamBridge` 通过 SSE 向实时 subscriber 推送事件：

| 事件类型 | 内容 |
|---------|------|
| `metadata` | run_id, thread_id, assistant_id |
| `updates` | State values（title, artifacts, todos） |
| `events` | 自定义事件（subagent 状态、tool 进度）——包括 `task_started`, `task_running`, `task_completed`, `task_failed`, `task_timed_out`, `task_cancelled` |
| `messages-tuple` | 逐 chunk 的消息增量（AI text delta, tool_call, tool_result） |
| `error` | 错误信息 |
| `end` | run 结束（携带累计 token usage） |

### 心跳与重连

`MemoryStreamBridge` 15 秒无事件时发 `HEARTBEAT_SENTINEL` 保持连接。`Last-Event-ID` 支持 subscribe 时续传。

### OTEL / External Monitor 集成

DeerFlow 不直接集成 OpenTelemetry 或外部监控系统。但 Langfuse/LangSmith tracing callback 可以集成到外部平台。如果企业有自建监控基础设施，需要通过这些 callback 桥接。

### 缺失：Fleet Dashboard

DeerFlow 没有 agent 级别的聚合仪表盘。IT 管理者无法在一个界面看到：

- 所有活跃 agent 的状态
- Tool 调用成功率/失败率
- 策略违规趋势
- Token 消耗趋势
- 异常行为检测

**行业方向：** Microsoft Agent Governance Toolkit 提供 Agent Map 可视化；TrueFoundry Agent Gateway 提供统一的可观测仪表盘。DeerFlow 的数据（RunJournal、tracing span、SSE events）**能**支撑这些能力，只是目前没有内建 UI。

## 成本归属

### Token 用量追踪

`TokenUsageMiddleware` 在每个 AIMessage 上标注 `usage_metadata`（input_tokens, output_tokens, total_tokens）。收集粒度是**每个 LLM 调用**。

### Subagent 成本合并

Subagent 的 token 消耗由 `SubagentTokenCollector` 收集，缓存在 `_subagent_usage_cache` 中（key = `tool_call_id`）。`TokenUsageMiddleware` 在下一轮 `after_model` 中从缓存中取出 subagent 用量，合并到触发 subagent 的 AIMessage 上。

**成本归属链：**
```
Lead Agent 第 N 轮 AIMessage (dispatch 3 个 subagent)
    → subagent_1 token usage → 合并到 AIMessage.usage_metadata
    → subagent_2 token usage → 合并到 AIMessage.usage_metadata
    → subagent_3 token usage → 合并到 AIMessage.usage_metadata
```

这样，一次 "dispatch subagent → subagent 工作 → 返回结果" 的完整 token 消耗归属于触发它的父 message。

### stream_usage 自动启用

`create_chat_model()` 对自定义 base_url 的 OpenAI-compatible provider 自动启用 `stream_usage=True`。原因是 LangChain 只在标准 OpenAI endpoint 下默认开启 stream_usage——自定义 gateway（如 doubao、deepseek）会静默丢失 usage 数据。

### 缺失：实时成本仪表盘

- 有 per-model token 统计，但无 per-agent 汇总
- 有 per-run token 统计，但无预算上限和实时告警
- 有 tracing span（Langfuse），但无成本归因到具体 user/thread 的聚合视图

## 部署与运维

### 配置热更新

| 类型 | 变更方式 | 生效时间 |
|------|---------|---------|
| 基础设施（database, sandbox, channels） | 编辑 config.yaml | **需要重启** |
| 策略（model, tool, memory, prompt） | 编辑 config.yaml | mtime 检测 → 下次请求 |
| MCP servers | `PUT /api/mcp/config` 或编辑 extensions_config.json | 立即 |
| Skills 开关 | `PUT /api/skills/{name}` 或编辑 extensions_config.json | 立即 |

### 健康检查

`GET /health` — Gateway 健康检查端点。不涉及 agent runtime 深度健康检测。

### 迁移

`persistence/migrations/` — Alembic-based 数据库 schema 迁移。支持 user isolation 迁移脚本 `scripts/migrate_user_isolation.py`。

### 缺失

- 无 Agent 级 SLO/error budget
- 无 Circuit breaker 级别的自动降级（LLMErrorHandlingMiddleware 有 per-call retry + circuit breaker，但无 agent 级熔断）
- 无 Chaos engineering 支持
- 无 Agent 灰度发布
