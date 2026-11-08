---
title: "TypeSafe (Jev) — 共用判定客户端"
description: "`deerflow/typesafe/` 是 v2.2.0 新增的传输层：一套客户端（生命周期/认证/重试/截止预算/有界响应解析/错误分类/共享键）被三类适配器共用，而状态内容、问题与阈值、失败方向、缓存、业务审计全部留在适配器里——风险门 fail-closed，memory 预筛 fail-soft。"
type: index
---

# TypeSafe (Jev) — 共用判定客户端

`backend/packages/harness/deerflow/typesafe/` 在 v2.2.0 里是**全新目录**，共 **1141 行**（不含 `AGENTS.md` 的 71 行与 `__pycache__`）：`backend/packages/harness/deerflow/typesafe/client.py` 580 行 + `backend/packages/harness/deerflow/typesafe/connection.py` 294 行 + `backend/packages/harness/deerflow/typesafe/__init__.py` 118 行 + `backend/packages/harness/deerflow/typesafe/validation.py` 91 行 + `backend/packages/harness/deerflow/typesafe/errors.py` 58 行。它在 2.1.0 中不存在对应物（[同步 #8 计划](../../_upstream-sync/UPDATE_PLAN_8.md) 把它列为 `deerflow/typesafe/` "❌ 无页"的新子系统）。

它解决的问题只有一个：**三个宿主侧消费者要把同一段文本交给同一个远端判定服务，但共享的只能是"把请求安全地送出去、把答案安全地拿回来"这件事**。共享的部分写死在一处，业务语义写在各自适配器里；包内每一行注释都在重复这条边界（`backend/packages/harness/deerflow/typesafe/client.py:7-11`、`backend/packages/harness/deerflow/typesafe/__init__.py:13-30`、`AGENTS.md:11-19`）。

| 层 | 归属 | 内容 |
|----|------|------|
| 传输 | **本包**（`typesafe/`） | 客户端生命周期与 `transport_factory` 注入、认证、重试与退避、截止预算、响应解析与错误分类、UTF-8 线宽度计数、请求骨架 |
| 业务 | **每个适配器** | state 内容、问题/评分细则/阈值/判定方向、失败策略（拒绝 vs 照常）、缓存语义、业务审计 |

→ Back to [parent README](../README.md)

## 能力一览

| 能力 | 关键符号（真实行号） | 说明 |
|------|----------------------|------|
| 一次评估一个客户端 | `TypeSafeClient`（`backend/packages/harness/deerflow/typesafe/client.py:212-426`） | 无缓存、无连接池；`transport_factory` 永远是**工厂**，因为 httpx 关闭客户端时会关掉被注入的 transport（`backend/packages/harness/deerflow/typesafe/client.py:84-86`） |
| 请求骨架 | `_payload` / `_headers`（`backend/packages/harness/deerflow/typesafe/client.py:309-317`） | `{"state", "model", "questions"}`；`Authorization: Bearer …` + `Accept-Encoding: identity` |
| 有界、不解码的响应 | `_read_bounded` + `_reject_content_encoding` + `_accumulate`（`backend/packages/harness/deerflow/typesafe/client.py:429-482`） | 拒绝非 identity 的 `Content-Encoding`，边读边计数，超过 `MAX_RESPONSE_BYTES = 64 KiB`（`backend/packages/harness/deerflow/typesafe/client.py:76`）即失败 |
| 两层错误 | `TypeSafeError`（`backend/packages/harness/deerflow/typesafe/errors.py:33-48`）/ `QuestionError`（`backend/packages/harness/deerflow/typesafe/client.py:171-182`） | 请求级 = 异常（4 个 `cause`）；问题级 = **数据**（`AnswerSet.errors_by_question`，`backend/packages/harness/deerflow/typesafe/client.py:185-196`） |
| 截止预算 | `_check_budget` / `_deadline_error` / `_remaining`（`backend/packages/harness/deerflow/typesafe/client.py:408-426`） | async 用 `asyncio.timeout` 真正取消；sync 在头部后、body 每片前后、解析后各查一次，**迟到结果丢弃**（`backend/packages/harness/deerflow/typesafe/client.py:321-332`） |
| 重试 | `_RETRYABLE_STATUS_CODES`（`backend/packages/harness/deerflow/typesafe/client.py:70`） | 仅 `429` / `529` 与 `httpx.TransportError`；指数退避 `retry_backoff * 2**(attempt-1)` 且被剩余预算截断 |
| 连接解析 | `resolve_connection` / `resolve_connection_for_mode`（`backend/packages/harness/deerflow/typesafe/connection.py:111-193`） | 优先级：消费者 `config` > 顶层 `typesafe:` 块 > 内置默认；凭据**按层**解析；`mode: off` 短路为 `None` |
| 两个身份 | `credential_fingerprint` / `public_parameters`（`backend/packages/harness/deerflow/typesafe/connection.py:94-108`）+ `sharing_key`（`backend/packages/harness/deerflow/typesafe/client.py:234-255`） | 内部合并身份 vs 公开策略身份，**永不混用** |
| 线宽度 | `wire_size`（`backend/packages/harness/deerflow/typesafe/client.py:89-101`） | 只报告字节数，**替换不了任何消费者的字符上限**（一个 CJK 字符是 3 字节） |
| 可记录 model | `recordable_model`（`backend/packages/harness/deerflow/typesafe/client.py:112-127`） | 响应里的 `model` 是响应内容；只有符合 `_MODEL_TOKEN` 形状才原样记录，否则记 `unrecorded:sha256:…` |
| 配置校验 | `backend/packages/harness/deerflow/typesafe/validation.py`（91 行） | `finite_float` / `whole_number` / `defaulted_text` / `credential_text` / `criteria_entry`：让坏部署在**构造期**失败 |

## 架构

```mermaid
flowchart TB
    subgraph consumers["适配器（业务语义，各自持有）"]
        G["guardrails/typesafe.py<br/>TypeSafeGuardrailProvider 464 行<br/>noul: risky_tool_call<br/>p >= threshold ⇒ deny"]
        P["agents/memory/prescreen/typesafe.py<br/>TypeSafeMemoryPrescreen 195 行<br/>noul: memory_worth_keeping<br/>p < 0.2 ⇒ skip 提取"]
        S["agents/memory/signals/typesafe.py<br/>TypeSafeSignalClassifier 258 行<br/>noul × 2: affirmation / negation<br/>p >= 0.5 ⇒ hint label"]
    end

    subgraph shared["deerflow.typesafe（本页，1141 行）"]
        C["TypeSafeClient<br/>ask / aask · sharing_key"]
        K["TypeSafeConnection<br/>resolve_connection · public_parameters<br/>credential_fingerprint"]
        E["TypeSafeError + 4 causes"]
        V["validation：finite_float / whole_number<br/>defaulted_text / credential_text"]
    end

    CFG["config.yaml → typesafe: 块<br/>config/typesafe_config.py<br/>TypeSafeConfig (strict)"]

    G -->|resolve_connection| K
    P -->|resolve_connection| K
    S -->|resolve_connection| K
    G -->|ask / aask| C
    P -->|ask| C
    S -->|ask| C
    CFG -.->|typesafe_defaults()| K
    C --> E
    K --> V

    CO["agents/memory/signals/coordinator.py<br/>MemorySignalCoordinator 600 行<br/>combine=auto/always/never"]
    CO -->|sharing_key 比对| P
    CO -->|sharing_key 比对| S

    G --> MW["guardrails/middleware.py<br/>fail_closed ⇒ deny"]
    CO --> MEM["deermem 提取路径<br/>失败 ⇒ 照常提取"]
```

三条不变量（都能在源码里点到）：

1. **策略参数进不了传输层**。`CONNECTION_FIELDS`（`backend/packages/harness/deerflow/typesafe/connection.py:56-65`）只列 8 个连接键；消费者 `config` 里其余键（`threshold`、`skip_threshold`、`tools`、`cache_size`…）在这一层被 `_configured()`（`backend/packages/harness/deerflow/typesafe/connection.py:196-200`）直接丢弃。
2. **两个消费者阈值不同，也应当能共享一次请求**。所以 `sharing_key()` 只包含连接设置、凭据指纹、`transport_factory` 身份与消费者附加维度（`max_state_chars` / cache 设置），**不含问题、细则与阈值**（`backend/packages/harness/deerflow/typesafe/client.py:234-246`）。
3. **失败策略不在这一层**。同一套 `TypeSafeError`，门把它映射成拒绝，memory 把它映射成"照常"（`backend/packages/harness/deerflow/typesafe/__init__.py:20-24`、`AGENTS.md:22-27`）。

## 文件导航

| 文件 | 内容 |
|------|------|
| [01-client-and-connection.md](01-client-and-connection.md) | **契约面**：`TypeSafeClient` 的请求/响应/截止/重试/有界读取逐行；`AnswerSet` 两层结果的数据形状；`TypeSafeConnection` 的优先级、按层凭据解析、`public_parameters()` vs `credential_fingerprint()` vs `sharing_key()`；顶层 `typesafe:` 块与 `resolve_connection_for_mode(mode="off")` 短路；`backend/packages/harness/deerflow/typesafe/validation.py` 五个校验器的失败时机；错误分类的 4 个 `cause` 由谁产出、由谁消费 |
| [02-adapters-failure-policy.md](02-adapters-failure-policy.md) | **策略面**：三个适配器并排对比（state、问题、阈值与方向、缓存、失败方向）；**fail-closed vs fail-soft** 的完整代码路径（`GuardrailMiddleware` 异常分支 / coordinator 的 `request_failed`）；问题级失败如何逐题降级（信号门"一个方向坏了不影响另一个"）；`allowed_tools` 的 `None` vs `[]`；`openai_decisions` dialect 复用本层的两个 seam；`combine` 与 `sharing_key` 的一致性要求；`eval_typesafe_risk_gate.py` 的五个 population |

## 调用方（全仓 grep `deerflow.typesafe`）

生产代码里 import 本包的文件共 **14 个**（不含本包自身）：

| 类别 | 文件 | 用到的符号 |
|------|------|-----------|
| 适配器 | `guardrails/typesafe.py` | `QUESTION_NOUL` / `AnswerSet` / `Question` / `TransportFactory` / `TypeSafeClient` / `recordable_model` / `resolve_connection` / `typesafe_defaults` / `CAUSE_INVALID_RESPONSE` / `TypeSafeError` / `criteria_entry` / `defaulted_text` / `finite_float` / `whole_number`（`guardrails/typesafe.py:60-63`） |
| 适配器 | `agents/memory/prescreen/typesafe.py` | `QUESTION_NOUL` / `Answer` / `Question` / `TransportFactory` / `TypeSafeClient` / `recordable_model` / `resolve_connection` / `typesafe_defaults` / 三个校验器（`guardrails/typesafe.py:30-32`） |
| 适配器 | `agents/memory/signals/typesafe.py` | 同上（`guardrails/typesafe.py:28-30`） |
| dialect | `openai_decisions/client.py` | `CATEGORY_MISSING` / `CATEGORY_TYPE` / `Answer` / `AnswerSet` / `Question` / `QuestionError` / `TypeSafeClient` / `validate_choice_label` / `validate_probability` / `resolve_connection` / `CAUSE_INVALID_RESPONSE` / `TypeSafeError`（`openai_decisions/client.py:41-51`） |
| dialect 适配器 | `guardrails/openai_decisions.py` / `agents/memory/prescreen/openai_decisions.py` / `agents/memory/signals/openai_decisions.py` | 只 import `TransportFactory` / `TypeSafeClient` / `TypeSafeConnection`（各 `:42-48`） |
| 编排 | `agents/memory/signals/coordinator.py` | `TypeSafeError`（捕获后记 `request_failed`，`agents/memory/signals/coordinator.py:61`） |
| 共享判定件 | `agents/memory/judging.py` | `Answer`（`agents/memory/judging.py:25`） |
| 热重载签名 | `agents/memory/manager.py` | `typesafe_defaults` / `resolve_connection_for_mode`（`agents/memory/manager.py:1022,1048`） |
| 配置 | `config/typesafe_config.py` | 反向：本包 `typesafe_defaults()` **延迟 import** `deerflow.config.typesafe_config`（`backend/packages/harness/deerflow/typesafe/connection.py:203-213`），避免传输层拖进配置包 |
| 脚本 | `scripts/eval_typesafe_risk_gate.py` | 只 import 适配器（`guardrails.typesafe`），不直接用本包（`scripts/eval_typesafe_risk_gate.py:70-78`） |

`backend/app/`（Gateway）对本包**零引用**：它只被 harness 内部的判定路径使用。前端也不感知。

## 与其它域的关系

| 相关域 | 关系 | 页面 |
|--------|------|------|
| 安全 / 风险门 | `TypeSafeGuardrailProvider` 与 `OpenAIDecisionsGuardrailProvider` 是 2.2.0 三道工具级风险门里的两道，共用本层的传输与门语义 | [../../operations/security/03-guardrail.md](../../operations/security/03-guardrail.md)（「2.2.0 三道工具级风险门」节）、[../../operations/security/04-trust-boundary.md](../../operations/security/04-trust-boundary.md) |
| Memory 子系统 | `prescreen/` 与 `signals/` 两个判定子包用本层的 `Answer` / `sharing_key`；`judging.py` 提供两者共用的 batch digest 与答案缓存 | [../../concepts/memory/manager-contract-and-backend-clients.md](../../concepts/memory/manager-contract-and-backend-clients.md)、[../../concepts/memory/extract-queue-persist-pipeline.md](../../concepts/memory/extract-queue-persist-pipeline.md) |
| 配置系统 | `typesafe:` 顶层块由 `config/typesafe_config.py` 的 `TypeSafeConfig`（strict 模式）承载；`guardrails.provider.config` / `memory.prescreen.config` / `memory.signal_classification.config` 是三个消费者层 | [../configuration/README.md](../configuration/README.md) |
| 模型层（同构的"工厂 + 适配器"叙事） | 两者都是"一个入口 + 多个协议适配器"：模型层按 `model.use` 路由，本包按"backend + 消费者槽位"路由 | [../model-layer/README.md](../model-layer/README.md) |
| OpenAI Decisions dialect | 同槽位、不同 endpoint：复用本层 `TypeSafeClient` 的传输生命周期，只覆写 `_payload` / `_parse` / `provider_label` 与 `endpoint_path` | 本目录 [02-adapters-failure-policy.md](02-adapters-failure-policy.md#dialect-复用哪两个-seam)（索引行待父 README 补，见文末） |
| 构建/发布身份 | `release_policy_parameters()` 经 `deerflow_extension_api.canonical_hash` 产出每个消费者的公开策略身份 | [../shared-utils-contract.md](../shared-utils-contract.md)（同目录姊妹文档，跨界的一处引用点：`sharing_key` 也用它） |

## 配置键在哪

| 键 | 位置 | 谁读 |
|----|------|------|
| `typesafe.api_key` / `api_key_env` / `base_url` / `model` / `timeout` / `deadline_seconds` / `max_attempts` / `retry_backoff` | `config.yaml` 顶层 `typesafe:`（`config.example.yaml:3372-` 的注释块；模型见 `config/typesafe_config.py:22-46`） | `TypeSafeConfig.connection_defaults()` → `typesafe_defaults()` → 每个 `resolve_connection(defaults=…)` |
| `guardrails.provider.config.{threshold,instructions,criteria,tools,allowed_tools,max_state_chars,cache_size,cache_ttl_seconds}` | 消费者层（`config.example.yaml:3313` 的 Option 4 注释块） | `TypeSafeGuardrailProvider.__init__`（`guardrails/typesafe.py:154-204`） |
| `memory.prescreen.{mode,use,config}` | 消费者层（`config.example.yaml:2381-` 注释块） | `resolve_memory_prescreen`（`agents/memory/prescreen/contract.py:97-127`） |
| `memory.signal_classification.{mode,use,config,combine}` | 消费者层（`config.example.yaml:2400-` 注释块） | `resolve_memory_signal_classifier` + `MemorySignalCoordinator` |
| `TYPESAFE_API_KEY` | 环境变量（`backend/packages/harness/deerflow/typesafe/connection.py:44`） | `DEFAULT_API_KEY_ENV`，仅在没有任何层指定凭据时才查（`backend/packages/harness/deerflow/typesafe/connection.py:243-249`） |

## 测试与证据

| 测试 | 行数 | 钉住的契约 |
|------|------|-----------|
| `tests/test_typesafe_client.py` | 446 | 两层结果（一题坏不影响另一题）、`wire_size` 与 httpx 一致、字符上限不被字节替换、凭据不进异常链、identity 编码、超限 body、深嵌套、滴水式 body 在截止处停下 |
| `tests/test_typesafe_config.py` | 327 | 优先级、`mode: off`、两个身份不混用 |
| `tests/test_typesafe_guardrail_provider.py` | 846 | 门语义 + 与 `GuardrailMiddleware` 的集成 |
| `tests/blocking_io/test_typesafe_guardrail_provider.py` | 106 | async 路径必须留在事件循环外 |
| `tests/test_openai_decisions.py` | 552 | dialect 只换线协议；两个 backend 永不共享合并请求（`tests/test_openai_decisions.py:452-461`） |
| `tests/test_memory_prescreen.py` | 1487 | 预筛/信号的失败方向、`combine`、per-question 缓存 |
| `tests/test_typesafe_risk_eval_script.py` | 413 | 线上评估脚本的 population 分类 |
| `scripts/eval_typesafe_risk_gate.py` | 525 | 线上评估：rename-vs-disable 校验、五个 population、延迟与误拦目标（`_LATENCY_TARGET_SECONDS` / `_FALSE_BLOCK_TARGET`，`:87-88`） |

## 事实清单（编译期核对）

| 事实 | 位置 |
|------|------|
| 包内 5 个 `.py`，共 1141 行；`backend/packages/harness/deerflow/typesafe/__init__.py` 的 `__all__` 导出 40 个名字，**不含** `credential_text`（只从 `deerflow.typesafe.validation` 取） | `backend/packages/harness/deerflow/typesafe/__init__.py:77-118` |
| 默认值：`https://api.typesafe.ai` / `TYPESAFE_API_KEY` / `jev-latest` / timeout 5 s / deadline 10 s / attempts 2 / backoff 0.5 s | `backend/packages/harness/deerflow/typesafe/connection.py:43-49` |
| 默认端点路径 `/v1/systemone` | `backend/packages/harness/deerflow/typesafe/connection.py:51` |
| 可重试状态码只有 `429`（`frozenset({429})`）、`529`（`frozenset({529})`） | `backend/packages/harness/deerflow/typesafe/client.py:70` |
| 响应上限 64 KiB，且 401 才附上"检查 API key"提示 | `backend/packages/harness/deerflow/typesafe/client.py:76,369-370` |
| `AnswerSet.model` 为**必填**且必须非空串（缺 `model` 即 `invalid_response`） | `backend/packages/harness/deerflow/typesafe/client.py:389-391` |
| `Question.criteria` 对 `choice` 必填、对 `noul` 可选 | `backend/packages/harness/deerflow/typesafe/client.py:143-151` |
| 三个适配器只有 `noul` 问题；仓库里**没有**生产代码构造 `choice` 问题 | `guardrails/typesafe.py:198-203`、`deerflow/agents/memory/prescreen/typesafe.py:106-112`、`deerflow/agents/memory/signals/typesafe.py:111-114` |

> 未逐行核实：`AGENTS.md:54` 提到 `openai_decisions/` 的 issue 编号 `#7005`——本页只在 `openai_decisions/__init__.py:3` 与 `openai_decisions/client.py:3` 的 docstring 里见到同一编号，未独立核对 GitHub issue 内容。
