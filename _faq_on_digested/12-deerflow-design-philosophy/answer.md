# DeerFlow 的设计理念：让智能体完成可交付的任务

## 核心结论

DeerFlow 不是只负责回答问题的研究代理，而是围绕任务执行组织起来的 super agent harness：模型决定下一步做什么，运行时为它提供工具、上下文和执行环境，并在交接、压缩、权限、资源与交付边界上施加约束。README 将方向概括为从 deep research 扩展到通用任务执行，并列出文件系统、记忆、技能、沙箱执行、规划与子代理等能力。（`../../README.md:939-949`）

从当前实现归纳，DeerFlow 的设计取向可以概括为：**让模型保留处理开放问题的灵活性，同时把关键的执行边界、状态边界和可验证条件交给明确的运行时机制；最终交付按证据说明，而不由一次模型自述代替。**这是一组从代码和一手文档抽取出的设计原则，不是项目声明过的官方口号，也不意味着所有任务都能由程序确定性地验收。

## 五个相互支撑的原则

1. **面向行动和产物，而不止于生成回答。** Agent loop 在模型回答中包含工具调用时执行工具并继续，在没有工具调用时结束；沙箱文件、工具、子代理和可呈现产物让任务能够越过纯文本问答。（`../../_digest/overview/01-system-overview.md:19-45`） 对文件交付，`present_files` 将可见产物限定在当前线程的 outputs 目录，而不是把任意路径都当作已交付。（`../../backend/packages/harness/deerflow/tools/builtins/present_file_tool.py:33-80`）

2. **模型负责适应，运行时负责边界。** 模型可以选择工具和后续步骤；工具装配、中间件、能力授权、子代理并发/总量、循环检测、澄清中断、沙箱和文件边界则由运行时层控制。用户输入和远程内容也被视作不可信数据来处理。关键不是把每个任务写成预设流程，而是令开放式决策处于可配置、可拦截、可恢复的执行框架内。（`../../backend/packages/harness/deerflow/agents/lead_agent/agent.py:1190-1245`） [中间件链说明](../../backend/packages/harness/deerflow/agents/middlewares/AGENTS.md)

3. **直接路径优先，委派须有净收益。** 子代理不是复杂任务的默认答案。提示词要求先比较专业能力、上下文隔离或独立并行所带来的收益，与启动、重复发现、协调合成、状态冲突及副作用成本；并行任务须互相独立，随后每一批都要重新评估。（`../../backend/packages/harness/deerflow/agents/lead_agent/prompt.py:425-449`） （`../../backend/packages/harness/deerflow/tools/builtins/task_tool.py:703-733`）

4. **上下文、知识和状态按用途分层。** Skill 支持先发现、按需载入，避免把全部工作资料塞进每次请求；会话摘要和任务连续性处理线程内长期工作，memory 面向跨轮次持久信息，而不是把任务临时状态都变成用户画像。（`../../_digest/concepts/skills-tools/skill-md-and-tool-assembly.md:54-115`） （`../../_digest/internals/runtime/task-continuity.md:9-37`） Durable context 将框架权威规则与摘要、委派结果、技能引用等历史数据分开注入；后者明确是数据而非指令。（`../../backend/packages/harness/deerflow/agents/middlewares/durable_context_middleware.py:34-43`）

5. **完成状态和证据强度分开。** 执行结束不等于验收通过；工具回执证明调用发生，不证明论断正确；`UNVERIFIED` 表示证据缺失，不表示条件失败。可程序判定的文件存在、非空、写回或测试执行条件可以由检查器核对；不可判定的标准必须保持未验证，重要主张还需核查原始证据。（`../../backend/packages/harness/deerflow/subagents/acceptance_checks.py:1-53`） （`../../backend/packages/harness/deerflow/tools/builtins/task_tool.py:715-733`）

## 它不等于什么

- **不是每种协作都等同于同一个计划图。** 项目的核心 agent loop 是模型调用—工具执行循环；goal 续跑、普通委派和持久 batch 等能力有各自的触发条件、状态和完成语义。（`../../_digest/overview/01-system-overview.md:19-63`） （`../../_digest/internals/runtime/goal-continuation.md:9-41`） （`../../_digest/orchestration-ladder/01-完成语义与崩溃窗口-接受可见静止处置.md:20-40`）
- **不是记忆越多越好。** Skill、对话摘要、线程内 task continuity、跨会话 memory 解决不同问题，有不同作用域、保留方式和可信度；任务笔记或摘要不能作为“操作已成功”的证据。（`../../_digest/internals/runtime/task-continuity.md:25-37`）
- **不是成功状态天然代表业务完成。** “已接受”“已执行”“下一轮模型可见”“资源已释放”“业务目标满足”是不同阶段；不同原语的持久化和恢复语义也不同。（`../../_digest/orchestration-ladder/01-完成语义与崩溃窗口-接受可见静止处置.md:11-40`）
- **不是 Harness 与 Gateway 混为一层。** Harness 包含可嵌入的 agent 运行能力；应用层负责 Gateway、HTTP/身份和 IM 等接入。依赖方向是 app 使用 harness，反向导入由测试禁止。（`../../_digest/overview/02-harness-app-boundary.md:11-61`）

## 实践中的设计判断

面对一个新能力，可以依次问：它属于模型应作出的任务决策，还是必须由运行时强制执行的规则？它的状态是当前请求、线程连续性、跨会话记忆，还是应用层持久任务？它需要完整内容还是发现后按需加载？完成条件里哪些可由程序检查，哪些只能报告为未验证？如果需要委派，是否存在明确的专业、隔离或并行净收益，且输入输出和副作用所有权是否清晰？

这些问题不是新增的规范清单，而是把现有代码中的职责边界转成可复用的推理方法。如何把一次任务沿这些边界走到交付，可看[任务交付路径](task-delivery-walkthrough.md)。

## 相关研究与源码

- [_digest/overview/07-design-philosophy-evidence.md](../../_digest/overview/07-design-philosophy-evidence.md)：本题的一手证据索引与解释边界。
- [_digest/overview/01-system-overview.md](../../_digest/overview/01-system-overview.md)：Agent loop 与服务分层。
- [_digest/overview/02-harness-app-boundary.md](../../_digest/overview/02-harness-app-boundary.md)：Harness / App 依赖边界。
- [_digest/concepts/skills-tools/skill-md-and-tool-assembly.md](../../_digest/concepts/skills-tools/skill-md-and-tool-assembly.md)：技能发现和载入。
- [_digest/internals/runtime/task-continuity.md](../../_digest/internals/runtime/task-continuity.md)：线程内连续性及其限制。
- [_digest/orchestration-ladder/01-完成语义与崩溃窗口-接受可见静止处置.md](../../_digest/orchestration-ladder/01-完成语义与崩溃窗口-接受可见静止处置.md)：多阶段完成语义。
- （`../../backend/packages/harness/deerflow/agents/lead_agent/prompt.py:425-523`）、（`../../backend/packages/harness/deerflow/subagents/acceptance_checks.py:1-53`）、（`../../backend/packages/harness/deerflow/agents/middlewares/durable_context_middleware.py:34-43`）：委派、验收和上下文信任边界。
