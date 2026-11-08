---
title: "Summarization 深度解析"
description: "上下文压缩的完整机制：触发条件、保留策略、摘要生成、与 DurableContext 的协作、阈值选择指南。"
topics: [summarization, context-window, middleware, configuration]
---

# Summarization 深度解析

## 工作原理

`SummarizationMiddleware`（中间件 **#20**，仅 lead agent；subagent 链也继承）在每次模型调用前检查是否超过阈值。如果触发：

1. **计算分割点**：`keep` 配置决定保留尾部多少条消息（从最新往旧数）
2. **安全分割**：绝不拆分 AI/Tool 对——如果分割点落在 ToolMessage 上，向前搜索配对的 AIMessage 并保留
3. **摘要生成**：用独立模型（默认 `model_name: null` = 默认模型，推荐便宜模型如 `gpt-4o-mini`，thinking 关闭）压缩早期消息
4. **存到状态**：摘要写入 `ThreadState.summary_text`（LastValue channel），**不**作为消息存储
5. **DurableContext 重新注入**：`DurableContextMiddleware`（**#19**，在 #20 summarization 之前运行）捕获 skill 引用和 delegation 后再压缩，压缩后在模型请求中重新注入 `summary_text` + skill 引用

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

这是理解 summarization 最关键的一点。DurableContextMiddleware（**#19**）在 summarization（#20）之前运行：

1. **压缩前**：捕获 skill 引用（`ThreadState.skill_context`）和 task delegation（`ThreadState.delegations`）
2. **压缩后**：将 `summary_text` + skill 引用 + delegation 渲染为隐藏 HumanMessage `<durable_context_data>`，注入到模型请求中

这意味着即使消息被压缩，agent 仍然知道：
- 之前加载过哪些 skills（path + description，不含 SKILL.md body）
- 有哪些活跃的 task delegation 及其状态
- 压缩摘要文本

## 手动 Compaction 🆕

自动 summarization 的补充——用户可以通过 API 主动触发压缩：

`POST /api/threads/{id}/compact`

- **复用同一 middleware**：`DeerFlowSummarizationMiddleware`，共享 trigger/keep/model/prompt 配置
- **写入新 checkpoint**：更新 `messages`（移除旧消息）和 `summary_text`
- **只 bump 变更的 channel versions**：不做全量 checkpoint 重写
- **串行化**：与 `/goal` 写入和 run admission 共享 per-thread 锁，防止与 goal 更新或 runs 竞争
- **Run 进行中时立即返回 409**：防止并发修改 checkpoint（不等待，直接拒绝）
- **失败返回 500**：不暴露内部错误细节

与自动 summarization 的区别：
- 自动：在 `before_model` hook 中触发，作为 agent loop 的一环
- 手动：独立 API 调用，不经过 agent loop，直接操作 checkpoint

### 手动压缩的宿主侧契约（`runtime/context_compaction.py`，224 行）

路由只是薄壳；真正的工作核心是 `compact_thread_context(accessor, thread_id, *, keep=None, force=True, user_id=None, agent_name=None, model_name=None, app_config=None) -> ThreadCompactionResult`。它在**不执行 agent**的前提下模拟 lead 的解析与写回：

| 契约 | 细节 |
|------|------|
| 状态访问 | 只经 `CheckpointStateAccessor`（`aget` / `aupdate`）——delta 模式下直接读 saver 会拿到哨兵值，所以这是硬约束 |
| agent 绑定 | `_checkpoint_agent_binding(snapshot.metadata)` 读服务端写入的 `CHECKPOINT_AGENT_NAME_METADATA_KEY`。返回 `(binding_known, name)`；**`binding_known=False`（pre-binding 旧状态）时忽略 body 提示**，body 的 `agent_name` 只能选"兼容的摘要模型"，**永远不能**授权或归属一次 memory 写入 |
| memory flush | `memory_enabled = binding_known and (checkpoint_agent_name is None or agent_config.memory_enabled is not False)`；不可读的 agent config **fail closed**（跳过 flush），因为读不到的策略无法授权一次 durable 写。`skip_memory_flush=not memory_enabled` 传给同一 `create_summarization_middleware()` |
| 模型解析 | `_aresolve_thread_model_name()` 与 lead 的 `_resolve_model_name` 同序：显式请求 model（要能在 `app_config` 里查到）→ 线程自定义 agent 的 `model` → `config.models[0]`。custom-agent 配置读取只在没给请求 model 时发生，走 `asyncio.to_thread`（blocking-IO 检测器不会误报，宽 `except` 也遮不住 loop 上抛的 `BlockingError`） |
| 写回 | `aupdate(..., as_node="manual_compaction")`，channel 用 `Overwrite(preserved_messages)`、`summary_text`，以及可选的 `task_history`；**只 bump 变更的 channel versions**。更新 config **复制自 snapshot.config**（保留 checkpoint 血缘），`binding_known` 时把 agent 绑定键原样盖回（`None` agent 写 `DEFAULT_AGENT_NAME_METADATA_VALUE`） |
| 异常分工 | `ContextCompactionDisabled`：summarization 关着（`_create_compaction_middleware` 返回 `None` 时抛）；`ContextCompactionFailed("summary generation failed")`：`SummaryGenerationError`——**"可压缩但摘要模型失败"是独立失败**，不能塌缩成 `compacted=False`（后者前端读作"不需要压缩"）；`LookupError`：thread 无 checkpoint；无消息或无结果 → `compacted=False, reason="not_enough_messages"` |
| 结果对象 | `ThreadCompactionResult` 是 frozen dataclass：`thread_id` / `compacted` / `reason` / `removed_message_count` / `preserved_message_count` / `summary_updated` / `checkpoint_id` / `total_tokens` |

`force` 与 `raise_on_failure` **相互独立**：手动调用方总是要看到生成失败（即使 `force=False` 且已过阈值），所以底层用 `raise_on_failure=True` 调用 `middleware.acompact_state()`。

同目录的 `runtime/context_keys.py`（33 行）就是这两个 checkpoint 级 server-owned 键的落点：`CHECKPOINT_AGENT_NAME_METADATA_KEY` 与 `DEFAULT_AGENT_NAME_METADATA_VALUE`。

## 与 Sub-agent 的关系

🆕 Sub-agent **现在继承** SummarizationMiddleware（`build_subagent_runtime_middlewares` 中附加），与 lead agent 共享同一 `summarization.enabled` 开关和配置。`DurableContextMiddleware` 在 summarization 之前附加，`SystemMessageCoalescingMiddleware` 放在最内层。

## Memory Flush Hook

在消息被移除前，`memory_flush_hook` 提取即将被压缩的用户+AI 消息，推入 memory 队列（非阻塞），防止重要信息在压缩中丢失。

## 故障处理

摘要生成失败（模型调用异常）→ 返回 `None`，**跳过本次压缩**（不崩溃）。下次模型调用时重新评估触发条件。

源码：`deerflow/agents/middlewares/summarization_middleware.py`，`deerflow/config/summarization_config.py`
