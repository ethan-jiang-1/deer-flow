# 03 — 扩展 PR 最小证据集（机器可对表）

> 本页**自足**：没读过本专题其他页也能照做。一个 DeerFlow 扩展 = 一个 Python 包，经
> `deerflow.extensions` group 的 entry point 暴露 `@extension` 标注的
> `install(registry, config)`，经 `config.yaml` 顶层 `plugins:` 启动时装载。术语表在
> [01](01-extension-testing-strategy.md)，组合样例在 [02](02-extension-testing-playbook.md)。
>
> **用法**：写完扩展后对着下表逐行问"样板在哪、我的对应文件在哪、验收命令过不过"——
> 答不上来的行就是缺口。智能体建仓时同样按此表自检。

## 计划时（写代码之前）

1. **先对表七贡献形态**（[扩展契约](../../backend/packages/harness/deerflow/extensions/AGENTS.md)）：
   能力是否已有现货；你的扩展贡献哪几类。
2. **点名测试面**：这个扩展会动 model-visible 面吗（middleware-owned tools、结果变换）？
   会贡献 routers/services 吗？会发布可配置面吗？——每个"会"对应下表一个台阶，在 PR
   描述里写清。
3. **契约红线先读**：贡献的中间件是**观察性 wrap**（改不了模型请求，见
   [01 台阶四](01-extension-testing-strategy.md)）；routers 挂在 host 路由之后且必须
   会话认证；`plugins:` 是 startup-only。设计阶段对着红线定形态，比测试阶段返工便宜。

## 写测试时（五个台阶逐一对表）

| 台阶 | 最小要求 | 样板（抄这里） | 我的文件 | 验收命令 |
|---|---|---|---|---|
| ① 入口点守卫 | 打包层恰一个 entry point + marker；真 loader 零诊断 + 贡献在场 | [test_entry_point.py](../../examples/deerflow-extension-example/tests/test_entry_point.py) | _____ | `pytest tests/test_entry_point.py -q` |
| ② 行为 spec | 真依赖、只 stand-in 脚本化模型；断言 state/请求记录/store，不断言自报 | [test_plugin.py](../../examples/deerflow-extension-example/tests/test_plugin.py) | _____ | `pytest tests/test_plugin.py -q` |
| ③ 装载遏制 | skip / fail-open 归因 / fail-closed / install 回滚 / 爆炸隔离 五用例 | [test_lifecycle.py](../../examples/deerflow-extension-example/tests/test_lifecycle.py) + [broken_extension.py](../../examples/deerflow-extension-example/tests/broken_extension.py) | _____ | `pytest tests/test_lifecycle.py -q` |
| ④ REAL composition | 真 `ExtensionSpec` → `compose_stack` → `build_test_agent`；config **两脸**（model-visible + descriptor） | [test_composition.py](../../examples/deerflow-extension-example/tests/test_composition.py) | _____ | `pytest tests/test_composition.py -q` |
| ⑤ 组装转录 | model-visible 改动 → 同 PR：keyless 转录钉 + （宿主仓库）录制场景 | [test_model_surface.py](../../examples/deerflow-extension-example/tests/test_model_surface.py)；全车道 [replay_provider.py](../../backend/tests/replay_provider.py) | _____ | `pytest tests/test_model_surface.py -q` |

按承诺增补（见 [02](02-extension-testing-playbook.md)）：纯观察 → "宿主结果不变"断言；
guard 型 → 负例矩阵先于触发分支；LLM-backed → 与 `make test-live` 成对；可选依赖 →
缺席不探测。

## 提 PR 前（同 PR 交付清单）

- **转录证据**：改动模型所见（工具命名/schema/结果形状/消息流）→ 同 PR 更新 keyless
  转录钉；宿主仓库的录制场景按 record/replay 流程同 PR 加改，**每个 diff 人工过目**。
- **README 已知限制**：扩展 README 带具体的"已知限制"节——脚本化模型证明不了什么、
  观察性 wrap 约束下做不了什么，要写下来。
- **config 面**：新增私有 `config` 键必须在台阶④证明两脸跟随；`plugins:` 记录变更
  提醒 operator 重启 Gateway（startup-only）。
- **进程状态**：所有装载/组装用例经 `extension_process_state()` 隔离——泄漏会污染
  同进程后续测试。
