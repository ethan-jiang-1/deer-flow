# 同一条不变量，两种形状

> 本篇回答「为什么两边几乎处处相反」。结论先行：不是谁对谁错，是**各自的持久化形态、运行拓扑、消费方式**决定了哪种配对方式成立。

![形状对照：顶部共同目标条「模型实际收到什么，必须有可 diff 的固定形态」；左侧 DSH 流水线——真跑一次产生 session.jsonl（含 request/header），同一份文件既作回放输入又作期望输出，按 first-call 位置绑定回放；右侧 DeerFlow 流水线——record_gateway（Playwright+真模型）产出 fixture JSON（caller+input_hash+output），ReplayChatModel 按归一化哈希配对，期望是独立提交的 SSE golden；中缝标出两个关键分歧：system prompt 在 DSH 被 pin 成 sidecar（不变量要求），在 DeerFlow 被整体排除出匹配键（prompt 是高频编辑面）；期望在 DSH 是一份文件两用，在 DeerFlow 是独立 golden](./figures/two-shapes.svg)

## 共同的目标

两边都在回答同一个问题：**模型实际收到了什么，必须有一个可 diff 的固定形态。**

- DSH 侧的起点是事故（178 单测全绿、生产不能用）与设计目标「真运行的保真度 + 夹具的确定性」（21/01:9-29）。
- DeerFlow 侧这句措辞在 2.2.0 **已经不在了**：原出处 `examples/deerflow-extension-example/tests/test_model_surface.py` L5-7「If you change what the model sees (tool naming, result shape, message flow), this test fails — that is the point」所在的文件已随示例家族重构删除（上游里从不存在等价物，属 fork 自制内容，已删除）。现行等价表述以 `backend/docs/REPLAY_E2E.md` L7-9 的「mock 造 fake green」诊断与 `backend/tests/test_replay_golden.py` L70-72 的断言分工为准——目标不变，出处换了。

## 六个决定点的对照（sync #8 补第 7 行）

| 决定点 | DSH（快照层） | DeerFlow（record/replay 车道） | 为什么相反 |
|---|---|---|---|
| 夹具形态 | `session.jsonl`：事件溯源轨迹，含 `request/header` | JSON `turns[{caller, input_hash, output}]` | DSH 持久化层本来就是轨迹；DeerFlow 夹具是录制器产物，只记「调用→输出」 |
| 配对方式 | 位置绑定（first-call 序） | 归一化输入哈希 × caller 命名空间（顺序无关） | DSH 一个场景只允许一条在飞模型流；DeerFlow 多 caller 交错（lead / `middleware:title` / suggest / subagent），次序不值得依赖（`backend/tests/replay_provider.py` L22-35） |
| system prompt | pin 成 sidecar（可重建性不变量要求） | **整体排除出匹配键**（L201-207） | DSH 的不变量要求钉住一切 model-visible 面；DeerFlow 认定 prompt 是「最常编辑的实现细节」，hash 它 = 无关 PR 红屏 |
| 挥发噪声 | typed token（`{{session:1}}` 首现编号，保关系去噪声） | 正则归一化（UUID/TS/DATE/PATH 剥掉；`<system-reminder>` 整块剥；`hide_from_ui` 消息剔除，L144-176、L225） | DSH 要从夹具重建请求所以必须保关系；DeerFlow 只需要配对，抹掉最省 |
| 期望在哪 | 同一份日志（一份文件两用） | 独立提交的 SSE golden + miss 对账 | DeerFlow 的 golden 是「被测协议」的独立 oracle，坏脚本回放出来若与 golden 不符会红 |
| 静默失效的对手 | patch 不生效 / provider 抢流 / title 占脚本位（21/03:129-137） | Gateway 把 miss 吞成正常 assistant 错误消息，SSE 形状不变、golden 绿着变陈旧（L95-101） | 两边都发现「最危险的是不报错」，都把 fail loud 当设计属性：DSH 校对 `--dump-config`；DeerFlow 进程内 miss 列表 + `test_replay_golden.py` L85 `assert not misses` |
| **并发**（sync #8 补第 7 行） | **是固有限制**：并发子会话会不确定地抢脚本位（21/03:143，回放器自己声明的已知限制），所以 L4 场景按许可清单收窄——「涉及并发子代理委派的场景」列入不建判据（21/05:48） | **题设上不存在**：键是 caller + 归一化输入哈希而不是位置，`subagent:*` 各占自己的桶，谁先跑都拿回自己的输出（L22-32） | DSH 从轨迹**按位置推导**脚本，并发没有稳定的第 N 条；DeerFlow 从「调用→输出」表按内容查找，风险从「绑错脚本」转移到「同一 caller + 同一输入被并发重复调用时按 `deque` 顺序消费」——只有两路产出可交换时才无害 |

