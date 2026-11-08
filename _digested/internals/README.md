---
title: "Internals — 内部机制深入"
description: "当你需要理解"它为什么这样工作"而不是"怎么用它"时，来这里。"
type: index
---

# Internals — 内部机制深入

当你需要理解"它为什么这样工作"而不是"怎么用它"时，来这里。

## 子目录

| 目录 | 内容 |
|------|------|
| `agent-loop/` | Agent 循环核心：三层嵌套、中间件即循环、扩展点、代码追踪 |
| `middleware/` | 中间件体系：6 hook 点、链组装、37 条目位（35 内置类 + 2 通用槽位）目录、Claude Code 对比 |
| `model-layer/` | 模型抽象：`create_chat_model()` 工厂、thinking/vision、streaming |
| `harness-hooks/` | 扩展点：配置热加载、单例传播、反射加载、Guardrail、MCP 拦截器、ContextVar 覆盖 |
| `configuration/` | 配置系统：config.yaml 全字段参考、extensions_config.json、动态加载 |
| `runtime/` | 自建运行时：RunManager、StreamBridge、Serialization、RunJournal |
| `persistence/` | 持久化：DB/Checkpointer/Store 三后端（SQLite/Postgres/Memory）、checkpoint full/delta 双模式与 delta 历史缓存 |
| `mcp/` | MCP 深度：Session Pool、OAuth、缓存失效、按用户凭据、Durable Task |

## 跨目录文档

| 文件 | 内容 |
|------|------|
| [`shared-utils-contract.md`](shared-utils-contract.md) | `deerflow/utils/` 里被多处依赖的不变量：事件双发、`file_io`/`assembly_io` 专用池与 ContextVar、消息身份与原文保留、thread_id 规则、端口预留、图外 oneshot LLM、outline/think-block 解析边界、"活动内容" MIME |
