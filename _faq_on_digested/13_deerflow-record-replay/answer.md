# A13: DeerFlow 有没有 DSH 那套「录制会话快照」的思想？

![一页看懂：左列（蓝）思想同源——DeerFlow 测试策略明写移植自 DSH，第⑤级台阶「组装转录」对应快照层，录制/回放/两层消费/发布包四个零件全在；中列（绿）形状相反——DSH trajectory 夹具、位置绑定、pin request/header、一份文件两用，DeerFlow hash-by-input、顺序无关、排除 system prompt、回放输入与 SSE golden 期望分离；右列（琥珀与红）生产侧不对等与三个缺口——checkpoint+run_events 都不含模型请求面，于是没有 run→fixture 导出器（bug 复现断头）、没有 override 等价物（四类失败）、没有调用数对账（少了调用无感知）；底部一句话记法：思想同源，形状相反；多层证据各管一面，生产落盘缺 model-visible](./figures/answer-overview.svg)

## 一分钟答案

**「DeerFlow 没有这套东西」错了一半；另一半是对的。**

1. **机制层面：有，但不是"移植来的"，是并行长成的东西。** ⚠️ **sync #8 更正**：旧版本这里写「`docs/testing/README.md` L3 明写移植自 DSH、五级台阶第⑤级组装转录」——**`docs/testing/` 整个目录是 fork 时的自制内容，上游从不存在，已随 2.2.0 同步清除**（同批被清的还有 `deerflow.testing` 发布包）。现行一手证据只剩代码：`backend/tests/replay_provider.py` + `backend/tests/_replay_fixture.py` + `backend/tests/test_replay_golden.py` + `frontend/playwright.record.config.ts`，机制文档是 `backend/docs/REPLAY_E2E.md`。所以准确说法是：**上游 DeerFlow 自己演化出了一套 record/replay，形状与 DSH 那套同源同题但各自成立**（→ [mechanism-inventory.md](mechanism-inventory.md)）。
2. **形状层面：处处相反，但各自成立。** DSH：trajectory 夹具、位置绑定、pin 住 request/header、一份文件两用。DeerFlow：hash-by-input、顺序无关、挥发字段先归一化、**有意把 system prompt 排除出匹配键**（`backend/tests/replay_provider.py` L201）、回放输入与期望（独立提交的 SSE golden）分离。两边都把取舍理由写在源码注释里——这不是谁抄错谁，是各自宿主事实（持久化形态、运行拓扑、消费方式）的自然后果（→ [two-shapes.md](two-shapes.md)）。
3. **生产落盘层面：不对等——最初判断对的那一半。** DeerFlow 落盘的是 checkpoint（graph state）+ run_events（UI 事件面，事件类型清单 `backend/packages/harness/deerflow/runtime/events/catalog.py` L58-66 与 L117 的 `WORKER_RUN_EVENT_DEFINITIONS` 里没有一条记「模型收到了什么」）。模型实际收到的完整请求落盘即消失，没有 session.jsonl 等价物，也没有 model-visible ⟺ logged 式的不变量声明（→ [production-logging-gap.md](production-logging-gap.md)）。v2.2.0 给这道缺口**收了窄窄一条边**：`run_events` 表新增 `content_sha256` 列，能证明"这条事件的内容没被改过"，**但仍不含模型请求面**——可验证性有了，可复现性没有。
4. **它已经拿到过回报。** #3352：后端 ordering 测试全绿、前端单测把假设 hardcode 进 mock 也全绿，只有真前端 × 真后端的车道抓到上下文压缩后刷新线程乱序——「组装转录/真实组装」思想的价值证明，DeerFlow 版的 DSH「ACP 事故」（病例详见 `_digested/test-strategy/03-contract-e2e.md`，此处不重复）。
5. **缺口三个，按值/价排序**：生产 run→夹具导出器（bug 复现路线断头，最值得补）> 调用数对账（少了调用无感知，最便宜）> override 等价物（四类失败表达不了，按事故触发）。另有一条反方向提醒：**不要**为了「更 DSH」把 system prompt 塞回回放哈希（→ [gaps-and-worth.md](gaps-and-worth.md)）。

一句话记法：**思想同源，形状相反；多层证据各管一面，生产落盘缺 model-visible。**

## 详细展开