## system prompt 的两种命运（最值得琢磨的一行）

- **DSH：pin 是功能。** model-visible ⟺ logged（21/01:67-79）：动请求头而夹具没动 → 要么改动对模型不可见、要么不变量破了。sidecar diff 是报警器。
- **DeerFlow：排除也是功能。** L201-207 原文：「The lead-agent system prompt is a living, frequently-edited implementation detail … Hashing it would make every fixture go stale — and red-fail on unrelated PRs」；「The conversation flow (user input -> tool calls -> results -> answer) is the stable key」。
- **合起来看**：同一条「prompt 漂移要报警」的需求，DSH 放进回放匹配，DeerFlow **只能放到别处**——而 v2.2.0 里那个「别处」变薄了：原来的两脸断言（`ScriptedModel.requests` + assembly fingerprint）依据的 `docs/testing/01-extension-testing-strategy.md` L110-112 与 `deerflow.testing` **都是 fork 自制内容，上游从不存在，已随 2.2.0 同步清除**（`.md` 文件、`deerflow/testing/` 包目录均已不在树里）。
- **诚实账单（2.2.0 重算）**：分层降低了夹具维护成本，代价是全车道**不抓 prompt 漂移**——改了 system prompt 而没有任何就地 `ScriptedModel` / `FakeToolCallingModel` 断言覆盖时，回放照样绿，DSH 的夹具会红。2.2.0 之后连「该由谁报警」都没有现成基建：要 prompt 报警，得在**自己的测试文件里**写 `class ScriptedModel(BaseChatModel)`（样板：`backend/tests/test_goal_evaluator_accounting.py:29`）把请求录下来断言。这是把 pin 摘出去的代价，不是免费午餐。

## 噪声处理的同构与分歧

- 同构：都在「消噪声、保语义」。DSH 只 tokenize 地址级噪声、不脱敏任意文本（21/01:89-90）；DeerFlow 挥发正则只抹格式不抹语义。
- 分歧：DeerFlow 把整个 `<system-reminder>` 块剥掉（L140-144）——前端注入的日期/动态上下文跨天必变，剥掉才能让夹具跨天、跨「浏览器 vs 直接 POST」两条路径重放。DSH 遇到同类问题（运行上下文）选择保留事件、pin 内容。根源仍是**要不要从夹具重建请求**这一条。

## 为什么 DeerFlow 用不了位置绑定

`backend/tests/replay_provider.py` L22-35 拆解：真实运行中 lead agent 自己的 turn、TitleMiddleware、memory、subagent 都会发起模型调用，「their count/order is not something we want a replay to depend on」。于是：

- 按 caller + 归一化输入哈希配对，不同 caller 相同文本不抢桶（caller 命名空间 L29-32）；
- 不可复现的后台调用直接在配置里禁（memory/summarization，`_replay_fixture.py` L59）——对应 DSH 的 title LLM 占脚本位（21/03:137）：**两边都把「回放消费方不止 lead agent」当成一等现实**。

## 这一篇要你记住的

- 形状相反的根源是三个宿主事实：持久化形态（轨迹 vs 调用记录）、运行拓扑（单流 vs 多 caller）、消费方式（要重建请求 vs 只配对）。
- 「prompt 进不进匹配键」是两边最大的哲学分歧，都是有意为之、都写了理由。
- DSH 用一条不变量解决的问题，DeerFlow 用分层解决；分层的代价是全车道不抓 prompt 漂移——而 2.2.0 把「分层里负责报警的那一层」（`deerflow.testing` 的 `ScriptedModel.requests`）清掉了，于是那部分补全要靠每个测试文件自建就地夹具。
