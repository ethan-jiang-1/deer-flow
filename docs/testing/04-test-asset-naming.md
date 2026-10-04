# 04 — 测试资产命名法：名字即机制

> 本篇把 DeerFlow 测试资产的既有考究固化成文。核心命题：**测试文件的名字不是标签，是
> 机制**——它决定 pytest 收不收集、归属哪条车道、证据能不能被检索到。DSH 的对应物是
> face 后缀绑 tsc program、`.e2e` 绑车道 config、`(HMR safety)` 可检索标记；DeerFlow
> 的轴心不同但等价。写新测试前对一遍本篇六条规则；违规样例都真实发生过（见各条出处）。

## 规则一：前缀 = 收集语义

| 前缀/形态 | 语义 | 现存例子 |
|---|---|---|
| `test_*.py` | 被 pytest 收集 | 690 个顶层文件 |
| `_.py`（下划线开头） | 共享 helper，**永不收集** | `_agent_e2e_helpers.py`、`_router_auth_helpers.py`、`_opensandbox_helpers.py`、`_conversation_access_helpers.py` |
| `manual_*.py` | 手动脚本，不收集 | `manual_browser_live_check.py` |
| 裸 infra 模块 | 按**名字**被生产配置引用 | `replay_provider.py`（回放 config 的 `use:` 指名引用）、`seed_runs_router.py` |
| `fixtures/`、`support/`、`monocle/` | 自包含资产区（fixtures 可有自己的 README/requirements） | `fixtures/replay/`、`support/`（Monocle 行为套件） |

**推论（反例）**：一个**被收集的**测试模块永远不能成为另一个测试模块的 fixture 库——
`from test_X import ...` 会让被导入模块的收集副作用在导入者里重放。历史上存在 4 处
（conversation×2、threads_router←projects_router、blocking_io acquire←provider），已于
2026-01 收敛进 `_.py` helper。共享fixture 的家：模块级假体/脚手架进同目录 `_helpers`，
数据资产进 `fixtures/`，成套行为环境进 `support/`。

## 规则二：marker = 注册契约

marker 必须注册在 [backend/pyproject.toml](../../backend/pyproject.toml) 的
`[tool.pytest.ini_options].markers` 里并带说明。现有四个，每个都是
"**全局默认行为 + marker 退/进**"的成对设计：

| marker | 默认行为 | marker 的作用 |
|---|---|---|
| `no_auto_user` | conftest 给所有测试设用户 contextvar | 单测显式退出，验证"无用户上下文"路径 |
| `allow_blocking_io` | blocking_io 车道拦一切阻塞 I/O | 单测显式豁免 |
| `live` | 离线车道（`make test`）排除 | `make test-live` 显式进入 |
| `integration` | —— | 外部服务缺席自动跳 |

自定义 marker 先注册再用；不注册的话规则不会报错，但契约就散落在 tribal knowledge 里。

## 规则三：门是两层的——车道成员 + 用例内守卫

"会打真 API / 真外部服务"的测试，**必须同时**具备：

1. **车道成员**：`pytest.mark.live`（决定离线车道收不收集你）；
2. **用例内守卫**：skipif/env 检查（决定 live 车道里你跳不跳、要什么凭据）。

两层缺一不可：只有第二层 = 游离在车道系统外（在有 key 的开发机上 `make test` 会真打
API）；只有第一层 = live 车道里没有凭据就报错而不是跳过。

**命名联动**：文件名带 `_live` 就必须携带 `live` 标记。历史漂移已收敛（2026-01）：
`test_create_deerflow_agent_live.py`、`test_client_e2e.py`、
`test_deferred_tool_promotion_real_llm.py`（原 `requires_llm` skipif / `ONEAPI_E2E`
自造门）、`test_delegation_ledger_live.py`（原 `RUN_DEERFLOW_LEDGER_LIVE` 自造门）——
自造门降级为用例内守卫，车道归属统一归 `live` marker。

**混合文件的形态**（[test_client_e2e.py](../../backend/tests/test_client_e2e.py)）：
一部分用例真打 LLM、一部分（文件管理）处处可跑——按**用例**标 `live`，不整文件标。
组合装饰器模式：

```python
_LLM_SKIP = pytest.mark.skipif(..., reason="...")


def requires_llm(item):
    """Live-lane membership plus the key guard, composed into one decorator."""
    return pytest.mark.live(_LLM_SKIP(item))
```

## 规则四：不变量钉子——"Pinned by" 双向检索

AGENTS.md（根、backend、21 个模块级）里每条关键不变量以
`Pinned by tests/test_*.py`（细到函数名与 node id）收尾。这构成双向检索：

- 读到契约条款 → grep 测试名找到证据；
- 改测试名 → grep 旧名找到所有引用它的契约条文，**同步改名**。

**文件名 = 不变量名**：钉子文件以不变量命名（`test_harness_boundary.py`、
`test_ci_uv_version_pin.py`、`test_compose_default_bind_host.py`），而不是以被测类命名
——被测类会重构，不变量不会。

## 规则五：车道三轴，各管一件事

| 轴 | 机制 | 决定什么 |
|---|---|---|
| 执行机制 | **目录**（`tests/blocking_io/` + 自带 conftest） | 换一种跑法（Blockbuster 严格门包住 setup/call/teardown） |
| 条件执行 | **marker**（`live` / `integration`） | 同一种跑法下，收不收集、缺外部件跳不跳 |
| 速度 | **`.test_durations` 基线** | shard 怎么均衡；速度不编码进名字，编码进基线文件（`make test-shard-durations` 刷新） |

## 规则六：扩展仓库的阶梯词根（配合 [01](01-extension-testing-strategy.md) 五台阶）

下游 DeerFlow 应用/扩展仓库的测试文件名按台阶词根走，使证据级别可检索：

| 台阶 | 词根 | 样板 |
|---|---|---|
| ① 入口守卫 | `test_entry_point.py` | [example](../../examples/deerflow-extension-example/tests/test_entry_point.py) |
| ② 行为 spec | `test_plugin.py` / `test_<贡献类>.py` | [example](../../examples/deerflow-extension-example/tests/test_plugin.py) |
| ③ 装载遏制 | `test_lifecycle.py` + `broken_extension.py`（坏 fixture 模块） | [example](../../examples/deerflow-extension-example/tests/test_lifecycle.py) |
| ④ REAL composition | `test_composition.py` | [example](../../examples/deerflow-extension-example/tests/test_composition.py) |
| ⑤ 组装转录 | `test_model_surface.py`（keyless）；录制场景进 `fixtures/replay/` | [example](../../examples/deerflow-extension-example/tests/test_model_surface.py) |

## 与 DSH 的对照

| DSH 考究 | DeerFlow 对应 | 差异本质 |
|---|---|---|
| `.host.spec` / `.client.spec` 后缀 → tsc face program | 规则五的目录/marker 双轴 | Python 无双类型检查面；车道归属由 pytest 机制承担 |
| `(HMR safety)` ×72 可检索标记 | 规则四的 `Pinned by` ×21（到函数级） | DSH 标在用例名里；DeerFlow 标在契约条文里，双向锚定 |
| `.e2e` 后缀 → 独立 vitest config | 规则三的 `_live` + `live` marker | 同构：后缀/名字声明车道，config/Makefile 执行车道 |
| `harness.ts` + 禁 import e2e | 规则一的 `_helpers` + 收集禁令 | 同一条纪律 |
| built-bin-smoke 16 文件门清单 | `.test_durations` 基线 | 门清单显式 vs 基线文件隐式 |
