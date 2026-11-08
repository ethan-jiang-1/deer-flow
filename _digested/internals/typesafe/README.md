---
title: "TypeSafe (Jev) — 共用判定客户端"
description: "v2.2.0 新增的传输层：一套客户端（生命周期/认证/重试/截止预算/有界响应/错误分类/共享键）被三类适配器共用；状态、问题与阈值、失败方向、缓存、审计全部留在适配器。"
type: index
topics: [typesafe, transport-layer, fail-closed, fail-soft]
---

# TypeSafe (Jev) — 共用判定客户端

> **定位**：回答「三个宿主侧消费者要把同一段文本交给同一个远端判定服务，什么该共享、什么必须留在业务侧」；共享的只有「把请求安全送出去、把答案安全拿回来」，风险门 fail-closed、memory 预筛 fail-soft。
> **边界**：失败策略不在本层（去 [02](02-adapters-failure-policy.md)）；配置键与 `typesafe:` 顶层块在 [../configuration/](../configuration/README.md)；第二个 dialect 的线协议在 [../openai-decisions/](../openai-decisions/README.md)。

## 阅读路径

1. **先看**：[01-client-and-connection.md](01-client-and-connection.md) — 客户端、连接、三种身份与错误分类。
2. **再看**：[02-adapters-failure-policy.md](02-adapters-failure-policy.md) — 三个适配器并排与相反失败方向。
3. **深入**：[../openai-decisions/01-wire-contract.md](../openai-decisions/01-wire-contract.md) — 同一传输上的第二个 dialect。

## 本篇目

| 文件 | 主题 | 深度 |
|---|---|---|
| [01-client-and-connection.md](01-client-and-connection.md) | 请求骨架、有界读取、截止预算、重试、4 个 `cause`、`wire_size`、`recordable_model`、`AnswerSet` 两层结果、连接三级优先级、三种身份、五个校验器；无缓存、无连接池 | 概览 |
| [02-adapters-failure-policy.md](02-adapters-failure-policy.md) | 三个适配器（464 / 195 / 258 行）的 state、阈值、缓存键与失败路径；`openai_decisions` 的 seam；线上评估 population | 深入 |

## 宪章与约定

- 包内有独立宪章：[backend/packages/harness/deerflow/typesafe/AGENTS.md](../../../backend/packages/harness/deerflow/typesafe/AGENTS.md)（71 行，含 Dialects 段）；写作纪律沿用 [根 README](../README.md)。

## 相关目录

- [internals 父级](../README.md) — 13 个内部机制子目录的总入口。
- [openai-decisions](../openai-decisions/README.md) — 复用本层传输的第二个 dialect。
- [configuration](../configuration/README.md) — `typesafe:` 块与三个消费者层。
- [安全 / guardrail](../../enterprise-operations/security/03-guardrail.md) — 2.2.0 三道工具级风险门。
- [memory / manager 契约](../../concepts/memory/manager-contract-and-backend-clients.md) — `prescreen/` 与 `signals/` 的消费方。

## 速览

- **规模 1141 行 / 5 个 `.py`**：`client.py` 580、`connection.py` 294、`__init__.py` 118、`validation.py` 91、`errors.py` 58；`__all__` 导出 40 个名字，**不含** `credential_text`。
- **默认值**：`https://api.typesafe.ai` / `TYPESAFE_API_KEY` / `jev-latest` / 5s timeout / 10s deadline / 2 attempts / 0.5s backoff；端点 `/v1/systemone`；响应上限 64 KiB，仅 401 附「检查 API key」提示。
- **三条不变量**：`CONNECTION_FIELDS` 只认 8 个连接键，阈值等策略参数进不了传输层；`sharing_key()` 不含问题/细则/阈值，所以不同阈值的消费者仍可共享一次请求；同一套 `TypeSafeError` 由适配器映射成拒绝或「照常」。
- **只有 `noul` 进入生产**：三个适配器都只构造 `noul` 问题，仓库里没有生产代码构造 `choice`；`AnswerSet.model` 必填且非空，缺 `model` 即 `invalid_response`。
- **调用方与证据**：生产代码里 import 本包的共 14 个文件（不含本包自身），集中在 3 个适配器、4 个 OpenAIDecisions 文件、coordinator / judging / manager 与配置模块，`backend/app/` 零引用；8 个测试/脚本约 4.7k 行（`test_typesafe_client` 446、`test_typesafe_config` 327、`test_typesafe_guardrail_provider` 846、`test_memory_prescreen` 1487、`test_openai_decisions` 552、risk eval 413 + 525、blocking-io 106）。
