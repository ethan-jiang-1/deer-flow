---
title: "Task Continuity — 任务连续性"
description: "opt-in 的任务笔记 + 压缩历史召回：task_note/history_search/history_read 三工具、thread 级 SQLite 归档、retention/作用域/失败语义、与 memory 的边界、上游评测结论。"
topics: [runtime, compaction, task-continuity, notes, recall]
---

# Task Continuity — 任务连续性

> **归属说明**：本文件放在 `internals/runtime/` 而非 `concepts/memory/`，因为它是**线程内、压缩后**的连续性机制（thread 作用域 SQLite，随 thread 删除而清除，不写长期用户画像），与 [goal-continuation.md](goal-continuation.md) 同类。

一个全新 opt-in 子系统（同步 #6，`1b76ab90` / PR #5382）：开启后 agent 可以写**短任务笔记**，并在上下文被成功压缩（compaction）后**召回被移除消息的细节**——解决长任务跨压缩丢上下文。

## 定位与边界

- 默认关闭，`config.yaml` 开启：

```yaml
task_continuity:
  enabled: true          # 默认 false
  max_batches: 32        # 1–64
  max_records_per_batch: 256  # 1–1024
  max_record_chars: 16000     # 1000–64000
```

- **与 memory 系统明确独立**：不依赖 `memory.enabled`、与 memory 模式无关；**不写长期用户画像**；特性本身不需要 embedding 服务或额外模型调用。
- 增量补强既有通道（summary、goal、todos、delegation ledger），不替代任何一个。
- 标准 lead-agent 构造器（含 custom-agent bootstrap）和 `DeerFlowClient` 经现有 authorization filter 暴露三个工具；直接 `create_deerflow_agent` 集成需显式组合 middleware/tools（无自动安装）。active skill 的 tool policy 与运行时授权仍然生效。

## 三个工具与精确预算

| 工具 | 预算 | 说明 |
|------|------|------|
| `task_note` | **8 条 × 750 字符 × 4 个 source ID**（key：40 个 ASCII 字母/数字/`_`/`-`） | 保存/替换/删除（空 content = 删除）命名笔记。满员时拒绝新 key，需先替换/删除既有 key；并行更新合计超容时 reducer 保留最后 8 个 insertion-order key（看下一次注入的 notebook 确认保留项）。source ID 只做可用性检查，不代表语义支持——**所有笔记都是 model report**，不经验证 |
| `history_search` | **最多 8 条 × 600 字符摘录** | 关键词检索当前消息 + 当前 checkpoint 可达的压缩批次。英文按词、中文按**二字 bigram**；纯 lexical——改述不会被可靠匹配，模型可能需要多次换词搜索 |
| `history_read` | **4000 字符分页** | 按精确 source ID 读取原文；结果带 `truncated` 标记和 `next_offset`（还有剩余文本时） |

注意：笔记与检索文本都是**历史数据，不是新指令**，也不是"某操作真的成功了"的证明。source ID 包含内容与消息身份——消息被修改就产生不同版本（`source_id = "r" + sha256(...)[:32]`）。

## 归档什么、存到哪

成功压缩（自动与手动）把**即将离开活跃消息列表**的可见 user/assistant 文本、tool-call 名称/参数、tool-result 文本归档进批次。排除：system 消息、框架注入、reasoning 字段、artifacts、图片与二进制块（即便带 `text` 字段的非 text 类型块也不进归档）；可见的附件引用保留为文本，但不复制附件字节。澄清卡的有效用户回答会被收录（即使其 `HumanMessage` 对 UI 隐藏）；隐藏框架注入仍然排除。

**存储位置**：

```
{DEER_FLOW_HOME}/users/{user_id}/threads/{thread_id}/task-history/history.sqlite
```

在 sandbox 挂载的 `user-data` **之外**。SQLite 结构：`batches` 表 + FTS5 虚拟表 `sources`（`batch`/`id`/`payload` UNINDEXED + `words` 全文列）。来源敏感性与原任务消息相同。**线程作用域**：无跨 thread 搜索、无独立全局索引；thread 删除即移除整个目录；多主机部署需要各 worker 挂同一 thread 文件系统。

## Retention 与物理上限

- 批次上限 `max_batches`（默认 32）、每批记录 `max_records_per_batch`（默认 256）、单条 `max_record_chars`（默认 16000，超出截断并标 `truncated: true`）。
- **SQLite 硬顶**：`PRAGMA max_page_count=32768`（默认页大小下 = **128 MiB**）。
- 最老物理批次随新批次捕获而过期——**即使旧 checkpoint 仍引用它们**；读取/搜索返回 `partially_expired` 或 `unavailable`，缺失 source 需重新验证。`omitted_records` 描述最近一次捕获的记录上限截断数。
- 驱逐在替换插入**之前**、同一写事务内完成（`BEGIN IMMEDIATE` 先锁再选 victim，防并发捕获基于过期 retention 状态规划）；插入仍超页顶则回滚、保留旧批次。重复捕获受保护——即便 retention 上限被调小也不会丢当前批。
- 存储失败**保全普通压缩**（summary 不回滚），只把 history 标记 unavailable。异步写入经 `run_file_io` offload，取消返回前先排空（`acapture` 的 shield 循环）。

## 作用域绑定与回滚安全

