---
title: "Task Continuity — 任务连续性"
description: 'opt-in 的任务笔记 + 压缩历史召回：task_note/history_search/history_read 三工具、thread 级 SQLite 归档、retention/作用域/失败语义、与 memory 的边界、上游评测结论。'
topics: [runtime, compaction, task-continuity, notes, recall]
verified_against: v2.2.0
last_verified: 2026-11-08
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
| `task_note` | **8 条 × 750 字符 × 4 个 source ID**（key：40 个 ASCII 字母/数字/`_`/`-`） | 保存/替换/删除（空 content = 删除）命名笔记。满员时返回 `note_capacity`，需先替换既有 key 或等本批结束（🆕 语义见下"批次预留"）。source ID 只做可用性检查，不代表语义支持——**所有笔记都是 model report**，不经验证 |
| `history_search` | **最多 8 条 × 600 字符摘录** | 关键词检索当前消息 + 当前 checkpoint 可达的压缩批次。英文按词、中文按**二字 bigram**；纯 lexical——改述不会被可靠匹配，模型可能需要多次换词搜索。🆕 可选 `role=user\|assistant\|tool` |
| `history_read` | **4000 字符分页** | 按精确 source ID 读取原文；结果带 `truncated` 标记和 `next_offset`（还有剩余文本时）。**没有** role 参数 |

### 🆕 2.2.0：`history_search` 的 role 过滤与精确摘录

**`role`**（`tools.py::_history_search`）：`user` / `assistant` / `tool`，在工具边界映射成存储里的 `human` / `ai` / `tool`；省略或 `null` 搜全部角色。非法值返回 `{"error": "invalid_role"}`。**过滤发生在 8 条上限之前**（归档侧先进 SQL，活动消息侧先进列表），所以过滤是"在这个角色里取前 8 条"，不是"取前 8 条再筛"。返回的 `role` 仍是存储值（`human`/`ai`/`tool`）。`history_read` 刻意不加 role 参数。

**精确摘录**（`archive.py::_search_excerpt`）：2.1.0 是 `text[:600]`——摘录永远是源开头，跟查询词没有关系。2.2.0 改为：

- 返回 `excerpt` + `excerpt_start` / `excerpt_end`，是**可读源文本上的 0 基、半开区间字符偏移**，可与 `history_read(offset=excerpt_start)` 直接对接；
- 以**最早一个落得下的匹配**为中心开窗（两侧尽量居中），落不下就继续找下一个匹配，包括**重叠**匹配；一个都落不下则退回源开头并置 `excerpt_match = false`；
- casefold 会把某些字符展开成多个（如 `ß`→`ss`），所以偏移要映射回**原字符**，不能用字节或 casefold 后字符串的下标；
- 活动源用 **substring** 匹配；归档源用与 FTS 索引同一套 **token span**；同一 ID 两个都有时**活动文本优先**；归档有重复版本（同一 source 在不同长度被归档过）时取**首个 rowid 版本**，与 `history_read` 的取法一致，偏移也必须基于同一份文本。

### 🆕 2.2.0：`task_note` 的批次容量预留

2.1.0 的规则是"下单条时看当前 `len(notes)`"。问题：模型在一个 batch 里并行发出多条 `task_note`，每条都看到同一个旧 `notes` 快照，于是都以为有空位，最后靠 reducer 的"保留最后 8 条 insertion-order"兜底——静默丢笔记。

2.2.0（`tools.py::_has_note_capacity`）：

- 从 `runtime.state["messages"]` 里**最后一条 AIMessage** 取出本 batch 的所有 `task_note` 调用，按 **tool-call 顺序**逐个预留 slot；只有被预留到的 key 才被接受。
- 兄弟调用里**结构非法**的（key/content/source 形状不合法）直接跳过、不占位，也不在预留阶段做 source 查找。
- **兄弟删除或运行时拒绝腾出的 slot 不会借给本批**——它们尚未提交，可能被拒；这些空位在**下一批**重算。
- 直接工具调用（没有模型 batch）退化为原来的单调用容量检查。
- 预留和执行共用 `_note_shape_error()`，所以"预留能过、执行被拒"这种分歧不会出现。
- 启用 artifact handle 解析时，预留读的是 `ArtifactResolutionMiddleware` 提供的**调用局部实参视图** `RESOLVED_TOOL_CALL_ARGS_KEY = "__resolved_tool_call_args"`（`state.py`）——它与执行用的是同一个 resolver；该键**只存在于当前 `ToolRuntime.state`**，不进消息、不进 checkpoint。解析关闭或直接工具图下用原始参数。

