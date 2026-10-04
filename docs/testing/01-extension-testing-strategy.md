# 01 — 扩展测试策略：五级证据阶梯（DeerFlow 版）

> 本篇面向**扩展作者**：你的扩展是一个 Python 包，经一个 PEP 621 entry point 暴露
> `install(registry, config)`，由 `config.yaml` 顶层 `plugins:` 在启动时装载。本篇讲
> "你写一个新扩展，测试面怎么摆"。组合按承诺怎么挑看 [02](02-extension-testing-playbook.md)，
> PR 逐条对表看 [03](03-extension-pr-checklist.md)。
>
> 本系列移植自 DSH 插件测试策略，台阶结构保持同构；凡 DeerFlow 契约不同处，本篇以
> **DeerFlow 为准**并标注差异——最关键的一处见台阶四的"观察性 wrap 契约"。

## 先对齐六个名词（本篇自足）

| 名词 | 一句话 |
|---|---|
| **扩展** | 一个 Python 包；`deerflow.extensions` group 里**恰一个** entry point，指向 `@extension(api=..., name=...)` 标注的 `install(registry, config)` |
| **`plugins:`** | `config.yaml` 顶层的启动列表，operator-controlled 代码执行边界；**startup-only**，任何改动都要重启 Gateway（没有热插拔） |
| **七贡献形态** | middleware contributors / task-lifecycle / system-model observers / agent-assembly observers / context-compaction observers / Gateway-lifetime services / eager routers |
| **`LoadedExtensions`** | 装载产物；每条贡献带 `(source, contribution)` 归因，是 fail-open 语义的载体 |
| **`IsolatedMiddleware`** | 扩展中间件的隔离包装：失败发诊断 fail-open、不重复下游副作用；**wrap 钩子是观察性的**（见台阶四） |
| **脚本化模型** | `deerflow.testing.ScriptedModel`——扩展测试里唯一常见 mock；按脚本吐 `AIMessage`，并**记录收到的每个请求与每次 `bind_tools`** |

## 现象是什么：同一套要求，五个台阶

条款是通用的，落到扩展身上有固定形态：**入口点守卫 → 行为 spec → 装载遏制 → REAL
composition → 组装转录**，五个台阶逐级抬高入口真实性。台阶 1~3 都在离线单元车道；
台阶 4 分进程内级（扩展作者必做）与 host 级（发布到 Gateway 的扩展建议补）；台阶 5 是
录制回放车道。跳过任何一级，都有对应的、在 DeerFlow 里已经发生过的事故形态（见各台阶
"为什么"）。

## 台阶一：入口点契约守卫（spec 级，成本最低）

**最小要求（两层各一测）**：

1. 打包层——分发物在 `deerflow.extensions` group 恰暴露一个 entry point，`@extension`
   标注的 api marker 与 name 在位；
2. 装载层——**真 loader 读真 entry point**：零诊断，且 `LoadedExtensions` 里七类贡献
   与包承诺一致（`has_middleware_contributors` / `has_task_lifecycle` / … / `services`
   / `routers`）。

样板：[examples/deerflow-extension-example/tests/test_entry_point.py](../../examples/deerflow-extension-example/tests/test_entry_point.py)——两层各一个测试。

**为什么这么严**：DeerFlow 对可选扩展是 **fail-open** 的——装载失败只留一条归因诊断，
Gateway 照常启动。这意味着"扩展根本没装上"是**默认失败模式**：没有这个守卫，贡献缺席
不会从任何绿灯里看出来。另有一个 loader 现状要知道：**api marker 缺失被容忍**（只有
"存在但不兼容/不合法"才拒绝）——marker 契约实际由 `@extension` 装饰器 + 兼容性拒绝共同
执行，所以装载层守卫必须跑真 loader，而不是自己 re-implement 检查。

## 台阶二：行为 spec（真依赖，只 stand-in 最外层包装）

**政策投影**："keep everything downstream real"。DeerFlow 的"最外层包装"就是模型：
真 loader → 真 `IsolatedMiddleware` → 真 `create_agent` 图，唯一 stand-in =
`ScriptedModel`。