- Checkpoint state 只保存**批次引用 + user/thread 作用域绑定**（`digest([user_id, thread_id])`），归档实体在文件系统。每个 reader（source 查找、捕获失败恢复、durable-context 渲染）都验证该元数据。
- 畸形 history 报告 `unavailable` 而不是中断任务；一次成功捕获即替换为有效元数据。已存在的有效引用仍可查，受同样的作用域与 retention 规则约束。
- **回滚到旧 checkpoint 无法泄露未来批次**；把 checkpoint 拷贝到其他 user/thread 不获得对原归档的访问权。
- Fork 可经既有 checkpoint 拷贝行为继承普通笔记/消息，但**不拷贝归档文件**；分支创建清除父归档引用与状态，继承的笔记引用因此可能不可用，需在分支内重新验证。

## 失败语义

| 状态 | 含义 |
|------|------|
| `unavailable` | 捕获失败 / 元数据畸形 / 存储故障；捕获失败后 history 工具**保持** unavailable（即使旧 source 仍可读） |
| `scope_unavailable` | 作用域不匹配（scope binding 校验失败） |
| `partially_expired` | 引用的批次中部分已物理过期；缺失 source 必须重新验证 |

未初始化（从未压缩过）时 history 缺失属正常，不算 unavailable。

## 写通道归一化（reducer / channel）

- `task_notes` 是 ThreadState 上的 `TaskNotesChannel`（`BinaryOperatorAggregate` 子类）+ `merge_task_notes` reducer：**每次 checkpoint 写入都归一化**，包括首次写入和经 Gateway/直接集成的 `Overwrite` 状态替换（这些路径绕过 reducer，靠 channel `update()` 兜底）。畸形条目与删除标记被丢弃，只保留最后 8 条有效笔记，每条保留项都强制标 `authority: model_report`。
- 直接状态写只做 source-ID **语法**检查；只有 `task_note` 工具在收录引用前检查可用性。
- durable-context reader（`DurableContextMiddleware`）对已存储状态应用同样校验，把 `{"notes": ..., "history_status": ..., "omitted_records": ...}` 注入既有的隐藏、转义 human 数据通道——**system 通道只有静态权威契约**。
- 未启用时 `task_notes` channel 保持未初始化：普通状态/SSE 快照里不出现 notebook。
- Subagent 压缩**不归档进父 thread**（子代理内部消息 `archive_task_history=False`）；特性也不向子图传递任意父状态、不自动恢复已停止的 run。

## 实现索引

| 文件 | 职责 |
|------|------|
| `backend/packages/harness/deerflow/agents/task_continuity/archive.py`（187 行） | SQLite 归档 + FTS5 检索：`scope()` / `records()` / `capture()` / `acapture()` / `lookup()`，`digest()` 生成 batch/source ID |
| `backend/packages/harness/deerflow/agents/task_continuity/state.py`（99 行） | `normalize_task_history` / `normalize_task_notes` / `merge_task_notes` / `TaskNotesChannel`，全部预算常量与 ID 正则 |
| `backend/packages/harness/deerflow/agents/task_continuity/tools.py`（105 行） | 三个 `StructuredTool`（同步 + 协程双模式，Gateway 异步 / DeerFlowClient 同步图都要）；`append_task_continuity_tools()` 仅在 `enabled=True` 时追加 |
| `backend/packages/harness/deerflow/config/task_continuity_config.py` | `TaskContinuityConfig`（pydantic，含 ge/le 钳制） |
| `backend/packages/harness/deerflow/agents/middlewares/summarization_middleware.py` | 压缩时调 `capture()`/`acapture()`，把 `task_history` 写入 checkpoint 更新 |
| `backend/packages/harness/deerflow/agents/thread_state.py` | `task_notes` / `task_history` channel 接线 |

## 证据包与测试

上游附带完整公开评测：[docs/experiments/task-continuity-20260912/](../../../docs/experiments/task-continuity-20260912/README.md)（A/B/C/D 协议、脚本、结果、[VALIDATION.md](../../../docs/experiments/task-continuity-20260912/VALIDATION.md)）。**关键结论**：向量检索（Qwen3-Embedding-0.6B + 等权 RRF 混合）叠加在关键词检索之上**未建立稳定净收益**（C vs D：净 −5.0 个百分点，配对 bootstrap 95% 区间 [−15.0, +5.0]，精确 McNemar p=0.625）——因此**生产实现是纯 lexical，无向量依赖**。注意：这些数字描述的是强制压缩下的独立 replay 原型，不是生产实现或完整 DeerFlow 基线的验收率。

`backend/tests/test_task_continuity.py`（607 行）覆盖：真实图压缩 + checkpoint resume 后的 source 恢复、作用域/回滚隔离、retention、截断、失败行为与工具契约。手动 live 集成检查用生产 middleware + 原生工具 + 合成历史：

```sh
cd backend
uv run python scripts/manual_task_continuity_check.py \
  --endpoints /path/to/private.json --output /tmp/task-continuity-check.json
```

私有 JSON 含 `llm_base`/`llm_model`/可选 `llm_key`，绝不提交。检查故意让摘要省略精确批次码，再重建图并要求 source search/read、一条带引用的 task note 和实际正确的 JSON manifest——验证的是受控恢复机制，不是生产验收率或质量基准。

---
> **See also:** [goal-continuation.md](goal-continuation.md)（同为线程内连续性机制）· [04-journal.md](04-journal.md)（压缩/摘要事件流）· [上游文档](../../../docs/task-continuity.md) · [concepts/memory/](../../concepts/memory/)（独立于 memory 系统）
