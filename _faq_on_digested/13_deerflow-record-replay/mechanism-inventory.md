# 机制清单：DeerFlow 已经长出了什么

> 本篇回答「零件全不全、长在哪、对应 DSH 的什么」。ReplayChatModel 自身的机制（归一化、caller key、golden 格式）不在本篇重复——以 [_digested/testing/07-record-replay.md](../../_digested/testing/07-record-replay.md) 为准；这里只做**零件盘点与跨仓对应**。

## 一句话

DeerFlow 不是「有类似思想」，是**同一思想的移植体**：三个零件（录制、回放、两层消费）全部在位，每个都能指出 DSH 对应物；21 号 FAQ 总结的三条经验里，「静默失效要 fail loud」「录制配置要 hermetic」各自长出了实现，「机制要发布成包」**没有**（v2.2.0 的测试夹具只活在 `backend/tests/` 内，见证据五）。

## 证据一：移植是明牌，不是暗合（现行出处是仓内文档与测试）

> ⚠️ **sync #8 更正（2.2.0）**：本条原据的 `docs/testing/README.md` L3/L29-37 与 `docs/testing/01-extension-testing-strategy.md` L114-124 **是 fork 时的自制内容，上游从不存在，已随 2.2.0 同步清除**；引用它们的地方一律改指下列上游文档与测试。

- 同一论断（两层车道、每条断言各守一面）在 2.2.0 的权威出处是 `backend/docs/REPLAY_E2E.md` L12-17（两层分工）与 L29-40（#3352 跨栈病例），以及 `backend/tests/test_replay_golden.py` L1-10、L70-72（为什么形状断言与 miss 清单防的不是同一类事）。
- 被移植的**语义**仍成立：DeerFlow 取的是 DSH「真跑一次 → 提交夹具 → 无 key 回放」的机制；21/01:94-99 列的六个守门人中，DeerFlow 只照做了「无 key 组装转录」（第 1 条）与「成本回到每次运行」（第 5 条），其余四条（历史世代格式回归、第二处 pin、事故 0001 式回归）没有对应物——这正是 [gaps-and-worth.md](gaps-and-worth.md) L0–L4 表的来源。

## 证据二：录制端——record-through-browser

`backend/scripts/record_gateway.py` L1-11 docstring：

> Runs the gateway with a REAL model and a callback that appends every model call's `(input_hash, output)` to a JSONL file. Because the run is driven by the real frontend (Playwright), the captured inputs are EXACTLY what the frontend produces (date system-reminder, suggestions/title calls, ...)

- 与 DSH 同源点：夹具是**系统的真实产物**而不是手搭 mock（DSH 否决「手写模型分片」的理由，21/01:37，同一句话）。
- hermetic 前提：录制网关把 `DEER_FLOW_HOME` 覆写指向全新临时目录（L110-111，注释：「an outer `DEER_FLOW_HOME` can't leak in and shift prompt-affecting paths/skills」）——对应 21/03:53「录制前提不是默认满足」的同款问题。
- 拼装：`backend/scripts/build_fixture_from_jsonl.py` L1-6，JSONL capture + `.meta.json` sidecar（scenario/mode/prompt）→ 回放夹具。
- 成本面：`frontend/playwright.record.config.ts` L7「never run in CI」——录制永远人工、要真 key（对应 DSH record/refresh 串行的成本属性，21/01:98）。

## 证据三：回放端——`ReplayChatModel`

- `backend/tests/replay_provider.py` L283-289；夹具经 `fixture` kwarg 或 `DEERFLOW_REPLAY_FIXTURE`（L85）；`bind_tools` no-op（L384-385）。
- **miss fail loud**：L342-351 的 KeyError 带已知哈希清单 + 归一化输入前 800 字符——诊断自带证据。
- 挂载：配置 `models[].use: replay_provider:ReplayChatModel`（L49-56 用法注释）；独立回放网关 `backend/scripts/run_replay_gateway.py`。对应 DSH「挂 llm-replay 插件 + patch 指夹具」（21/03:101-119）：形态不同、职责相同。

## 证据四：两层消费——独立期望，不是一份文件两用

