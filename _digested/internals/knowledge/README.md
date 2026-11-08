---
title: "Knowledge — 只读检索契约"
description: "v2.2.0 新增的 provider 中立只读检索契约（614 行）：4 个证据模型 + 6 个 Protocol + 12 个能力位；provider 自带凭据、HTTP 与 ACL，DeerFlow 只做「能不能问」「问回来的东西能不能给模型看」。"
type: index
topics: [knowledge, retrieval, evidence, provider-contract]
---

# Knowledge — 只读检索契约

> **定位**：回答「怎么让第二家知识库插进来而核心不必认识它」：核心只拥有契约、证据形状、预算裁剪与失败文本；provider 拥有凭据、HTTP 与「谁都能看什么」。
> **边界**：**不做** ACL 存储、provider 配置、HTTP 调用与资源权限；与 [../capabilities/](../capabilities/README.md) 的能力目录无关（`category: knowledge` 只是画廊标签）；知识工具不是 builtin，完全由 `config.yaml → tools[]` 驱动。

## 阅读路径

1. **先看**：[01-contract-and-capabilities.md](01-contract-and-capabilities.md) — 数据面与 12 个能力位；能力位是所有其它行为的开关。
2. **再看**：[02-sources-and-budgets.md](02-sources-and-budgets.md) — 证据信封、引用转义与两次预算裁剪。
3. **深入**：[03-tool-entry-and-failure-policy.md](03-tool-entry-and-failure-policy.md) — 工具执行时序、作用域生命期与失败策略。

## 本篇目

| 文件 | 主题 | 深度 |
|---|---|---|
| [01-contract-and-capabilities.md](01-contract-and-capabilities.md) | 7 个 Pydantic 模型、6 个 Protocol、能力投影矩阵、注册校验、配置解析 | 概览 |
| [02-sources-and-budgets.md](02-sources-and-budgets.md) | 证据信封、`citation()` 转义、整条丢弃、`prune_sources()` 对账、RAGFlow 原生预算器的独立 ID 命名空间、子 agent 转发 | 深入 |
| [03-tool-entry-and-failure-policy.md](03-tool-entry-and-failure-policy.md) | 12 步执行时序、四档身份、双重作用域闸、四类错误文本与 Gateway 状态码 | 深入 |

## 宪章与约定

- 本目录无独立宪章（`deerflow/knowledge/` 下无 `AGENTS.md`）；写作纪律沿用 [根 README](../README.md)。上游设计契约见 [backend/docs/KNOWLEDGE.md](../../../backend/docs/KNOWLEDGE.md)（345 行），三篇正文按源码展开。

## 相关目录

- [internals 父级](../README.md) — 13 个内部机制子目录的总入口。
- [typesafe](../typesafe/README.md) — 同一类 fail-closed vs fail-soft 取舍的参照。
- [middleware](../middleware/README.md) — `KnowledgeScopeMiddleware` 与 `ToolOutputBudgetMiddleware` 在链上的位置。
- [runtime](../runtime/README.md) — `knowledge_scope` 写入 server-owned 的 runtime context。
- [configuration](../configuration/README.md) — `knowledge_base.enabled` 与 `tools[]` 连接参数。
- [security / 扩展边界](../../enterprise-operations/security/06-extension-boundary.md) — `registry.knowledge_provider()` 的注册契约。

## 速览

- **能力位是声明的集合**：`KnowledgeCapabilities` 冻结、`supports()` 纯集合判断；默认只有 `search`；注册期 `validate_provider()` 要求能力位对应的方法都是 `async`；多工具取**交集**，多 provider 身份则砍到只剩 all/disabled。
- **作用域硬失败**：`selected` 必须带 `dataset_filter`；没有 `search_scoped` 时直接失败，绝不降级成全库搜；子 agent 缺身份也不冒充 `lead_agent`。
- **证据可追溯，且只认工具证据**：`id = sha256(...)[:32]`，内容变则 ID 变；artifact 的 `excerpt` 恒等于模型看到的正文；放不下的 hit 整条丢弃；预算变换后 `prune_sources()` 重新对账；`sources_from_messages()` 四道门（`type=="tool"` / 版本为 int 1 / ID 与内容自洽 / excerpt 与链接在正文里），子 agent 只转发真正被引用过的证据；provider 异常从不进模型输出，只写 `type(exc).__name__`。
- **Provider 生态**：RAGFlow 内置适配器（6 个能力位，`search` + `search_scoped`）；LightRAG 无 `search_scoped`（只接受非收窄作用域）；WeKnora 扩展必须走 `search_scoped`，`search()` 直接 `PermissionError`。
- **测试**：10 个离线 suite（`test_knowledge_{contract,provider,citation_budget,scope,scope_middleware,retrieval_tools,router,provider_router}.py`、`test_weknora_extension.py`、`test_retrieval_plugin_artifacts.py`，合计约 2.5k 行）+ live 1 + blocking-io 1。
