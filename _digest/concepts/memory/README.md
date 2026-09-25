---
title: "memory"
description: "可插拔 Memory 后端：提取/队列/持久化管线，以及 Manager 契约面、工具面、summarization 挂钩点与各 backend 客户端初始化/失败模式。"
type: index
---

# memory

## 主题索引

| 文件 | 内容 |
|------|------|
| `extract-queue-persist-pipeline.md` | 管线主体：可插拔后端架构、DeerMem storage v2（Markdown fact/双层乐观锁/两阶段日志）、debounced 提取、staleness review、consolidation、hybrid-v1 驱逐、近重复门、per-user 隔离、API 与配置速查 |
| `manager-contract-and-backend-clients.md` | 补齐契约面：`MemoryManager` 分层/实例化不变量/严格读策略/单例工厂与 host hook、`get_memory_tools` 的 JSON 工具面、`summarization_hook` 挂钩点、deermem/mem0/honcho/openviking/noop 的 config 校验与 client 初始化/失败模式 |

→ Back to [parent README](../README.md)