- Layer 1（协议形状）：`backend/tests/test_replay_golden.py` L1-10——真 Gateway + 回放模型，SSE 事件序列逐事件等于提交进仓的 golden（L97）；Layer 2（语义渲染）：真前端 + Chromium（`backend/docs/REPLAY_E2E.md` L12-17）。
- **结构意义**：回放输入（fixture）与期望（`*.events.json` golden）是两个文件。DSH 自认的残余风险「一份文件两用会把坏脚本一致地复现出来」（隔壁 DSH 仓 21/01:59-63）在 DeerFlow 形状里**天然不存在**；代价是 golden 随有意协议变更人工刷新（`DEERFLOW_WRITE_GOLDEN=1`：开关在 `backend/tests/test_replay_golden.py:89`，命令见 `backend/docs/REPLAY_E2E.md:94`）——与 DSH 夹具 refresh 纪律同构。
- 2.2.0 的语料现状：`backend/tests/fixtures/replay/` 仍只有 write_read_file.ultra 一个场景（fixture + golden 两份文件，fixture 里 5 个 turns）；Layer 2 四个 spec 里只有 `real-backend-render.spec.ts` 读这份 fixture。

## 证据五：机制是发布的包

> ⚠️ **sync #8 更正（2.2.0）**：本条原据 `deerflow.testing`（随 `deerflow-harness` wheel 发布的测试工具包）
> 论证「机制是发布的包」。该包是 **fork 时的自制内容，上游从不存在，已随 2.2.0 同步清除**。
> 「机制可复用判据」在此**不成立**：2.2.0 的回放与脚本化模型都是 `backend/tests/` 内的仓内夹具
> （`replay_provider.py`、`_replay_fixture.py`、`test_goal_evaluator_accounting.py:29` 的
> `class ScriptedModel(BaseChatModel)`），下游仓要么复制要么自建。以下两条保留为**历史记录**，
> 不再作为现行事实引用。

- ~~`deerflow.testing` 随 `deerflow-harness` wheel 发布~~（已不适用）；原据 `testing/AGENTS.md`「One mock only」「Test-only, but published」。
- keyless 切片：原据 `examples/deerflow-extension-example/tests/test_model_surface.py`——**该文件在 2.2.0 树里已不存在**（示例家族重构后只剩 `test_entry_point.py` / `test_plugin.py` / `test_tool_stats.py`），全树也搜不到 `deerflow.testing` 的任何调用方。DSH `request/header` pin 的语义等价物（「改了模型看得到的东西就让测试红」）在 2.2.0 只能靠**就地写**的 `class ScriptedModel(BaseChatModel)`（如 `backend/tests/test_goal_evaluator_accounting.py:29`）或 `FakeToolCallingModel` 自建。替身谱系定位见 `_digested/test-strategy/02-deterministic-llm.md`（四级替身表）。

## 证据六：hermetic config——同一问题、不同解法

- 问题声明：`backend/tests/_replay_fixture.py` L1-8「Record and replay MUST drive the gateway through an identical, prompt-affecting config — otherwise the system prompt differs and the recorded input hashes never match」。
- `build_config_yaml`（L49-59）钉死 prompt-affecting 一切：sandbox/tool_groups 固定、skills 指空目录、extensions_config 空、**memory/summarization 禁用**（后台 debounce 不可复现）。
- record 与 replay 的**唯一**差异是 `models[].use` 一块（L20/L31/L39，同名 model 只换实现）。
- 对照 DSH：21/01:42 记录的教训——「live 与 snapshot 配置各一份 → 125 行近乎复制 → 静默漂移 → overlay patch」。DeerFlow 的解法是**一个共享 builder、差异收敛到一个参数**：在漂移发生前从结构上排除。

## 这一篇要你记住的

- 问题不是「有没有」而是「活成什么样」：录制、回放、两层消费三个零件全在，且各有 DSH 对应物；第四件「发布的包」没有（证据五）。
- 两层期望结构（fixture ≠ golden）天然规避「一份文件两用」的残余风险——不是对 DSH 的批评，是两种夹具形态的自然后果。
- 录制要专门跑（key + Playwright + hermetic home）：DeerFlow 里「夹具从哪来」的成本比 DSH 高——伏笔见 [production-logging-gap.md](production-logging-gap.md)。