对应的回归在 `backend/tests/test_task_note_capacity.py`（跑真实图；锁一个快照无法协调并行 Command）。

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
行数为 v2.2.0 实测。

| `backend/packages/harness/deerflow/agents/task_continuity/archive.py`（254 行，v2.1.0 为 187） | SQLite 归档 + FTS5 检索：`scope()` / `records()` / `capture()` / `acapture()` / `lookup()`，`digest()` 生成 batch/source ID；🆕 `_token_spans()` / `_search_excerpt()` |
| `backend/packages/harness/deerflow/agents/task_continuity/state.py`（103 行，v2.1.0 为 99） | `normalize_task_history` / `normalize_task_notes` / `merge_task_notes` / `TaskNotesChannel`，全部预算常量与 ID 正则；🆕 `RESOLVED_TOOL_CALL_ARGS_KEY` |
| `backend/packages/harness/deerflow/agents/task_continuity/tools.py`（166 行，v2.1.0 为 105） | 三个 `StructuredTool`（同步 + 协程双模式，Gateway 异步 / DeerFlowClient 同步图都要）；`append_task_continuity_tools()` 仅在 `enabled=True` 时追加；🆕 `_note_shape_error()` / `_has_note_capacity()` |
| `backend/packages/harness/deerflow/agents/task_continuity/AGENTS.md`（🆕 2.2.0 新增，39 行） | 预留/摘录两条契约的开发约束 |
| `backend/packages/harness/deerflow/config/task_continuity_config.py` | `TaskContinuityConfig`（pydantic，含 ge/le 钳制） |
| `backend/packages/harness/deerflow/agents/middlewares/summarization_middleware.py` | 压缩时调 `capture()`/`acapture()`，把 `task_history` 写入 checkpoint 更新 |
| `backend/packages/harness/deerflow/agents/thread_state.py` | `task_notes` / `task_history` channel 接线 |

## 证据包与测试

上游附带完整公开评测：[docs/experiments/task-continuity-20260912/](../../../docs/experiments/task-continuity-20260912/README.md)（A/B/C/D 协议、脚本、结果、[VALIDATION.md](../../../docs/experiments/task-continuity-20260912/VALIDATION.md)）。**关键结论**：向量检索（Qwen3-Embedding-0.6B + 等权 RRF 混合）叠加在关键词检索之上**未建立稳定净收益**（C vs D：净 −5.0 个百分点，配对 bootstrap 95% 区间 [−15.0, +5.0]，精确 McNemar p=0.625）——因此**生产实现是纯 lexical，无向量依赖**。注意：这些数字描述的是强制压缩下的独立 replay 原型，不是生产实现或完整 DeerFlow 基线的验收率。

`backend/tests/test_task_continuity.py`（1004 行，v2.1.0 为 607 行；2.2.0 新增 397 行）覆盖：真实图压缩 + checkpoint resume 后的 source 恢复、作用域/回滚隔离、retention、截断、失败行为与工具契约，以及 🆕 role 过滤、摘录偏移（含 casefold 展开与重叠匹配）、批次预留。手动 live 集成检查用生产 middleware + 原生工具 + 合成历史：

```sh
cd backend
uv run python scripts/manual_task_continuity_check.py \
  --endpoints /path/to/private.json --output /tmp/task-continuity-check.json
```

私有 JSON 含 `llm_base`/`llm_model`/可选 `llm_key`，绝不提交。检查故意让摘要省略精确批次码，再重建图并要求 source search/read、一条带引用的 task note 和实际正确的 JSON manifest——验证的是受控恢复机制，不是生产验收率或质量基准。

---
> **See also:** [goal-continuation.md](goal-continuation.md)（同为线程内连续性机制）· [04-journal.md](04-journal.md)（压缩/摘要事件流）· [上游文档](../../../docs/task-continuity.md) · [concepts/memory/](../../concepts/memory/)（独立于 memory 系统）
