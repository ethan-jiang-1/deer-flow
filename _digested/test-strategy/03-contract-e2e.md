---
title: "契约与跨栈 E2E"
description: "契约如何在 Python/TS 两侧被同一份 JSON 钉住；mock E2E 的 fake-green 问题如何被两层 record/replay 跨栈层解决；#3352 案例——两侧单测全绿、真栈损坏的病只有真前端+真后端能抓。"
topics: [testing, contracts, e2e, replay]
---

# 契约与跨栈 E2E

前后端两侧各有完整单测，契约仍然会碎——因为**每一侧的单测都在各自 mock 对方的形状**。DeerFlow 对这个裂缝有系统的认知，`backend/docs/REPLAY_E2E.md` 的开篇就是诊断书：

> "The mock-based frontend e2e hand-writes the backend's JSON/SSE, so a backend schema or SSE change passes green (**'fake green'**). These layers replay a recorded **real** run against the **real** backend … so contract drift turns the build red instead."

本篇梳理这条防线上的四道机制，由窄到宽。

## 1. 跨语言契约 JSON：一份文档，两端各钉一次

`contracts/` 目录放三种跨栈契约，每种都有**后端 pytest 与前端 rstest 各一个测试读取同一份 JSON**：

| 契约 | 后端钉住 | 前端钉住 |
|------|---------|---------|
| `contracts/slash_skill_contract.json`（保留 /skill 名 + 命名语法） | `backend/tests/test_slash_skill_contract.py` | `frontend/tests/unit/core/skills/slash-contract.test.ts` |
| `contracts/subagent_status_contract.json`（status/stop_reason 词汇表、metadata 键与上限） | `backend/tests/test_subagent_status_contract.py` | `frontend/tests/unit/core/tasks/subtask-result.test.ts` |
| `contracts/run_event_stream_contract.json`（run 事件流定义） | `backend/tests/test_run_event_stream_contract.py` | 事件序列由 replay golden 层覆盖 |

前端测试读同一文件并把正则经 `new RegExp(...)` 规范化，**防止 Python 与 JS 的转义差异自己变成漂移源**。同族做法还有权限清单两处钉：`frontend/tests/e2e-real-backend/auth-disabled-contract.spec.ts` 与 `backend/tests/test_auth_me_permissions.py` 共同钉完整路由权限表（`frontend/AGENTS.md` 明文要求"update both when adding registered permissions"）。

## 2. Gateway 一致性：用对方的 Pydantic 模型解析自己的 dict

`backend/tests/test_client.py:3540` 的 `TestGatewayConformance` 验证 SDK 路径与 Gateway 路径的输出格式一致。手法经济：不同时跑两条路径，而是**把 `DeerFlowClient` 返回的 dict 交给 Gateway 对应的 Pydantic response model 解析**——字段缺失或类型不符即 `ValidationError`，CI 抓 drift。覆盖消息格式、tool call 参数、流式 chunk 序列、token usage 传递。

## 3. 真 SDK payload 钉住：mock 抓不到的漂移类别

比"格式不一致"更隐蔽的是**对上游 SDK 行为的错误假设**。`backend/app/gateway/AGENTS.md:143` 记录了一个真实案例：`langgraph_sdk` 只丢弃 `None`，所以 `stream_resumable=False` 会出现在每个请求里且含义是"不可恢复"——按直觉拒绝它的 422 会打断所有 IM channel run（#4466）。教训成文为：

> "`tests/test_run_request_validation.py::test_gateway_accepts_langgraph_sdk_default_payload` pins the real SDK payload against this boundary; **channel tests mock the SDK client and cannot catch this class of drift**."

即：凡"我们假设了第三方库的行为"的边界，都要用**该库的真实默认 payload**做钉住测试，mock 掉它就等于把这个假设变成不可检验的。

## 4. 两层 record/replay 跨栈层：真前端 × 真后端

`02-deterministic-llm.md` 已拆解 replay 机制本身；这里看它作为**跨栈契约层**的用法与不可替代性。

- **Layer 1**（后端 SSE golden）：进程内真 Gateway + replay 模型，断言事件形状序列 = 提交的 golden。
- **Layer 2**（`frontend/tests/e2e-real-backend/`）：Playwright 同时拉起真 Next.js 与真 replay gateway，DOM 断言是门（CI 的 `replay-e2e.yml` 在契约任一侧变更时触发：`frontend/**`、`backend/app/gateway/**`、`backend/packages/harness/**`）。

### #3352 案例：为什么必须有 Layer 2

`backend/docs/REPLAY_E2E.md` 完整复盘了这个 bug：上下文压缩后刷新 thread，历史渲染乱序。根因是**前后端之间的语义错位**——后端 `RunManager.list_by_thread` 按最新在前返回（PR #2932），而前端（`core/threads/hooks.ts`）遍历后**逐页前插**，一旦 checkpoint 不再持有旧消息，时间序就被反转。关键在于：**后端的排序测试全程是绿的，前端的回归单测又把"后端最新在前"硬编码在 mock 里——两侧单测都绿，真栈是坏的**。修复（#3354）之后，`multi-run-order.spec.ts` 成为常驻跨栈守卫：用 test-only 种子 router（`backend/tests/seed_runs_router.py`，仅在 `DEERFLOW_ENABLE_TEST_SEED=1` 时挂载）种出"≥2 个 run 且**故意无 checkpoint**"的历史——逼前端走 per-run 重载路径，让这类错位变成可复现的确定性场景。

## Mock E2E 的位置：快而宽，自认边界

跨栈层解决契约漂移，但不取代 mock E2E（`frontend/tests/e2e/`，45 个 spec）。后者用一个 2000 余行的共享工具 `frontend/tests/e2e/utils/mock-api.ts` 注册约 59 个 `page.route()` 处理器，几乎覆盖整个 Gateway 面；SSE 由 `handleRunStream` 手工拼帧（`event:`/`data:` 行 + `text/event-stream`），需要"流挂住不放"来测中间态时（如 reasoning 与 answer 的渲染顺序），`frontend/tests/e2e/streaming-reasoning-order.spec.ts` 甚至起一个真 `node:http` 服务器写帧不收尾。**解释**：mock E2E 的价值是 UI 交互流程的宽度与速度；它的盲区（后端契约漂移）由 replay 层显式接手——两层各自声明边界，互不越界。四条 Playwright 车道的全景、mock 层工程化细节与断言风格，见 `06-frontend-and-tui.md`。

## 替身哲学的边界：什么时候拒绝 fake

`01-doctrine.md` 已引用 ownership store 的例子（"no fake-redis tier because a fake would not execute the Lua exclusions"）。同一原则在跨栈语境的对应物：Layer 2 不去 mock 浏览器 nor mock 后端，而是让**两者都真实**、只把中间的模型换成确定性回放。`sandbox/AGENTS.md` 拒绝假 Redis、`REPLAY_E2E.md` 拒绝手写 JSON/SSE、gateway 层拒绝 mock SDK——三个"拒绝"指向同一条选型准则：**替身可以替换"贵的与不确定的"（模型、时间、外部凭证），不可以替换"被测的语义本身"（原子性、协议、第三方行为）**。
