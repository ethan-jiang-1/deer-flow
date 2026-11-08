---
title: "确定性 LLM 替身谱系"
description: "DeerFlow 如何在不调真实模型的前提下跑完整 agent 栈：FakeToolCallingModel 剧本模型、ReplayChatModel 内容寻址回放、Monocle trace 断言、手动录制层——以及'响亮失败'如何穿透中间件的吞错。"
topics: [testing, deterministic, replay, agent]
---

# 确定性 LLM 替身谱系

agent 系统测试的中心矛盾：**被测系统的核心组件（LLM）是非确定的、慢的、要花钱的**。DeerFlow 的答案不是"mock 掉 agent"，而是在 **LLM 边界上替换模型**、让其余一切保持生产代码。这条边界上长出了一个四级替身谱系，按"离真实行为的距离"排列：

| 级 | 替身 | 机制 | 距真实行为 |
|----|------|------|-----------|
| 1 | `FakeToolCallingModel` | 预编程剧本（两轮：tool_call → 终文） | 完全虚构，但图是真的 |
| 2 | `ReplayChatModel` | 录制回放：按 caller+输入哈希命中真实录制的模型输出 | 真实行为的**记录** |
| 3 | Monocle trace 断言 | 对真实运行的结构化 trace 做行为断言 | 真实行为本身（live 门后） |
| 4 | 录制层（Playwright record） | 驱动真前端+真模型**生产** fixture | 真实，仅手动，永不进 CI |

## 级 1：FakeToolCallingModel——剧本模型

源码 `backend/tests/_agent_e2e_helpers.py:20`。构造极简：继承 LangChain 的 `FakeMessagesListChatModel`，把 `bind_tools` 变成 no-op 返回 `self`（因为输出由 `responses=` 预编程，不需要 schema 处理）。`build_single_tool_call_model` 生成标准两轮剧本：第一轮发一个指定名字与参数的 tool_call，第二轮回一段终文结束循环。

价值不在"假"，而在**真**：`langchain.agents.create_agent` 的完整图——中间件链、ToolNode、真实工具执行——全部照跑，只是模型输出被钉死。要验证"agent 收到 X 时会用参数 Y 调工具 Z"这类契约行为，这是毫秒级的手段。

这个底座之上长出了一族测试内局部 fake（全树 23 个文件引用 `FakeMessagesListChatModel` / `GenericFakeChatModel`），替身边界始终不变：`RecordingModel`（`backend/tests/test_subagent_executor.py:731`，记录每轮 `bind_tools` 收到的工具名清单）测"工具可见性随轮次变化"的中间件；捕获中间件对消息改写的 capturing fake、多轮剧本驱动子代理预算语义的 scripted fake 等。**与 pi 无关的共性**：它们都是静态队列——"读上一轮真实上下文决定下一步"的需求交给级 2 的录制回放（真实上下文已经录在 fixture 里）。

## 级 2：ReplayChatModel——内容寻址的录制回放

源码 `backend/tests/replay_provider.py`（415 行），这是整个体系里最精密的一件。核心思想：**录一次真实运行（需要 key，手动），之后永久离线回放（零 key，CI 可跑）**。但它与常见"按轮次索引回放"有本质区别。

### 为什么按输入哈希匹配，而不是按轮次索引

一次真实运行的模型调用来自多个 caller 交错：lead agent 自己的轮次、`TitleMiddleware` 自动起标题、suggest agent、subagent。它们的数量与顺序不可依赖。于是 fixture 按 **caller + 归一化输入消息的 SHA-256** 索引：每个调用拿回"当初这个输入录到的输出"，与顺序无关。caller 身份从 LangGraph tags（`lead_agent`、`middleware:*`、`subagent:*`）或 `run_name` 解析，并有别名表（`title_agent` → `middleware:title`）兜底执行路径丢失 tag 的情况。

### 归一化：让录制跨机器、跨日期、跨 PR 存活

`_normalize_text`（`backend/tests/replay_provider.py:167`）在哈希前剥掉所有易变内容：`<system-reminder>` 块、UUID、ISO 时间戳、日期、临时目录绝对路径、输入消毒中间件的边界标记、剥离后残留的空 role 行。

**最关键的一个决定**（`_canonical_messages`，`backend/tests/replay_provider.py:193`）：**system prompt 整个剔除出匹配键**。理由写在 docstring 里——lead agent 的 system prompt 是"频繁编辑的实现细节，不是被测契约"；把哈希进去，任何人改一段提示词，全部 fixture 报废、无关 PR 集体变红。会话流（用户输入 → tool calls → 结果 → 回答）才是识别一次录制轮次的稳定契约。同样，`hide_from_ui` 的框架注入消息（动态日期、记忆注入）一律不参与键。

### 响亮失败，并穿透中间件的吞错

miss 不会静默返回：`_match` 抛出带诊断的 `KeyError`（已知哈希清单 + 归一化输入前 800 字符预览，`backend/tests/replay_provider.py:344`）。但这里有个精巧的陷阱：**Gateway 的 `LLMErrorHandlingMiddleware` 会把模型异常吞成正常的 assistant 错误消息**——SSE 事件形状不变，Layer 1 的 shape-golden 依然全绿。所以测试侧维护一个进程级 `_replay_misses` 清单，`test_replay_golden.py` 在断言事件序列之外**专门断言这个清单为空**（`backend/tests/test_replay_golden.py:84`）——这是唯一可靠的"fixture 过期"信号。整个设计的态度写在 docstring 里："never pass silently"。

