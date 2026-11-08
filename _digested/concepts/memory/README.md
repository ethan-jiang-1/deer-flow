---
title: "memory"
description: "可插拔 Memory 后端：提取/队列/持久化管线（含 2.2.0 的 cognitiveStyle / cognitive 类别 / 词法相关性排序 / prescreen+signal 门），以及 Manager 契约面、5 个工具的 JSON 工具面、summarization 挂钩点与各 backend 客户端初始化/失败模式。"
type: index
---

# memory

## 主题索引

| 文件 | 内容 |
|------|------|
| `extract-queue-persist-pipeline.md` | 管线主体：可插拔后端架构、DeerMem storage v2（Markdown fact/双层乐观锁/两阶段日志）、debounced 提取、staleness review、consolidation、hybrid-v1 驱逐、近重复门、per-user 隔离、**2.2.0 的 `cognitiveStyle` 摘要段与 10 个 fact 类别**、**确定性词法相关性排序（IDF + greedy-MMR）**、retrieval 配置的四个坑、API 与配置速查 |
| `manager-contract-and-backend-clients.md` | 补齐契约面：`MemoryManager` 分层/实例化不变量/严格读策略/单例工厂与 host hook（含 2.2.0 的 `supports_agent_scoped_management` / `refresh_judge`）、`get_memory_tools` 的 **5 个** JSON 工具（含 `memory_get`）、`summarization_hook` + `locale.py` 的 locale 对齐、`judging.py` 与 `prescreen/`+`signals/` 两个判定子包、deermem/mem0/honcho/openviking/noop 的 config 校验与 client 初始化/失败模式、各文件行数 |

→ Back to [parent README](../README.md)
