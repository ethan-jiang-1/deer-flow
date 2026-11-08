---
title: "前端与 TUI 测试"
description: "rstest node/dom 成本分流、Playwright 四车道与 mock 层工程化、本地 SSE 服务器构造流式中间态、几何断言、Textual pilot + 纯 reducer 的无头 TUI。"
topics: [testing, frontend, tui, playwright]
---

# 前端与 TUI 测试

DeerFlow 有两个界面层，痛点各不相同：

- **Web 前端**（Next.js + React）：核心痛点是 **SSE 流式渲染的时序**与**前后端契约漂移**——mock 掉后端的手写 JSON/SSE 会让后端 schema 变更"绿色通过"（fake green，`backend/docs/REPLAY_E2E.md` 开篇诊断，详见 `03-contract-e2e.md`）；
- **TUI**（Textual 终端工作台，跑在内嵌 `DeerFlowClient` 上）：渲染、按键、滚动、CJK 光标。

两层加起来 254 个前端测试文件（unit 202 + e2e 45 + auth 2 + real-backend 4 + record 1），另有 16 个 TUI 测试文件。

## 一、rstest node/dom 分流：按成本选环境

分流不靠自觉，靠**文件名后缀路由**（`frontend/rstest.config.ts:22`）：

- `*.test.ts(x)` → 纯 node project（145 个文件，几乎全部纯逻辑：流模式白名单、message-merge、stream-throttle、thread-branch-tree…）；
- `*.dom.test.ts(x)` → happy-dom project（57 个文件，仅限"行为存在于真实 React 之下"的测试）。

配置注释把经济学写明："A DOM environment costs roughly 3x the runtime of this suite"（DOM 环境成本约 3 倍）。`frontend/AGENTS.md:43` 补充判据（原文）：

> "A hook whose behavior only exists under real React (effect ordering, cleanup on unmount, re-render on store change) belongs in a `.dom.test.*` file rather than a node test that mocks `react` itself."

即：只有真 React 行为（effect 顺序、卸载清理、store 变化重渲染）才配付 3 倍成本。**实践中**，仅需要渲染输出的测试直接用 `renderToStaticMarkup` 在 node 环境解决（如 `frontend/tests/unit/core/reasoning-trigger.test.ts`）——不引 DOM、不断言交互。

单测无 MSW、无 vitest，全用 rstest 内建：`rs.mock()`（70 个文件）、`rs.stubGlobal("fetch", ...)`（18 个）、`rs.useFakeTimers()`（7 个，如 50ms 提交节流测试）。

SSE 单测的代表模式——**流协议在单测层被降维成"函数调用序列"**：`frontend/tests/unit/core/threads/incremental-stream-state.dom.test.tsx` 用 `rs.mock("@langchain/langgraph-sdk/react")` 替换 `useStream`（`:47`）捕获 options，再手动调 `options.onUpdateEvent(...)` 注入流事件（`:102`、`:113`），断言增量状态合并。真实 SSE 在这里只是"会按序到达的事件数组"。

## 二、Playwright 四车道：mock 宽度 × 真实性梯度的显式分层

四套 config 对应四条车道，真实性递增、数量递减：

```
e2e (45 spec / 214 test)          mock 后端，快而宽 —— 自认"不证明后端契约"
  └─ e2e-auth (2 / 5)             认证开启路径（前端端口 3001 + 故意不可达的 gateway 127.0.0.1:65535）
      └─ e2e-real-backend (4 / 4) 真前端 × 真 replay gateway，跨栈契约
          └─ e2e-record (1 / 1)   真前端 × 真模型，录制 fixture，"never run in CI"
```

### 1. mock 车道：有状态 mock 层的工程化

`frontend/tests/e2e/utils/mock-api.ts` 是一个 2145 行的共享资产：`mockLangGraphAPI`（`:303`）注册 **59 条** `page.route()`，**闭包内可变状态**模拟后端（threads/projects/documents/trash 真正随 POST/PATCH/DELETE 变化），并刻意镜像后端契约细节——pin 排序 pinned-first、thread 重复 POST 幂等、双删 404 视为幂等成功。SSE 用 `handleRunStream`（`:2098`）拼一次性 `text/event-stream` body（`metadata → values → end`）。

### 2. 本地 SSE 服务器：制造"挂住的流"

需要测**流式中间态**时，一次性 body 不够——3 个 spec（`streaming-reasoning-order`、`artifact-batched-stream`、`subtask-card`）用 `node:http` 起本地服务器：

- `startHeldOpenStreamServer()`（`frontend/tests/e2e/streaming-reasoning-order.spec.ts:81`）写出 `metadata → values → messages(AIMessageChunk 同时带 reasoning_content 与正文)` 后**不结束响应**，把回合钉在流式中间态；`page.route(...)` 把真请求 `route.continue({ url })` 重定向过去；
- `frontend/tests/e2e/artifact-batched-stream.spec.ts` 专门制造**分批 tool_call_chunks 时序**：第一个 chunk 带半截 JSON，300ms 后补第二段——正对 Gateway"有界批量刷新"契约。

断言是**几何的**：`expectRenderedAbove`（`streaming-reasoning-order.spec.ts:113`）取两个 locator 的 `boundingBox()`，断言"Thinking"面板的 y 小于答案文本的 y——渲染顺序契约不依赖任何快照。

### 3. real-backend 车道：fake-green 的解药

`frontend/playwright.real-backend.config.ts` 启**两个 webServer**：replay gateway（`backend/scripts/run_replay_gateway.py`，`DEERFLOW_ENABLE_TEST_SEED=1`）+ 真 Next.js。四个 spec 各守一类跨栈契约：