### hermetic 配置：录制与回放的同一性

`backend/tests/_replay_fixture.py` 集中构造 record/replay **完全相同**的网关配置（`build_config_yaml`，`_replay_fixture.py:49`）：本地沙箱、固定三件工具（ls/read_file/write_file）、指向空 skills 目录、**memory 与 summarization 关闭**——因为它们的后台去抖调用时序不可复现；`prepare_hermetic_extras`（`:100`）写一份空的 `extensions_config.json`（零 MCP）。system prompt 里一切环境依赖内容被清零，fixture 才能"跨机器、跨日期、跨提示词编辑"回放。录制与回放之间**只有 `models[].use` 一块不同**——同一性由构造保证，不靠约定。

### 两层验证面

- **Layer 1（后端 golden）**：`test_replay_golden.py` 进程内起真 Gateway（`create_app()` + 真注册/CSRF/建线程/发流），`sse_event_shapes`（`_replay_fixture.py:114`）把 SSE 流折叠为"事件名 + 排序后的顶层键"，与提交的 golden JSON 比对。**断言形状不断言值**——形状是前端消费的契约，值是易变的。golden 重生成用 `DEERFLOW_WRITE_GOLDEN=1`。
- **Layer 2（跨栈渲染）**：`frontend/tests/e2e-real-backend/`，Playwright 起真 Next.js + 真 replay gateway（`playwright.real-backend.config.ts` 启两个 webServer），DOM 断言为门。跨栈的必要性见 `03-contract-e2e.md`。

配套还有 `backend/tests/seed_runs_router.py`：一个**只在 replay gateway 挂载的 test-only FastAPI router**（`DEERFLOW_ENABLE_TEST_SEED=1` 时生效），通过 Gateway 自己的 run/event store 种出"无 checkpoint 的多 run 历史"——不需要模型、录制或 key，就能确定性地复现 #3352 那类前端重载排序 bug 的前置条件。

## 级 3：Monocle——对 trace 的行为断言

`backend/tests/monocle/` 换了思路：不做模型替身，而是**对运行的结构化 trace（agent 调用、每次 tool call、token 消耗、耗时）做断言**，断言词汇表：`called_agent` / `contains_input` / `called_tool` / `does_not_call_tool` / `under_token_limit` / `under_duration`。两层用法（README 原话）：离线示例加载提交的真实 trace（`traces/web_research_ev_battery.json`）"guards the trace format and the asserter wiring, not DeerFlow's behaviour"——它钉住的是断言词汇表与 trace 格式本身；两个 live 测试驱真实 agent 并对真实 trace 断言"路由、工具选择、token 成本有没有漂移"，由 `MONOCLE_LIVE_TESTS=1` 显式开门（`run_agent` fixture 未设 flag 即 skip，`.env` 加载只发生在 live fixture 内——收集期永不读 secrets）。因依赖 ML eval 栈（torch/transformers），整包 `importorskip` 干净跳过，普通后端环境零负担。

## 级 4：录制层——fixture 的生产端

`frontend/tests/e2e-record/`（`frontend/playwright.record.config.ts`）驱**真前端 + 真模型**网关，捕获浏览器实发的模型调用（保证输入与浏览器路径逐字节一致），经 `backend/scripts/build_fixture_from_jsonl.py` 缝合成 fixture（存 `backend/tests/fixtures/replay/`）。注释明言 "never run in CI"——录制是 dev 机器上的手动工序，产物 fixture 里不含 API key。机制三件套：

1. `backend/scripts/record_gateway.py` 给 `create_chat_model` 打补丁装 callback handler：`on_chat_model_start`（`:39`）记录输入 + caller，`on_llm_end`（`:54`）把 `{caller, conversation_hash, input_hash, output}` 追加写入 JSONL——因为由真前端驱动，date system-reminder、suggestions/title 调用这些浏览器实际产物都被捕获，fixture 才能对浏览器路径干净回放；
2. `frontend/tests/e2e-record/record-write-read-file.spec.ts` 驱动场景后 `waitForCaptureStable`（`:30`，12 秒稳定窗口、160 秒上限，超时硬失败）——"a recording must stabilize, or it is not trustworthy"；
3. `backend/scripts/build_fixture_from_jsonl.py` 把 JSONL + meta 缝合成 fixture JSON，产物不含 API key。

## 谱系选型原则（解释）

四级替身对应四类问题：**验证图的行为契约**用级 1（毫秒、零 fixture）；**验证前后端协议形状**用级 2（真实记录、确定性回放）；**验证行为质量本身**（选了什么工具、花了多少 token）用级 3 的 live 面；**生产新 fixture**用级 4。共同点只有一个：**替换点永远贴着 LLM 边界，离 LLM 越远的生产代码越保持原样**——这保证了"替身绿"与"真栈绿"之间的差距被压到最小，而剩下的差距由 `03-contract-e2e.md` 的跨栈层兜底。
