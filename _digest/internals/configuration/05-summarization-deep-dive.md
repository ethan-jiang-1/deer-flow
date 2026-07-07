---
title: "Summarization 深度解析"
description: "上下文压缩的完整机制：触发条件、保留策略、摘要生成、与 DurableContext 的协作、阈值选择指南。"
topics: [summarization, context-window, middleware, configuration]
---

# Summarization 深度解析

## 工作原理

`SummarizationMiddleware`（中间件 #16，仅 lead agent）在每次模型调用前检查是否超过阈值。如果触发：

1. **计算分割点**：`keep` 配置决定保留尾部多少条消息（从最新往旧数）
2. **安全分割**：绝不拆分 AI/Tool 对——如果分割点落在 ToolMessage 上，向前搜索配对的 AIMessage 并保留
3. **摘要生成**：用独立模型（默认 `model_name: null` = 默认模型，推荐便宜模型如 `gpt-4o-mini`，thinking 关闭）压缩早期消息
4. **存到状态**：摘要写入 `ThreadState.summary_text`（LastValue channel），**不**作为消息存储
5. **DurableContext 重新注入**：`DurableContextMiddleware`（#15，在 #16 之前运行）捕获 skill 引用和 delegation 后再压缩，压缩后在模型请求中重新注入 `summary_text` + skill 引用

```
消息历史: [old...mid...new]
                │
         ┌──────┴──────┐
         │  keep: 10    │ → 尾部 10 条保留（不压缩）
         └──────┬──────┘
                │
         ┌──────┴──────┐
         │  早期消息     │ → 用便宜模型生成摘要
         └──────┬──────┘
                │
         ┌──────┴──────┐
         │ summary_text │ → 存到 ThreadState（LastValue）
         └──────────────┘
```

## 配置

```yaml
summarization:
  enabled: true
  model_name: null          # null = 默认模型（推荐设便宜模型）
  trigger:
    - type: tokens
      value: 32000         # token 数达此值时触发
    # - type: messages
    #   value: 50          # 消息数达此值时触发
    # - type: fraction
    #   value: 0.8         # 达模型 max_input 的 80% 时触发
  keep:
    type: messages
    value: 10              # 保留最近 10 条消息（不压缩）
  trim_tokens_to_summarize: 15564
  summary_prompt: null      # null = LangChain 默认 prompt
  skill_file_read_tool_names: [read_file, read, view, cat]
```

触发器是 **OR 逻辑**——任一条件满足即触发。热加载，无需重启。

## 阈值选择指南

| 场景 | 推荐配置 |
|------|---------|
| 快速实验（8K 上下文） | `tokens: 5000, keep: 5` |
| 日常开发（32K 上下文） | `tokens: 20000, keep: 10`（默认） |
| 长对话（128K 上下文） | `tokens: 80000, keep: 20` |
| 严格省钱 | `fraction: 0.5` + 设 `model_name: "gpt-4o-mini"` |

经验法则：trigger 设在模型 max_input 的 ~50-60%。太低浪费时间频繁压缩，太高容易超出窗口。

## 与 DurableContext 的协作

这是理解 summarization 最关键的一点。DurableContextMiddleware（#15）在 summarization 之前运行：

1. **压缩前**：捕获 skill 引用（`ThreadState.skill_context`）和 task delegation（`ThreadState.delegations`）
2. **压缩后**：将 `summary_text` + skill 引用 + delegation 渲染为隐藏 HumanMessage `<durable_context_data>`，注入到模型请求中

这意味着即使消息被压缩，agent 仍然知道：
- 之前加载过哪些 skills（path + description，不含 SKILL.md body）
- 有哪些活跃的 task delegation 及其状态
- 压缩摘要文本

## 与 Sub-agent 的关系

Sub-agent **没有** SummarizationMiddleware。Sub-agent 依赖 `max_turns`（recursion_limit）防止无限增长，通过 `GraphRecursionError` → `MAX_TURNS_REACHED` 捕获。

## Memory Flush Hook

在消息被移除前，`memory_flush_hook` 提取即将被压缩的用户+AI 消息，推入 memory 队列（非阻塞），防止重要信息在压缩中丢失。

## 故障处理

摘要生成失败（模型调用异常）→ 返回 `None`，**跳过本次压缩**（不崩溃）。下次模型调用时重新评估触发条件。

源码：`deerflow/agents/middlewares/summarization_middleware.py`，`deerflow/config/summarization_config.py`
