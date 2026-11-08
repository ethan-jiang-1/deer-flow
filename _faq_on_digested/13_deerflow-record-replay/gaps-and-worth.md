# 缺什么、值多少、按什么顺序补

> 本篇回答「缺口清单与行动判断」。三个缺口按值/价排序；末尾有一条反方向提醒和 DeerFlow 语境的 L0–L4 现状表。

## 一句话

DeerFlow 版缺口有三个：生产 run→夹具的导出器（bug 复现路线断头）、override 等价物（四类失败表达不了）、调用数对账（少了调用无感知）。**最值的是第一个**；另外不要为了「更 DSH」把 system prompt 塞回回放哈希。

## 缺口一：生产 run → 夹具的管道（最值得补）

- 现状：DSH 的 bug 复现三档做法（21/06）在 DeerFlow 只有第零档——口头复述 + 手搭 `ScriptedModel` 场景（替身谱系见 `_digested/test-strategy/02-deterministic-llm.md`）。
- 为什么可行：原料大半在——run_events 有 `llm.human.input` / `llm.ai.response` / `llm.tool.result`（`runtime/events/catalog.py` L61-63），checkpoints 有 messages 转录；而哈希口径天然一致：「The same `hash_messages` is used by the recorder and here, so record and replay agree by construction」（`backend/tests/replay_provider.py` L37-41）——导出器只要把一次 run 的调用序列拼成 fixture JSON，键就不需要第二次发明。
- 难点（诚实账单）：
  - caller 归因要从持久化数据恢复——录制时靠回调拿 tags/run_name（L127-134），DB 里未必有等价信息；
  - 「模型收到的输入」只能重建到**归一化投影**粒度——恰好够配对（哈希就是投影），不够 pin（缺 `request/header` 原文）。所以这条管道补的是**复现**，不是 DSH 那种**钉住**——两者在 21/04 的账本里本来就分列。
- 隐私：用户文本进夹具 = 21/03:157 的 live/authored 选择题在 DeerFlow 重演；DeerFlow 没有 typed token 基建，authored 化全靠手工。

## 缺口二：override 等价物（四类失败）

- DSH：`replay.override.json` 表达 pre-2xx 抛 / post-2xx 抛 / 挂起 / 注入重试（21/02:77-92）——「复现 provider 401 / 用户取消 / 流挂住不用另搭 mock」。
- DeerFlow：`ReplayChatModel` 只会成功吐 AIMessage（L354-382）；错误路径只能靠单测层替身表达，全车道无对应物。而 DeerFlow 恰好有一个「错误被中间件吞掉」的敏感面（LLMErrorHandlingMiddleware——`_replay_misses` 的整个设计 L95-101 就是因为错误处理吞异常），**「错误形态的回放」对 DeerFlow 的边际价值其实比 DSH 更高**。
- 但优先级仍低：等一个真实的「错误形态回归」事故再建（21 号 L4 按触发条件启用的同款判据）。

## 缺口三：调用数对账（最便宜）

- 位置绑定的 DSH 少调多调都炸；DeerFlow 哈希绑定「多了且不匹配 → miss 炸；**少了 → 无感知**」。fixture 的 turns 数与实际消耗数对账（等价 DSH 的 `assertConsumed`，21/03:142）是一行断言的事，但现在没有。
- 现状下「少了调用」的暴露路径只有 SSE golden（事件序列变了才红）——「次序内消失」恰好是 golden 最难抓的形态。

## 反方向提醒：不要把 system prompt 塞回哈希

- 诱惑：DSH 靠 `request/header` pin 抓 prompt 漂移，看着更强，照抄？
- 不要。`backend/tests/replay_provider.py` L201-207 的理由在 DeerFlow 语境更强（prompt 是高频编辑面）。要 prompt 报警，正确位置是显式 opt-in 的 prompt-golden 测试或 `ScriptedModel` 断言——塞进回放哈希，每个改 prompt 的 PR 都会带一次全量 re-record。

## 值多少的校准

- **已经拿到的回报**：#3352（两侧单测全绿、只有真前端 × 真后端抓到，`backend/docs/REPLAY_E2E.md` L29-40；病例详解见 `_digested/test-strategy/03-contract-e2e.md`）——对应 DSH 的 ACP 事故，两边各自用一次真事故为自己的车道做了 existence proof。
- **覆盖面校准**：目前夹具语料 = 1 个场景（`backend/tests/fixtures/replay/` 下 write_read_file.ultra），与 DSH 210 场景不是一个量级。DeerFlow 的台阶五现状是「车道存在 + 样板存在」，不是「语料治理存在」——正是 21 号 05 篇「机制与制度分开」的活例：DeerFlow 拿了机制，corpus policy / 世代 / manifest 那套制度没有拿（也暂时不需要）。

## 采用阶梯（DeerFlow 语境现状盘点）

| 阶 | 内容 | 现状 |
|---|---|---|
| L0 | hermetic config + 两层 golden 车道 | ✅ 已在（`_replay_fixture.py` + `test_replay_golden.py` + 前端 e2e-real-backend） |
| L1 | 扩展作者 keyless 切片（`ScriptedModel.requests`） | ✅ 已在（`test_model_surface.py` + `deerflow.testing`） |
| L2 | 多场景语料 + 触发式更新纪律 | ⚠️ 车道在，语料 1 个场景 |
| L3 | run→fixture 导出器（bug 复现） | ❌ 最值得补（缺口一） |
| L4 | override 等价物 + 调用数对账 | ❌ 按事故触发（对账便宜，可随 L3 顺手做） |

## 这一篇要你记住的

- 三个缺口按「值/价」排序：导出器 > 调用数对账 > override 等价物。
- 导出器补的是复现不是钉住——因为生产侧没有 request/header（[production-logging-gap.md](production-logging-gap.md) 结论的直接下游）。
- 已经拿到的回报（#3352）说明这条思想在 DeerFlow 不是理论；缺的是把「复现」那一端接上。
