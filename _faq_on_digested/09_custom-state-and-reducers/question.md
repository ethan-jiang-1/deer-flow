# Q9: 怎么扩展 ThreadState？什么时候用 NotRequired，什么时候用 Annotated + 自定义 reducer？

> **问题：** DeerFlow 的 ThreadState 已经有 12 个字段了，但如果我想加自己的字段——比如跟踪审查计数、已审批 PR 列表——我该怎么做？什么时候用简单的 `NotRequired[T]`，什么时候需要写自定义 reducer？Reducer 怎么写？
