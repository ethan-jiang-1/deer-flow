# Middleware 条目位：39 的算法与 canonical 目录

> 本页只解释“39 个条目位”的口径，不复制完整逐条表。逐条目录以
> [`_digested/internals/middleware/03-catalog.md`](../../_digested/internals/middleware/03-catalog.md)
> 为准；两阶段组装细节见
> [`_digested/internals/middleware/02-chain-assembly.md`](../../_digested/internals/middleware/02-chain-assembly.md)。

## 39 = 19 + 20

v2.2.0 的 lead 链分两阶段组装：

| 阶段 | 代码位置 | 条目位 |
|---|---|---|
| 共享基础层（lead + subagent） | `_build_runtime_middlewares()`（`tool_error_handling_middleware.py:347`，经 `build_lead_runtime_middlewares()` `:538` 导出） | **1–19** |
| lead-only 层 | `build_middlewares()`（`lead_agent/agent.py:485`）追加 | **20–39** |

合计 **39 个条目位**。v2.1.0 的口径是 37；v2.2.0 重排为 19 + 20。

“条目位”不等于“某次运行的实际实例数”：

- 含两个通用槽位——caller 传入的 `custom_middlewares`、config 声明的 `load_configured_extension_middlewares()`；
- 含条件性条目——如 `CompletedSubagentUsageMiddleware` 只在 token budget 与 usage 都开启时出现，`SubagentDateContextMiddleware` 只在 subagent 链；
- 单链实际条数随 feature、模型 vision、plan mode、扩展配置变化。

## v2.2.0 的增减

- **新增 5 个实例位**：`KnowledgeScopeMiddleware`、`PiiRedactionMiddleware`、`ArtifactResolutionMiddleware`、`ArtifactCaptureMiddleware`、`ModelContentCompatibilityMiddleware`。
- **删除** `SkillToolPolicyMiddleware`（`skill_tool_policy_middleware.py` 整文件；`skills/tool_policy.py` 同样删除，#6935）。`allowed-tools` 降级为兼容元数据，不再收窄工具集。
- **尾部新增** `TerminalResponseMiddleware`、`ModelLengthFinishReasonMiddleware`、`SafetyFinishReasonMiddleware`；`ClarificationMiddleware` 仍是默认链的最后一条。

## 为什么不在 FAQ 里贴全表

FAQ 的规则是“不重复 `_digested` 已写过的内容，指向它而不是复制”。中间件顺序、每条 hook 与条件位都在 canonical 目录里维护；FAQ 只保留“39 怎么算”和读法，避免两份表各自漂移。

读具体条目时按这个顺序：

1. 先看 [`03-catalog.md`](../../_digested/internals/middleware/03-catalog.md) 的编号与两阶段分组；
2. 需要组装代码与顺序不变量时看 [`02-chain-assembly.md`](../../_digested/internals/middleware/02-chain-assembly.md)；
3. 需要“middleware 如何变成 LangGraph node”时回到 [answer.md](answer.md)。
