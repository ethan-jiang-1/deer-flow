# 02 — 扩展测试实战：承诺决定组合

> [01](01-extension-testing-strategy.md) 给出台阶模型与名词表，本篇读真扩展的测试组合，
> 提炼可照抄的模式。基线：本仓库 example 扩展五件套 + host 侧样板。每节末尾给"移植到
> 你的扩展"一句话。

## 现象是什么：组合的形状跟着"扩展承诺"走

七种贡献形态不必记七套测法——按**承诺**归并成四类：

| 承诺 | 覆盖的贡献形态 | 组合形状 |
|---|---|---|
| 有行为 + 有 Config | middleware contributor、service、router | 全家桶（五件套） |
| 纯观察 | task-lifecycle、system-model/assembly/compaction observers | "收到什么 + 失败不炸宿主" |
| 什么时不做（guard 型） | 条件触发的中间件 | 负例矩阵 |
| 依赖模型 / 依赖可选包 | LLM-backed 逻辑、可选依赖扩展 | 记录请求本身 + 成对 live / 缺席不探测 |

写自己的扩展时**先写承诺，再挑组合**，而不是按文件数抄。

## 一、全家桶：example 扩展的五件套

[examples/deerflow-extension-example/tests/](../../examples/deerflow-extension-example/tests/)
是"一个扩展该有的全部测试文件"的最小完备样例（16 个用例全离线、全 keyless）：

| 文件 | 台阶 | 测什么 | 关键手法 |
|---|---|---|---|
| `test_entry_point.py` | ① | 打包层 + 装载层守卫 | 真 loader 读真 entry point：零诊断 + 五类贡献在场 |
| `test_plugin.py` | ② | 贡献类自身行为 | 真 `ExtensionData` store、真 FastAPI app；只 stand-in 掉 registry |
| `test_lifecycle.py` | ③ | 装载遏制四不变量 | skip / fail-open 归因 / fail-closed / install 回滚 / 爆炸隔离 |
| `test_composition.py` | ④ | 组装语义 + **两脸** | 真 loader → `compose_stack` → `build_test_agent`；config `note` 同时改工具 schema/结果（model-visible 脸）与 `policy_parameters`（descriptor 脸） |
| `test_model_surface.py` | ⑤ | 模型收到的转录 | 两调用转录钉成结构断言；改"模型所见"必打红 |

`broken_extension.py` 是刻意的坏扩展 fixture：不兼容 marker / install 爆炸 / 贡献者
爆炸，各打一个遏制分支——**你的仓库也该有一个自己的 broken fixture 模块**。

**移植到你的扩展**：换扩展名、entry point、贡献类名三个标识符，五件套形状不变；
若你的 config 有别的可配置面，把 `note` 的两脸断言换成你的面。

## 二、kit 三段骨架（抄进任何扩展仓库）

```python
from deerflow.testing import (
    ScriptedModel, build_test_agent, compose_stack, describe_middleware,
    extension_process_state, load_extensions_for_test,
    final_message, tool_call_then_final, tool_call_message,
)
from deerflow.extensions.loader import ExtensionSpec

# ① boot：真 loader，spec 形态 = config.yaml plugins: 记录
with extension_process_state():
    loaded, diagnostics = load_extensions_for_test(
        [ExtensionSpec(use="your_extension:install", config={"your_flag": "value"})]
    )
    assert diagnostics == []                      # 或断言 fail-open 的归因诊断

    # ② build：真组装点 + 真 agent 图；唯一 stand-in 是脚本化模型
    model = ScriptedModel(tool_call_then_final("your_tool", {"arg": 1}, final_text="done"))
    agent = build_test_agent(loaded, model)
    state = asyncio.run(agent.ainvoke({"messages": [HumanMessage(content="go")]}))

    # ③ assert：两脸 + state 外部事实，不探 graph 内部
    #   model-visible 脸: model.bound_tools / model.requests
    #   descriptor 脸:    describe_middleware(m).policy_parameters / .extension
    #   行为脸:           state["messages"] 里的 ToolMessage / 最终回复
```

## 三、纯观察贡献：测"收到什么、失败不炸宿主"

observer/lifecycle 贡献没有行为分支可断言，测的是三件事：

