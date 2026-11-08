# 机制清单：DeerFlow 已经长出了什么

> 本篇回答「零件全不全、长在哪、对应 DSH 的什么」。ReplayChatModel 自身的机制（归一化、caller key、golden 格式）不在本篇重复——以 [_digested/testing/07-record-replay.md](../../_digested/testing/07-record-replay.md) 为准；这里只做**零件盘点与跨仓对应**。

## 一句话

DeerFlow 不是「有类似思想」，是**同一思想的移植体**：四个零件（录制、回放、消费、发布包）全部在位，每个都能指出 DSH 对应物；连 21 号 FAQ 总结出的三条经验（机制要发布成包、静默失效要 fail loud、录制配置要 hermetic）都各自长出了实现。

## 证据一：移植是明牌，不是暗合

- `docs/testing/README.md` L3：「移植自 DeepSeek Harness 的插件测试策略（`_digested/test-strategy/08·09·10`），按 DeerFlow 的扩展契约重写」；L29-37 五级阶梯表，第⑤级行「组装转录 | keyless 转录固定；全车道 = record/replay」。
- `docs/testing/01-extension-testing-strategy.md` L114-124（台阶五）：「DeerFlow 的全车道**已经存在**」，直接列出录制脚本、回放 provider、夹具目录三个锚点。
- 移植不是逐字翻译：startup-only 改掉台阶三的形状（没有 HMR 可测 → 测装载遏制四不变量）；`IsolatedMiddleware` 的观察性 wrap 契约收走「改请求」的面（L97-103）；可配置性证据从「注入的 prompt」换成「配置出的工具 + 两脸断言」（L110-112）。这正是 21 号「机制可以拿，制度不要抄」的 DeerFlow 落法。

## 证据二：录制端——record-through-browser

`backend/scripts/record_gateway.py` L1-13 docstring：

> Runs the gateway with a REAL model and a callback that appends every model call's `(input_hash, output)` to a JSONL file. Because the run is driven by the real frontend (Playwright), the captured inputs are EXACTLY what the frontend produces (date system-reminder, suggestions/title calls, ...)

- 与 DSH 同源点：夹具是**系统的真实产物**而不是手搭 mock（DSH 否决「手写模型分片」的理由，21/01:37，同一句话）。
- hermetic 前提：录制网关把 `DEER_FLOW_HOME` 覆写指向全新临时目录（L87-90，注释：「an outer `DEER_FLOW_HOME` can't leak in and shift prompt-affecting paths/skills」）——对应 21/03「录制前提不是默认满足」的同款问题。
- 拼装：`backend/scripts/build_fixture_from_jsonl.py` L1-6，JSONL capture + `.meta.json` sidecar（scenario/mode/prompt）→ 回放夹具。
- 成本面：`frontend/playwright.record.config.ts` L7「never run in CI」——录制永远人工、要真 key（对应 DSH record/refresh 串行的成本属性，21/01:98）。

## 证据三：回放端——`ReplayChatModel`

- `backend/tests/replay_provider.py` L283-289；夹具经 `fixture` kwarg 或 `DEERFLOW_REPLAY_FIXTURE`（L85）；`bind_tools` no-op（L384-385）。
- **miss fail loud**：L342-351 的 KeyError 带已知哈希清单 + 归一化输入前 800 字符——诊断自带证据。
- 挂载：配置 `models[].use: replay_provider:ReplayChatModel`（L49-56 用法注释）；独立回放网关 `backend/scripts/run_replay_gateway.py`。对应 DSH「挂 llm-replay 插件 + patch 指夹具」（21/03:101-119）：形态不同、职责相同。

## 证据四：两层消费——独立期望，不是一份文件两用

- Layer 1（协议形状）：`backend/tests/test_replay_golden.py` L1-10——真 Gateway + 回放模型，SSE 事件序列逐事件等于提交进仓的 golden（L97）；Layer 2（语义渲染）：真前端 + Chromium（`backend/docs/REPLAY_E2E.md` L12-17）。
- **结构意义**：回放输入（fixture）与期望（`*.events.json` golden）是两个文件。DSH 自认的残余风险「一份文件两用会把坏脚本一致地复现出来」（21/01:59-63）在 DeerFlow 形状里**天然不存在**；代价是 golden 随有意协议变更人工刷新（`DEERFLOW_WRITE_GOLDEN=1`，L92-95）——与 DSH 夹具 refresh 纪律同构。

## 证据五：机制是发布的包

- `deerflow.testing` 随 `deerflow-harness` wheel 发布；`backend/packages/harness/deerflow/testing/AGENTS.md` L12-15「One mock only」「Test-only, but published」——下游仓 import 而不是拷 fake。对应 21/03 证据一「回放器是发布在 npm 上的普通插件」：机制可复用判据在 DeerFlow 全部成立。
- keyless 切片：`examples/deerflow-extension-example/tests/test_model_surface.py` L1-7「If you change what the model sees (tool naming, result shape, message flow), this test fails — that is the point」——DSH `request/header` pin（21/02:53-63）的语义等价物，载体从 sidecar 文件换成进程内断言（`ScriptedModel.requests` / `bound_tools`，`testing/models.py` L41-51「This is the model-visible face」）。替身谱系定位见 `_digested/test-strategy/02-deterministic-llm.md`（四级替身表）。

## 证据六：hermetic config——同一问题、不同解法

- 问题声明：`backend/tests/_replay_fixture.py` L1-8「Record and replay MUST drive the gateway through an identical, prompt-affecting config — otherwise the system prompt differs and the recorded input hashes never match」。
- `build_config_yaml`（L49-59）钉死 prompt-affecting 一切：sandbox/tool_groups 固定、skills 指空目录、extensions_config 空、**memory/summarization 禁用**（后台 debounce 不可复现）。
- record 与 replay 的**唯一**差异是 `models[].use` 一块（L20/L31/L39，同名 model 只换实现）。
- 对照 DSH：21/01:42 记录的教训——「live 与 snapshot 配置各一份 → 125 行近乎复制 → 静默漂移 → overlay patch」。DeerFlow 的解法是**一个共享 builder、差异收敛到一个参数**：在漂移发生前从结构上排除。

## 这一篇要你记住的

- 问题不是「有没有」而是「活成什么样」：四个零件全在，且各有 DSH 对应物。
- 两层期望结构（fixture ≠ golden）天然规避「一份文件两用」的残余风险——不是对 DSH 的批评，是两种夹具形态的自然后果。
- 录制要专门跑（key + Playwright + hermetic home）：DeerFlow 里「夹具从哪来」的成本比 DSH 高——伏笔见 [production-logging-gap.md](production-logging-gap.md)。
