# 生产侧落盘：DeerFlow 没有 session.jsonl

> 本篇回答「DSH 的持久化即 model-visible 面，DeerFlow 的持久化是什么」。run_events 的机制事实（RunEventStore / RunJournal 契约）以 [_digested/observability/02-run-events-and-journal.md](../../_digested/observability/02-run-events-and-journal.md) 为准，本篇只盘点**它记什么、不记什么**。

## 一句话

DSH 的持久化层**就是** model-visible 面：`session.jsonl` 记着 `request/header`，model-visible ⟺ logged 让「生产日志、回放夹具、导出」三面一体。DeerFlow 的持久化是 checkpoint（graph state）+ run_events（UI 事件面）+ 工作区，**模型实际收到的完整请求落盘即消失**——这是两个仓最深的一处不对等，也是缺口清单的根源。

## DSH 侧回顾（经 21 号引用）

- `session.jsonl` 默认 zstd 落盘，`request/header` 是核心资产（21/02:53-63）。
- 不变量 model-visible ⟺ logged：到达模型请求的东西必须能从会话日志重建（21/01:67-79）→ 生产日志即夹具原料（DSH 的 llm-replay 接受未投影的原始运行日志）。
- 导出：`/export` 与 Download session log 出明文 zip（21/03:99）。

## DeerFlow 侧盘点：生产到底落了什么

三样东西，各记什么、缺什么：

1. **Checkpoints**（LangGraph checkpointer；接线形状 `backend/packages/harness/deerflow/runtime/checkpoint_state.py` L130）：graph state = messages 转录等。这是「对话状态」的持久化，**不是「每次调用收到什么」的持久化**。两个具体例证：
   - ViewImageMiddleware 在 `wrap_model_call` 内注入图片 payload，「the payload never enters graph state」（`backend/AGENTS.md` Vision Support 节）——模型收到的东西可以**有意地**不进持久化；
   - compaction 写新 checkpoint 只更新 `messages` / `summary_text`（`backend/AGENTS.md` Context Summarization 节）——checkpoint 记状态变迁，不记请求。
2. **run_events**（`backend/packages/harness/deerflow/persistence/models/run_event.py` L14；`(thread_id, seq)` 唯一约束 L33）：事件类型清单见 `runtime/events/catalog.py` L58-71——`run.start` / `llm.human.input` / `llm.ai.response` / `llm.tool.result` / `llm.error` / `subagent.*` / `context:memory` / `workspace.changes`。**记了模型说了什么、工具回了什么，没有一条记「模型收到了什么」**：没有 `request/header` 等价物。它是 UI/审计事件流（消费面见 digest），不是轨迹。
3. **工作区 / sandbox**：文件产物 + `workspace.changes` 事件——与 DSH 的 `workspace.expected/`（独立世界 oracle，21/01:86）角色部分同源，但那是测试侧期望，不是生产落盘。

## 结论：那条不变量在 DeerFlow 没有被声明

- 全仓检索：没有 model-visible ⟺ logged 的对应表述（`model-visible` 只作形容词零散出现，如 `tools/builtins/tool_search.py` L179、`subagents/status_contract.py` L3，语义是「模型看得到的」，不是可重建性不变量）。
- **后果一**：不能从生产数据重建一次模型调用——用户报 bug 只能带截图与文字描述。
- **后果二**：录制必须专门跑——`record_gateway.py` 要 key、要 Playwright、要起专用网关（L26-33 env 要求）。「真跑一次留下日志」在 DeerFlow 不是免费的。
- **公平性说明（这不是单纯缺陷）**：DSH 是单机 CLI，日志归用户所有、体量可控；DeerFlow 是多用户服务（SQLite/Postgres），全量 request/header 落盘意味着体积、隐私、审计三个成本面的量级变化。没有这条不变量是**未做声明**，而不声明就不欠机制。21 号「机制可以拿，制度不要抄」在这里反向适用：连「要不要这条不变量」本身都是一个要自己做的决定。

## 这一篇要你记住的

- DeerFlow 的三样持久化各管「状态 / 事件 / 工作区」，没有一样管「请求」。
- 「夹具从哪来」在两个仓是两种世界观：DSH 生产日志即原料；DeerFlow 必须专门录制。
- 缺的不是某张表，是一条不变量的声明——有了它，[gaps-and-worth.md](gaps-and-worth.md) 缺口一（run→fixture 导出器）才有立足点。