| 文件 | 回答什么 |
|---|---|
| [mechanism-inventory.md](mechanism-inventory.md) | 机制的每个零件在哪、对应 DSH 的什么（录制端 / 回放端 / 两层消费 / 发布包 / hermetic config） |
| [two-shapes.md](two-shapes.md) | 六个决定点的对照表；system prompt 的两种命运；为什么 DeerFlow 用不了位置绑定 |
| [production-logging-gap.md](production-logging-gap.md) | checkpoint / run_events / 工作区各记什么、缺什么；不变量未被声明的后果与公平性说明 |
| [gaps-and-worth.md](gaps-and-worth.md) | 三个缺口按值/价排序；不要补什么；DeerFlow 语境的 L0–L4 |

## 相关 digest 笔记（知识基础；机制细节以它们为准，本 FAQ 不重复）

- [_digested/testing/07-record-replay.md](../../_digested/testing/07-record-replay.md) —— ReplayChatModel 机制：归一化、system 排除、caller-aware key、golden JSON
- [_digested/test-strategy/02-deterministic-llm.md](../../_digested/test-strategy/02-deterministic-llm.md) —— 确定性 LLM 四级替身谱系（`ScriptedModel` 所在的谱系）
- [_digested/test-strategy/03-contract-e2e.md](../../_digested/test-strategy/03-contract-e2e.md) —— 两层跨栈 e2e 与 #3352 病例
- [_digested/observability/02-run-events-and-journal.md](../../_digested/observability/02-run-events-and-journal.md) —— RunEventStore / RunJournal 事件流契约（生产落盘侧的机制事实以此为准）

## 关键源码

- ⚠️ **sync #8 更正（2.2.0）**：原先这里的 `docs/testing/*` 与 `backend/packages/harness/deerflow/testing/models.py`（`ScriptedModel` 发布包）**是 fork 时的自制内容，上游从不存在，已随 2.2.0 同步清除**。2.2.0 的脚本化模型只是局部夹具（如 `backend/tests/test_goal_evaluator_accounting.py:29` 的 `class ScriptedModel(BaseChatModel)`），不发布、不可复用——本文「证据五：机制是发布的包」一节据此降级。
- `backend/scripts/record_gateway.py` L1-13（record-through-browser docstring）、L87-90（hermetic DEER_FLOW_HOME）；`backend/scripts/build_fixture_from_jsonl.py` L1-6（JSONL → fixture 拼装）
- `backend/tests/replay_provider.py` L22-35（why hash-by-input）、L37-41（record/replay 共享同一哈希）、L85（`DEERFLOW_REPLAY_FIXTURE`）、L95-101（`_replay_misses` 与被吞风险）、L144-176（归一化正则）、L201（system 排除）、L225（hide_from_ui 剔除）、L245-252（哈希函数）、L283-289（ReplayChatModel）、L342-351（miss fail loud）、L384-385（bind_tools no-op）
- `backend/tests/_replay_fixture.py` L1-8（record/replay 必须同 config）、L20/L31/L39（只换 `models[].use` 一块）、L49-59（hermetic config：skills 空目录、memory/summarization 禁用）
- `backend/tests/test_replay_golden.py` L1-10（Layer 1）、L83-87（miss fail loud 断言）、L97（`assert events == golden`）；`backend/docs/REPLAY_E2E.md` L12-17（两层分工）、L29-40（#3352）
- `backend/packages/harness/deerflow/persistence/models/run_event.py` L14、L33（`(thread_id, seq)` 唯一约束）；`backend/packages/harness/deerflow/runtime/events/catalog.py` L58-71（事件类型清单）；`backend/packages/harness/deerflow/runtime/checkpoint_state.py` L130（checkpointer 接线形状）
- `frontend/playwright.record.config.ts` L7（never run in CI）、L21（录制入口命令）

## 外部来源与基线

- **DSH 仓**（本机 `/Users/bowhead/deepseek-harness`）：`_faq_on_digested/21_recorded-session-snapshots/` 的 question / answer / 01-06 篇，下文以「21/01:59-63」形式引用（21 号文件自身行号）。其基线 `dsh-v0.2.1-rc.2`（`687f282e8625c6b8d11ff58211a90524be2e4317`，2026-10-18；DSH FAQ 21 号 question 已升到这个基线，本文旧版写的 `dsh-v0.2.0-rc.2`/`639ed01539` 已过时）。**行号纪律**：下文所有「21/xx:NN」都以该树为准，DSH 侧换基线后需重扫。
- **DeerFlow 侧基线**：工作树 `230149ed7`（2026-10-09 21:34）。行号以该树为准；树从 `ff63563f1` 前移后抽验 7 处关键锚点未漂。
