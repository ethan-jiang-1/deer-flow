# 指南预算与文档测试：指令也是受治理资产

## 这页解决什么问题

给 agent 的指南文档有两个特有病症：**过长挤占上下文并稀释指令密度**，以及**过期比没有更糟**（agent 会信）。DeerFlow 主仓给两个病各上了一个机器门禁。与[卷二·架构契约页](../sdlc-reference/06-architecture-docs-contracts.md)互补：那里列门禁清单，这里讲这套治理对应用仓自己的指南意味着什么。

## 机制（运行时事实 + 机器门禁，对 v2.1.0 核验）

**尺寸预算分级**。[check_agent_guidance.py](https://github.com/bytedance/deer-flow/blob/v2.1.0/scripts/check_agent_guidance.py) 的常量按目录深度分四档（KiB）：

| 层级 | 软线 / 硬线 |
|---|---|
| 根 `AGENTS.md` | 16 / 20 |
| 模块层（`backend/`、`frontend/`、`scripts/`） | 28 / 32 |
| 子系统层 | 40 / 48 |
| 完整祖先链累计 | 80 / 96 |

检查在 [lint-check.yml](https://github.com/bytedance/deer-flow/blob/v2.1.0/.github/workflows/lint-check.yml) 的 `agent-guidance` job 执行：超硬线是 error；且只在本次 diff 触及的文件上生效——门禁咬的是"正在变长的指南"，不是存量。

**文档示例进测试**。[test_middleware_documentation.py](https://github.com/bytedance/deer-flow/blob/v2.1.0/backend/tests/test_middleware_documentation.py) 把文档里的自定义 middleware 示例直接 `exec()`，断言 API 未过期、链顺序与 guard 清单一致。指南中的代码不是插图，是被测资产。

**语义边界（诚实读法）**：预算钉**尺寸**，示例测试钉**可执行性**——两者都不证明指南的**内容正确**（编号、条目归属这类漂移仍在门禁之外）。这套治理把最坏的两类失效（膨胀、示例过期）挡住了，没有也不声称挡住全部。

## 应用仓能借鉴什么

**可移用（顺序建议）**：① 先有指南，再谈治理——没有 AGENTS.md 的仓第一步是写一份根指南；② 指南开始变长时引入预算——阈值不必照抄（DeerFlow 的分档是它自己的规模长出来的），但**软/硬两档 + 只咬 diff 触及的文件 + 祖先链累计**这三个设计决定值得保留；③ 指南里出现代码示例的第一天就让它进测试。**应用仓建议**：extension 包仓的 README 里如果有 `install()` 示例，这就是你版的第一优先级——示例过期直接导致别人装不上你的包。**代价**：预算治理需要维护检查脚本本身；只有一份指南的仓用不上，别提前上。

## 证据入口

- [check_agent_guidance.py](https://github.com/bytedance/deer-flow/blob/v2.1.0/scripts/check_agent_guidance.py)（分档常量，tag 与宿主分支一致）与 [lint-check.yml](https://github.com/bytedance/deer-flow/blob/v2.1.0/.github/workflows/lint-check.yml)（agent-guidance job）
- [test_middleware_documentation.py](https://github.com/bytedance/deer-flow/blob/v2.1.0/backend/tests/test_middleware_documentation.py)