- **断言从真入口进**：`agent.ainvoke` 的返回 state（`messages`、`ToolMessage` 结果）、
  `ScriptedModel.requests`（模型真正收到了什么）、扩展自己的 store 副作用（host 级
  `ExtensionData` 由 lifecycle 贡献者注入，见 [02](02-extension-testing-playbook.md)）。
- **不要断言 agent 自报的东西**。日志措辞、模型说的"我调用了 X"都不算数；断言 state、
  持久化行、模型请求记录这些外部事实。
- 类级单元（只测你自己的贡献类，stand-in 掉 registry/宿主）允许，但它不算组装证据——
  两者分工见 [02](02-extension-testing-playbook.md)。

样板：[test_plugin.py](../../examples/deerflow-extension-example/tests/test_plugin.py)
（类级）；host 侧 [backend/tests/test_extension_injection.py](../../backend/tests/test_extension_injection.py)
（放置/隔离语义）。

## 台阶三：装载遏制与生命周期（startup-only 的变形）

DSH 的台阶三是 HMR-safety（dispose fiber → 贡献消失）。DeerFlow **没有热插拔**——
`plugins:` 改动必须重启——所以这一级变形为四条**装载遏制**不变量，加一组运行时侧序：

| 不变量 | 含义 | 样板 |
|---|---|---|
| skip | `enabled: false` 不 import、不贡献、零诊断 | [test_lifecycle.py](../../examples/deerflow-extension-example/tests/test_lifecycle.py) |
| fail-open | 可选扩展装载失败 → 归因诊断 + 其余照常 | 同上（`MISSING` 用例） |
| fail-closed | `required: true` 装载失败 → 启动中止（operator 显式 opt-in） | 同上 |
| 爆炸隔离 | 贡献者在 install 时或组装时爆炸 → 只回滚/隔离它自己，其余贡献照常落位 | 同上（`raising_install` / `exploding_contributor`） |

运行时侧（host 级样板的职责）：服务停止序（逆序、每服务有界超时、失败不饿死后继）与
`IsolatedMiddleware` 的 fail-open 归因——host 侧样板
[backend/tests/test_gateway_extension_service_lifecycle.py](../../backend/tests/test_gateway_extension_service_lifecycle.py)、
[backend/tests/test_extension_isolation.py](../../backend/tests/test_extension_isolation.py)。

## 台阶四：REAL composition（两级，分工不同；DeerFlow 最重要的差异在这里）

政策原文同 DSH："hand-built registry 不算组装证据"。两级：

1. **进程内级（扩展作者必做）**：真 loader 读真 `ExtensionSpec`（即 `plugins:` 记录的
   形态）→ `compose_stack()`（真组装点）→ `build_test_agent()`（真 agent 图）→ 脚本化
   模型驱动。断言**两脸**——同一个 config flag 必须同时改变：
   - **model-visible 脸**：模型收到的工具 schema（`ScriptedModel.bound_tools`）与工具
     结果（消息转录里的 `ToolMessage`）；
   - **descriptor 脸**：`release_policy_parameters()` → `describe_middleware().policy_parameters`
     （进 assembly fingerprint），并带 `extension` 归因。

   样板：[test_composition.py](../../examples/deerflow-extension-example/tests/test_composition.py)。

   ⚠️ **观察性 wrap 契约（DSH 作者最容易踩的坑）**：`IsolatedMiddleware` 的 wrap 钩子
   把**原始 request 钉死**传给下游 handler——"a contributed wrapper may inspect the
   request but cannot substitute a new one after the host's policy/authorization
   layers have run"。所以贡献的中间件**改不了模型请求**（DSH 里"插件注入 system prompt"
   的套路在这里不成立）；它拥有的 model-visible 面是 **middleware-owned tools**（schema
   与结果）与返回值变换。想改 prompt，走宿主自有中间件或未来的宿主扩展点，不要指望
   wrap 钩子。可配置性的证明载体因此从"注入的 prompt"换成"配置出的工具"。
