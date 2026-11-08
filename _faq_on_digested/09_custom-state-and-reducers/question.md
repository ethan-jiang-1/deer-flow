# Q9: 怎么扩展 ThreadState？什么时候用 NotRequired，什么时候用 Annotated + 自定义 reducer？

> **问题：** DeerFlow 的 ThreadState 已经有 17 个自有字段了（加上从 LangChain `AgentState` 继承的 `messages` / `jump_to` / `structured_response`），但如果我想加自己的字段——比如跟踪审查计数、已审批 PR 列表——我该怎么做？什么时候用简单的 `NotRequired[T]`，什么时候需要写自定义 reducer？Reducer 怎么写？
>
> **追问（v2.2.0 语境）：** 为什么同一个 `ThreadState` 在 full 和 delta 两种 checkpoint 模式下不是同一个 schema？我加了字段，为什么在 delta 模式下中间件读不到？

