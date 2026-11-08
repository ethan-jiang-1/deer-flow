# 任务交付路径：从请求到可说明的结果

用“实现一个小功能并交付代码和测试结果”为例，DeerFlow 的理念可以看作一条有边界的执行路径。以下是从源码抽象出的阅读模型，并非每个 run 都会经过每种可选能力。

## 1. 接收任务并形成当前上下文

用户请求进入 thread。模型看到当前任务、有效的项目和用户上下文，以及被发现或载入的技能。不是所有长期资料都会预先展开：skill 可采用渐进发现；对话接近上下文预算时，摘要保留近期历史；启用 task continuity 时，可以为压缩离开的消息提供线程内检索。它们的作用域不同，摘要或笔记不构成动作成功的证明。（`../../_digested/concepts/skills-tools/skill-md-and-tool-assembly.md:1-42`） （`../../_digested/internals/runtime/task-continuity.md:25-37`）

## 2. 选择行动，必要时澄清或委派

Lead agent 以模型和工具循环推进任务。若关键要求缺失，可以通过澄清中断等待用户回答。若工作适合委派，先判断专业能力、上下文隔离或独立并行的净收益是否大于重复探索、协调合成和副作用等成本。共享文件且高度依赖先后测试反馈的实现任务，通常适合直接执行；互不依赖的只读调查更可能适合并行。（`../../backend/packages/harness/deerflow/agents/middlewares/clarification_middleware.py` L75-94 class 声明与行为说明） （`../../backend/packages/harness/deerflow/agents/lead_agent/prompt.py` L600-641 的 `DELEGATION CHECK` 块）

> 🔄 同步 #8（v2.2.0）：两处引证都要修。`clarification_middleware.py:74-94` 现在正好落在类的 docstring 上——**这反而是好事，它讲清了 2.2.0 的澄清机制是"两段式"**：(1) `after_model` 只做一件事，**丢掉同一 AIMessage 里的兄弟工具调用**（否则 `[ask_clarification, bash]` 这种混合批次会既执行业务工具又回环到模型）；(2) 真正的短路在 `wrap_tool_call`（L524）里由 `_handle_clarification` 返回 `Command(goto=END)`（L474-522）。**澄清不再是"设一个 `jump_to`"**，而是工具层的 Command 中断。详见 [Q7 §3.3 与场景 C](../07_graph-nodes/answer.md)。
>
> `prompt.py:425-449` 已漂移，委派判据在 **L600-641**（`Expected benefit = ...` / `Expected cost = ...` / 「Delegate only when the expected benefit is clearly greater than the expected cost.」）。

如果委派，任务范围、预期产物和副作用所有权应具体；客观可检查的交付要求可附上 acceptance criteria。子代理返回是报告而非权威事实。即使文件检查通过，也只说明明确写出的条件成立；论断正确性仍需按其风险核对。（`../../backend/packages/harness/deerflow/subagents/acceptance_checks.py` L1-63 模块 docstring「Deterministic acceptance-criteria checks」；回执怎么读见 `../../backend/packages/harness/deerflow/agents/lead_agent/prompt.py` L631-641）

> 🔄 同步 #8（v2.2.0）：`1-53` 只覆盖到 docstring 前半。2.2.0 的 docstring 里多了一句值得单独记住的「**Vocabulary layering**: the leaf booleans are `checked`/`holds` — never `satisfied`/`verified`/`passed`.」——**强肯定词被运行时硬门独占**，所以子代理验收结果里读到 `holds` 时，它的强度恰好是"这个写明了的执行条件成立"，不是"任务被接受了"。这条直接支撑本文 §5 的分层。

## 3. 在受控执行环境里改动和观察

模型可以调用工具；运行时则负责过滤可用能力、检查调用、处理错误、维持 thread 状态和沙箱资源。工具结果回到模型上下文后，模型可以依据观察结果继续行动。沙箱隔离、工具授权和文件范围不是模型自述出来的属性，而由对应运行时路径及其配置决定。本文不把任意沙箱实现概括成相同强度的安全保证。

值得保持的心智模型是：模型提出动作，运行时执行并返回结果；若工具调用返回错误，执行记录和业务判断仍然是两件事。工具回执能指明某次调用发生，不能独立证明工具输出正确或任务完成。（`../../_digested/orchestration-ladder/01-完成语义与崩溃窗口-接受可见静止处置.md:20-40`）

## 4. 处理长任务而不混淆状态

