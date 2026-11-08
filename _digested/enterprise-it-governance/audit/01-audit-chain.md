---
title: "审计链路"
description: "三层审计：SandboxAudit、RunJournal、completed-run evidence。"
topics: [governance, audit]
---

# 审计链路

三层审计：SandboxAudit、RunJournal、completed-run evidence。

## 审计链路

### 三层审计

| 层 | 机制 | 覆盖范围 | 格式 |
|----|------|---------|------|
| **Tool 执行审计** | `SandboxAuditMiddleware` → `logger.info("[SandboxAudit] ...")` | bash 命令 | 纯文本日志 |
| **Run 生命周期** | `RunJournal` → `record_middleware()` | run 状态变更 | 结构化（Python dict → DB/内存） |
| **Tracing** | Langfuse/LangSmith callback | LLM 调用 + tool 调用 + graph node | OpenTelemetry span |
| 🆕 **Guardrail 决策** | `GuardrailMiddleware._record_guardrail_event()` → `journal.record_middleware(tag="guardrail")` | tool_call 的 deny 与"provider 报错后放行" | 结构化（RunJournal 事件） |

### SandboxAudit 审计日志

每次 bash 执行都会记录：
- 原始命令（LLM 产出的）
- 分割后的子命令
- 高危/中危模式匹配结果
- 决策（block / warn / pass）

**缺失：** 日志不是结构化 JSON。接入 SIEM/SOAR 需要额外解析。

### RunJournal

`deerflow/runtime/journal.py` — `RunJournal` 是 run 结构化事件的汇聚点。有 `record_middleware(event_type="middleware:...")` 方法，`"guardrail"` tag 由 `MIDDLEWARE_GUARDRAIL_TAG` 定义（`journal.py:1529` 附近注释说明它构成 `event_type="middleware:guardrail"`）。

**🆕 guardrail 现在会写它**（v2.1 早期文档"guardrail 没有调用它"已不成立）：`GuardrailMiddleware._record_guardrail_event()`（`guardrails/middleware.py:131`）在三种情形下落一条 `middleware:guardrail` 事件：

| `action` | 触发条件 |
|----------|---------|
| `deny_tool_call` | 决策为 deny（policy 拒绝、本地预检拒绝、fail-closed 合成拒绝） |
| `allow_tool_call_after_provider_error` | provider 抛错但 `fail_closed=False`，按放行执行 |

**allow 决策仍然不落库**——正常放行不产生事件，这是有意的（每个 tool call 都写一条会把 journal 淹掉）。所以"某个时间段内 agent 被拒绝了哪些操作"这个问题现在**可以查 RunJournal**，但"被允许了哪些"仍然只能从 tracing/usage 侧推。

记录的 `changes` 字段：`tool_name`、`tool_call_id`、`agent_id`、`is_subagent`、`user_role`、`allow`、`policy_id`、`reason_codes`、`reason_messages`（截断到 `_REASON_MESSAGE_LIMIT`）、`fail_closed`、`provider_error`。

**两条边界**：
- **best-effort**：`record_middleware` 抛异常只记 warning，**绝不改变 tool 执行行为**（docstring 原话："audit persistence is best-effort and must never change tool execution behavior"）。
- **没有 `__run_journal` 的运行时不写**：embedded client 与 subagent 执行都跳过持久化（注释原文："Native subagents do not currently inherit `__run_journal`"）。所以 **subagent 里的 guardrail 拒绝在 journal 里是看不见的**——这是一个真实的审计盲区。

### 🆕 Completed-run evidence（2.2.0 的只读投影面）

`deerflow_extension_api/completed_run_evidence.py` 给插件一个**只读、带上限、带 coverage 声明**的已完成 run 证据视图，供外部系统做对账/报表：

| 约束 | 值 | 位置 |
|------|-----|------|
| 单页事件数 | `max_events=200`（1..2000） | `EvidenceLimits`（`:11`） |
| 单页字节 | `max_bytes=256 KiB`（1 KiB..1 MiB） | 同上 |
| 事件内容摘要 | `content_sha256`，不是原文 | `CompletedRunEvent`（`:52`） |
| 覆盖声明 | `coverage="lead-journal-v1"` | `CompletedRunSnapshot`（`:43`） |

**`coverage="lead-journal-v1"` 是诚实性声明，不是营销词**：`coverage_limits` 默认包含 "No complete background subagent, remote MCP, or external side-effect coverage."——即这份证据**不覆盖**后台 subagent、远端 MCP、外部副作用。做合规报告时不能把它当成"完整 run 记录"。

`seal_state`（默认 `"partial"`）进一步区分"这个 run 结束了"与"这份快照封口了"。宿主侧实现 `HostCompletedRunEvidenceReader`（`extensions/completed_run_evidence.py:39`）明写是给 **trusted in-process plugins, not a sandbox** 的；legacy digest 另有 1 MiB / 64 SQL chunks / 2 s 每页的硬上限，超了返回 `LIMIT_EXCEEDED` 而不是慢慢查。

**读权限**：插件必须经 `deerflow_extension_api/run_evidence.py` 的 `require_run_evidence_reader()`，宿主 resolver 返回 `None` 表示不支持（抛 `NotImplementedError`），拒绝抛 `PermissionError`，**resolver 自身的异常照常上抛**——**绝不**回退到全局 reader。

### 🆕 Skill mutation 的审计与恢复面（管理员）

`app/gateway/routers/skill_mutations.py`（prefix `/api/skill-mutations`，**admin only**）提供运维侧的恢复入口：

| 路由 | 用途 |
|------|------|
| `GET /operations` | 列出 mutation operation（`limit` ≤ 100） |
| `GET /operations/{operation_id}` | 单条（`operation_id` 必须是 32 位 hex） |
| `POST /operations/{operation_id}/recover` | 按 operation 恢复 |
| `POST /owners/{owner_id}/recover` | 按 owner 批量恢复 |

错误映射：`UNAVAILABLE`（mutation runtime 未启用）→ 503、找不到 → 404、状态冲突 → 409。PAT 够不到这些路由（见 [../identity/README.md](../identity/README.md)）。

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

