# ⛔ 已废弃

本文描述的 middleware 模型（SkillsPolicy / MemoryRead / ArtifactInject / PromptCaching / DateContext / ToolAuth / ToolResultValidation）是早期架构草案，**与实际代码不符**。

请使用 **[middleware/ section](../middleware/README.md)** 代替：

- 设计哲学 → [middleware/00-overview.md](../middleware/00-overview.md)
- Hook 点与执行流 → [middleware/01-hooks-and-flow.md](../middleware/01-hooks-and-flow.md)
- 链装配与定位 → [middleware/02-chain-assembly.md](../middleware/02-chain-assembly.md)
- 完整目录（逐源码核实） → [middleware/03-catalog.md](../middleware/03-catalog.md)

**实际 middleware 数量：19 个**（不是本文的 20 个）。实际 hook 点：**6 种**（不是本文的 5 阶段）。