上下文压缩让模型能继续工作，但压缩是有损的；摘要是对话历史的投影。Goal 可在 Gateway 路径上依据可见对话证据触发有限续跑，并在缺少证据、等待用户或运行失败等情况停止；它不是对任意进程崩溃后的普遍自动恢复承诺。（`../../_digested/internals/runtime/goal-continuation.md:9-41`） Task continuity 可找回部分压缩前记录，但有线程作用域、保留上限和失败状态，也不自动恢复已停止的 run。（`../../_digested/internals/runtime/task-continuity.md:49-82`）

因此，应把“当前对话”“摘要”“任务笔记”“长期 memory”“运行事件/持久 checkpoint”视作不同种类的状态。它们可以互补，不应仅因都能再次出现在 prompt 里就当作同一种事实。

## 5. 验证、呈现并说明缺口

完成实现后，优先记录真实测试命令及其输出，再检查目标文件和关键行为。程序能确定的条件由代码检查；不可确定的条件标为 `UNVERIFIED`，不擅自升格为成功，也不误报成失败。重要结论仍需对照实际文件、测试结果或其他原始证据。

若结果是应由用户查看的文件，需将其保存在当前 thread 的 outputs 范围并通过 `present_files` 呈现。调用结束、工具回执、run 终态、文件存在和业务目标满足各有不同含义；最终说明应交代交付物、采取的验证、尚未证实的部分。（`../../backend/packages/harness/deerflow/tools/builtins/present_file_tool.py` L33-80 `_normalize_presented_filepath`——`outputs_path` 缺失即拒绝、路径必须 resolve 到 outputs 目录下；L83 起是工具本体） （`../../_digested/orchestration-ladder/01-完成语义与崩溃窗口-接受可见静止处置.md:20-40`）

> 🔄 同步 #8（v2.2.0）：`present_file_tool.py` 行号区间仍有效（全文 121 行）。**v2.2.0 给这一步加了一层运行时强制**：README 明确「Gateway runs automatically enforce native delivery for artifacts created or modified under `/mnt/user-data/outputs`: `present_files` must present at least one output produced by the current run, and the terminal `run.delivery` receipt must be durably recorded.」——**"交付"从提示词纪律变成了 Gateway 侧的可核对条件**。同时产物路径会在**同一认证 user + thread 作用域**内解析后再做 outputs 边界校验，堵掉跨用户/跨线程的路径借用。

## 这条路径体现的取舍

- 任务规划和动作选择保持模型驱动，但能力边界、资源限额和关键拦截由系统运行时执行。
- 只在有实际收益时把工作交给另一个 agent，并为结果保留足以核查的上下文与证据句柄。
- 通过摘要、技能发现和线程连续性管理上下文容量，但不把模型生成的记忆或总结伪装成事实证明。
- 把可交付的产物、可复核的执行记录和仍未知的部分同时纳入完成报告。

这是对已有运行时职责的综合解释。不同接入方式、配置和任务可能不启用澄清、goal、subagent、memory 或 task continuity 等能力；不要从这条概念路径推断每次运行都具有同一组组件。

## 🔄 同步 #8（v2.2.0）：这条路径上新增/replace 的东西

除上面各节的逐条更正外，v2.2.0 还在这条路径上改了几处结构，读的时候值得带上：

| 位置 | 2.2.0 变化 | 对这条路径的意义 |
|---|---|---|
| §2 澄清 | `after_model` 只负责丢弃兄弟工具调用，短路改由 `wrap_tool_call` 返回 `Command(goto=END)` | "中断"是**工具层**的事，不是改 `jump_to` |
| §3 工具装配 | `Send` 载荷改为 `Send("tools", [tool_call])`（`factory.py` L1881），不再把 `state` 内联进每个 Send | 并行工具调用不再随 state 大小二次膨胀；这是可观察的性能属性，不是语义变化 |
| §4 状态分层 | `messages` 在 delta 模式下走 `DeltaChannel`；`tool_artifacts` / `tool_artifact_processed` 新增为顶层字段 | "工件清单"和"对话历史"现在都是显式分层的一等公民 |
| §5 交付 | Gateway 侧强制 native delivery + 认证作用域解析 | 交付从"应该这样做"变成"不做就拒" |
| 全程 | `subagent_stop_reason` 从 3 值扩到 4 值（新增 `model_length_capped`） | 委派提前结束的原因里多了"模型长度上限"，不再只能归入传统三类 |

一句话：**这条路径的形状没变，但每一站的"谁负责"更清楚了**——澄清归工具层、交付归 Gateway、工件归 state 字段、委派终止原因归契约枚举。