- `auth-disabled-contract.spec.ts`：无 cookie GET `/api/v1/auth/me` 必须返回完整权限数组——与后端 `backend/tests/test_auth_me_permissions.py` **双端钉同一张权限表**（`frontend/AGENTS.md:45` 明文要求 "update both"）；
- `multi-run-order.spec.ts`（#3352 回归，见 `03-contract-e2e.md`）：经 test-only seeder 种两条**无 checkpoint** 的 run，断言 ALPHA 消息的 boundingBox y 小于 OMEGA；
- `project-trash.spec.ts`：zod 解析 Gateway 响应 shape + `expect.poll` 轮询真实删除；
- `real-backend-render.spec.ts`：跨栈渲染 + 全套唯一的视觉回归点（见下）。

### 4. 断言风格：最终状态，不是像素

- 全套无组件快照（`toMatchSnapshot` 零匹配）；断言以 `getByRole`/`getByText`/`expect.poll`/请求序列为主；
- 唯一视觉回归 `frontend/tests/e2e-real-backend/real-backend-render.spec.ts:127` 的 `toHaveScreenshot` **仅本地跑**——注释原文（`:122` 起）："Visual regression is OS-sensitive (a macOS baseline won't match CI's Linux render), so it's a local dev gate only; in CI we capture the render as an artifact for human review instead of hard-asserting a cross-OS baseline. The DOM assertions above are the CI gate."。CI 下走 `process.env.CI` 分支改存 screenshot artifact 供人工审查，**DOM 断言才是 CI 门禁**。

## 三、TUI 测试：把状态机做成纯函数

DeerFlow 的 TUI 是 Textual 应用（`backend/packages/harness/deerflow/tui/`，15 个 `.py`）。它的测试策略建立在一个架构决定上：**除 `app.py` 与 `widgets/composer.py` 外，全部模块不依赖 Textual**。

| 层 | 文件 | 可测性 |
|----|------|--------|
| 入口决策 | `tui/cli.py` 的 `plan_launch(argv, stdin_isatty, stdout_isatty, env)`（`:104`） | **纯函数**，无 I/O、不构造 client——TTY 判定/启动模式/退出码全部直接单测 |
| 状态 | `tui/view_state.py`：frozen dataclass + 纯 `reduce(state, action)` | **纯函数**——模块 docstring 开篇即声明 "no Textual / rendering dependency"；测试侧称它 "The reducer is the testable heart of the TUI"（`backend/tests/test_tui_view_state.py:3`） |
| 运行时 | `tui/runtime.py` 的 `translate(StreamEvent) → [Action]`（`:41`） | 纯映射，直接单测 |
| 渲染 | `render.py`、`command_registry.py`、`input_history.py`、`message_format.py` | 纯辅助，直接单测 |
| App | `app.py` + `widgets/composer.py` | 唯一需要真 Textual 的层 |

设计文档的 Testing Decisions（`docs/superpowers/specs/2026-06-13-deerflow-tui.md`）把这条策略成文：

> "Good TUI tests should validate behavior at the highest practical seam"（`:206`）

> "Snapshot-like tests for layout state, not brittle terminal screenshots, for core panels and overlays."（`:210`）

> "A skipped-by-default live TUI smoke test can run only when a valid local config and credentials are present."（`:219`）

### 16 个测试文件的分档

- **pilot 档**（5 个，Textual 原生 `run_test()` 飞行器）：`test_tui_app` / `test_tui_composer` / `test_tui_overlays` / `test_tui_palette` / `test_tui_transparent`——驱动按键/滚动/模态，不需要任何 ANSI 层。如 `_fill_scrollable_transcript`（`backend/tests/test_tui_app.py:55`）构造满屏 transcript 测"用户上翻时流式更新不拉回底部"的滚动跟随契约；
- **纯函数档**（11 个，无 Textual）：`test_tui_cli`（`plan_launch` 启动规划，含 `DEER_FLOW_TUI` 环境变量强制开启路径）、`test_tui_cli_main`、`test_tui_view_state`（reducer：按 id 合并 delta、tool_call 去重、空 id 丢弃…）、`test_tui_runtime`、`test_tui_command_registry`、`test_tui_input_history`、`test_tui_message_format`、`test_tui_palette_render`、`test_tui_persistence`、`test_tui_render`、`test_tui_session`。

CJK/光标这类终端协议细节被压缩到唯一一处：`widgets/composer.py:21` 覆写 `_cursor_offset`，修正 Textual `Input._cursor_offset` 的无条件 `+1` 偏移——协议补丁集中在 App 层，测试面不扩散。

## 四、架构启示

1. **mock 车道快而宽，但必须自认边界**：DeerFlow 给 mock e2e 的定位是"UI 交互流程的宽度"，其盲区（后端契约漂移）由 replay 跨栈层**显式接手**——每层声明自己"不证明什么"，互不越界；
2. **流式时序是可构造的**：挂住连接的本地 SSE 服务器 + 分批 chunk + 几何断言，把"渲染顺序"从不可测的视觉问题变成可断言的坐标问题；
3. **UI 状态机纯函数化是无头测试的最优解**：能不碰渲染协议就不碰；必须碰时用框架原生 pilot，把协议补丁集中在 App 层；
4. **视觉回归降级为本地门禁**：OS 敏感的东西不进 CI 当阻塞门，CI 存 artifact 供人审——"门禁只放确定性的东西进来"（与 blocking-io 门禁的哲学一致，见 `01-doctrine.md` §6）。
