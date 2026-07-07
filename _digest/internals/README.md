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
| `middleware/` | 中间件体系：6 hook 点、链组装、29 middleware 目录、Claude Code 对比 |
| `model-layer/` | 模型抽象：`create_chat_model()` 工厂、thinking/vision、streaming |
| `harness-hooks/` | 扩展点：配置热加载、单例传播、反射加载、Guardrail、MCP 拦截器、ContextVar 覆盖 |
| `configuration/` | 配置系统：config.yaml 全字段参考、extensions_config.json、动态加载 |
| `runtime/` | 自建运行时：RunManager、StreamBridge、Serialization、RunJournal |
| `persistence/` | 持久化：DB/Checkpointer/Store 三后端（SQLite/Postgres/Memory） |
| `mcp/` | MCP 深度：Session Pool、OAuth、缓存失效 |
