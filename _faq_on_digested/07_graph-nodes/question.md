# Q7: Agent 图里有两个固定 Node——model 和 tools。它们怎么工作？我能怎么影响它们？

> **问题：** DeerFlow 的 LangGraph agent 图有两个固定 node：`model`（调 LLM）和 `tools`（执行工具）。这两个 node 不能删，但说能通过 `wrap_model_call`/`wrap_tool_call` 深度影响——具体怎么做到的？我应该用哪种 hook 来影响它们？
>
> **追问（v2.2.0 语境）：** 听说 `wrap_model_call` 里不能返回 `Command(goto=...)` 了，那想让中间件改变「下一步去哪」该用什么？另外 `ask_clarification` 到底是在 `after_model` 短路、还是在工具层短路？