1. **收到什么**：事件参数形状（`TaskInfo`/`TaskOutcome`/`SystemModelRequest` 快照）按
   契约到达——host 侧样板
   [backend/tests/test_extension_task_lifecycle.py](../../backend/tests/test_extension_task_lifecycle.py)、
   [backend/tests/test_extension_system_model_calls.py](../../backend/tests/test_extension_system_model_calls.py)；
2. **store 归属**：app store 与 task store 各自拿到什么（middleware/system-call 站点经
   `task_store_from_runtime` 恢复；detached 系统工作拿隔离 store）；
3. **失败不炸宿主**：贡献者抛错 → 归因诊断 + 宿主结果不变（fail-open 的 origin 语义：
   宿主任务的真取消要传播，贡献者自己的 `CancelledError` 要被遏制）。

**移植到你的扩展**：观察者测试先写"宿主结果不变"断言，再写"我收到了什么"——顺序反了
就等于承认宿主可以被我破坏。

## 四、guard 型贡献：负例矩阵

条件触发的中间件，测试对象不是"它做了什么"而是"**它什么时不做**"。每个分支对应一条
会被回归破坏的边界：

- **不触发**负例（先写）：scope 不匹配 → 透传；无 task store → 透传；配置缺席 → 透传；
  未命中条件 → 透传（不碰 `request`/`handler` 以外的任何东西）；
- **触发**分支：每个可观察效果一个用例；
- **竞态两序**：两个到达顺序各一个用例（如宿主 abort 先到 vs 你的 deadline 先到）。

host 侧负例矩阵样板：[backend/tests/test_extension_injection.py](../../backend/tests/test_extension_injection.py)
（malformed placement / 非 middleware 贡献 / 单侧包装——每条负例都带归因断言）。

**移植到你的扩展**：先列"不触发"负例，再列触发分支；注意 `IsolatedMiddleware` 会给
单侧 wrap 钩子补 pass-through 对侧——别把"没实现 sync 侧"当成"guard 在 sync 路径生效"。

## 五、LLM-backed / 可选依赖：记录请求本身 + 成对 live

- **断言模型请求本身**：`ScriptedModel.requests` 记录每个请求的消息序列——断言消息
  形状、signal 语义，而不只是最终文本；超时、取消、坏 JSON 各一个用例。
- **成对形态**：keyless spec（脚本化模型，离线）+ live 测试（`make test-live` /
  `DEER_FLOW_RUN_LIVE_TESTS=1`，需 config.yaml 与凭据）成对交付——离线证明逻辑，在线
  证明"对真模型工作"。live 用例必须**用例内守卫**关键前置（key 存在、config 可用），
  不能只有 skip 分支。host 侧样板：[backend/tests/test_client_live.py](../../backend/tests/test_client_live.py)。
- **可选依赖**：依赖缺席时装载与运行都不得探测/启动那个东西——装载层断言 fail-open
  归因，运行层断言透传（guard 负例）。

## 六、host 级追加：什么该宿主仓库测

扩展仓库测到台阶④的进程内级为止；以下属 host 仓库职责，你的应用 repo 若自带 Gateway
/app 层则照抄 host 样板：

| 面 | 样板 |
|---|---|
| `create_app()` 装载 + app.state / 进程单例 | [test_extension_app_loading.py](../../backend/tests/test_extension_app_loading.py) |
| routers：host-wins、冲突原子回滚、auth 投影 | 同上 + [test_extension_route_principal.py](../../backend/tests/test_extension_route_principal.py) |
| 组装点与放置不变量 | [test_extension_stack_wiring.py](../../backend/tests/test_extension_stack_wiring.py)、[test_extension_placement_guarantees.py](../../backend/tests/test_extension_placement_guarantees.py) |
| 服务启动/停止序与超时 | [test_gateway_extension_service_lifecycle.py](../../backend/tests/test_gateway_extension_service_lifecycle.py) |

## 为什么测试文件的注释密度是有意的

每个 stand-in 都写明自己证明不了什么（`ScriptedModel` 不证明真实 provider；`test_plugin`
的假 registry 只为隔离被测类）。这与 [01](01-extension-testing-strategy.md) 的 mock
白名单同源：**测试注释是"这份证据的适用边界"的声明处**。抄样板时把注释一起抄，别删。
