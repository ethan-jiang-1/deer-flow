---
title: "LLM 抽象层"
description: "怎么做到换模型不改代码？create_chat_model() 工厂把配置路由到 11 条 provider 路径，thinking/vision 统一抽象，streaming 做 chunk 归一化；另有托管模型的加密目录作为第二个模型来源。"
type: index
topics: [models, llm, provider-factory, streaming]
---

# LLM 抽象层

> **定位**：回答「换模型为什么不用改代码、thinking/vision 怎么跨 provider 适配、streaming 的 chunk 怎么归一化、管理员在 Web 上加的模型怎么进工厂」；给要接新 provider 或调模型行为的开发者。
> **边界**：模型配置字段在 [../configuration/](../configuration/README.md)；StreamBridge 的传输层在 [../runtime/02-stream-bridge.md](../runtime/02-stream-bridge.md)；判定客户端（另一类适配器叙事）在 [../typesafe/](../typesafe/README.md)。

## 阅读路径

1. **先看**：[00-overview.md](00-overview.md) — 工厂、ModelConfig、适配器全景与凭证加载。
2. **再看**：[01-thinking-vision.md](01-thinking-vision.md) — thinking 三种配置模式与 vision 启用链路。
3. **深入**：[managed-models.md](managed-models.md) — 服务端拥有的路由契约与加密 catalog。

## 本篇目

| 文件 | 主题 | 深度 |
|---|---|---|
| [00-overview.md](00-overview.md) | `create_chat_model()` 流程、ModelConfig schema、provider 适配器全景、凭证加载 | 概览 |
| [01-thinking-vision.md](01-thinking-vision.md) | thinking 三种模式、`thinking` 快捷方式、`reasoning_effort`、vision 启用链路 | 深入 |
| [02-streaming.md](02-streaming.md) | StreamBridge 传输层、per-provider chunk 归一化、SSE 事件模型、Last-Event-ID 重连 | 深入 |
| [managed-models.md](managed-models.md) | 12 个 provider preset、精确 ID 能力矩阵、Fernet 加密 catalog、四端点 + revision 乐观锁、有界 probe | 深入 |

## 宪章与约定

- 包内有独立宪章：[backend/packages/harness/deerflow/models/AGENTS.md](../../../backend/packages/harness/deerflow/models/AGENTS.md)（272 行）；写作纪律沿用 [根 README](../README.md)。

## 相关目录

- [internals 父级](../README.md) — 13 个内部机制子目录的总入口。
- [configuration](../configuration/README.md) — `model.use` / ModelConfig 的字段与热加载。
- [runtime](../runtime/README.md) — StreamBridge 与序列化层。
- [typesafe](../typesafe/README.md) — 同构的「一个入口 + 多个协议适配器」叙事。
- [安全 / 信任边界](../../enterprise-operations/security/04-trust-boundary.md) — 托管模型为何不允许客户端指定 endpoint。

## 速览

- **一个公开入口**：`create_chat_model()`；其余全是 `model.use` 的类路径解析。
- **11 条 provider 路由**：9 个 DeerFlow 自定义适配器 + 2 条标准 LangChain 直通；另有 4 个仅换 `base_url` 的变体（口径核对见 [00](00-overview.md) 的「总计」段）。
- **thinking 在 model 层、vision 在 middleware 层**：前者改传给 provider 的参数，后者在 model 调用前注入图片。
- **托管模型是第二来源**：`config.yaml` 之外的加密 catalog 经 `merge_managed_models()` 合进同一份生效快照；路由必须留在服务端。
- **源码入口**：`deerflow/models/factory.py:create_chat_model()`、`config/model_config.py`、各 provider 适配器文件（`claude_provider.py` / `patched_*.py` / `vllm_provider.py` / `mindie_provider.py` / `openai_codex_provider.py`）、`models/credential_loader.py`；托管模型注册表在 `config/managed_model*.py`，路由在 `app/gateway/routers/managed_models.py`。