2. **host 级（发布到 Gateway 的扩展建议补）**：真 `create_app()` 装载真 `plugins:`——
   contributed routers 挂在所有 host 路由之后（host 永远赢）、服务启动序、路由 auth 投影。
   样板：[backend/tests/test_extension_app_loading.py](../../backend/tests/test_extension_app_loading.py)、
   [backend/tests/test_extension_stack_wiring.py](../../backend/tests/test_extension_stack_wiring.py)、
   [backend/tests/test_extension_route_principal.py](../../backend/tests/test_extension_route_principal.py)。

**为什么两脸**：库的配置测试只验行为分支；扩展的配置还会流到模型可见面与装配身份
（fingerprint）——只测一脸，另一脸的漂移无人知晓。`DEFAULT_*` 常量或单测 hook 不构成
可配置性证据。

## 台阶五：组装转录（model-visible 改动必须同 PR）

DeerFlow 的全车道**已经存在**：[backend/scripts/record_gateway.py](../../backend/scripts/record_gateway.py)
录制真实场景为 fixture（`backend/tests/fixtures/replay/`），
[backend/tests/replay_provider.py](../../backend/tests/replay_provider.py) 按
**hash-by-input** 回放（无 key；按 caller+输入归一化哈希配对，顺序无关，易变字段先归一化）。
扩展改动 model/protocol-visible 面时，同 PR 加或更新录制场景。

扩展仓库自己的 **keyless 切片**：用 `ScriptedModel.requests` 把"模型收到的转录"钉成
结构断言——任何改变模型所见（工具命名、结果形状、消息流）的改动都会打红 diff，直到同
PR 有意识地刷新。样板：[test_model_surface.py](../../examples/deerflow-extension-example/tests/test_model_surface.py)。

## 配套纪律（与台阶同交）

- **mock 白名单**：唯一常见 mock = 脚本化模型；网络/时钟才可 mock。
  **DeerFlow 增补**：进程全局扩展状态（loaded singleton + runtime diagnostics）是真实
  生产全局态——测试必须经 `extension_process_state()` 隔离，否则诊断断言会被上一个
  测试的泄漏满足。
- **每个 stand-in 写明自己证明不了什么**：`ScriptedModel` 的 docstring 声明它不证明
  真实 provider/流式/重试；你的测试里每个假体照此办理。
- **sync/async 成对**：wrap 钩子实现两侧（LangChain 把一对视为一个能力，单侧静默观察
  不到另一条路径）。
- **车道**：`make test`（离线）/ `make test-blocking-io` / `make test-live`
  （`DEER_FLOW_RUN_LIVE_TESTS=1`，需凭据）；LLM-backed 扩展与 live 成对（见 02）。

## 为什么这么定（解释）

1. **台阶按事故成本排序**。fail-open 让"静默不生效"成为默认失败模式，所以最便宜的
   入口守卫放最前；REAL composition 最贵，放最后且只测组装语义，不重复测行为。
2. **startup-only 改变了台阶三的形状**：没有 dispose 可测，就有装载遏制四不变量可测
   ——移植不是翻译，是按宿主契约重排证据面。
3. **两脸的载体由宿主契约决定**：DSH 用 description 措辞，DeerFlow 用工具 schema/结果
   + descriptor——因为观察性 wrap 契约收走了"改请求"这个面。

## 源码锚点

- [backend/packages/harness/deerflow/testing/](../../backend/packages/harness/deerflow/testing/)——测试套件（`ScriptedModel` / `load_extensions_for_test` / `compose_stack` / `build_test_agent` / `extension_process_state` / `describe_middleware`）
- [examples/deerflow-extension-example/tests/](../../examples/deerflow-extension-example/tests/)——五件套全景（本系列的 tool-todo）
- [backend/packages/harness/deerflow/extensions/AGENTS.md](../../backend/packages/harness/deerflow/extensions/AGENTS.md)——扩展契约权威
- [backend/packages/harness/deerflow/extensions/isolation.py](../../backend/packages/harness/deerflow/extensions/isolation.py)——观察性 wrap 契约的实现处
- [backend/tests/replay_provider.py](../../backend/tests/replay_provider.py) + [backend/scripts/record_gateway.py](../../backend/scripts/record_gateway.py)——台阶五全车道
