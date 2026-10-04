# 测试策略：基于 DeerFlow 的扩展与智能体应用

> 移植自 DeepSeek Harness 的插件测试策略（`_digested/test-strategy/08·09·10`），按 DeerFlow
> 的扩展契约重写。受众：**基于 `deerflow-harness` 构建智能体应用的仓库作者**——你写的每个
> 扩展是一个 Python 包，经一个 PEP 621 entry point 暴露 `install(registry, config)`，由
> `config.yaml` 顶层 `plugins:` 在启动时装载（startup-only，改动必须重启 Gateway）。
>
> 扩展契约的权威描述：[backend/packages/harness/deerflow/extensions/AGENTS.md](../../backend/packages/harness/deerflow/extensions/AGENTS.md)。

## 为什么需要这套策略

DSH 的核心经验：**阶梯按事故成本排序，样板可抄是策略落地的唯一方式**。最便宜的断言
（一行守卫）挡住过最贵的事故；而一个团队里 43 个测试文件含同一断言，不是因为纪律好，
是因为有一个样板文件可以被抄。

DeerFlow 侧的现状正是缺这一层：host 自己的扩展测试很厚（`backend/tests/` 下 27 个
extension 测试文件），但面向扩展/应用作者的**模板与可复用测试套件**此前是空的。本系列
补上它，配套的可复用套件是 harness 包里的 **`deerflow.testing`**。

## 四篇导读

| 篇 | 回答的问题 | 对应 DSH |
|---|---|---|
| [01 — 策略：五级证据阶梯](01-extension-testing-strategy.md) | 政策对一个新扩展的要求：台阶怎么摆、为什么这么排 | 08 |
| [02 — 实战：承诺决定组合](02-extension-testing-playbook.md) | 五类真实组合的解剖：你的扩展承诺什么，就长什么样 | 09 |
| [03 — 检查单：PR 最小证据集](03-extension-pr-checklist.md) | 计划时、写测试时、提 PR 前逐条对表（含建仓引导） | 10 |
| [04 — 命名法：名字即机制](04-test-asset-naming.md) | 测试资产命名六条规则：收集语义、车道归属、证据检索 | 命名考究 |

## 五级证据阶梯（一图流）

| 台阶 | DeerFlow 形态 | 样板（抄这里） |
|---|---|---|
| ① 入口点契约守卫 | 真 loader 读真 entry point：零诊断 + 贡献在场 | [examples/.../test_entry_point.py](../../examples/deerflow-extension-example/tests/test_entry_point.py) |
| ② 行为 spec | 真依赖，只 stand-in 脚本化模型；从真入口断言 | [examples/.../test_plugin.py](../../examples/deerflow-extension-example/tests/test_plugin.py) |
| ③ 装载遏制 | fail-open / fail-closed / skip / 爆炸隔离 四不变量 | [examples/.../test_lifecycle.py](../../examples/deerflow-extension-example/tests/test_lifecycle.py) |
| ④ REAL composition | 真 loader + 真组装点 + 真 agent 图；同一 config 的**两脸** | [examples/.../test_composition.py](../../examples/deerflow-extension-example/tests/test_composition.py) |
| ⑤ 组装转录 | keyless 转录固定；全车道 = record/replay | [examples/.../test_model_surface.py](../../examples/deerflow-extension-example/tests/test_model_surface.py)；[backend/tests/replay_provider.py](../../backend/tests/replay_provider.py) |

## 最小起步（建仓三步）

1. 把 [examples/deerflow-extension-example/tests/](../../examples/deerflow-extension-example/tests/)
   复制进你的扩展仓库，换掉三个标识符：扩展名、entry point、贡献类名；
2. 依赖加 `deerflow-harness`（测试套件随 harness 发布：`from deerflow.testing import ...`）；
3. 对 [03 检查单](03-extension-pr-checklist.md) 的五台阶表逐行问"我的对应文件在哪"——
   答不上来的行就是缺口。
