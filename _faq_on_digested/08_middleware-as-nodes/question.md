# Q8: Middleware 就是 Node？before_model/after_model 怎么会变成真实的 LangGraph node？

> **问题：** 有人说 DeerFlow 的 middleware 的 hook 方法在编译时变成真正的 LangGraph node——这不是比喻？具体是什么机制？before_model/after_model 和 wrap_model_call/wrap_tool_call 有什么区别？为什么 after_model 是反向执行？
