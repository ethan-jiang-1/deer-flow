---
title: "LLM 抽象层"
description: "怎么做到换模型不改代码？thinking/vision 这些新能力怎么统一抽象？"
type: index
---

# LLM 抽象层

怎么做到换模型不改代码？thinking/vision 这些新能力怎么统一抽象？

**回答的核心问题**：`create_chat_model()` 工厂怎么路由到 9 个自定义适配器（+ 2 个标准直通 = 11 条路由）、thinking/vision 的跨 provider 适配策略、streaming 的 chunk 归一化与 SSE 事件模型；以及 `config.yaml` 之外的第二个模型来源（托管模型加密 catalog）如何合并进同一份生效快照。

> **约束：不修改项目源代码。** 本 `_digested/` 下所有内容仅作研究记录。详见 [根 README](../README.md)。

## 阅读顺序

| 文件 | 内容 |
|------|------|
| **00-overview.md** | 全景：`create_chat_model()` 工厂、ModelConfig schema、9 个 DeerFlow 适配器 + 标准 LangChain 直通路径、凭证加载 |
| **01-thinking-vision.md** | Thinking mode 三种配置模式、`thinking` 快捷方式、reasoning_effort、Vision 启用链路 |
| **02-streaming.md** | StreamBridge 传输层 + per-provider chunk 归一化、SSE 事件模型 |
| **managed-models.md** | 托管模型：12 个 provider preset 的「服务端拥有路由」契约、精确 ID 能力矩阵、Fernet 加密 catalog 与 `merge_managed_models()` 快照合并、`/api/managed-models` 四端点（admin + revision 乐观锁 + `RedactedModelRoute` 防密钥回显）、与 chat 同路径的有界 probe |

## 关键问题

- `config.yaml` 里换个 `model.use` class path 就能切 provider？→ `00-overview.md` Factory 流程
- vLLM 的 `enable_thinking` 和 Anthropic 的 thinking 模式有什么不同？→ `01-thinking-vision.md` 三种配置模式
- streaming 的 token delta 是怎么在不同 provider 之间统一成前端期望格式的？→ `02-streaming.md` Chunk 归一化
- 哪些 provider 需要 patch 类？为什么要 patch？→ `00-overview.md` Provider 适配器全景
- Vision 是怎么从 tool 执行到 model 调用的？→ `01-thinking-vision.md` Vision 启用链路
- StreamBridge 的 Last-Event-ID 重连怎么工作？→ `02-streaming.md` MemoryStreamBridge
- 管理员在 Web 上加的模型怎么进到 `create_chat_model()`？为什么客户端不能指定 endpoint？→ `managed-models.md`

## 源文件索引

| 组件 | 路径 |
|------|------|
| 工厂入口 | `deerflow/models/factory.py:create_chat_model()` |
| ModelConfig | `deerflow/config/model_config.py` |
| Provider 适配器 | `deerflow/models/claude_provider.py` · `patched_openai.py` · `patched_deepseek.py` · `patched_minimax.py` · `vllm_provider.py` · `mindie_provider.py` · `openai_codex_provider.py` |
| 凭证加载 | `deerflow/models/credential_loader.py` |
| 托管模型注册表 | `deerflow/config/managed_model_providers.py` · `deerflow/config/managed_models.py` |
| 托管模型路由 | `app/gateway/routers/managed_models.py` |
| Vision middleware | `deerflow/agents/middlewares/view_image_middleware.py` |
| StreamBridge | `deerflow/runtime/stream_bridge/` |
