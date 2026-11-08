---
title: "OpenAI Decisions — 决策传输（#7005）"
description: "v2.2.0 新增的第二个决策后端：把已经问给 TypeSafe(Jev) 的问题，用同一个 TypeSafeClient 说成 POST /v1/decisions 的 predicate 语言；只拥有线协议，传输生命周期严格继承。"
type: index
topics: [openai-decisions, typesafe, dialect, decision-provider]
---

# OpenAI Decisions — 决策传输（#7005）

> **定位**：`backend/packages/harness/deerflow/openai_decisions/` 回答「同一个决策槽位怎么换一条线协议」：endpoint、envelope、问题编码、答案校验、错误分类归本包；鉴权/重试/退避/截止预算/有界 body 读取一行都不重写。
> **边界**：不是新决策系统——不新增配置 schema、阈值、缓存或失败方向；传输层归 [../typesafe/](../typesafe/README.md)；三个消费者的业务语义（风险门 / memory 预筛 / 信号分类）仍在各自适配器。

## 阅读路径

1. **先看**：[01-wire-contract.md](01-wire-contract.md) — 请求 envelope、`noul → predicate` 与答案解析。
2. **再看**：[02-connection-config.md](02-connection-config.md) — 连接解析、默认值与 `use:` 一行配置。
3. **深入**：[03-three-consumers.md](03-three-consumers.md) — 三个消费者与同一 refusal 的相反后果。

## 本篇目

| 文件 | 主题 | 深度 |
|---|---|---|
| [01-wire-contract.md](01-wire-contract.md) | `input` 而非 `state`、`questions` 数组、criteria 折进 instructions、信封级/问题级失败分界、`model` 回声 | 概览 |
| [02-connection-config.md](02-connection-config.md) | `provider_defaults()`、`base_url` 层级、`api_key_env` 三层优先级、导出缺口、热重载边界 | 深入 |
| [03-three-consumers.md](03-three-consumers.md) | 三个适配器的 seam、fail-closed vs fail-soft、`sharing_key` 为何必然不同、离线测试 | 深入 |

## 宪章与约定

- 本目录无独立宪章；包内**没有** `AGENTS.md`（只有两个 `.py`）。成文边界在 [typesafe/AGENTS.md](../../../backend/packages/harness/deerflow/typesafe/AGENTS.md) 的 **Dialects** 段（54–70 行）与 [backend/docs/GUARDRAILS.md](../../../backend/docs/GUARDRAILS.md) 的 Option 4b 节；写作纪律沿用 [根 README](../README.md)。

## 相关目录

- [internals 父级](../README.md) — 13 个内部机制子目录的总入口。
- [typesafe](../typesafe/README.md) — 共享传输与第一个 dialect。
- [configuration](../configuration/README.md) — 三个消费者槽位的 `use` / `config` 写法。
- [安全 / guardrail](../../enterprise-operations/security/03-guardrail.md) — 风险门语义与 fail-closed。
- [memory / manager 契约](../../concepts/memory/manager-contract-and-backend-clients.md) — pre-screen 与 signal classification 的失败方向。

## 速览

- **规模与出处**：267 行（`client.py` 222 + `__init__.py` 45），上游 commit `1fd266e0c`，issue #7005；全目录无 `AGENTS.md`。
- **只覆写两个方法 + 一个类属性**：`_payload` / `_parse` / `provider_label`；`ask` / `aask` 全部继承。`__init__.py` 只转发 11 个符号，`resolve_decisions_connection` 未被 re-export 覆盖。
- **两个 seam 撑起 dialect**：`provider_label` 与 `TypeSafeConnection.endpoint_path`；本包没有 import `httpx`，没有任何 retry / timeout / body-size 常量。
- **默认值**：`https://api.openai.com` + `/v1/decisions`、`OPENAI_API_KEY`；**`model` 默认空串，构造即失败**，必须由部署命名。
- **三个消费者方向相反、范围可控**：风险门 `fail_closed: true` 时 refusal 也是拒绝；memory 两条路线把同一 refusal 当作「这一题没意见」；`sharing_key` 因 `endpoint_path` 进公开参数而必然不同；生产调用方只有三个适配器（`guardrails` / `prescreen` / `signals` 的 `openai_decisions.py`）+ 1 个测试文件；commit 改了 16 个文件，**不含**任何配置 schema；离线 suite `test_openai_decisions.py`（552 行，`httpx.MockTransport`）钉住线映射与 gate 方向。

> 未核实：`POST /v1/decisions` 的**服务端语义**在仓库内没有 fixture 之外的证据；各正文页就地标注。
