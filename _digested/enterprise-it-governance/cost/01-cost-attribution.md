---
title: "成本归属"
description: "Token 用量追踪、subagent 成本合并、stream_usage、缺失的实时仪表盘。"
topics: [governance, cost]
---

# 成本归属

Token 用量追踪、subagent 成本合并、stream_usage、缺失的实时仪表盘。

## 成本归属

### Token 用量追踪

`TokenUsageMiddleware` 在每个 AIMessage 上标注 `usage_metadata`（input_tokens, output_tokens, total_tokens）。收集粒度是**每个 LLM 调用**。

### Subagent 成本合并

Subagent 的 token 消耗由 `SubagentTokenCollector` 收集，缓存在 `_subagent_usage_cache` 中（key = `tool_call_id`）。`TokenUsageMiddleware` 在下一轮 `after_model` 中从缓存中取出 subagent 用量，合并到触发 subagent 的 AIMessage 上。

**成本归属链：**
```
Lead Agent 第 N 轮 AIMessage (dispatch 3 个 subagent)
    → subagent_1 token usage → 合并到 AIMessage.usage_metadata
    → subagent_2 token usage → 合并到 AIMessage.usage_metadata
    → subagent_3 token usage → 合并到 AIMessage.usage_metadata
```

这样，一次 "dispatch subagent → subagent 工作 → 返回结果" 的完整 token 消耗归属于触发它的父 message。

### stream_usage 自动启用

`create_chat_model()` 对自定义 base_url 的 OpenAI-compatible provider 自动启用 `stream_usage=True`。原因是 LangChain 只在标准 OpenAI endpoint 下默认开启 stream_usage——自定义 gateway（如 doubao、deepseek）会静默丢失 usage 数据。

### 缺失：实时成本仪表盘

- 有 per-model token 统计，但无 per-agent 汇总
- 有 per-run token 统计，但无预算上限和实时告警
- 有 tracing span（Langfuse），但无成本归因到具体 user/thread 的聚合视图