- **sync/async 成对**：wrap 钩子两侧都实现，或注释声明为何单侧。
- **破坏性面**：`extensions_config.json` schema、`contracts/` 下的 JSON 契约、
  extension-api 语义变了 → 同 PR 说明迁移路径（host 侧 pin `deerflow-extension-api==0.2.x`
  精确版本，扩展声明 range——别在 PR 里偷偷改 range 语义）。

## 你的 PR 在 CI 里会经过什么（DeerFlow 宿主车道）

| 车道 | 对扩展仓库的含义 |
|---|---|
| `make test` | 全量离线套件（含你的五件套）；必须全绿 |
| `make test-blocking-io` | 严格阻塞 I/O 门（`tests/blocking_io/`）——asyncio 里别开同步文件/网络 |
| `make test-shard` | 时长感知分片；新增重测试要留意基线 |
| `make test-live` | opt-in（`DEER_FLOW_RUN_LIVE_TESTS=1`），LLM-backed 成对形态的在线半 |
| `make lint` / `make format` | ruff；后端 CI 强制 `ruff format --check` |

## 反例清单（每条都有出处，答不上出处就是没读懂）

1. **hand-built registry 充当组装证据**——`FakeRegistry` 手搭只够隔离被测类（台阶②）；
   组装证据必须真 loader + 真组装点（台阶④）。出处：[01 台阶四](01-extension-testing-strategy.md)。
2. **对 agent 自报做关键词探测**——断言 `ScriptedModel.requests` / state / 持久化行 /
   HTTP 响应这些外部事实，而不是模型说它做了什么。出处：[01 台阶二](01-extension-testing-strategy.md)。
3. **把 tunable 写成常量再钉死**——`DEFAULT_*` 不构成可配置性；用真 loader + 两脸跟随。
   出处：[01 台阶四](01-extension-testing-strategy.md)。
4. **指望贡献中间件改写模型请求**——`IsolatedMiddleware` 是观察性 wrap，request 被
   钉死；model-visible 面是 middleware-owned tools。出处：[isolation.py](../../backend/packages/harness/deerflow/extensions/isolation.py) `_invoke_sync` 注释。
5. **单侧 wrap 钩子当双侧用**——LangChain 把 sync/async 对视为一个能力，缺的一侧被
   补成 pass-through，那条路径静默不生效。出处：[isolation.py](../../backend/packages/harness/deerflow/extensions/isolation.py) `_WRAP_HOOK_PAIRS`。
6. **进程全局状态泄漏**——不 reset loaded singleton / runtime diagnostics，诊断断言被
   上个测试的泄漏满足。出处：[01 配套纪律](01-extension-testing-strategy.md)。
7. **只有 skip 分支、没有用例内守卫**——live/可选前置在用例内再断言一次。
8. **为凑绿改断言 / 弱化归因 / 加 sleep**——掩盖修法一律拒绝；修的是产品或测试的
   假设，不是断言。
9. **跨测试文件 import / 车道漂移**——共享 fixture 进 `_.py` helper，永不
   `from test_X import`；文件名带 `_live` 就必须携带 `live` 标记。全部命名规则见
   [04 命名法](04-test-asset-naming.md)。

## 命令速查

```sh
# 扩展仓库（或 example 本身）：五件套全绿
cd examples/deerflow-extension-example && uv run --extra dev pytest tests -q
#   （首次同步后可直接用 .venv/bin/python -m pytest tests -q）

# DeerFlow 宿主侧
cd backend && make test                  # 全量离线
cd backend && make test-blocking-io      # 阻塞 I/O 门
cd backend && PYTHONPATH=. uv run pytest tests/test_extension_injection.py -q   # 单文件
cd backend && make test-live             # 成对形态的在线半（需凭据）
cd backend && make lint && make format   # ruff
```

## 建仓引导（新 DeerFlow 应用仓库第一天）

1. `cp -r examples/deerflow-extension-example/tests <你的扩展>/tests`，换三个标识符：
   扩展名、entry point、贡献类名；`broken_extension.py` 改成你自己的坏 fixture；
2. 依赖加 `deerflow-harness`（kit 随 harness 发布）；工具链照抄 example 的
   `pyproject.toml`（ruff + pytest 车道）；
3. 跑一遍命令速查；对着"写测试时"的表逐行填"我的文件"列——填不满的行就是第一周的
   工作清单；
4. 把本文件"提 PR 前"一节复制进你的仓库 PR 模板。
