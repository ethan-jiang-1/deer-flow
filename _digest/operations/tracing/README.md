---
title: "Tracing — 追踪系统"
description: "| 文件 | 内容 |"
type: index
---

# Tracing — 追踪系统

## 文件索引

| 文件 | 内容 |
|------|------|
| [langsmith-langfuse-dual-provider.md](langsmith-langfuse-dual-provider.md) | 全景：两层附着策略、LangSmith/Langfuse 双 provider、工厂模式、Langfuse v4 合约、元数据注入、配置、环境标签 |

## 关键设计决策

- **图根级别附着 > 模型级别附着** — Langfuse v4 只在 `on_chain_start(parent_run_id=None)` 时将 metadata 提升到根 trace
- **`inject_langfuse_metadata()` 双路径共享** — Gateway worker 和嵌入式 client 走同一个 helper，防止漂移
- **调用者覆盖优先** — `setdefault` 确保前端设置的 `langfuse_session_id` 不被覆盖
- **LangSmith-only 零影响** — `build_langfuse_trace_metadata()` 在 Langfuse 未启用时返回 `{}`

## 测试覆盖

| 测试文件 | 覆盖范围 |
|---------|---------|
| `test_tracing_factory.py` | factory — provider 检测、异常传播、空 provider 返回 `[]` |
| `test_tracing_metadata.py` | metadata — 所有字段映射、空值回退、tags 生成 |
| `test_worker_langfuse_metadata.py` | worker 注入 — `inject_langfuse_metadata` 在 `run_agent()` 中正确合并 |
| `test_client_langfuse_metadata.py` | client 注入 — `DeerFlowClient.stream()` 同样调用共享 helper |
